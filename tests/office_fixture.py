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

BOARD = {"project": "Fixture Game", "tasks": [
    {"id": "T-1", "title": "First", "status": "done", "milestone": "M1"},
    {"id": "T-2", "title": "Second", "status": "in_progress", "milestone": "M1"},
    {"id": "T-3", "title": "Third", "status": "ready", "milestone": "M2"},
    {"id": "T-4", "title": "Fourth", "status": "backlog", "milestone": "M2"},
]}

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
    return tmp


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
