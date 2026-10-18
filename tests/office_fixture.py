"""Shared fixture for the Office manage-mode tests: a throwaway game project plus
a live office server (the real ThreadingHTTPServer + Handler) on port 0.

The fixture never launches real agents or start.bat: agent cmds are harmless
Python one-liners, and tests patch subprocess.Popen / urlopen where needed.
"""
import json
import shutil
import sys
import tempfile
import threading
from http import client as http_client
from http.server import ThreadingHTTPServer
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT / "template" / "office"))

import server  # noqa: E402

TOKEN = "test-token-123"

STATUS = """# Fixture Game: Live Status

Updated: 2026-10-18 12:00:00

**Now:** Fixture activity
**Current task:** -
"""

BOARD = {"project": "Fixture Game", "next_id": 8, "tasks": [
    {"id": "T-1", "title": "First", "status": "done", "milestone": "M1",
     "priority": 2, "type": "code", "owner": "coder", "depends_on": [], "attempts": 2,
     "description": "First task", "acceptance": ["it works"],
     "history": [
         {"attempt": 1, "at": "2026-10-18 10:00:00", "worker": "coder_1", "work": "done",
          "checks": True, "qa": "pass", "checks_after_qa": True, "review": "approve"},
         {"attempt": 2, "at": "2026-10-18 11:00:00", "worker": "coder_1", "work": "done",
          "checks": True, "qa": "pass", "checks_after_qa": True, "review": "approve"},
     ]},
    {"id": "T-2", "title": "Second", "status": "in_progress", "milestone": "M1",
     "priority": 3, "type": "code", "owner": "coder", "depends_on": ["T-1"], "attempts": 1,
     "description": "Second task", "acceptance": ["it builds"], "history": []},
    {"id": "T-3", "title": "Third", "status": "ready", "milestone": "M2",
     "priority": 3, "type": "code", "owner": "coder", "depends_on": ["T-2"], "attempts": 0,
     "description": "Third task", "acceptance": ["it runs"], "history": []},
    {"id": "T-4", "title": "Fourth", "status": "backlog", "milestone": "M2",
     "priority": 4, "type": "design", "owner": "coder", "depends_on": [], "attempts": 0,
     "description": "Fourth task", "acceptance": ["sketch"], "history": []},
    {"id": "T-5", "title": "Blocked one", "status": "blocked", "milestone": "M2",
     "priority": 1, "type": "code", "owner": "coder", "depends_on": [], "attempts": 3,
     "description": "Blocked task", "acceptance": ["unblock me"], "history": [],
     "blocked_reason": "needs help"},
    {"id": "T-6", "title": "Cycle A", "status": "backlog", "milestone": "M2",
     "priority": 3, "type": "code", "owner": "coder", "depends_on": ["T-7"], "attempts": 0,
     "description": "Cycle part one", "acceptance": ["a"], "history": []},
    {"id": "T-7", "title": "Cycle B", "status": "backlog", "milestone": "M2",
     "priority": 3, "type": "code", "owner": "coder", "depends_on": ["T-6"], "attempts": 0,
     "description": "Cycle part two", "acceptance": ["b"], "history": []},
]}

# Minimal PNG bytes for run-folder screenshots (valid magic, dummy body).
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 100

PY = sys.executable


def default_agents():
    return {
        "ok1": {"cmd": [PY, "-c", "print('OK')"], "model": "m-ok", "account": "acct-a"},
        "ok2": {"cmd": [PY, "-c", "print('OK')"], "model": "m-ok2", "account": "acct-b"},
    }


def make_project():
    """Build a throwaway game project; the caller owns the TemporaryDirectory."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / "project").mkdir()
    (root / "project" / "STATUS.md").write_text(STATUS, encoding="utf-8")
    (root / "project" / "events.log").write_text(
        "2026-10-18 12:00:00  ORCHESTRATOR START\n", encoding="utf-8")
    (root / "project" / "board.json").write_text(json.dumps(BOARD), encoding="utf-8")
    shutil.copy(ENGINE_ROOT / "template" / "project" / "OWNER_REQUESTS.md",
                root / "project" / "OWNER_REQUESTS.md")
    (root / "orchestrator").mkdir()
    write_config(root, default_agents(), topic="test-topic")
    (root / "project" / "commands").mkdir(exist_ok=True)
    (root / "project" / "commands" / "done").mkdir(exist_ok=True)
    _make_tasks(root)
    _make_runs(root)
    return tmp


def _make_tasks(root):
    tasks_dir = root / "project" / "tasks"
    tasks_dir.mkdir(exist_ok=True)
    for t in BOARD["tasks"]:
        (tasks_dir / f"{t['id']}.md").write_text(
            f"# {t['id']}: {t['title']}\n\n{t.get('description', '')}\n", encoding="utf-8")


def _make_runs(root):
    """Two attempts for T-1 with json/log/png/patch, plus a run folder for T-5."""
    import time
    runs = root / "project" / "runs"
    for n in (1, 2):
        d = runs / "T-1" / f"a{n}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "work.json").write_text(json.dumps(
            {"status": "done", "summary": f"work attempt {n}"}), encoding="utf-8")
        (d / "qa.json").write_text(json.dumps(
            {"verdict": "pass", "summary": f"qa {n}", "out_of_scope_bugs": []}), encoding="utf-8")
        (d / "review.json").write_text(json.dumps(
            {"verdict": "approve", "summary": f"review {n} looks good"}), encoding="utf-8")
        (d / "work.coder_1.log").write_text(
            f"$ work attempt {n}\n(rc=0, timed_out=False)\n\nline one\nline two\n", encoding="utf-8")
        (d / "qa.codex.log").write_text(
            f"$ qa attempt {n}\n(rc=0, timed_out=False)\n\nqa ok\n", encoding="utf-8")
        (d / f"screenshot_shot{n}.png").write_bytes(PNG_BYTES)
        (d / f"fix{n}.patch").write_text(
            f"--- a/file{n}.gd\n+++ b/file{n}.gd\n@@ -1 +1 @@\n-old\n+new\n", encoding="utf-8")
    # Blocked task run folder (one attempt, minimal).
    bd = runs / "T-5" / "a3"
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "work.json").write_text(json.dumps({"status": "blocked", "summary": "stuck"}),
                                   encoding="utf-8")
    (bd / "work.coder_1.log").write_text("$ blocked\n(rc=1, timed_out=False)\n\nstuck\n",
                                          encoding="utf-8")
    # Stagger mtimes so /api/screenshots has a deterministic order.
    base = time.time() - 300
    for i, p in enumerate(sorted(runs.glob("T-*/a*/*.png"))):
        ts = base + i * 100
        try:
            import os
            os.utime(p, (ts, ts))
        except OSError:
            pass


def write_config(root, agents, topic="test-topic"):
    cfg = {"agents": agents}
    if topic is not None:
        cfg["notify"] = {"ntfy_topic": topic}
    (Path(root) / "orchestrator" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


class OfficeServer:
    """The real office HTTP server in a thread, with module globals set directly."""

    def __init__(self, root, manage=False, demo=False, procs=None):
        server.ROOT = Path(root)
        server.MANAGE = manage
        server.TOKEN = TOKEN
        server.DEMO = demo
        server.LAN_IP = ""
        server._procs.update(procs or {"orchestrator": False, "supervisor": False, "checked": 0.0})
        with server._lock:
            server._cache.update({"t": 0.0, "state": None})
            server._shots.update({"t": 0.0, "data": []})
        with server._probe_lock:
            server._probe.update({"running": False, "results": {}})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"


def call(srv, method, path, body=None, raw=None, token=TOKEN, host=None):
    """(code, payload) for a JSON API call. body=None sends no payload.

    Uses http.client directly (not urllib) so tests may patch
    urllib.request.urlopen to observe the server's notify call.
    """
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["X-Office-Token"] = token
    if host is not None:
        headers["Host"] = host
    conn = http_client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    try:
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        raw_body = r.read()
        try:
            return r.status, (json.loads(raw_body) if raw_body else {})
        except ValueError:
            return r.status, {}
    finally:
        conn.close()


def snapshot(root):
    """path -> bytes for every file under project/ and orchestrator/."""
    out = {}
    for folder in ("project", "orchestrator"):
        base = Path(root) / folder
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    out[str(p.relative_to(root))] = p.read_bytes()
    return out
