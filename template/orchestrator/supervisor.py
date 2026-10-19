"""Lightweight supervisor: keeps the orchestrator alive and calls in an AI fixer when the team stalls.

Every 2 minutes:
- If no `orchestrator.py` process is running (and project/STOP doesn't exist), relaunch start.bat and alert.
- Look for stalls (no progress for `stall_minutes`, lane B idle while independent work is ready, a lane B merge stuck,
  agents failing repeatedly). On a stall: post an ntfy alert and launch a headless supervisor agent (Claude, then Codex
  if Claude is rate-limited) with project/roles/supervisor.md. At most one AI fixer runs at a time, with a cooldown.

This runs whether or not anyone's interactive session is open, so stalls are caught within minutes.
"""
import datetime as dt
import json
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "project"
EVENTS = PROJECT / "events.log"
STATUS = PROJECT / "STATUS.md"
BOARD = PROJECT / "board.json"
SUP_RUNS = PROJECT / "runs" / "_supervisor"


def config() -> dict:
    cfg = json.loads((ROOT / "orchestrator" / "config.json").read_text(encoding="utf-8"))
    # Owner-only settings (the ntfy topic) live in the untracked config.local.json; its keys override config.json's.
    local = ROOT / "orchestrator" / "config.local.json"
    if local.exists():
        for k, v in json.loads(local.read_text(encoding="utf-8")).items():
            cfg[k] = {**cfg.get(k, {}), **v} if isinstance(v, dict) else v
    return cfg


def scfg() -> dict:
    return {"stall_minutes": 40, "lane_idle_minutes": 20, "cooldown_minutes": 45, "agents": ["claude", "codex"],
            "timeout_minutes": 30, **(config().get("supervisor") or {})}


def alert(title: str, msg: str, priority: str = "high") -> None:
    topic = (config().get("notify") or {}).get("ntfy_topic")
    if not topic:
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode(), method="POST",
                                     headers={"Title": title, "Priority": priority, "Tags": "skull"})
        urllib.request.urlopen(req, timeout=20).read()
    except Exception:  # noqa: BLE001
        pass


def log_event(msg: str) -> None:
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")


def orchestrator_running() -> bool:
    ps = ("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like '*orchestrator.py*' }).Count")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip()
    return out.isdigit() and int(out) > 0


def project_complete() -> bool:
    """Read the board, not the event log: a "PROJECT COMPLETE" line lingers in the log after the owner reopens the
    project for new milestones, which made a freshly started supervisor exit at once."""
    try:
        return bool(json.loads(BOARD.read_text(encoding="utf-8")).get("project_complete"))
    except (OSError, ValueError):
        return False


# ----------------------------------------------------------------------------- stall detection

LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})  (.*)$")
PROGRESS_RE = re.compile(r"T-\d+ a\d+ (WORK|CHECKS|QA|REVIEW)\b|^DONE T-|^PLAN done|^LANE B merged|^MILESTONE|"
                         r"^ORCHESTRATOR START")
WAITING_RE = re.compile(r"^SLEEP |^STOP requested|waiting for .* usage limit")


def recent_events(max_lines: int = 400) -> list[tuple[dt.datetime, str]]:
    try:
        lines = EVENTS.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except OSError:
        return []
    out = []
    for ln in lines:
        m = LINE_RE.match(ln)
        if m:
            try:
                out.append((dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2)))
            except ValueError:
                pass
    return out


def ready_independent_tasks() -> int:
    """Ready code/asset tasks whose dependencies are finished (lane B could take them)."""
    try:
        board = json.loads(BOARD.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    finished = {t["id"] for t in board["tasks"] if t["status"] in ("done", "dropped")}
    return sum(1 for t in board["tasks"] if t["status"] == "ready" and t["type"] in ("code", "asset")
               and all(d in finished for d in t.get("depends_on", [])))


_lane_b_idle_since: dt.datetime | None = None


def find_stall(now: dt.datetime | None = None, ev: list | None = None) -> str | None:
    """A one-line reason if the team looks stalled, else None. `now`/`ev` can be injected to replay history."""
    global _lane_b_idle_since
    c = scfg()
    now = now or dt.datetime.now()
    ev = recent_events() if ev is None else [(t, m) for t, m in ev if t <= now]
    if not ev:
        return None
    last_progress = max((t for t, m in ev if PROGRESS_RE.search(m)), default=None)
    last_wait = max((t for t, m in ev if WAITING_RE.search(m)), default=None)
    if last_progress and now - last_progress > dt.timedelta(minutes=c["stall_minutes"]):
        if not (last_wait and last_wait > last_progress):
            return (f"no progress events for {int((now - last_progress).total_seconds() // 60)} min "
                    f"(last at {last_progress:%H:%M})")
    window = [m for t, m in ev if now - t < dt.timedelta(minutes=30)]
    merges_waiting = sum(1 for m in window if m.startswith("LANE B waiting to merge"))
    if merges_waiting >= 2 and not any(m.startswith("LANE B merged") for m in window[-10:]):
        return f"lane B merge stuck ({merges_waiting} 'waiting to merge' events in 30 min)"
    fails = sum(1 for m in window if m.startswith("AGENT FAIL") or "WORK produced no result" in m)
    if fails >= 3:
        return f"{fails} agent failures/no-result steps in the last 30 min"
    if sum(1 for m in window if m.startswith("ORCHESTRATOR ERROR")) >= 2:
        return "repeated ORCHESTRATOR ERROR in the last 30 min"
    try:
        lane_b_idle = re.search(r"\*\*Lane [B-Z]:\*\* idle", STATUS.read_text(encoding="utf-8")) is not None
    except OSError:
        lane_b_idle = False
    if lane_b_idle and ready_independent_tasks() > 0:
        _lane_b_idle_since = _lane_b_idle_since or now
        if now - _lane_b_idle_since > dt.timedelta(minutes=c["lane_idle_minutes"]):
            return (f"lane B idle for {int((now - _lane_b_idle_since).total_seconds() // 60)} min while "
                    f"{ready_independent_tasks()} ready code/asset task(s) have their dependencies done")
    else:
        _lane_b_idle_since = None
    return None


# ----------------------------------------------------------------------------- AI fixer

_fixer = {"proc": None, "started": 0.0, "agent": None, "reason": "", "log": None, "last_launch": 0.0}
LIMIT_RE = re.compile(r"rate.?limit|usage limit|hit your (\w+ )?limit|limit reached|quota|too many requests", re.I)


def launch_fixer(reason: str, agents: list[str]) -> None:
    cfg = config()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = SUP_RUNS / stamp
    d.mkdir(parents=True, exist_ok=True)
    report = d / "report.json"
    prompt_file = d / "prompt.md"
    prompt_file.write_text(
        f"# Supervisor call ({stamp})\n\nTrigger: **{reason}**\n\nFollow `project/roles/supervisor.md` exactly. "
        f"No human is available: don't ask questions.\n\nWrite your JSON report to: `{report.relative_to(ROOT).as_posix()}`\n",
        encoding="utf-8")
    prompt = (f"Read the file {prompt_file.relative_to(ROOT).as_posix()} and carry out the instructions in it exactly. "
              f"Finish by writing the JSON report it names.")
    agent = agents[0]
    cmd = [prompt if p == "{prompt}" else p for p in cfg["agents"][agent]["cmd"] if p != "{images}"]
    log = d / f"{agent}.log"
    fh = log.open("w", encoding="utf-8")
    exe = shutil.which(cmd[0]) or cmd[0]  # honours PATHEXT (claude.CMD); `where` lists npm's sh shim first
    proc = subprocess.Popen([exe] + cmd[1:], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=fh,
                            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    _fixer.update(proc=proc, started=time.time(), agent=agent, reason=reason, log=log, last_launch=time.time(),
                  rest=agents[1:], report=report)
    log_event(f"SUPERVISOR-AI {agent} called: {reason} (log {log.relative_to(ROOT).as_posix()})")


def check_fixer() -> None:
    """Follow up on a running fixer: time it out, fall back to the next agent on a usage limit, report the result."""
    proc = _fixer["proc"]
    if proc is None:
        return
    elapsed = time.time() - _fixer["started"]
    if proc.poll() is None:
        if elapsed > scfg()["timeout_minutes"] * 60:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            log_event(f"SUPERVISOR-AI {_fixer['agent']} timed out after {int(elapsed // 60)} min")
            _fixer["proc"] = None
        return
    _fixer["proc"] = None
    try:
        tail = _fixer["log"].read_text(encoding="utf-8", errors="replace")[-3000:]
    except OSError:
        tail = ""
    report = None
    try:
        report = json.loads(_fixer["report"].read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        pass
    if report is None and _fixer.get("rest") and (elapsed < 120 or LIMIT_RE.search(tail)):
        log_event(f"SUPERVISOR-AI {_fixer['agent']} unavailable ({'usage limit' if LIMIT_RE.search(tail) else 'quick exit'}); "
                  f"trying {_fixer['rest'][0]}")
        launch_fixer(_fixer["reason"], _fixer["rest"])
        return
    if report:
        summary = f"found: {report.get('found', '')[:300]} | fixed: {report.get('fixed', '')[:300]}"
        log_event(f"SUPERVISOR-AI {_fixer['agent']} done: {summary}")
        alert("{{GAME_NAME}}: supervisor fixed a stall" if report.get("fixed") else "{{GAME_NAME}}: supervisor report",
              summary + (f"\nNEEDS YOU: {report['needs_owner']}" if report.get("needs_owner") else ""),
              priority="high" if report.get("needs_owner") else "default")
    else:
        log_event(f"SUPERVISOR-AI {_fixer['agent']} finished without a report (rc={proc.returncode})")


# ----------------------------------------------------------------------------- main loop

def main() -> None:
    misses = 0
    while True:
        if project_complete():
            alert("{{GAME_NAME}}: finished!", "The final milestone is complete and the team has stopped. Play builds/{{EXE_NAME}}.exe.")
            break
        if (PROJECT / "STOP").exists():
            break
        try:
            misses = 0 if orchestrator_running() else misses + 1
            if misses >= 2:  # down for two checks in a row (start.bat's own 60 s auto-restart didn't bring it back)
                subprocess.run(["explorer.exe", str(ROOT / "start.bat")])
                alert("{{GAME_NAME}}: orchestrator restarted", "It was not running, so the supervisor relaunched start.bat.")
                log_event("SUPERVISOR relaunched start.bat (orchestrator was not running)")
                misses = 0
                time.sleep(300)
                continue
            check_fixer()
            reason = find_stall() if misses == 0 else None
            cooldown = scfg()["cooldown_minutes"] * 60
            if reason and _fixer["proc"] is None and time.time() - _fixer["last_launch"] > cooldown:
                alert("{{GAME_NAME}}: team stalled", f"{reason}. Calling the AI supervisor to fix it.")
                launch_fixer(reason, list(scfg()["agents"]))
        except Exception as e:  # noqa: BLE001 - the supervisor must never die
            try:
                log_event(f"SUPERVISOR internal error: {e!r}"[:300])
            except OSError:
                pass
        time.sleep(120)


if __name__ == "__main__":
    main()
