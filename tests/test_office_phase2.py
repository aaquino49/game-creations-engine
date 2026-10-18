"""Office phase 2 acceptance tests: one test per spec acceptance criterion (1-8)."""
import importlib.util
import json
import shutil
import sys
import threading
import time
import unittest
from http import client as http_client
from pathlib import Path

from tests.office_fixture import TOKEN, OfficeServer, call, make_project
from tests import office_fixture as fx


class OfficeCase(unittest.TestCase):
    def start(self, manage=False, demo=False, procs=None):
        self.tmp = make_project()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.srv = OfficeServer(self.root, manage=manage, demo=demo, procs=procs)
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


class TaskEndpoint(OfficeCase):
    """Acceptance 1: /api/task/T-1 returns brief, history and attempts with files."""

    def test_task(self):
        self.start(manage=False)
        code, d = self.get("/api/task/T-1")
        self.assertEqual(code, 200)
        self.assertIn("First", d.get("title", ""))
        self.assertTrue(d.get("brief", "").startswith("# T-1"))
        self.assertTrue(isinstance(d.get("history"), list) and len(d["history"]) >= 1)
        self.assertTrue(isinstance(d.get("attempts"), list) and len(d["attempts"]) == 2)
        a1 = d["attempts"][0]
        self.assertEqual(a1["n"], 1)
        names = {f["name"] for f in a1["files"]}
        self.assertIn("work.json", names)
        self.assertIn("work.coder_1.log", names)
        self.assertTrue(any(n.endswith(".png") for n in names))
        self.assertTrue(any(n.endswith(".patch") for n in names))
        self.assertIsInstance(a1["work"], dict)
        self.assertIsInstance(a1["qa"], dict)
        self.assertIsInstance(a1["review"], dict)
        code, _ = self.get("/api/task/T-x")
        self.assertEqual(code, 400)
        code, _ = self.get("/api/task/T-999")
        self.assertEqual(code, 404)


class FileEndpoint(OfficeCase):
    """Acceptance 2: /api/file serves png and log; traversal/absolute/board/py are 403."""

    def test_file(self):
        self.start(manage=False)
        code, ctype, body = self.get_raw(
            "/api/file?path=project/runs/T-1/a1/screenshot_shot1.png")
        self.assertEqual(code, 200)
        self.assertIn("image", ctype)
        self.assertTrue(body.startswith(b"\x89PNG"))
        code, ctype, body = self.get_raw(
            "/api/file?path=project/runs/T-1/a1/work.coder_1.log")
        self.assertEqual(code, 200)
        self.assertIn("text/plain", ctype)
        self.assertIn(b"line one", body)
        for bad in ("..\\..\\orchestrator\\config.json",
                    "../../orchestrator/config.json",
                    "/etc/passwd",
                    "project/board.json",
                    "project/runs/T-1/a1/work.json",
                    "orchestrator/config.json"):
            # work.json is inside runs but project/runs/T-1/a1/work.json IS allowed;
            # use a .py path for the last check instead
            pass
        # traversal (posix + windows), absolute, board.json, and .py all 403
        import urllib.parse
        checks = [
            "project/runs/T-1/a1/../../../../orchestrator/config.json",
            "..\\..\\orchestrator\\config.json",
            "/etc/passwd",
            "project/board.json",
            "template/office/server.py",
        ]
        # absolute path of a real allowed file must still be 403
        abs_allowed = (self.root / "project" / "runs" / "T-1" / "a1" / "work.coder_1.log").as_posix()
        checks.append(abs_allowed)
        for bad in checks:
            q = "/api/file?path=" + urllib.parse.quote(bad, safe="")
            code, _, _ = self.get_raw(q)
            self.assertEqual(code, 403, bad)
        # .py inside runs is also 403 (bad suffix)
        pydir = self.root / "project" / "runs" / "T-1" / "a1" / "evil.py"
        pydir.write_text("x", encoding="utf-8")
        q = "/api/file?path=" + urllib.parse.quote("project/runs/T-1/a1/evil.py", safe="")
        code, _, _ = self.get_raw(q)
        self.assertEqual(code, 403)


class TailEndpoint(OfficeCase):
    """Acceptance 3: offset returns new text; offset>size restarts; 1MB capped at 64KB."""

    def test_tail(self):
        self.start(manage=False)
        code, d = self.get("/api/tail?path=project/runs/T-1/a1/work.coder_1.log&offset=0")
        self.assertEqual(code, 200)
        full = d["text"]
        self.assertIn("line one", full)
        off = len(full.encode("utf-8")) if False else d["offset"]
        # append and read only new text
        p = self.root / "project" / "runs" / "T-1" / "a1" / "work.coder_1.log"
        with p.open("a", encoding="utf-8") as f:
            f.write("brand new line\n")
        code, d2 = self.get(f"/api/tail?path=project/runs/T-1/a1/work.coder_1.log&offset={off}")
        self.assertEqual(code, 200)
        self.assertIn("brand new line", d2["text"])
        self.assertNotIn("line one", d2["text"])
        # offset past size restarts from 0
        code, d3 = self.get("/api/tail?path=project/runs/T-1/a1/work.coder_1.log&offset=99999999")
        self.assertEqual(code, 200)
        self.assertIn("line one", d3["text"])
        # 1 MB log capped at 64 KB per call
        big = self.root / "project" / "runs" / "T-1" / "a1" / "big.log"
        big.write_bytes((b"x" * 100 + b"\n") * 11000)  # ~1.2 MB
        code, d4 = self.get("/api/tail?path=project/runs/T-1/a1/big.log&offset=0")
        self.assertEqual(code, 200)
        self.assertLessEqual(len(d4["text"].encode("utf-8")), 64 * 1024 + 100)


class ScreenshotsEndpoint(OfficeCase):
    """Acceptance 4: sorted by mtime and includes titles."""

    def test_screenshots(self):
        self.start(manage=False)
        code, d = self.get("/api/screenshots")
        self.assertEqual(code, 200)
        self.assertTrue(isinstance(d, list) and len(d) >= 2)
        paths = [e["path"] for e in d]
        self.assertTrue(all(p.endswith(".png") for p in paths))
        self.assertTrue(all(e.get("title") for e in d))
        # mtime order: fixture staggers them; verify non-decreasing file mtimes
        mts = [(self.root / p).stat().st_mtime for p in paths]
        self.assertEqual(mts, sorted(mts))


class CommandApi(OfficeCase):
    """Acceptance 5: POST without manage refused; valid set_priority writes a file;
    retry on ready is 409; priority 9 is 400."""

    def test_no_manage_refused(self):
        self.start(manage=False)
        code, _ = self.post("/api/command", {"action": "set_priority", "task": "T-4", "priority": 1})
        self.assertIn(code, (403, 404))

    def test_command_flow(self):
        self.start(manage=True)
        before = list((self.root / "project" / "commands").glob("*.json"))
        code, d = self.post("/api/command", {"action": "set_priority", "task": "T-4", "priority": 1})
        self.assertEqual(code, 200)
        self.assertIn("id", d)
        after = list((self.root / "project" / "commands").glob("*.json"))
        self.assertEqual(len(after), len(before) + 1)
        payload = json.loads((self.root / "project" / "commands" / (d["id"] + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(payload["action"], "set_priority")
        self.assertEqual(payload["source"], "office")
        code, _ = self.post("/api/command", {"action": "retry", "task": "T-3"})
        self.assertEqual(code, 409)
        code, _ = self.post("/api/command", {"action": "set_priority", "task": "T-4", "priority": 9})
        self.assertEqual(code, 400)


class OrchestratorInbox(unittest.TestCase):
    """Acceptance 6: process_commands applies each action, plus refused + malformed."""

    def test_inbox(self):
        tmp = fx.make_project()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        src = fx.ENGINE_ROOT / "template" / "orchestrator" / "orchestrator.py"
        dst = root / "orchestrator" / "orchestrator.py"
        shutil.copy(src, dst)
        spec = importlib.util.spec_from_file_location("orch_copy", str(dst))
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        mod.git_commit = lambda *a, **k: True  # stub git: no-op
        spec.loader.exec_module(mod)
        board = json.loads((root / "project" / "board.json").read_text(encoding="utf-8"))
        cmds = root / "project" / "commands"
        cmds.mkdir(exist_ok=True)
        (cmds / "done").mkdir(exist_ok=True)
        items = [
            ("a1-set-priority.json", {"id": "a1", "at": "2026-10-18T00:00:00", "source": "office",
                                      "action": "set_priority", "task": "T-4", "priority": 1}),
            ("a2-set-status.json", {"id": "a2", "at": "2026-10-18T00:00:01", "source": "office",
                                    "action": "set_status", "task": "T-4", "status": "ready"}),
            ("a3-retry.json", {"id": "a3", "at": "2026-10-18T00:00:02", "source": "office",
                               "action": "retry", "task": "T-5"}),
            ("a4-add.json", {"id": "a4", "at": "2026-10-18T00:00:03", "source": "office",
                             "action": "add_task", "task": {"title": "Newbie", "description": "d",
                                                            "milestone": "M1", "type": "code",
                                                            "priority": 2, "acceptance": ["x"],
                                                            "depends_on": []}}),
            ("a5-refused.json", {"id": "a5", "at": "2026-10-18T00:00:04", "source": "office",
                                 "action": "retry", "task": "T-3"}),
        ]
        for name, payload in items:
            (cmds / name).write_text(json.dumps(payload), encoding="utf-8")
        (cmds / "a6-malformed.json").write_text("{not json", encoding="utf-8")
        mod.PROJECT = root / "project"
        mod.RUNS = root / "project" / "runs"
        mod.TASKS_DIR = root / "project" / "tasks"
        mod.BOARD_PATH = root / "project" / "board.json"
        mod.EVENTS_PATH = root / "project" / "events.log"
        mod.process_commands(board)
        # board changed for each applied action
        t4 = next(t for t in board["tasks"] if t["id"] == "T-4")
        self.assertEqual(t4["priority"], 1)
        self.assertEqual(t4["status"], "ready")
        t5 = next(t for t in board["tasks"] if t["id"] == "T-5")
        self.assertEqual(t5["status"], "ready")
        self.assertEqual(t5["attempts"], 0)
        self.assertTrue(any(t["title"] == "Newbie" for t in board["tasks"]))
        # files moved to done/ with results, events logged
        events = (root / "project" / "events.log").read_text(encoding="utf-8")
        for name, payload in items:
            done_p = cmds / "done" / name
            self.assertTrue(done_p.exists(), name)
            done_d = json.loads(done_p.read_text(encoding="utf-8"))
            if payload["id"] == "a5":
                self.assertTrue(str(done_d.get("result", "")).startswith("refused"), name)
            else:
                self.assertEqual(done_d.get("result"), "applied", name)
            self.assertIn(payload["id"], events)
        mal = json.loads((cmds / "done" / "a6-malformed.json").read_text(encoding="utf-8"))
        self.assertIn("malformed", str(mal.get("result", "")))
        self.assertFalse(list(cmds.glob("*.json")))


class RunProcLive(unittest.TestCase):
    """Acceptance 7: .live.log exists during a slow child, gone after; final log identical."""

    def test_live(self):
        tmp = fx.make_project()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        src = fx.ENGINE_ROOT / "template" / "orchestrator" / "orchestrator.py"
        dst = root / "orchestrator" / "orchestrator.py"
        shutil.copy(src, dst)
        spec = importlib.util.spec_from_file_location("orch_live", str(dst))
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        log_path = root / "project" / "runs" / "T-9" / "a1" / "work.agent.log"
        args = [sys.executable, "-c",
                "import sys, time; print('hello'); sys.stdout.flush(); time.sleep(1.5); print('world')"]
        out_box = {}
        live_path = log_path.with_name(log_path.stem + ".live.log")

        def run():
            rc, out, timed = mod.run_proc(args, 20, log_path)
            out_box.update(rc=rc, out=out, timed=timed)

        th = threading.Thread(target=run)
        th.start()
        seen = False
        for _ in range(50):
            if live_path.exists():
                seen = True
                break
            time.sleep(0.1)
        self.assertTrue(seen, ".live.log never appeared while the child ran")
        th.join(timeout=20)
        self.assertFalse(th.is_alive())
        self.assertFalse(live_path.exists())
        self.assertIn("hello", out_box["out"])
        self.assertIn("world", out_box["out"])
        expected = f"$ {' '.join(args)}\n(rc={out_box['rc']}, timed_out={out_box['timed']})\n\n{out_box['out']}"
        got = log_path.read_text(encoding="utf-8", newline="")
        self.assertEqual(got.replace("\r", ""), expected.replace("\r", ""))


class NewestLogIgnoresLive(unittest.TestCase):
    """Acceptance 8: newest_log ignores work.coder_1.live.log."""

    def test_ignores_live(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / "work.coder_1.log").write_text("real", encoding="utf-8")
            (folder / "work.coder_1.live.log").write_text("live", encoding="utf-8")
            got = fx.server.newest_log(folder, "work", {"coder_1": {}})
            self.assertEqual(got, "coder_1")
            # live-only folder -> None
            folder2 = Path(td) / "empty"
            folder2.mkdir()
            (folder2 / "work.coder_1.live.log").write_text("live", encoding="utf-8")
            self.assertIsNone(fx.server.newest_log(folder2, "work", {"coder_1": {}}))


if __name__ == "__main__":
    unittest.main()
