"""Paper-search requests: dashboard creates them, Claude Code fulfils them, the dashboard shows the result."""

import pytest
from fastapi.testclient import TestClient

from backtester.cli import main
from backtester.research import Library
from backtester.research.requests import RequestError, Requests, instruction
from backtester.web.app import create_app


@pytest.fixture
def project(tmp_path):
    return tmp_path


@pytest.fixture
def client(project):
    return TestClient(create_app(project))


def test_create_validates_and_saves(tmp_path):
    reqs = Requests(tmp_path)
    with pytest.raises(RequestError):
        reqs.create("  ")
    with pytest.raises(RequestError):
        reqs.create("x" * 301)
    r = reqs.create("  momentum   in ETFs ", "prefer\nafter 2010")
    assert r["query"] == "momentum in ETFs" and r["notes"] == "prefer after 2010" and r["status"] == "pending"
    assert r["id"] in r["instruction"] and "momentum in ETFs" in r["instruction"] and "--request" in r["instruction"]
    assert [x["id"] for x in reqs.pending()] == [r["id"]]


def test_ids_cannot_escape_the_folder(tmp_path):
    reqs = Requests(tmp_path)
    for bad in ("../../etc/passwd", "x", ""):
        with pytest.raises(KeyError):
            reqs.get(bad)
        with pytest.raises(KeyError):
            reqs.delete(bad)


def test_cli_fulfils_a_request(project, capsys):
    rid = Requests(project / "research" / "library").create("tactical asset allocation")["id"]
    lib = str(project / "research" / "library")
    main(["paper", "requests", "--library", lib])
    assert rid in capsys.readouterr().out
    main(["paper", "add", "--library", lib, "--request", rid, "--title", "A Quantitative Approach", "--year", "2007",
          "--finding", "timing cuts drawdown"])
    capsys.readouterr()
    main(["paper", "request-done", rid, "--library", lib, "--summary", "found one"])
    done = Requests(project / "research" / "library").get(rid)
    assert done["status"] == "done" and done["summary"] == "found one" and len(done["papers"]) == 1
    assert Library(project / "research" / "library").get(done["papers"][0])["title"] == "A Quantitative Approach"
    capsys.readouterr()
    main(["paper", "requests", "--library", lib])
    assert rid not in capsys.readouterr().out          # only pending ones are listed


def test_cli_rejects_unknown_request(project):
    with pytest.raises(SystemExit):
        main(["paper", "add", "--library", str(project / "lib"), "--request", "20260101-000000-abcd", "--title", "T"])


def test_dashboard_flow(client, project):
    page = client.get("/research").text
    assert "Consensus" in page and "OpenAlex" in page            # both sources offered
    assert client.post("/api/requests", json={"query": "x"}).status_code == 400
    made = client.post("/api/requests", json={"query": "pairs trading in equities"}).json()
    rid = made["id"]
    assert rid in made["instruction"]
    html = client.get("/research/requests").text
    assert "pairs trading in equities" in html and "Waiting for Claude" in html and "Copy instruction" in html
    lib = Library(project / "research" / "library")
    pid = lib.add("Pairs Trading", year=2006, authors="Gatev")
    Requests(project / "research" / "library").attach_paper(rid, pid)
    Requests(project / "research" / "library").complete(rid, "One classic paper")
    html = client.get("/research/requests").text
    assert "Done" in html and "One classic paper" in html and "Pairs Trading" in html
    assert client.post(f"/api/requests/{rid}/delete").json() == {"ok": True}
    assert client.post(f"/api/requests/{rid}/delete").status_code == 404
    assert client.post("/api/requests/..%2Fx/delete").status_code == 404
    assert "pairs trading" not in client.get("/research/requests").text


def test_instruction_names_the_request():
    s = instruction({"id": "20260101-000000-abcd", "query": "q", "notes": ""})
    assert "20260101-000000-abcd" in s and "Extra guidance" not in s
