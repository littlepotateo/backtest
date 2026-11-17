"""Tests for the dashboard: pages, safety of ids and re-run requests, option surfaces."""

import json
import subprocess

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backtester import Strategy
from backtester.analysis.findings import to_jsonable, validate
from backtester.analysis.metrics import compute_metrics
from backtester.data.cache import Cache
from backtester.engine import CostModel, RunConfig, Runner
from backtester.explain import explain
from backtester.web import data as D
from backtester.web.app import create_app
from backtester.web.jobs import BadRequest, Jobs


class Trend(Strategy):
    universe = ["SPY"]
    params = {"n": 20}
    param_grid = {"n": [5, 10, 20, 40]}

    def on_bar(self, ctx):
        c = ctx.closes("SPY", self.params["n"])
        if len(c) == self.params["n"]:
            ctx.order_target_percent("SPY", 1.0 if c[-1] > c.mean() else 0.0)


class ShortCall(Strategy):
    universe = ["SPY"]
    options_on = ["SPY"]

    def on_bar(self, ctx):
        if ctx.position("SPY") < 100:
            ctx.order_target("SPY", 100)
        elif not ctx.options.positions("SPY"):
            ctx.options.order(ctx.options.select("SPY", "C", 30, delta=0.3), -1)


def save_run(root, name, cls, bars_df, validated=False, benchmark="SPY"):
    cache = Cache(root / "data" / "cache")
    cache.save("SPY", "1d", bars_df, source="test")
    start = bars_df.index[40].strftime("%Y-%m-%d")           # after the realised-volatility warm-up
    r = Runner(cls, RunConfig(costs=CostModel.zero(), start=start), cache=cache)
    res = r.run()
    res.meta["benchmark"] = benchmark
    res.meta["strategy_file"] = "strategies/examples/sma_cross.py"
    d = res.save(root / "runs" / name)
    metrics = compute_metrics(res, 0.0, bars_df["close"])
    (d / "metrics.json").write_text(json.dumps(metrics))
    if validated:
        v = to_jsonable(validate(r, None, benchmark_close=bars_df["close"], n_paths=100))
        (d / "validation.json").write_text(json.dumps(v))
        (d / "explanation.md").write_text("STALE TEXT FROM AN OLD VERSION")
    return d, res


@pytest.fixture
def project(tmp_path, bars):
    rng = np.random.default_rng(0)
    df = bars(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, 420))), start="2022-01-03 14:30")
    save_run(tmp_path, "20260101-000001-Trend", Trend, df, validated=True)
    save_run(tmp_path, "20260101-000002-ShortCall", ShortCall, df)
    (tmp_path / "strategies").mkdir()
    (tmp_path / "strategies" / "ok.py").write_text("# strategy")
    return tmp_path


@pytest.fixture
def client(project):
    return TestClient(create_app(project))


def test_pages_render_with_real_content(client):
    home = client.get("/")
    assert home.status_code == 200 and "Latest results" in home.text and "Trend" in home.text      # recent runs on the home page
    listing = client.get("/runs")
    assert listing.status_code == 200 and "20260101-00000" in listing.text and "Trend" in listing.text
    assert "not validated" in listing.text                           # the unvalidated run says so
    page = client.get("/run/20260101-000001-Trend")
    assert page.status_code == 200
    for text in ("Total return", "Monthly returns", "Does it hold up?", 'id="chart-data"', "Re-run with changes"):
        assert text in page.text, text
    data = json.loads(page.text.split('id="chart-data" type="application/json">')[1].split("</script>")[0])
    assert len(data["equity"]["x"]) == len(data["equity"]["y"]) > 100 and data["benchmark"] is not None
    assert min(data["drawdown"]["y"]) <= 0 and len(data["walkforward"]) >= 1
    assert client.get("/research").status_code == 200 and client.get("/compare").status_code == 200
    assert client.get("/static/plotly.min.js").status_code == 200 and client.get("/static/app.js").status_code == 200


def test_explanation_is_regenerated_not_read_stale(client, project):
    text = client.get("/run/20260101-000001-Trend").text
    assert "STALE TEXT FROM AN OLD VERSION" not in text
    v = json.loads((project / "runs" / "20260101-000001-Trend" / "validation.json").read_text())
    assert "what the backtest says" in text
    # the chip and the explanation agree on the evidence level
    level = D.trust_level(v["flags"])[0]
    assert f"Evidence: {level}" in text and f"How much to trust it: {level}" in text


def test_bad_run_ids_are_refused(client, project):
    assert client.get("/run/does-not-exist").status_code == 404
    assert client.get("/run/..%2F..%2Fetc").status_code == 404
    assert client.get("/run/_jobs").status_code == 404
    for bad in ("..", "../x", "a/b", "", ".hidden", "x y"):
        with pytest.raises(D.NotFound):
            D.safe_run_dir(project / "runs", bad)
    assert client.get("/compare?a=nope&b=nope").status_code == 404


def test_compare_two_runs(client):
    r = client.get("/compare?a=20260101-000001-Trend&b=20260101-000002-ShortCall")
    assert r.status_code == 200 and "Growth of 1" in r.text and "Total return" in r.text
    data = json.loads(r.text.split('id="chart-data" type="application/json">')[1].split("</script>")[0])
    assert data["a"]["y"][0] == pytest.approx(1.0, abs=0.05) and data["b"]["name"].startswith("ShortCall") and data["b"]["short"] == "ShortCall"


def test_monthly_table_adds_up(project):
    r = D.load_run(project / "runs", "20260101-000001-Trend", project / "data" / "cache")
    total = np.prod([1 + row["total"] for row in r["monthly"]["rows"]]) - 1
    assert total == pytest.approx(r["equity"].iloc[-1] / r["initial"] - 1)
    for row in r["monthly"]["rows"]:
        months = [m for m in row["months"] if m is not None]
        assert np.prod([1 + m for m in months]) - 1 == pytest.approx(row["total"], abs=1e-9)


def test_rerun_requests_are_validated(project):
    jobs = Jobs(project, project / "runs", project / "data" / "cache")
    ok = {"strategy": "strategies/ok.py", "start": "2020-01-01", "cash": "50000", "params": "fast=10\nslow=40",
          "tests": ["walkforward", "montecarlo"], "paths": "500"}
    cmd = jobs.command(ok)
    assert cmd[:3] == [cmd[0], "-m", "backtester.cli"] and "validate" in cmd and "--param" in cmd
    assert cmd[cmd.index("--tests") + 1] == "walkforward,montecarlo" and cmd[cmd.index("--cash") + 1] == "50000.0"
    for bad in ({"strategy": "../etc/passwd"}, {"strategy": "strategies/missing.py"}, {"strategy": "pyproject.toml"},
                {**ok, "start": "yesterday"}, {**ok, "cash": "abc"}, {**ok, "cash": "-5"},
                {**ok, "params": "x; rm -rf /"}, {**ok, "params": "a=1\nbad line"}, {**ok, "tests": ["nonsense"]},
                {**ok, "benchmark": "SPY; ls"}, {**ok, "paths": "99999999"}):
        with pytest.raises(BadRequest):
            jobs.command(bad)
    (project / "outside.py").write_text("x")
    with pytest.raises(BadRequest):
        jobs.command({"strategy": "outside.py"})                     # a .py file, but not under strategies/


def test_rerun_starts_a_job_and_reports_status(client, project, monkeypatch):
    started = {}

    class FakeProc:
        pid = 1

        def __init__(self, cmd, cwd, stdout, stderr, env=None):
            started["cmd"] = cmd
            started["env"] = env
            stdout.write("Saved to /x/runs/20260102-000000-Trend (explanation.md written)\n")
            stdout.flush()

        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", FakeProc)
    r = client.post("/rerun", data={"strategy": "strategies/ok.py", "start": "2021-01-01", "tests": ["checks"]},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/jobs/")
    assert "validate" in started["cmd"]
    assert started["env"]["PYTHONUTF8"] == "1"          # the child reads and writes files as UTF-8 on Windows too
    page = client.get(r.headers["location"])
    assert page.status_code == 200 and "done" in page.text and "20260102-000000-Trend" in page.text
    assert client.post("/rerun", data={"strategy": "../x.py"}).status_code == 400
    assert client.get("/jobs/zzzz").status_code == 404
    assert client.get("/rerun/20260101-000001-Trend").status_code == 200


def test_cross_site_posts_are_refused(client):
    r = client.post("/rerun", data={"strategy": "strategies/ok.py"}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    same = client.post("/rerun", data={"strategy": "../x"}, headers={"origin": "http://testserver"})
    assert same.status_code == 400                                   # reached the handler


def test_option_surfaces(client, project):
    page = client.get("/run/20260101-000002-ShortCall")
    assert "Option surfaces (3D)" in page.text and 'id="surface"' in page.text
    dates = [o.split('"')[0] for o in page.text.split('<select id="surf-date"')[1].split("</select>")[0].split('value="')[1:]]
    assert dates
    d = dates[0]
    pos = client.get(f"/api/run/20260101-000002-ShortCall/surface?kind=position&what=gamma&date={d}")
    assert pos.status_code == 200
    s = pos.json()
    z = np.array(s["z"])
    assert z.shape == (len(s["y"]), len(s["x"])) and (z <= 1e-9).all() and z.min() < 0   # a short call is short gamma
    assert s["scale"] == "diverging" and s["legs"] and "C" in s["legs"][0]
    value = client.get(f"/api/run/20260101-000002-ShortCall/surface?kind=position&what=value&date={d}").json()
    assert value["z_label"] == "position value" and value["scale"] == "sequential"
    contract = client.get(f"/api/run/20260101-000002-ShortCall/surface?kind=contract&what=gamma&right=C&date={d}").json()
    cz = np.array(contract["z"])
    assert (cz >= 0).all() and contract["z_label"].startswith("dollar gamma") and contract["scale"] == "sequential"
    assert client.get(f"/api/run/20260101-000002-ShortCall/surface?kind=position&what=gamma&date=2000-01-01").status_code == 400
    assert client.get(f"/api/run/20260101-000002-ShortCall/surface?kind=bogus&date={d}").status_code == 400
    assert client.get(f"/api/run/20260101-000002-ShortCall/surface?kind=contract&what=rho&date={d}").status_code == 400
    assert client.get(f"/api/run/20260101-000001-Trend/surface?kind=position&date={d}").status_code == 400   # no options


def test_research_page_shows_papers_and_links_runs(project):
    from backtester.research import Library
    lib = Library(project / "research" / "library")
    pid = lib.add("A Test Paper", authors="Someone", year=2020, claims=["it works"])
    lib.link_run(pid, project / "runs" / "20260101-000001-Trend")
    page = TestClient(create_app(project)).get("/research").text
    assert "A Test Paper" in page and "abstract only" in page and "from the abstract only" in page and "/run/20260101-000001-Trend" in page
    assert "<script>" not in page                                    # raw HTML in notes is escaped
