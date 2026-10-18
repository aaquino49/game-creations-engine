"""Office phase 3 acceptance tests: one test per spec acceptance criterion (1-10)."""
import datetime as dt
import json
import sys
import unittest
import urllib.parse
from http import client as http_client
from pathlib import Path
from unittest import mock

from tests.office_fixture import TOKEN, OfficeServer, call, make_project, write_config
from tests import office_fixture as fx

PY = sys.executable
FMT = "%Y-%m-%d %H:%M:%S"


def ts(base, **kw):
    return (base + dt.timedelta(**kw)).strftime(FMT)


def rich_project(root: Path, base: dt.datetime):
    """Overwrite the fixture with a realistic events.log covering every format,
    a hand-computable board, notes docs, play.bat and a fake exe."""
    agents = {
        "coder_1": {"cmd": [PY, "-c", "print('OK')"], "model": "m-one", "account": "openai"},
        "coder_2": {"cmd": [PY, "-c", "print('OK')"], "model": "m-two", "account": "openai"},
        "coder_3": {"cmd": [PY, "-c", "print('OK')"], "model": "m-three", "account": "other"},
    }
    write_config(root, agents, topic="test-topic")
    cfg_p = root / "orchestrator" / "config.json"
    cfg = json.loads(cfg_p.read_text(encoding="utf-8"))
    cfg["paid_agents"] = ["coder_1"]
    cfg["coders"] = ["coder_1"]
    cfg_p.write_text(json.dumps(cfg), encoding="utf-8")

    board = {"project": "Fixture Game", "next_id": 30, "tasks": [
        {"id": "T-20", "title": "Alpha", "status": "done", "milestone": "M1",
         "priority": 2, "type": "code", "owner": "coder", "depends_on": [], "attempts": 1,
         "description": "alpha", "acceptance": ["a"],
         "history": [{"attempt": 1, "at": ts(base, hours=-5), "worker": "coder_1",
                      "work": "done", "checks": True, "qa": "pass",
                      "checks_after_qa": True, "review": "approve"}]},
        {"id": "T-21", "title": "Beta", "status": "done", "milestone": "M1",
         "priority": 3, "type": "code", "owner": "coder", "depends_on": ["T-20"], "attempts": 2,
         "description": "beta", "acceptance": ["b"],
         "history": [{"attempt": 1, "at": ts(base, hours=-4), "worker": "coder_2",
                      "work": "done", "checks": True, "qa": "fail",
                      "checks_after_qa": False, "review": "revise"},
                     {"attempt": 2, "at": ts(base, hours=-3), "worker": "coder_2",
                      "work": "done", "checks": True, "qa": "pass",
                      "checks_after_qa": True, "review": "approve"}]},
        {"id": "T-22", "title": "Gamma", "status": "blocked", "milestone": "M2",
         "priority": 1, "type": "code", "owner": "coder", "depends_on": [], "attempts": 1,
         "description": "gamma", "acceptance": ["g"], "blocked_reason": "stuck",
         "history": [{"attempt": 1, "at": ts(base, hours=-2), "worker": "coder_1",
                      "work": "done", "checks": True, "qa": "fail",
                      "checks_after_qa": False, "review": "revise"}]},
        {"id": "T-23", "title": "Delta", "status": "ready", "milestone": "M2",
         "priority": 3, "type": "code", "owner": "coder", "depends_on": [], "attempts": 0,
         "description": "delta", "acceptance": ["d"], "history": []},
    ]}
    (root / "project" / "board.json").write_text(json.dumps(board), encoding="utf-8")

    until_hhmm = (base + dt.timedelta(hours=2)).strftime("%H:%M")
    L = []
    L.append(f"{ts(base, hours=-6)}  NEW TASK T-20 (coder, M1) from plan: Alpha")
    L.append(f"{ts(base, hours=-6)}  NEW TASK T-21 (coder, M1) from plan: Beta")
    L.append(f"{ts(base, hours=-6)}  NEW TASK T-22 (coder, M2) from plan: Gamma")
    L.append(f"{ts(base, hours=-5, minutes=-10)}  START T-20 [lane A] [coder/code] Alpha")
    L.append(f"{ts(base, hours=-5)}  T-20 a1 WORK done: alpha work")
    L.append(f"{ts(base, hours=-5)}  T-20 a1 CHECKS pass (12 passed)")
    L.append(f"{ts(base, hours=-5)}  T-20 a1 QA pass: looks good")
    L.append(f"{ts(base, hours=-5)}  T-20 a1 REVIEW approve: nice")
    L.append(f"{ts(base, hours=-5)}  DONE T-20 (attempt 1, lane A)")
    L.append(f"{ts(base, hours=-5)}  LANE A merged T-20 into main")
    L.append(f"{ts(base, hours=-4, minutes=-10)}  START T-21 [lane A] [coder/code] Beta")
    L.append(f"{ts(base, hours=-4)}  T-21 a1 WORK done: beta try one")
    L.append(f"{ts(base, hours=-4)}  T-21 a1 CHECKS pass (10 passed)")
    L.append(f"{ts(base, hours=-4)}  T-21 a1 QA fail: broken")
    L.append(f"{ts(base, hours=-4)}  T-21 a1 REVIEW revise: fix it")
    L.append(f"{ts(base, hours=-3, minutes=-5)}  T-21 a2 WORK done: beta try two")
    L.append(f"{ts(base, hours=-3)}  T-21 a2 CHECKS pass (10 passed)")
    L.append(f"{ts(base, hours=-3)}  T-21 a2 QA pass: good now")
    L.append(f"{ts(base, hours=-3)}  T-21 a2 REVIEW approve: ship it")
    L.append(f"{ts(base, hours=-3)}  DONE T-21 (attempt 2, lane A)")
    L.append(f"{ts(base, hours=-2, minutes=-30)}  START T-22 [lane B] [coder/code] Gamma")
    L.append(f"{ts(base, hours=-2)}  T-22 a1 WORK produced no result")
    L.append(f"{ts(base, hours=-2)}  T-22 a1 CHECKS FAIL (boom)")
    L.append(f"{ts(base, hours=-2)}  T-22 a1 QA fail: nope")
    L.append(f"{ts(base, hours=-2)}  T-22 a1 REVIEW revise: rethink")
    L.append(f"{ts(base, hours=-2)}  BLOCKED T-22: stuck on gamma")
    L.append(f"{ts(base, hours=-2)}  RECOVER T-22: was interrupted; back to ready")
    L.append(f"{ts(base, hours=-1, minutes=-50)}  START T-23 [lane B] [coder/code] Delta")
    L.append(f"{ts(base, hours=-1, minutes=-40)}  PLAN start (demo reason)")
    L.append(f"{ts(base, hours=-1, minutes=-30)}  PLAN done: planned demo board")
    L.append(f"{ts(base, hours=-1, minutes=-20)}  MILESTONE M1 COMPLETE")
    L.append(f"{ts(base, hours=-1, minutes=-15)}  FALLBACK coder_1 is limited until {until_hhmm}; coder_3 handles work steps")
    L.append(f"{ts(base, hours=-1, minutes=-10)}  USAGE LIMIT coder_2 (openai): limited until ~{until_hhmm} (test)")
    L.append(f"{ts(base, hours=-1, minutes=-5)}  QUOTA RESTORED openai: usage is back (test)")
    L.append(f"{ts(base, hours=-1)}  PREEMPTIVE HANDOFF openai at 97% of its 5h window (threshold 97%)")
    L.append(f"{ts(base, minutes=-55)}  PROVIDER DOWN coder_3 (rc=1 after 61s, server error): test down")
    L.append(f"{ts(base, minutes=-50)}  MODEL GONE coder_3: test gone")
    L.append(f"{ts(base, minutes=-45)}  QUICK FAIL coder_3 (rc=1 in 4s): test quick")
    L.append(f"{ts(base, minutes=-40)}  AGENT FAIL coder_3 work: rc=1 timed_out=False (test)")
    L.append(f"{ts(base, minutes=-30)}  SUPERVISOR-AI claude called: lane B quiet (log project/runs/T-22/a1/work.coder_1.log)")
    L.append(f"{ts(base, minutes=-26)}  SUPERVISOR-AI claude done: nudged lane B")
    L.append(f"{ts(base, minutes=-20)}  SUPERVISOR-AI codex called: stale lock (log project/runs/T-22/a1/work.coder_1.log)")
    L.append(f"{ts(base, minutes=-10)}  SUPERVISOR relaunched start.bat (orchestrator was not running)")
    L.append(f"{ts(base, minutes=-9)}  ORCHESTRATOR ERROR (1 in a row): test error")
    L.append(f"{ts(base, minutes=-8)}  LANE B ERROR: test lane error")
    L.append(f"{ts(base, minutes=-7)}  PLANNER ERROR: test planner error")
    L.append(f"{ts(base, minutes=-6)}  WATCHDOG killed Godot running 5 min: test")
    L.append("this line is malformed and has no timestamp")
    L.append("2026-13-99 99:99:99  nonsense timestamp line")
    (root / "project" / "events.log").write_text("\n".join(L) + "\n", encoding="utf-8")

    (root / "project" / "decisions.md").write_text("# Decisions\n\n| Date | Decision | Why |\n", encoding="utf-8")
    (root / "project" / "assumptions.md").write_text("# Assumptions\n\ntest\n", encoding="utf-8")
    (root / "project" / "PM_NOTES.md").write_text("# PM Notes\n\ntest notes\n", encoding="utf-8")
    ms = root / "project" / "milestones"
    ms.mkdir(exist_ok=True)
    (ms / "M1.md").write_text("# M1: First\n\ndone\n", encoding="utf-8")
    (root / "play.bat").write_text("@echo off\r\nif exist builds\\mygame.exe (start \"\" builds\\mygame.exe)\r\n",
                                   encoding="utf-8")
    bdir = root / "builds"
    bdir.mkdir(exist_ok=True)
    (bdir / "mygame.exe").write_bytes(b"MZ" + b"0" * 100)
    return base


class OfficeCase(unittest.TestCase):
    def start(self, manage=False, demo=False, rich=True):
        import time as _time
        self.tmp = make_project()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = dt.datetime.now().replace(microsecond=0) - dt.timedelta(hours=1)
        if rich:
            rich_project(self.root, self.base)
        self.srv = OfficeServer(self.root, manage=manage, demo=demo)
        # keep the opencode background thread (cwd=ROOT) from pinning the
        # throwaway dir on Windows: mark its cache fresh so no refresh spawns
        fx.server._opencode.update({"t": _time.time(), "days1": None,
                                    "days7": None, "error": "test stub"})
        self.addCleanup(self.srv.close)
        self.addCleanup(setattr, fx.server, "DEMO", False)
        self.addCleanup(setattr, fx.server, "MANAGE", False)

    def get(self, path, token=TOKEN, host=None):
        return call(self.srv, "GET", path, token=token, host=host)

    def post(self, path, body=None, raw=None, token=TOKEN, host=None):
        return call(self.srv, "POST", path, body=body, raw=raw, token=token, host=host)

    def get_raw(self, path):
        conn = http_client.HTTPConnection("127.0.0.1", self.srv.port, timeout=10)
        try:
            conn.request("GET", path, headers={"X-Office-Token": TOKEN})
            r = conn.getresponse()
            return r.status, r.getheader("Content-Type", ""), r.read()
        finally:
            conn.close()


class Scorecards(OfficeCase):
    """1. attempts, first-pass approvals and rates; a fallback counts for the substitute."""

    def test_scorecards(self):
        self.start(manage=False)
        code, d = self.get("/api/stats?hours=168")
        self.assertEqual(code, 200)
        by = {s["agent"]: s for s in d["scorecards"]}
        c1 = by["coder_1"]
        self.assertEqual(c1["attempts"], 2)
        self.assertEqual(c1["first_pass"], 1)
        self.assertAlmostEqual(c1["approval_rate"], 0.5)
        self.assertAlmostEqual(c1["checks_rate"], 1.0)
        self.assertAlmostEqual(c1["qa_rate"], 0.5)
        self.assertEqual(c1["blocked"], 1)
        c2 = by["coder_2"]
        self.assertEqual(c2["attempts"], 2)
        self.assertEqual(c2["first_pass"], 0)
        self.assertAlmostEqual(c2["approval_rate"], 0.5)
        self.assertEqual(by["coder_3"]["substitutions"], 1)
        # sorted by first-pass then approval rate: coder_1 first, gets the trophy in UI
        self.assertEqual(d["scorecards"][0]["agent"], "coder_1")
        self.assertIsNotNone(c1["median_work_min"])


class ThroughputEta(OfficeCase):
    """2. buckets + ETA: rate 0 gives —, fewer than 5 DONEs gives low confidence."""

    def test_buckets_and_eta(self):
        self.start(manage=False)
        code, d = self.get("/api/stats?hours=24")
        self.assertEqual(code, 200)
        self.assertEqual(d["throughput"]["bucket_hours"], 1)
        self.assertEqual(len(d["throughput"]["buckets"]), 24)
        self.assertEqual(sum(b["count"] for b in d["throughput"]["buckets"]), 2)
        code, d7 = self.get("/api/stats?hours=168")
        self.assertEqual(d7["throughput"]["bucket_hours"], 6)
        self.assertEqual(len(d7["throughput"]["buckets"]), 28)
        eta = d["eta"]
        self.assertIn("low", eta["board"])
        self.assertTrue(eta["board"]["low"])
        self.assertNotEqual(eta["board"]["label"], "—")
        # rate 0: fresh project with no DONEs
        self.tmp2 = make_project()
        self.addCleanup(self.tmp2.cleanup)
        root2 = Path(self.tmp2.name)
        import stats as st
        nodone = st.build_stats(root2, dt.datetime.now().replace(microsecond=0), 24)
        self.assertEqual(nodone["eta"]["board"]["label"], "—")


class Gantt(OfficeCase):
    """3. one bar per START; running task ends at now; naps end at QUOTA RESTORED."""

    def test_gantt(self):
        self.start(manage=False)
        code, d = self.get("/api/stats?hours=168")
        self.assertEqual(code, 200)
        bars = [b for ln in d["gantt"]["lanes"] for b in ln["bars"]]
        starts = [t for t, _ in
                  (l.split("  ", 1) for l in (self.root / "project" / "events.log").read_text(encoding="utf-8").splitlines() if "START T-" in l)]
        self.assertEqual(len(bars), 4)  # T-20, T-21, T-22, T-23
        running = [b for b in bars if b["outcome"] == "running"]
        self.assertEqual(len(running), 1)
        self.assertEqual(running[0]["task"], "T-23")
        self.assertEqual(running[0]["end"], d["gantt"]["now"])
        naps = [b for row in d["gantt"]["naps"] for b in row["bars"]]
        self.assertTrue(naps)
        # the openai nap ends at QUOTA RESTORED, i.e. before the "until" time
        import stats as st
        until = st._parse_until(f"limited until ~{(self.base + dt.timedelta(hours=2)).strftime('%H:%M')}",
                                self.base - dt.timedelta(hours=1))
        for row in d["gantt"]["naps"]:
            for b in row["bars"]:
                end = dt.datetime.strptime(b["end"], FMT)
                self.assertLessEqual(end, until)


class Routing(OfficeCase):
    """4. FALLBACK from→to counts."""

    def test_routing(self):
        self.start(manage=False)
        code, d = self.get("/api/stats?hours=168")
        self.assertEqual(code, 200)
        flows = {(f["from"], f["to"]): f["count"] for f in d["routing"]["flows"]}
        self.assertEqual(flows.get(("coder_1", "coder_3")), 1)
        counts = d["routing"]["counts"]["coder_2"]
        self.assertGreaterEqual(counts["usage_limit"], 1)


class OpencodeParser(unittest.TestCase):
    """5. parse_opencode_stats on the spec sample; garbage gives empty."""

    SAMPLE = (
        "│Total Cost                                        $0.16 │\n"
        "│ meta/muse-spark-1.3-contributor                        │\n"
        "│  Messages                                          282 │\n"
        "│  Input Tokens                                   674.3K │\n"
        "│  Output Tokens                                  193.4K │\n"
        "│  Cost                                          $0.1622 │\n"
    )

    def test_sample(self):
        import stats as st
        d = st.parse_opencode_stats(self.SAMPLE)
        self.assertAlmostEqual(d["total"], 0.16)
        m = d["models"]["meta/muse-spark-1.3-contributor"]
        self.assertAlmostEqual(m["cost"], 0.1622)
        self.assertEqual(m["messages"], 282)
        self.assertEqual(m["output_tokens"], 193400)
        self.assertEqual(m["input_tokens"], 674300)

    def test_garbage(self):
        import stats as st
        self.assertEqual(st.parse_opencode_stats("hello ???"), {"total": None, "models": {}})
        self.assertEqual(st.parse_opencode_stats(""), {"total": None, "models": {}})


class Incidents(OfficeCase):
    """6. called+done pair with duration; called with no outcome is in progress."""

    def test_incidents(self):
        self.start(manage=False)
        code, d = self.get("/api/stats?hours=168")
        self.assertEqual(code, 200)
        items = d["incidents"]["items"]
        claude = [i for i in items if i.get("agent") == "claude" and i["outcome"] == "done"]
        self.assertTrue(claude)
        self.assertEqual(claude[0]["duration_min"], 4.0)
        codex = [i for i in items if i.get("agent") == "codex"]
        self.assertTrue(codex)
        self.assertEqual(codex[0]["outcome"], "in progress")
        self.assertIn("supervisor_ai", d["incidents"]["counts"])


class MalformedAndHours(OfficeCase):
    """7. malformed lines never raise; hours=5 is 400."""

    def test_malformed(self):
        self.start(manage=False)
        code, d = self.get("/api/stats?hours=24")
        self.assertEqual(code, 200)
        self.assertTrue(d["scorecards"])
        code, _ = self.get("/api/stats?hours=5")
        self.assertEqual(code, 400)


class NotesFiles(OfficeCase):
    """8. /api/file allows decisions.md + milestone, still refuses board + config."""

    def test_notes_files(self):
        self.start(manage=False)
        code, d = self.get("/api/notes")
        self.assertEqual(code, 200)
        self.assertTrue(len(d["plans"]) >= 1)
        self.assertTrue(any(x["path"] == "project/decisions.md" for x in d["docs"]))
        for ok in ("project/decisions.md", "project/milestones/M1.md",
                   "project/assumptions.md", "project/PM_NOTES.md"):
            code, ctype, body = self.get_raw("/api/file?path=" + urllib.parse.quote(ok, safe=""))
            self.assertEqual(code, 200, ok)
            self.assertTrue(body, ok)
        for bad in ("project/board.json", "orchestrator/config.json"):
            code, _, _ = self.get_raw("/api/file?path=" + urllib.parse.quote(bad, safe=""))
            self.assertEqual(code, 403, bad)


class BuildPlay(OfficeCase):
    """9. /api/build finds the exe in play.bat; play needs the token and Popens play.bat."""

    def test_build(self):
        self.start(manage=True)
        code, d = self.get("/api/build")
        self.assertEqual(code, 200)
        self.assertEqual(d["exe"], "builds/mygame.exe")
        self.assertTrue(d["exists"])

    def test_play(self):
        self.start(manage=True)
        code, _ = self.post("/api/control", {"action": "play"}, token=None)
        self.assertEqual(code, 403)
        with mock.patch("subprocess.Popen") as popen:
            code, d = self.post("/api/control", {"action": "play"})
            self.assertEqual(code, 200)
            cmds = [c.args[0] for c in popen.call_args_list]
            self.assertIn(["cmd", "/c", "start", "", "play.bat"], cmds)
            for c in popen.call_args_list:
                self.assertEqual(c.kwargs.get("cwd"), self.root)


class DemoMode(OfficeCase):
    """10. every Phase 2/3 GET in demo is 200 with data; tails grow."""

    PATHS = ["/api/state", "/api/board", "/api/task/T-1",
             "/api/file?path=project/decisions.md",
             "/api/tail?path=project/runs/T-1/a1/work.coder_1.log&offset=0",
             "/api/commands", "/api/requests", "/api/probe",
             "/api/stats?hours=24", "/api/notes", "/api/build"]

    def test_demo_gets(self):
        self.start(manage=False, demo=True, rich=False)
        for p in self.PATHS:
            if p.startswith("/api/file"):
                code, ctype, body = self.get_raw(p)
                self.assertEqual(code, 200, p)
                self.assertTrue(body, p)
                continue
            code, body = self.get(p)
            self.assertEqual(code, 200, p)
            self.assertTrue(json.dumps(body).strip() not in ("", "{}", "[]", "null"), p)
        code, shots = self.get("/api/screenshots")
        self.assertEqual(code, 200)  # timeline keeps its empty state in demo

    def test_demo_tail_grows(self):
        self.start(manage=False, demo=True, rich=False)
        code, d1 = self.get("/api/tail?path=demo.log&offset=0")
        self.assertEqual(code, 200)
        code, d2 = self.get(f"/api/tail?path=demo.log&offset={d1['offset']}")
        self.assertEqual(code, 200)
        self.assertTrue(d2["text"])
        self.assertNotEqual(d2["text"], d1["text"])


if __name__ == "__main__":
    unittest.main()
