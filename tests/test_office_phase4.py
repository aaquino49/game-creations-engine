"""Office phase 4 acceptance tests: Settings (roster, fallbacks, lanes), bench,
approval gate, spend cap, plus polish Q5/Q8 determinism checks."""
import datetime as dt
import importlib.util
import json
import os
import shutil
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.office_fixture import TOKEN, OfficeServer, call, make_project
from tests import office_fixture as fx

PY = sys.executable
FMT = "%Y-%m-%d %H:%M:%S"


def poll_until(fn, timeout=10.0, step=0.1):
    """Poll fn() until truthy, with a deadline (no fixed sleeps)."""
    end = time.time() + timeout
    while True:
        got = fn()
        if got:
            return got
        if time.time() > end:
            raise AssertionError("poll deadline exceeded")
        time.sleep(step)


def rich_agents():
    return {
        "coder_1": {"cmd": ["opencode", "run", "--auto", "-m", "model-one", "{prompt}"],
                    "kind": "opencode", "model": "model-one",
                    "account": "acct-1", "label": "Coder 1"},
        "coder_2": {"cmd": ["opencode", "run", "--auto", "-m", "model-two", "{prompt}"],
                    "kind": "opencode", "model": "model-two",
                    "account": "acct-2", "label": "Coder 2"},
        "quarterback": {"cmd": ["claude", "-p", "{prompt}", "--model", "q-model",
                                "--dangerously-skip-permissions"],
                        "kind": "claude", "model": "q-model",
                        "account": "anthropic", "label": "Quarterback"},
        "qa_lead": {"cmd": ["codex", "exec", "-m", "qa-model", "--dangerously-bypass-approvals-and-sandbox",
                            "--skip-git-repo-check", "{prompt}", "{images}"],
                    "kind": "codex", "model": "qa-model",
                    "account": "openai", "label": "QA lead"},
    }


def write_rich_config(root: Path, coders=("coder_1", "coder_2")):
    cfg = {"agents": rich_agents(),
           "coders": list(coders),
           "paid_agents": ["coder_1"],
           "roles": {"quarterback": "quarterback", "qa": "qa_lead"},
           "fallback": {"coder_1:*": ["coder_2"], "coder_2:*": ["coder_1"],
                        "quarterback:*": ["qa_lead", "coder_1"]},
           "disabled_agents": [],
           "lanes": [{"name": "B", "dir": "C:/tmp/gh_laneB"},
                     {"name": "C", "dir": "C:/tmp/gh_laneC"}],
           "approval_gate": {"enabled": False, "types": [], "workers": [],
                             "timeout_minutes": 0},
           "spend_cap": {"daily_usd": 0, "agents": []},
           "_notes": "keep me",
           "custom_unknown": {"a": 1}}
    (root / "orchestrator" / "config.json").write_text(json.dumps(cfg, indent=2),
                                                      encoding="utf-8")
    return cfg


def load_mod(root: Path):
    """Import a copy of the orchestrator bound to the throwaway project."""
    src = fx.ENGINE_ROOT / "template" / "orchestrator" / "orchestrator.py"
    dst = root / "orchestrator" / "orchestrator.py"
    shutil.copy(src, dst)
    spec = importlib.util.spec_from_file_location("orch_phase4", str(dst))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    mod.git_commit = lambda *a, **k: True  # stub git: no-op
    spec.loader.exec_module(mod)
    mod.PROJECT = root / "project"
    mod.RUNS = root / "project" / "runs"
    mod.TASKS_DIR = root / "project" / "tasks"
    mod.BOARD_PATH = root / "project" / "board.json"
    mod.EVENTS_PATH = root / "project" / "events.log"
    mod.STOP_FILE = root / "project" / "STOP"
    return mod


class OfficeCase(unittest.TestCase):
    def start(self, manage=False, demo=False, rich=True, coders=("coder_1", "coder_2")):
        self.tmp = make_project()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        if rich:
            write_rich_config(self.root, coders=coders)
        self.srv = OfficeServer(self.root, manage=manage, demo=demo)
        fx.server._opencode.update({"t": time.time(), "days1": None,
                                    "days7": None, "error": "test stub"})
        self.addCleanup(self.srv.close)
        self.addCleanup(setattr, fx.server, "DEMO", False)
        self.addCleanup(setattr, fx.server, "MANAGE", False)

    def get(self, path, token=TOKEN, host=None):
        return call(self.srv, "GET", path, token=token, host=host)

    def post(self, path, body=None, raw=None, token=TOKEN, host=None):
        return call(self.srv, "POST", path, body=body, raw=raw, token=token, host=host)

    def cfg(self):
        return json.loads((self.root / "orchestrator" / "config.json").read_text(encoding="utf-8"))

    def get_mtime(self):
        _, d = self.get("/api/config")
        return d["mtime"]

    def save(self, changes, mtime=None):
        base = self.get_mtime() if mtime is None else mtime
        return self.post("/api/config", {"base_mtime": base, "changes": changes})


class ConfigApi(OfficeCase):
    """1. Config API: auth, model rewrite, -m refusal, bad model, stale base,
    backups, unknown keys."""

    def test_get_needs_token(self):
        self.start(manage=True)
        code, _ = self.get("/api/config", token=None)
        self.assertEqual(code, 403)
        code, d = self.get("/api/config")
        self.assertEqual(code, 200)
        self.assertIn("config", d)
        self.assertIn("mtime", d)
        self.assertIn("models", d)
        self.assertIn("paid", d)
        self.assertIn("kinds", d)
        self.assertTrue(d["paid"]["coder_1"])
        self.assertEqual(d["kinds"]["coder_1"], "opencode")

    def test_model_rewrite_only(self):
        self.start(manage=True)
        before = self.cfg()
        old_cmd = list(before["agents"]["coder_1"]["cmd"])
        code, d = self.save({"agents": {"coder_1": {"model": "new/model"}}})
        self.assertEqual(code, 200, d)
        after = self.cfg()
        self.assertEqual(after["agents"]["coder_1"]["model"], "new/model")
        self.assertEqual(after["agents"]["coder_1"]["cmd"],
                         [c if c != "model-one" else "new/model" for c in old_cmd])
        # everything else identical
        self.assertEqual(after["agents"]["coder_2"], before["agents"]["coder_2"])
        self.assertEqual(after["coders"], before["coders"])

    def test_no_m_flag_refused(self):
        self.start(manage=True)
        cfg = self.cfg()
        cfg["agents"]["plain"] = {"cmd": [PY, "-c", "print('OK')"], "kind": "opencode",
                                  "model": "x", "account": "acct-9", "label": "Plain"}
        (self.root / "orchestrator" / "config.json").write_text(json.dumps(cfg, indent=2),
                                                                encoding="utf-8")
        code, _ = self.save({"agents": {"plain": {"model": "other/m"}}})
        self.assertEqual(code, 400)

    def test_bad_model_and_stale(self):
        self.start(manage=True)
        code, _ = self.save({"agents": {"coder_1": {"model": "bad model!"}}})
        self.assertEqual(code, 400)
        code, _ = self.save({"agents": {"coder_1": {"model": "ok/m"}}}, mtime=1000.0)
        self.assertEqual(code, 409)

    def test_backup_and_unknown_keys(self):
        self.start(manage=True)
        bdir = self.root / "orchestrator" / "config.backups"
        # pre-create 25 backups with explicit mtimes (deterministic ordering)
        bdir.mkdir(parents=True, exist_ok=True)
        base = time.time() - 1000
        for i in range(25):
            p = bdir / f"config-202610{i:02d}-000000.json"
            p.write_text("{}", encoding="utf-8")
            os.utime(p, (base + i, base + i))
        code, d = self.save({"agents": {"coder_1": {"model": "kept/m"}}})
        self.assertEqual(code, 200, d)
        files = list(bdir.glob("config-*.json"))
        self.assertLessEqual(len(files), 20)
        after = self.cfg()
        self.assertEqual(after["_notes"], "keep me")
        self.assertEqual(after["custom_unknown"], {"a": 1})
        # event logged
        events = (self.root / "project" / "events.log").read_text(encoding="utf-8")
        self.assertIn("OFFICE config changed:", events)


class Validation(OfficeCase):
    """2. Removing the only coder / a role holder / a chain member is refused;
    a valid removal cleans every list."""

    def test_remove_only_coder(self):
        self.start(manage=True, coders=("coder_1",))
        cfg = self.cfg()
        cfg["coders"] = ["coder_1"]
        cfg["fallback"] = {}
        (self.root / "orchestrator" / "config.json").write_text(json.dumps(cfg, indent=2),
                                                                encoding="utf-8")
        code, _ = self.save({"remove": ["coder_1"]})
        self.assertEqual(code, 409)

    def test_remove_role_holder(self):
        self.start(manage=True)
        code, d = self.save({"remove": ["quarterback"]})
        self.assertEqual(code, 409, d)

    def test_remove_chain_member_stale_fallback_refused(self):
        self.start(manage=True)
        # remove coder_2 but keep it in a chain -> whole-config validation refuses
        code, d = self.save({"remove": ["coder_2"],
                             "fallback": {"coder_1:*": ["coder_2"]}})
        self.assertIn(code, (400, 409), d)

    def test_valid_removal_cleans(self):
        self.start(manage=True)
        code, d = self.save({"remove": ["coder_2"]})
        self.assertEqual(code, 200, d)
        after = self.cfg()
        self.assertNotIn("coder_2", after["agents"])
        self.assertNotIn("coder_2", after["coders"])
        for chain in (after.get("fallback") or {}).values():
            self.assertNotIn("coder_2", chain)
        self.assertNotIn("coder_2", after.get("disabled_agents", []))


class Lanes(OfficeCase):
    """3. Lane add derives dir; OneDrive refused; busy lane removal is 409."""

    def test_add_lane_dir(self):
        self.start(manage=True)
        code, d = self.save({"lanes": {"count": 4}})
        self.assertEqual(code, 200, d)
        after = self.cfg()
        self.assertEqual(len(after["lanes"]), 3)
        self.assertEqual(after["lanes"][-1]["name"], "D")
        self.assertTrue(after["lanes"][-1]["dir"].endswith("gh_laneD"), after["lanes"][-1])
        self.assertTrue(d["restart_needed"])

    def test_onedrive_refused(self):
        self.start(manage=True)
        cfg = self.cfg()
        cfg["lanes"] = []
        (self.root / "orchestrator" / "config.json").write_text(json.dumps(cfg, indent=2),
                                                                encoding="utf-8")
        code, d = self.save({"lanes": {"count": 2, "new_dir": "C:/Users/me/OneDrive/gh_laneB"}})
        self.assertEqual(code, 400, d)

    def test_remove_busy_lane(self):
        self.start(manage=True)
        (self.root / "project" / "STATUS.md").write_text(
            "# Fixture Game: Live Status\n\nUpdated: 2026-10-18 12:00:00\n\n"
            "**Now:** working\n**Current task:** -\n**Lane C:** T-2 Second (coder) - working on work\n",
            encoding="utf-8")
        fx.server.invalidate()
        code, d = self.save({"lanes": {"count": 2}})
        self.assertEqual(code, 409, d)


class BenchInbox(unittest.TestCase):
    """4. Bench through the orchestrator inbox (importlib pattern from Phase 2)."""

    def test_bench_unbench(self):
        tmp = make_project()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        write_rich_config(root)
        mod = load_mod(root)
        board = json.loads((root / "project" / "board.json").read_text(encoding="utf-8"))
        cmds = root / "project" / "commands"
        cmds.mkdir(exist_ok=True)
        (cmds / "done").mkdir(exist_ok=True)

        def send(name, payload):
            (cmds / name).write_text(json.dumps(payload), encoding="utf-8")

        send("b1.json", {"id": "b1", "action": "bench", "agent": "coder_2",
                         "reason": "noisy"})
        mod.process_commands(board)
        done = json.loads((cmds / "done" / "b1.json").read_text(encoding="utf-8"))
        self.assertEqual(done["result"], "applied")
        self.assertTrue(mod.unavailable("coder_2"))
        self.assertFalse(mod.unavailable("coder_1"))
        task = {"id": "T-9", "owner": "coder", "type": "code"}
        self.assertEqual(mod.resolve_worker(task, "A", 1), "coder_1")
        # benched agents are never probed
        with mock.patch.object(mod, "run_proc") as rp:
            rp.side_effect = AssertionError("must not probe a benched agent")
            mod.probe_agent("coder_2")
        persisted = json.loads((root / "orchestrator" / "config.json").read_text(encoding="utf-8"))
        self.assertIn("coder_2", persisted.get("disabled_agents", []))
        events = (root / "project" / "events.log").read_text(encoding="utf-8")
        self.assertIn("BENCH coder_2", events)

        # benching the last available coder is refused
        send("b2.json", {"id": "b2", "action": "bench", "agent": "coder_1"})
        mod.process_commands(board)
        done2 = json.loads((cmds / "done" / "b2.json").read_text(encoding="utf-8"))
        self.assertTrue(str(done2["result"]).startswith("refused"), done2)
        # unknown agent refused
        send("b3.json", {"id": "b3", "action": "bench", "agent": "ghost"})
        mod.process_commands(board)
        done3 = json.loads((cmds / "done" / "b3.json").read_text(encoding="utf-8"))
        self.assertTrue(str(done3["result"]).startswith("refused"), done3)

        # unbench restores everything
        send("b4.json", {"id": "b4", "action": "unbench", "agent": "coder_2"})
        mod.process_commands(board)
        done4 = json.loads((cmds / "done" / "b4.json").read_text(encoding="utf-8"))
        self.assertEqual(done4["result"], "applied")
        self.assertFalse(mod.unavailable("coder_2"))
        persisted2 = json.loads((root / "orchestrator" / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("coder_2", persisted2.get("disabled_agents", []))


class AwaitApproval(unittest.TestCase):
    """5. await_approval with a fake clock and sleep."""

    def _mod(self, root):
        write_rich_config(root)
        return load_mod(root)

    def test_approve_revise_timeout_stop(self):
        tmp = make_project()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        mod = self._mod(root)
        task = {"id": "T-5", "title": "Blocked one", "type": "code"}
        ap = root / "project" / "approvals"
        ap.mkdir(parents=True, exist_ok=True)
        (ap / "done").mkdir(exist_ok=True)

        class Clock:
            def __init__(self):
                self.t = 1000.0

            def __call__(self):
                return self.t

            def sleep(self, s):
                self.t += s

        # approve continues
        (ap / "T-5.json").write_text(json.dumps({"task": "T-5"}), encoding="utf-8")
        (ap / "T-5.decision.json").write_text(
            json.dumps({"decision": "approve", "feedback": ""}), encoding="utf-8")
        clock = Clock()
        dec, fb = mod.await_approval(task, 1, "A", sleep=clock.sleep, clock=clock)
        self.assertEqual(dec, "approve")
        self.assertTrue((ap / "done" / "T-5.json").exists())
        self.assertTrue((ap / "done" / "T-5.decision.json").exists())

        # revise returns the feedback
        (ap / "T-5.json").write_text(json.dumps({"task": "T-5"}), encoding="utf-8")
        (ap / "T-5.decision.json").write_text(
            json.dumps({"decision": "revise", "feedback": "fix it"}), encoding="utf-8")
        clock = Clock()
        dec, fb = mod.await_approval(task, 1, "A", sleep=clock.sleep, clock=clock)
        self.assertEqual(dec, "revise")
        self.assertEqual(fb, "fix it")

        # timeout auto-approves and logs the event
        mod.CONFIG["approval_gate"] = {"enabled": True, "types": [], "workers": [],
                                       "timeout_minutes": 0.05}
        (ap / "T-5.json").write_text(json.dumps({"task": "T-5"}), encoding="utf-8")
        try:
            (ap / "T-5.decision.json").unlink()
        except OSError:
            pass
        clock = Clock()
        dec, _ = mod.await_approval(task, 1, "A", sleep=clock.sleep, clock=clock)
        self.assertEqual(dec, "approve")
        events = (root / "project" / "events.log").read_text(encoding="utf-8")
        self.assertIn("APPROVAL TIMEOUT T-5 - auto-approved", events)

        # STOP raises StopRequested
        mod.CONFIG["approval_gate"] = {"enabled": True, "types": [], "workers": [],
                                       "timeout_minutes": 0}
        (ap / "T-5.json").write_text(json.dumps({"task": "T-5"}), encoding="utf-8")
        try:
            (ap / "T-5.decision.json").unlink()
        except OSError:
            pass
        (root / "project" / "STOP").write_text("stop\n", encoding="utf-8")
        try:
            with self.assertRaises(mod.StopRequested):
                mod.await_approval(task, 1, "A", sleep=lambda s: None,
                                   clock=lambda: 1000.0)
        finally:
            try:
                (root / "project" / "STOP").unlink()
            except OSError:
                pass


class ApprovalsApi(OfficeCase):
    """6. Office approvals: GET lists pending; POST writes; 400/409 rules."""

    def _pending(self, tid="T-2"):
        ap = self.root / "project" / "approvals"
        ap.mkdir(parents=True, exist_ok=True)
        (ap / "done").mkdir(exist_ok=True)
        (ap / f"{tid}.json").write_text(json.dumps(
            {"task": tid, "title": "Second", "attempt": 1, "lane": "A",
             "worker": "coder_1", "requested_at": "2026-10-18 12:00:00",
             "summary": "s", "review_summary": "r", "qa_verdict": "pass",
             "checks_summary": "c", "patch": "p", "screenshot": ""}), encoding="utf-8")

    def test_flow(self):
        self.start(manage=True)
        self._pending("T-2")
        code, d = self.get("/api/approvals", token=None)  # read-only
        self.assertEqual(code, 200)
        self.assertTrue(any(r["task"] == "T-2" for r in d["pending"]))
        code, _ = self.post("/api/approval", {"task": "T-2", "decision": "revise",
                                              "feedback": ""})
        self.assertEqual(code, 400)
        code, d = self.post("/api/approval", {"task": "T-2", "decision": "approve",
                                              "feedback": ""})
        self.assertEqual(code, 200, d)
        dec = json.loads((self.root / "project" / "approvals" / "T-2.decision.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(dec["decision"], "approve")
        code, _ = self.post("/api/approval", {"task": "T-999", "decision": "approve"})
        self.assertEqual(code, 409)


class SpendCap(unittest.TestCase):
    """7. Spend cap parks accounts; under-cap doesn't; failures don't block;
    the two parser copies agree."""

    SAMPLE = ("│Total Cost                                        $0.16 │\n"
              "│ meta/muse-spark-1.3-contributor                        │\n"
              "│  Messages                                          282 │\n"
              "│  Input Tokens                                   674.3K │\n"
              "│  Output Tokens                                  193.4K │\n"
              "│  Cost                                          $0.1622 │\n")

    def _mod(self, root):
        write_rich_config(root)
        cfg = json.loads((root / "orchestrator" / "config.json").read_text(encoding="utf-8"))
        cfg["agents"]["coder_1"]["model"] = "meta/muse-spark-1.3-contributor"
        cfg["spend_cap"] = {"daily_usd": 5.0, "agents": ["coder_1"]}
        (root / "orchestrator" / "config.json").write_text(json.dumps(cfg, indent=2),
                                                           encoding="utf-8")
        return load_mod(root)

    def test_over_under_unreadable(self):
        tmp = make_project()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        mod = self._mod(root)

        over = {"total": 5.12, "models": {"meta/muse-spark-1.3-contributor": {"cost": 5.12}}}
        with mock.patch.object(mod, "opencode_stats_today", return_value=over):
            mod.check_spend_cap("coder_1")
        self.assertIsNotNone(mod.limited_until("coder_1"))
        events = (root / "project" / "events.log").read_text(encoding="utf-8")
        self.assertEqual(events.count("SPEND CAP coder_1"), 1)
        self.assertIn("parked until 00:00", events)
        # second call: still exactly one event (once per day)
        with mock.patch.object(mod, "opencode_stats_today", return_value=over):
            mod.check_spend_cap("coder_1")
        events2 = (root / "project" / "events.log").read_text(encoding="utf-8")
        self.assertEqual(events2.count("SPEND CAP coder_1"), 1)

        # under the cap: a fresh module parks nothing
        mod2 = self._mod(root)
        under = {"total": 0.16, "models": {"meta/muse-spark-1.3-contributor": {"cost": 0.16}}}
        with mock.patch.object(mod2, "opencode_stats_today", return_value=under):
            mod2.check_spend_cap("coder_1")
        self.assertIsNone(mod2.limited_until("coder_1"))

        # unreadable stats don't block
        mod3 = self._mod(root)
        with mock.patch.object(mod3, "opencode_stats_today", return_value=None):
            mod3.check_spend_cap("coder_1")  # must not raise
            mod3.check_spend_cap("coder_1")
        self.assertIsNone(mod3.limited_until("coder_1"))
        events3 = (root / "project" / "events.log").read_text(encoding="utf-8")
        self.assertLessEqual(events3.count("SPEND CAP check failed"), 1)

    def test_parsers_agree(self):
        import stats as st
        tmp = make_project()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        mod = load_mod(root)
        for sample in (self.SAMPLE, "hello ???", "", "│Total Cost $1.20 │\n"):
            self.assertEqual(mod.parse_opencode_stats(sample),
                             st.parse_opencode_stats(sample))


class LimitsSpend(OfficeCase):
    """8. limits() treats SPEND CAP lines like USAGE LIMIT."""

    def test_spend_cap_line(self):
        self.start(manage=False)
        agents = {"coder_1": {"account": "acct-1"}, "coder_2": {"account": "acct-2"}}
        events = ["2026-10-18 12:00:00  SPEND CAP coder_1 $5.12 >= $5.00 today - parked until 00:00"]
        out = fx.server.limits(events, agents)
        self.assertIn("coder_1", out)
        self.assertEqual(out["coder_1"]["state"], "limited")


class DemoPhase4(OfficeCase):
    """9. Demo: Settings + Approvals from demo data, one benched agent,
    one pending approval, every POST is 409."""

    PATHS = ["/api/config", "/api/approvals"]

    def test_demo(self):
        self.start(manage=False, demo=True, rich=False)
        code, d = self.get("/api/config")
        self.assertEqual(code, 200)
        self.assertIn("config", d)
        code, d = self.get("/api/approvals")
        self.assertEqual(code, 200)
        self.assertEqual(len(d["pending"]), 1)
        code, st = self.get("/api/state?scene=working")
        self.assertEqual(code, 200)
        benched = [a for a in st["agents"] if a.get("benched")]
        self.assertEqual(len(benched), 1)
        for p in ("/api/config", "/api/approval", "/api/command"):
            code, d = self.post(p, {"x": 1})
            self.assertEqual(code, 409, p)
            self.assertEqual(d.get("error"), "demo mode")


class QaFixes(unittest.TestCase):
    """Regression tests for fixes made in Claude's Phase 4 QA."""

    def _mod(self):
        tmp = make_project()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        write_rich_config(root)
        return load_mod(root), root

    def test_spend_parked_agent_is_not_probed(self):
        mod, _ = self._mod()
        acct = mod.ACCOUNT.get("coder_1", "coder_1")
        mod._state.setdefault("spend_parked", {})[acct] = mod.dt.datetime.now() + mod.dt.timedelta(hours=1)
        calls = []
        mod.run_proc = lambda *a, **k: calls.append(a) or (0, "OK", False)
        mod.probe_agent("coder_1")
        self.assertEqual(calls, [], "a spend-parked agent answered a probe, which would lift the park")

    def test_agent_model_falls_back_to_cmd(self):
        mod, _ = self._mod()
        mod.CONFIG["agents"]["coder_1"].pop("model", None)
        mod.CONFIG["agents"]["coder_1"]["cmd"] = ["opencode", "run", "-m", "meta/muse-x", "{prompt}"]
        self.assertEqual(mod.agent_model("coder_1"), "meta/muse-x")

    def test_recover_drops_stale_approval(self):
        mod, root = self._mod()
        appr = root / "project" / "approvals"
        appr.mkdir(parents=True, exist_ok=True)
        (appr / "T-2.json").write_text("{}", encoding="utf-8")
        (appr / "T-2.decision.json").write_text('{"decision": "approve"}', encoding="utf-8")
        board = {"tasks": [{"id": "T-2", "status": "in_progress", "lane": "A"}]}
        try:
            mod.recover(board, lanes=("A",))
        except Exception:  # noqa: BLE001 - git/worktree steps don't exist in the fixture; only the cleanup matters
            pass
        self.assertFalse((appr / "T-2.json").exists())
        self.assertFalse((appr / "T-2.decision.json").exists())


if __name__ == "__main__":
    unittest.main()
