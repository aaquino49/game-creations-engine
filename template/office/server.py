#!/usr/bin/env python3
"""The Office: a cute, optional, read-only window onto the AI team.

  office.bat                          (or: python office/server.py)
  python office/server.py --lan       also reachable from your phone on the same Wi-Fi
  python office/server.py --project "C:/path/to/game" --port 8766

Serves a small web page that shows every agent as a little person: at a desk when working (with what they're on),
at the coffee machine or on the couch when idle, asleep when rate-limited, plus a progress bar per milestone.
It only READS project files (STATUS.md, events.log, board.json, config.json, runs/); it never writes to the project,
so opening or closing it has no effect on the team. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # overridden by --project
_procs = {"orchestrator": None, "supervisor": None, "checked": 0.0}
_cache: dict = {"t": 0.0, "state": None}
_lock = threading.Lock()
DEMO = False


def process_status(commands: list[str], script: str) -> bool | None:
    """Absolute launch paths identify this project; old relative launches are ambiguous."""
    target = (ROOT / "orchestrator" / script).as_posix().lower()
    ambiguous = False
    for command in commands:
        command = command.replace("\\", "/").lower()
        if re.search(r'(?:^|[\s"\'])' + re.escape(target) + r'(?=$|[\s"\'])', command):
            return True
        if re.search(r'(?:^|[\s"\'])(?:\./)?orchestrator/' + re.escape(script) + r'(?=$|[\s"\'])', command):
            ambiguous = True
    return None if ambiguous else False


# ----------------------------------------------------------------------------- reading the project

def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def watch_processes() -> None:
    """Background thread: is an orchestrator / supervisor running? (A PowerShell query takes a few seconds.)"""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
          "ForEach-Object { $_.CommandLine }")
    while True:
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 timeout=15, check=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            commands = out.splitlines()
            _procs["orchestrator"] = process_status(commands, "orchestrator.py")
            _procs["supervisor"] = process_status(commands, "supervisor.py")
        except Exception:  # noqa: BLE001
            _procs["orchestrator"] = _procs["supervisor"] = None
        _procs["checked"] = time.time()
        time.sleep(20)


def parse_time(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


EVENT_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+(.*)$")


def classify(text: str) -> dict:
    """Event line -> {kind, task, lane} for the page's animations and ticker."""
    m = re.match(r"DONE (T-\d+) \(attempt \d+, lane (\w)\)", text)
    if m:
        return {"kind": "done", "task": m.group(1), "lane": m.group(2)}
    m = re.match(r"START (T-\d+) \[lane (\w)\]", text)
    if m:
        return {"kind": "start", "task": m.group(1), "lane": m.group(2)}
    m = re.match(r"LANE (\w) merged (T-\d+)", text)
    if m:
        return {"kind": "merged", "task": m.group(2), "lane": m.group(1)}
    m = re.match(r"BLOCKED (T-\d+)", text)
    if m:
        return {"kind": "blocked", "task": m.group(1)}
    m = re.match(r"(T-\d+) a\d+ (WORK|CHECKS|QA|REVIEW) (\w+)", text)
    if m:
        return {"kind": m.group(2).lower() + "_" + m.group(3).lower(), "task": m.group(1)}
    for prefix, kind in (("MILESTONE", "milestone"), ("PROJECT COMPLETE", "complete"), ("PLAN start", "plan_start"),
                         ("PLAN done", "plan_done"), ("USAGE LIMIT", "limit"), ("QUOTA RESTORED", "restored"),
                         ("FALLBACK", "fallback"), ("SUPERVISOR", "supervisor"), ("PROVIDER DOWN", "limit"),
                         ("PREEMPTIVE HANDOFF", "limit"), ("MODEL GONE", "gone"),
                         ("RESTART", "restart"), ("ORCHESTRATOR START", "boot")):
        if text.startswith(prefix):
            return {"kind": kind}
    return {"kind": "other"}


def newest_log(folder: Path, step: str | None, agents: dict) -> str | None:
    """The agent behind the newest `<step>.<agent>.log` in a run folder (the one running now, or the last one)."""
    best, best_t = None, -1.0
    try:
        files = list(folder.glob("*.log"))
    except OSError:
        return None
    for f in files:
        m = re.match(r"^(\w+)\.(\w+)\.log$", f.name)
        if not m or m.group(2) not in agents or (step and m.group(1) != step):
            continue
        try:
            t = f.stat().st_mtime
        except OSError:
            continue
        if t > best_t:
            best, best_t = m.group(2), t
    return best


def agent_labels(agents: dict) -> dict:
    """label -> agent, from config.json labels and (for older projects) the AGENT_NAMES table in orchestrator.py."""
    out = {a.get("label", n): n for n, a in agents.items()}
    src = read(ROOT / "orchestrator" / "orchestrator.py")
    m = re.search(r"^AGENT_NAMES = \{(.*?)\}\s*$", src, re.M | re.S)
    if m:
        for name, label in re.findall(r'"(\w+)":\s*"([^"]+)"', m.group(1)):
            if name in agents:
                out[label] = name
    return out


def agent_from_activity(activity: str, labels: dict) -> str | None:
    """'<label> working on <step>' names the agent the orchestrator just started (longest label wins)."""
    head = activity.split(" working on ")[0] if " working on " in activity else ""
    return labels.get(head) or next((labels[l] for l in sorted(labels, key=len, reverse=True) if head.startswith(l)), None)


def latest_attempt(tid: str) -> Path | None:
    d = ROOT / "project" / "runs" / tid
    try:
        attempts = sorted((p for p in d.iterdir() if re.match(r"a\d+$", p.name)), key=lambda p: int(p.name[1:]))
    except OSError:
        return None
    return attempts[-1] if attempts else None


def step_of(activity: str) -> str:
    a = activity.lower()
    m = re.search(r"working on (\w+)", a)
    if m:
        return m.group(1)
    if "running godot checks" in a:
        return "checks"
    if "merge" in a:
        return "merge"
    if "sleeping until" in a:
        return "sleeping"
    if a.startswith("stopped"):
        return "stopped"
    return "other"


def limits(events: list[str], agents: dict) -> dict:
    """agent -> {state: limited|down|gone, until}, for limits still in force."""
    account = {n: a.get("account", n) for n, a in agents.items()}
    out: dict = {}
    now = dt.datetime.now()
    for line in events:
        m = re.match(r"(\S+ \S+)\s+(USAGE LIMIT|PROVIDER DOWN|MODEL GONE|PREEMPTIVE HANDOFF|QUOTA RESTORED) ([\w-]+)", line)
        if not m:
            continue
        when = parse_time(m.group(1))
        if not when:
            continue
        if m.group(2) == "QUOTA RESTORED":
            out = {k: v for k, v in out.items() if account.get(k) != m.group(3) and k != m.group(3)}
            continue
        u = re.search(r"until ~(?:\w{3} )?(\d{1,2}):(\d{2})", line)
        until = when.replace(hour=int(u.group(1)), minute=int(u.group(2)), second=0) if u else when + dt.timedelta(hours=1)
        if until < when:
            until += dt.timedelta(days=1)
        kind = {"USAGE LIMIT": "limited", "PREEMPTIVE HANDOFF": "limited",
                "PROVIDER DOWN": "down", "MODEL GONE": "gone"}[m.group(2)]
        subject = m.group(3)
        if kind == "limited":  # handoffs name an account; usage limits name an agent
            acct = account.get(subject, subject)
            for other, other_acct in account.items():
                if other_acct == acct:
                    out[other] = {"state": kind, "until": until}
        elif subject in agents:
            out[subject] = {"state": kind, "until": until}
    return {k: {"state": v["state"], "until": v["until"].strftime("%H:%M")} for k, v in out.items() if v["until"] > now}


def build_state() -> dict:
    p = ROOT / "project"
    cfg = read_json(ROOT / "orchestrator" / "config.json") or {}
    agents = cfg.get("agents") or {}
    board = read_json(p / "board.json") or {}
    status = read(p / "STATUS.md")
    all_events = read(p / "events.log").splitlines()
    tail = all_events[-800:]

    tasks = {t["id"]: t for t in board.get("tasks", [])}
    updated = parse_time((re.search(r"^Updated: (.+)$", status, re.M) or [None, ""])[1].strip())
    finished = {}  # task -> time it was DONE / BLOCKED (to correct a STATUS.md that hasn't been rewritten yet)
    for line in tail:
        m = re.match(r"(\S+ \S+)\s+(?:DONE|BLOCKED) (T-\d+)", line)
        if m:
            finished[m.group(2)] = parse_time(m.group(1))

    labels = agent_labels(agents)
    jobs = []  # what each agent is doing right now: {agent, station, lane, task, title, step, type}

    def lane_job(lane: str, task_text: str, activity: str) -> dict:
        m = re.match(r"^(T-\d+)\s+(.*?)(?:\s+\((\w+)\))?$", task_text.strip())
        if not m:
            return {"lane": lane, "state": "idle", "activity": activity}
        tid, title = m.group(1), m.group(2)
        if tid in finished and updated and finished[tid] and finished[tid] >= updated:
            return {"lane": lane, "state": "idle", "activity": "finished " + tid}
        step = step_of(activity)
        agent = agent_from_activity(activity, labels)
        if not agent and step not in ("checks", "merge", "sleeping", "stopped"):
            folder = latest_attempt(tid)
            if folder:
                agent = newest_log(folder, step if step in ("work", "qa", "review") else None, agents)
        t = tasks.get(tid, {})
        return {"lane": lane, "state": "busy", "task": tid, "title": title, "step": step, "agent": agent,
                "type": t.get("type", ""), "owner": t.get("owner", ""), "milestone": t.get("milestone", ""),
                "attempt": t.get("attempts", 0), "activity": activity}

    now_text = (re.search(r"^\*\*Now:\*\* (.*)$", status, re.M) or [None, ""])[1]
    cur = (re.search(r"^\*\*Current task:\*\* (.*)$", status, re.M) or [None, "-"])[1]
    lane_names = ["A"] + [ln.get("name", "?") for ln in cfg.get("lanes", [])]
    lanes = {}
    planner = {"busy": False}
    if "working on plan" in now_text and cur.strip() in ("-", ""):
        planner = {"busy": True, "reason": "", "activity": now_text}
        lanes["A"] = {"lane": "A", "state": "idle", "activity": "planning"}
    else:
        lanes["A"] = lane_job("A", cur if cur.strip() != "-" else "", now_text)
    for name, text in re.findall(r"^\*\*Lane (\w+):\*\* (.*)$", status, re.M):
        if text.strip() == "idle" or text.strip() == "off":
            lanes[name] = {"lane": name, "state": "idle", "activity": ""}
            continue
        m = re.match(r"^(T-\d+ .*?\(\w+\))(?: - (.*))?$", text)
        lanes[name] = lane_job(name, m.group(1), m.group(2) or "") if m else {"lane": name, "state": "idle", "activity": text}
    pl = re.search(r"^\*\*Planner:\*\* (.*?)(?: \((.*)\))?$", status, re.M)
    if pl:
        planner = {"busy": True, "activity": pl.group(1), "reason": pl.group(2) or ""}
    if planner["busy"]:
        runs = sorted((p / "runs" / "_plan").glob("*"), key=lambda q: q.name)
        planner["agent"] = (agent_from_activity(planner.get("activity", ""), labels) or agent_from_activity(now_text, labels)
                            or (newest_log(runs[-1], "plan", agents) if runs else None) or "claude")
        jobs.append({"agent": planner["agent"], "station": "plan", "step": "plan", "task": "",
                     "title": planner.get("reason") or "planning the next tasks"})
    for name in lane_names:
        ln = lanes.get(name) or {"lane": name, "state": "idle"}
        lanes[name] = ln
        if ln["state"] == "busy" and ln.get("agent") and ln.get("step") in ("work", "qa", "review"):
            jobs.append({"agent": ln["agent"], "station": f"lane:{name}", "step": ln["step"], "task": ln["task"],
                         "title": ln["title"], "type": ln.get("type", "")})

    # Supervisor's AI fixer: "SUPERVISOR-AI <agent> called" without a later done/timed out/unavailable/finished.
    fixer = None
    for line in tail:
        m = re.search(r"SUPERVISOR-AI (\w+) (called|done|timed out|unavailable|finished)", line)
        if m:
            fixer = m.group(1) if m.group(2) == "called" else None
    if fixer and fixer in agents:
        jobs.append({"agent": fixer, "station": "boss", "step": "fix", "task": "", "title": "fixing a stall for the supervisor"})
    last_sup = next((EVENT_RE.match(l).group(2) for l in reversed(tail) if "SUPERVISOR" in l and EVENT_RE.match(l)), "")

    lim = limits(tail, agents)
    agent_list = []
    for n, a in agents.items():
        kind = (a.get("cmd") or ["?"])[0]
        label = a.get("label") or next((l for l, x in labels.items() if x == n and l != n), n)
        agent_list.append({"id": n, "label": label, "tool": kind, "model": a.get("model", ""),
                           "paid": n in (cfg.get("paid_agents") or []), "coder": n in (cfg.get("coders") or []),
                           **({"limit": lim[n]} if n in lim else {})})

    # Subscriptions (usage-limit buckets): every account in play, worst state first. Shared by
    # every position on the account, so two roles on one model nap and recover together.
    acct_labels = cfg.get("accounts") or {}
    acct_members: dict = {}
    for n, a in agents.items():
        acct_members.setdefault(a.get("account", n), []).append(n)
    sev = {"gone": 3, "down": 2, "limited": 1}
    accounts = []
    for acct, members in acct_members.items():
        hits = [(m, lim[m]) for m in members if m in lim]
        if hits:
            m, l = max(hits, key=lambda h: (sev.get(h[1]["state"], 0), h[1].get("until", "")))
            accounts.append({"id": acct, "label": acct_labels.get(acct, acct),
                             "state": l["state"], "until": l["until"], "agents": members})
        else:
            accounts.append({"id": acct, "label": acct_labels.get(acct, acct), "state": "ok", "agents": members})
    accounts.sort(key=lambda x: (sev.get(x.get("state"), 0), x["id"]), reverse=True)

    # Milestones: done (+dropped) / total from the board; title from the close-out report if there is one.
    ms: dict = {}
    for t in board.get("tasks", []):
        m = ms.setdefault(t["milestone"], {"id": t["milestone"], "done": 0, "total": 0, "blocked": 0, "active": 0})
        m["total"] += 1
        m["done"] += t["status"] in ("done", "dropped")
        m["blocked"] += t["status"] == "blocked"
        m["active"] += t["status"] == "in_progress"
    order = sorted(ms.values(), key=lambda m: int(re.sub(r"\D", "", m["id"]) or 0))
    for m in order:
        head = read(p / "milestones" / f"{m['id']}.md").splitlines()[:1]
        mm = re.match(r"#\s*M\d+[^:]*:\s*(.*)", head[0]) if head else None
        m["title"] = mm.group(1).strip() if mm else ""
    order = [m for m in order if m["total"] > 0]

    events = []
    last = tail[-60:]
    start = len(all_events) - len(last)  # event ids are line numbers, so the page can spot new ones
    for i, line in enumerate(last):
        m = EVENT_RE.match(line)
        if m:
            events.append({"id": start + i,
                           "t": m.group(1)[11:16], "text": m.group(2)[:220], **classify(m.group(2))})

    flags = [f for f in ("STOP", "RESTART", "PLAN_NOW") if (p / f).exists()]
    game = (re.search(r"^# (.+?): Live Status", status, re.M) or [None, board.get("project") or ROOT.name])[1]
    return {
        "game": game, "time": dt.datetime.now().strftime("%H:%M"), "updated": updated.strftime("%H:%M") if updated else "",
        "orchestrator": _procs["orchestrator"], "supervisor": _procs["supervisor"], "flags": flags,
        "now": now_text, "lanes": [lanes[n] for n in lane_names], "planner": planner, "jobs": jobs,
        "agents": agent_list, "accounts": accounts, "milestones": order, "events": events, "supervisor_msg": last_sup[:200],
        "complete": bool(board.get("project_complete")),
        "configured": bool(agents), "demo": False,
        "counts": {s: sum(1 for t in board.get("tasks", []) if t["status"] == s)
                   for s in ("done", "in_progress", "ready", "backlog", "blocked")},
    }


def state() -> dict:
    with _lock:
        if time.time() - _cache["t"] > 2 or _cache["state"] is None:
            try:
                _cache["state"] = build_state()
            except Exception as e:  # noqa: BLE001  (a half-written file must never kill the page)
                _cache["state"] = {**(_cache["state"] or {}), "error": repr(e)[:300]}
            _cache["t"] = time.time()
        return _cache["state"]


# ----------------------------------------------------------------------------- web server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:  # keep the console quiet
        pass

    def send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        path = unquote(url.path)
        if path == "/api/state":
            if DEMO:
                from demo import demo_state
                scene = parse_qs(url.query).get("scene", ["auto"])[0]
                return self.send(200, json.dumps(demo_state(scene)).encode("utf-8"), "application/json")
            return self.send(200, json.dumps(state()).encode("utf-8"), "application/json")
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (HERE / rel).resolve()
        if HERE not in f.parents or not f.is_file() or f.suffix not in {".html", ".css", ".js", ".png", ".woff2", ".txt"}:
            return self.send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if f.suffix == ".woff2":
            ctype = "font/woff2"
        self.send(200, f.read_bytes(), ctype)


def main() -> int:
    global ROOT, DEMO
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="game folder (default: the folder this office/ is in)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="also serve on your local network (for a phone)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--demo", action="store_true", help="preview simulated workers without running agents or reading a project")
    a = ap.parse_args()
    if a.project:
        ROOT = Path(a.project).resolve()
    DEMO = a.demo
    if not DEMO and not (ROOT / "project").is_dir():
        print(f"{ROOT} doesn't look like a game project (no project/ folder). Use --project.")
        return 1
    if not DEMO:
        threading.Thread(target=watch_processes, daemon=True).start()
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    server = None
    for port in range(a.port, a.port + 20):
        try:
            server = ThreadingHTTPServer((host, port), Handler)
            break
        except OSError:
            continue
    if not server:
        print("No free port found.")
        return 1
    url = f"http://localhost:{server.server_port}/"
    print(f"The Office {'demo' if DEMO else 'for ' + ROOT.name} is open at {url}")
    if a.lan:
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
            print(f"On your phone (same Wi-Fi): http://{ip}:{server.server_port}/  (allow Python through the firewall)")
        except OSError:
            pass
    print("Close this window to close the office. The team keeps working either way.")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
