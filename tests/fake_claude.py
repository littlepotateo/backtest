"""A stand-in for the `claude` program: reads the prompt from stdin and prints stream-json like `claude -p --output-format stream-json`.
FAKE_CLAUDE picks the behaviour; FAKE_CLAUDE_LOG gets one line with the arguments of every call."""
import json
import os
import sys
import time

args = sys.argv[1:]
prompt = sys.stdin.read()
mode = os.environ.get("FAKE_CLAUDE", "ok")
if os.environ.get("FAKE_CLAUDE_LOG"):
    with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"args": args, "prompt_head": prompt[:80]}) + "\n")


def emit(**ev):
    print(json.dumps(ev), flush=True)


def reply(text, **extra):
    emit(type="result", subtype="success", is_error=False, result=text, duration_ms=1200, num_turns=2, **extra)
    sys.exit(0)


emit(type="system", subtype="init", tools=["Read"], mcp_servers=[])
if mode == "crash":
    sys.stderr.write("boom: something broke")
    sys.exit(3)
if mode == "slow":
    time.sleep(30)
if mode == "auth":
    emit(type="result", subtype="success", is_error=True, result="Invalid API key · Please run /login", duration_ms=5)
    sys.exit(1)
if mode == "bad_json":
    reply("Sure! Here are some thoughts but no JSON.")

SEARCH = {"summary": "Found two. Replicate the first one first.", "papers": [
    {"title": "Trend Following: A Test ﬁlter", "authors": "A. B. et al.", "year": 2020, "venue": "J. Fake", "url": "https://consensus.app/papers/details/x/",
     "consensus_id": "w:1", "finding": "Trend rules cut drawdowns.", "claims": ["Drawdowns were lower."]},
    {"title": "Second paper", "authors": "C. D.", "year": "2019", "venue": "", "url": "javascript:alert(1)", "consensus_id": "w:2", "finding": "f", "claims": []},
    {"title": "", "year": 2000}, "not a dict"]}
ANALYSIS = {"summary": "The paper tests a 10-month moving average on five asset classes.", "strategy_family": "trend following",
            "rules": ["Hold the asset when price is above its 10-month average", "Otherwise hold cash"], "universe": "five asset classes",
            "data_frequency": "monthly", "period_tested": "1973-2012", "claimed_results": ["Timing cut drawdowns to under 10%"],
            "assumptions_needed": ["Which cash rate to use"], "missing_information": ["Transaction costs"], "replication_difficulty": "easy",
            "can_backtest_here": "yes: SPY, EFA, IEF, DBC, VNQ from Yahoo", "suggested_strategy_description": "Hold each ETF above its 10-month average."}

if "TOPIC:" in prompt:
    if mode == "no_consensus":
        reply('{"error": "no_consensus"}')
    allowed = args[args.index("--allowedTools") + 1:]
    if mode == "denied" and "mcp__claude_ai_Consensus__search" not in allowed:
        emit(type="result", subtype="success", is_error=False, result="I could not use the search tool.", duration_ms=5,
             permission_denials=[{"tool_name": "mcp__claude_ai_Consensus__search", "tool_input": {}}])
        sys.exit(0)
    emit(type="assistant", message={"content": [{"type": "tool_use", "name": "mcp__claude_ai_Consensus__search", "input": {"query": "trend following"}}]})
    reply("Here you go:\n```json\n" + json.dumps(SEARCH) + "\n```")
if "Analyse this paper" in prompt:
    emit(type="assistant", message={"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}]})
    reply(json.dumps(ANALYSIS))
reply("{}")
