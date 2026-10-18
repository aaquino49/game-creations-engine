"""Office phase 1 acceptance tests: one test per spec acceptance criterion (1-9)."""
import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.office_fixture import TOKEN, OfficeServer, call, make_project, snapshot, write_config
from tests import office_fixture as fx

PY = sys.executable


class OfficeCase(unittest.TestCase):
    def start(self, manage=False, demo=False, procs=None, agents=None, topic="test-topic"):
        self.tmp = make_project()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        if agents is not None or topic != "test-topic":
            write_config(self.root, agents if agents is not None else fx.default_agents(), topic=topic)
        self.srv = OfficeServer(self.root, manage=manage, demo=demo, procs=procs)
        self.addCleanup(self.srv.close)
        self.addCleanup(setattr, fx.server, "DEMO", False)
        self.addCleanup(setattr, fx.server, "MANAGE", False)

    def get(self, path, token=TOKEN, host=None):
        return call(self.srv, "GET", path, token=token, host=host)

    def post(self, path, body=None, raw=None, token=TOKEN, host=None):
        return call(self.srv, "POST", path, body=body, raw=raw, token=token, host=host)

    def wait_probe(self, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            code, d = self.get("/api/probe")
            self.assertEqual(code, 200)
            if not d["running"]:
                return d
            time.sleep(0.2)
        self.fail("probe did not finish in time")


class ReadOnlyByDefault(OfficeCase):
    """Acceptance 1: without --manage every POST is 403/404, state.manage is false,
    and the fixture files are byte-identical."""

    def test_readonly(self):
        self.start(manage=False)
        before = snapshot(self.root)
        code, st = self.get("/api/state")
        self.assertEqual(code, 200)
        self.assertFalse(st["manage"])
        for path, body in (("/api/control", {"action": "plan_now"}),
                           ("/api/requests", {"text": "hi"}),
                           ("/api/probe", {}),
                           ("/api/notify-test", {})):
            code, d = self.post(path, body)
            self.assertIn(code, (403, 404), path)
            self.assertIn("error", d, path)
        code, _ = self.post("/api/no-such-endpoint", {})
        self.assertIn(code, (403, 404))
        self.assertEqual(snapshot(self.root), before)


class TokenAndHost(OfficeCase):
    """Acceptance 2: manage mode needs the token and a local Host."""

    def test_token_and_host(self):
        self.start(manage=True)
        code, d = self.post("/api/control", {"action": "plan_now"}, token=None)
        self.assertEqual(code, 403)
        self.assertEqual(d.get("error"), "bad token")
        code, d = self.post("/api/control", {"action": "plan_now"}, token="wrong")
        self.assertEqual(code, 403)
        self.assertEqual(d.get("error"), "bad token")
        code, _ = self.post("/api/control", {"action": "plan_now"}, host="evil.com")
        self.assertEqual(code, 403)
        code, _ = self.get("/api/requests", token=None)
        self.assertEqual(code, 403)
        code, st = self.get("/api/state")
        self.assertEqual(code, 200)
        self.assertTrue(st["manage"])


class ControlFlags(OfficeCase):
    """Acceptance 3: plan_now/stop/restart write flags + event lines; cancel removes."""

    def test_flags(self):
        self.start(manage=True)
        for action, flag in (("plan_now", "PLAN_NOW"), ("stop", "STOP"), ("restart", "RESTART")):
            code, d = self.post("/api/control", {"action": action})
            self.assertEqual(code, 200, action)
            self.assertIn(flag, d["flags"])
            text = (self.root / "project" / flag).read_text(encoding="utf-8")
            self.assertIn("requested from the Office at", text)
            events = (self.root / "project" / "events.log").read_text(encoding="utf-8")
            self.assertRegex(events, rf"OFFICE {action} requested")
        code, d = self.post("/api/control", {"action": "cancel", "flag": "STOP"})
        self.assertEqual(code, 200)
        self.assertNotIn("STOP", d["flags"])
        self.assertFalse((self.root / "project" / "STOP").exists())
        for bad in ("../x", "STOPPED", ""):
            code, _ = self.post("/api/control", {"action": "cancel", "flag": bad})
            self.assertEqual(code, 400, bad)
        code, _ = self.post("/api/control", {"action": "self-destruct"})
        self.assertEqual(code, 400)


class StartAction(OfficeCase):
    """Acceptance 4: start is 409 while running; otherwise drops STOP and Popens start.bat."""

    def test_start(self):
        self.start(manage=True, procs={"orchestrator": True, "supervisor": False, "checked": 0.0})
        code, _ = self.post("/api/control", {"action": "start"})
        self.assertEqual(code, 409)
        fx.server._procs["orchestrator"] = False
        (self.root / "project" / "STOP").write_text("x", encoding="utf-8")
        with mock.patch("subprocess.Popen") as popen:
            code, d = self.post("/api/control", {"action": "start", "supervisor": True})
            self.assertEqual(code, 200)
            self.assertFalse((self.root / "project" / "STOP").exists())
            cmds = [c.args[0] for c in popen.call_args_list]
            self.assertIn(["cmd", "/c", "start", "", "start.bat"], cmds)
            self.assertIn(["cmd", "/c", "start", "", "supervise.bat"], cmds)
            for c in popen.call_args_list:
                self.assertEqual(c.kwargs.get("cwd"), self.root)
        with mock.patch("subprocess.Popen") as popen:
            code, _ = self.post("/api/control", {"action": "start_supervisor"})
            self.assertEqual(code, 200)
            cmds = [c.args[0] for c in popen.call_args_list]
            self.assertEqual(cmds, [["cmd", "/c", "start", "", "supervise.bat"]])


class RequestsRoundTrip(OfficeCase):
    """Acceptance 5: POST then GET shows the request; (none) replaced; rest unchanged."""

    def test_requests(self):
        self.start(manage=True)
        before = (self.root / "project" / "OWNER_REQUESTS.md").read_text(encoding="utf-8")
        code, d = self.post("/api/requests", {"text": "  Hello team T-123\nsecond line  "})
        self.assertEqual(code, 200)
        code, d = self.get("/api/requests")
        self.assertEqual(code, 200)
        self.assertEqual(len(d["open"]), 1)
        self.assertIn("Hello team T-123 second line", d["open"][0])
        self.assertIn("from the Office", d["open"][0])
        after = (self.root / "project" / "OWNER_REQUESTS.md").read_text(encoding="utf-8")
        self.assertNotIn("(none)", after.split("## Handled")[0])
        # everything outside the inserted line is unchanged
        open_section = before.split("## Open")[1].split("## Handled")[0]
        placeholder = next(l for l in open_section.splitlines() if l.strip().lower().startswith("(none)"))
        for line in before.splitlines():
            if line == placeholder:
                continue
            self.assertIn(line, after)
        self.assertIn("## Handled", after)
        events = (self.root / "project" / "events.log").read_text(encoding="utf-8")
        self.assertIn("OFFICE request added", events)
        for bad in ("", "   ", "x" * 2001):
            code, _ = self.post("/api/requests", {"text": bad})
            self.assertEqual(code, 400, repr(bad)[:20])
        code, _ = self.post("/api/requests", {"text": "plan me", "plan_now": True})
        self.assertEqual(code, 200)
        self.assertTrue((self.root / "project" / "PLAN_NOW").exists())


class Probe(OfficeCase):
    """Acceptance 6: ok/fail results; a second concurrent POST is 409."""

    def test_probe_results(self):
        self.start(manage=True, agents={
            "good": {"cmd": [PY, "-c", "print('OK')"], "model": "g", "account": "a"},
            "bad": {"cmd": [PY, "-c", "import sys; print('nope'); sys.exit(1)"],
                    "model": "b", "account": "b"},
        })
        code, _ = self.post("/api/probe", {})
        self.assertEqual(code, 200)
        d = self.wait_probe()
        self.assertEqual(d["results"]["good"]["state"], "ok")
        self.assertEqual(d["results"]["bad"]["state"], "fail")
        for name, res in d["results"].items():
            self.assertIsInstance(res["seconds"], float, name)
            self.assertIsInstance(res["detail"], str, name)

    def test_probe_concurrent_409(self):
        self.start(manage=True, agents={
            "slow": {"cmd": [PY, "-c", "import time; time.sleep(2); print('OK')"],
                     "model": "s", "account": "s"},
        })
        try:
            code, _ = self.post("/api/probe", {})
            self.assertEqual(code, 200)
            code, d = self.post("/api/probe", {})
            self.assertEqual(code, 409)
        finally:
            self.wait_probe()
        d = self.wait_probe()
        self.assertEqual(d["results"]["slow"]["state"], "ok")


class NotifyTest(OfficeCase):
    """Acceptance 7: 409 with no topic; one urlopen to the right URL with a topic."""

    def test_notify(self):
        self.start(manage=True, topic=None)
        code, d = self.post("/api/notify-test", {})
        self.assertEqual(code, 409)
        self.assertIn("ntfy_topic", d.get("error", ""))
        write_config(self.root, fx.default_agents(), topic="test-topic")
        with mock.patch("urllib.request.urlopen") as open_:
            code, d = self.post("/api/notify-test", {})
            self.assertEqual(code, 200)
            self.assertEqual(open_.call_count, 1)
            req = open_.call_args[0][0]
            self.assertEqual(req.full_url, "https://ntfy.sh/test-topic")
            self.assertIn("test from the Office", req.get_header("Title"))
            self.assertEqual(open_.call_args[1].get("timeout"), 15)


class DemoMode(OfficeCase):
    """Acceptance 8: in demo mode every POST is 409 demo mode."""

    def test_demo(self):
        self.start(manage=False, demo=True)
        code, st = self.get("/api/state")
        self.assertEqual(code, 200)
        self.assertTrue(st["manage"])
        for path, body in (("/api/control", {"action": "plan_now"}),
                           ("/api/requests", {"text": "hi"}),
                           ("/api/probe", {}),
                           ("/api/notify-test", {})):
            code, d = self.post(path, body)
            self.assertEqual(code, 409, path)
            self.assertEqual(d.get("error"), "demo mode", path)


class BodyCap(OfficeCase):
    """Acceptance 9: a body over 64 KB is 413."""

    def test_body_too_large(self):
        self.start(manage=True)
        code, d = self.post("/api/requests", raw=b'{"text": "' + b"x" * 70000 + b'"}')
        self.assertEqual(code, 413)
        self.assertIn("error", d)


if __name__ == "__main__":
    unittest.main()
