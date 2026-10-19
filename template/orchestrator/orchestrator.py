#!/usr/bin/env python3
"""{{GAME_NAME}} orchestrator: runs the autonomous AI team loop.

Plain script, no AI. It owns project/board.json and git, calls the agents through their CLIs,
runs the Godot checks, and keeps project/STATUS.md current. See project/PROTOCOL.md.

Usage:
  python orchestrator/orchestrator.py            run until the project is complete or project/STOP exists
  python orchestrator/orchestrator.py --once     run at most one task (plus planning if needed), then exit
  python orchestrator/orchestrator.py --plan     run one planning step, then exit
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "project"
BOARD_PATH = PROJECT / "board.json"
RUNS = PROJECT / "runs"
TASKS_DIR = PROJECT / "tasks"
STOP_FILE = PROJECT / "STOP"
STATUS_PATH = PROJECT / "STATUS.md"
EVENTS_PATH = PROJECT / "events.log"
PM_NOTES = PROJECT / "PM_NOTES.md"
CONFIG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
# Owner-only settings (the ntfy topic) live in the untracked config.local.json; its keys override config.json's.
_LOCAL_CONFIG = Path(__file__).parent / "config.local.json"
if _LOCAL_CONFIG.exists():
    for _k, _v in json.loads(_LOCAL_CONFIG.read_text(encoding="utf-8")).items():
        CONFIG[_k] = {**CONFIG.get(_k, {}), **_v} if isinstance(_v, dict) else _v

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
GODOT_ERROR_RE = re.compile(r"(SCRIPT ERROR|Parse Error|^\s*ERROR:)", re.M)
SCRIPT_ERROR_RE = re.compile(r"(SCRIPT ERROR|Parse Error)")  # tests may push_error on purpose
EXIT_LEAK_RE = re.compile(r"still in use at exit|leaked at exit")  # reported as warnings, not failures
RATE_LIMIT_RE = re.compile(
    r"rate.?limit|usage limit|quota|RESOURCE_EXHAUSTED|\b429\b|too many requests|limit reached|"
    r"hit your (\w+ )?limit|session limit|weekly limit|limit\W+resets?|try again (later|at|in)|out of credits|"
    r"capacity|insufficient balance|\b402\b",
    re.I,
)
# Provider-side failures (not the agent's fault): OpenCode retries a 5xx for a minute or so and then exits,
# which is too slow for the quick-fail check. Route around them like a usage limit instead of burning attempts.
PROVIDER_DOWN_RE = re.compile(
    r"AI_(APICall|Retry)Error: .*(Internal Server Error|Service Unavailable|Bad Gateway|Gateway Timeout|"
    r"overloaded)|\b50[234]\b.*(server|gateway|unavailable)",
    re.I,
)
# The model id no longer exists on the provider (e.g. a free promo model was withdrawn): park it for long.
MODEL_GONE_RE = re.compile(r"ProviderModelNotFoundError|Model not found: ")
MODEL_GONE_MINUTES = 12 * 60
MILESTONES = ["M0", "M1", "M2", "M3", "M4", "M5"]
RESTART_EXIT_CODE = 75

# Two work lanes run in parallel threads. Lane A works in ROOT; lane B works in a separate git worktree and
# merges into ROOT after approval. Each thread sets _tl.root; git and agent processes run in that root.
_tl = threading.local()
MAIN_GIT_LOCK = threading.RLock()   # every git command in ROOT (lane B merges into it)
BOARD_LOCK = threading.RLock()      # board mutations + saves


def _worktree_lanes() -> dict[str, Path]:
    """Worktree lanes (B, C, ...) in order. Lane A always works in ROOT. Config: "lanes": [{"name", "dir"}, ...],
    falling back to the older single "lane_b" block."""
    lanes = CONFIG.get("lanes")
    if lanes is None:
        lb = CONFIG.get("lane_b", {})
        lanes = [{"name": "B", "dir": lb.get("dir", str(Path.home() / "{{SLUG}}_laneB"))}] if lb.get("enabled") else []
    return {str(entry["name"]).upper(): Path(entry["dir"]) for entry in lanes}


WORKTREE_LANES = _worktree_lanes()
LANE_B_DIR = WORKTREE_LANES.get("B", Path.home() / "{{SLUG}}_laneB")


def lane_dir(lane: str) -> Path:
    return ROOT if lane == "A" else WORKTREE_LANES[lane]


def lane_index(lane: str) -> int:
    return 0 if lane == "A" else 1 + list(WORKTREE_LANES).index(lane) if lane in WORKTREE_LANES else 1


def cur_lane() -> str:
    """The lane (or "P" for the background planner) the current thread works for."""
    return getattr(_tl, "lane", "A")


def cur_root() -> Path:
    return getattr(_tl, "root", ROOT)


@contextlib.contextmanager
def on_root(root: Path):
    """Temporarily run git/agents in another root (e.g. lane B committing its start in ROOT)."""
    old = cur_root()
    _tl.root = root
    try:
        yield
    finally:
        _tl.root = old


def git_lock():
    return MAIN_GIT_LOCK if cur_root() == ROOT else contextlib.nullcontext()


def ms_index(ms: str) -> int:
    """M0..M5 are v1; expansion milestones continue as M6, M7, ..."""
    m = re.fullmatch(r"M(\d+)", str(ms))
    return int(m.group(1)) if m else 999


def all_milestones(board: dict) -> list[str]:
    return sorted({t["milestone"] for t in board["tasks"]} | set(MILESTONES), key=ms_index)
TASK_FIELDS = ["title", "description", "acceptance", "priority", "depends_on", "owner", "type", "scenario", "milestone",
               "skip_qa", "needs_approval"]
ROLE_FOR_TYPE = {"code": "project/roles/coder.md", "asset": "project/roles/qa_assets.md",
                 "qa": "project/roles/qa_assets.md", "design": "project/roles/quarterback.md"}
# Agent labels, models and accounts come from config.json ("label", "model", "account" per agent).
# Positions are roles (quarterback, qa_lead, coder_1...); the model under each is swappable.
# ROLES maps the two appointed positions to agent ids (legacy default: claude/codex).
# Agents sharing an account (e.g. QA lead and coder_2 on one OpenAI plan) share its usage limit.
AGENT_NAMES = {name: a.get("label", name) for name, a in CONFIG["agents"].items()}
ROLES = CONFIG.get("roles", {})
QB = ROLES.get("quarterback", "quarterback" if "quarterback" in CONFIG["agents"] else "claude")
QA = ROLES.get("qa", "qa_lead" if "qa_lead" in CONFIG["agents"] else "codex")


def resolve_owner(owner: str) -> str:
    """Board owner tags are positions, not agents: legacy tags name the old agent ids, so map
    them onto the appointed agents (a no-op when the tag already names a configured agent)."""
    if owner in CONFIG["agents"]:
        return owner
    return {"claude": QB, "codex": QA}.get(owner, owner)
# Code tasks are owned by "coder": each lane starts with its own free model and attempts alternate between them,
# so a task one model keeps failing gets a fresh pair of eyes. An explicit owner naming one of the coders starts with it.
CODER_OWNERS = {"coder", *CONFIG.get("coders", []), *CONFIG.get("coders_alt", [])}


def coders() -> list[str]:
    return list(CONFIG.get("coders") or [])


def resolve_worker(task: dict, lane: str, attempt: int) -> str:
    owner = resolve_owner(task["owner"])
    if owner not in CODER_OWNERS:
        return owner
    pool = coders()
    benched = set(CONFIG.get("disabled_agents") or [])
    avail = [c for c in pool if c not in benched]
    if not avail:
        try:
            event(f"WARNING every coder is benched; ignoring the bench for this task")
        except Exception:  # noqa: BLE001
            pass
        avail = list(pool)
    pool = avail
    first = owner if owner in pool else pool[lane_index(lane) % len(pool)]
    i = pool.index(first)
    return pool[(i + attempt - 1) % len(pool)]
ROLE_LABEL = {"code": "the coder", "asset": "the asset producer", "qa": "the QA engineer",
              "design": "the quarterback (design task)"}

_state = {"now": "starting", "task": None}


class StopRequested(Exception):
    pass


class UsageLimitStop(StopRequested):
    """Raised when a subscription hits its usage limit and config says to stop rather than wait."""


# ----------------------------------------------------------------------------- utilities

def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rel(p: Path) -> str:
    """Path as agents should see it: relative to ROOT in lane A, absolute in lane B (agents run elsewhere)."""
    if cur_root() != ROOT:
        return p.resolve().as_posix()
    return p.relative_to(ROOT).as_posix()


def event(msg: str) -> None:
    line = f"{now()}  {msg}"
    print(line, flush=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(kind: str, title: str, message: str, email: bool = False, priority: str = "default") -> None:
    """Tell the owner something that needs them: push via ntfy.sh (phone app) and, for important things, email
    (ntfy forwards it). At most one alert per kind per `min_minutes_between`. Never blocks or raises."""
    cfg = CONFIG.get("notify") or {}
    topic = cfg.get("ntfy_topic")
    if not topic:
        return
    sent = _state.setdefault("notified", {})
    if time.time() - sent.get(kind, 0) < 60 * cfg.get("min_minutes_between", 60):
        return
    sent[kind] = time.time()
    headers = {"Title": title.encode("ascii", "replace").decode(), "Priority": priority, "Tags": "skull"}
    if email and cfg.get("email"):
        headers["Email"] = cfg["email"]

    def send() -> None:
        try:
            req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                                         headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:  # noqa: BLE001
            with EVENTS_PATH.open("a", encoding="utf-8") as f:
                f.write(f"{now()}  NOTIFY failed ({kind}): {e}\n")
    threading.Thread(target=send, daemon=True).start()


def set_now(activity: str, board: dict | None = None) -> None:
    _state["now" if cur_lane() == "A" else f"now_{cur_lane().lower()}"] = activity
    if board is not None:
        write_status(board)


def check_stop() -> None:
    if STOP_FILE.exists():
        raise StopRequested()


def sleep_minutes(minutes: float, board: dict, why: str) -> None:
    until = dt.datetime.now() + dt.timedelta(minutes=minutes)
    set_now(f"{why} - sleeping until {until:%H:%M}", board)
    event(f"SLEEP {minutes:.0f} min: {why}")
    while dt.datetime.now() < until:
        check_stop()
        time.sleep(20)


def start_godot_watchdog(max_minutes: int = 15) -> None:
    """Kill automation Godot processes (headless/screenshot/quit runs) that hang, e.g. when an agent forgets
    the quit flag and then waits on them forever. Plain `godot --path game` (a human playing) is left alone."""
    if os.name != "nt":
        return
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'Godot%'\" | "
          "Select-Object ProcessId,CommandLine,@{n='Age';e={((Get-Date)-$_.CreationDate).TotalMinutes}} | "
          "ConvertTo-Json -Compress")

    def watch() -> None:
        while True:
            time.sleep(60)
            try:
                out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                                     text=True, timeout=60).stdout.strip()
                procs = json.loads(out) if out else []
                for p in procs if isinstance(procs, list) else [procs]:
                    cmd = p.get("CommandLine") or ""
                    automated = any(f in cmd for f in ("--headless", "--screenshot", "--quit"))
                    # balance-bot simulations legitimately run long (many 20-night games); give them more room
                    limit = CONFIG.get("godot_watchdog_balance_minutes", 45) if "balance" in cmd else max_minutes
                    if automated and (p.get("Age") or 0) > limit:
                        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p["ProcessId"])], capture_output=True)
                        event(f"WATCHDOG killed Godot running {p['Age']:.0f} min: {cmd[-120:]}")
            except Exception:
                pass

    import threading
    threading.Thread(target=watch, daemon=True).start()


def prevent_sleep() -> None:
    if os.name == "nt":
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def read_json(path: Path):
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[1] if "\n" in text else text
        return json.loads(text)
    except (OSError, ValueError):
        return None


def _kill_tree(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def run_proc(args: list[str], timeout_s: float, log_path: Path | None = None,
             watch_rate_limit: bool = False) -> tuple[int, str, bool]:
    """Run a process in ROOT; kill the whole tree on timeout. Returns (rc, output, timed_out).

    With `watch_rate_limit` (OpenCode agents only), output is read live and the process is killed early once it matches
    `abort_output_re` (config) `abort_after_matches` times: OpenCode retries a rate-limited free model forever without
    exiting, which used to burn a full timeout. The pattern must match OpenCode's own error-log line format, so an agent
    that prints a file or diff containing the pattern text (e.g. this config) doesn't trip it.
    """
    exe = shutil.which(args[0]) or args[0]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1", GEMINI_CLI_TRUST_WORKSPACE="true")
    proc = subprocess.Popen([exe] + args[1:], cwd=cur_root(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env)
    abort_re = re.compile(CONFIG["abort_output_re"]) if watch_rate_limit and CONFIG.get("abort_output_re") else None
    abort_after = int(CONFIG.get("abort_after_matches", 3))
    chunks: list[bytes] = []
    hits = {"n": 0}
    live_path = log_path.with_name(log_path.stem + ".live.log") if log_path else None
    live_f = None
    if live_path:
        try:
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_f = live_path.open("w", encoding="utf-8", errors="replace")
            live_f.write(f"$ {' '.join(args)}\n(running)\n\n")
            live_f.flush()
        except Exception:  # noqa: BLE001 - live logs must never break an agent call
            try:
                if live_f:
                    live_f.close()
            except Exception:  # noqa: BLE001
                pass
            live_f = None

    def reader() -> None:
        for line in iter(proc.stdout.readline, b""):
            chunks.append(line)
            if live_f is not None:
                try:
                    live_f.write(ANSI_RE.sub("", line.decode("utf-8", errors="replace")))
                    live_f.flush()
                except Exception:  # noqa: BLE001
                    pass
            if abort_re and abort_re.search(line.decode("utf-8", errors="replace")):
                hits["n"] += 1
                if hits["n"] == abort_after:
                    _kill_tree(proc)
        proc.stdout.close()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        proc.wait()
    t.join(timeout=30)
    out = ANSI_RE.sub("", b"".join(chunks).decode("utf-8", errors="replace"))
    if hits["n"] >= abort_after:
        out += f"\n[orchestrator] killed early: output matched the rate-limit pattern {hits['n']} times (usage limit)\n"
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f"$ {' '.join(args)}\n(rc={proc.returncode}, timed_out={timed_out})\n\n{out}", encoding="utf-8")
    if live_f is not None:
        try:
            live_f.close()
        except Exception:  # noqa: BLE001
            pass
    if live_path:
        try:
            live_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    return proc.returncode, out, timed_out


def git(*args: str, check: bool = True) -> str:
    with git_lock():
        r = subprocess.run(["git", *args], cwd=cur_root(), capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def git_head() -> str:
    return git("rev-parse", "HEAD")


def git_commit(message: str, body: str = "", paths: list[str] | None = None) -> bool:
    """Commit everything (or only `paths`) in the current root."""
    with git_lock():
        if paths:
            git("add", "--", *paths, check=False)
            if not git("diff", "--cached", "--name-only", "--", *paths):
                return False
        else:
            git("add", "-A")
            if not git("status", "--porcelain"):
                return False
        args = ["commit", "-q", "-m", message]
        if body:
            args += ["-m", body]
        if paths:
            args += ["--", *paths]
        git(*args)
        return True


def git_revert_to(sha: str) -> None:
    """Hard-reset to sha. OneDrive or a lingering process can briefly lock folders, so retry the clean."""
    for i in range(6):
        with git_lock():
            r = subprocess.run(["git", "reset", "-q", "--hard", sha], cwd=cur_root(), capture_output=True, text=True)
            c = subprocess.run(["git", "clean", "-q", "-fd"], cwd=cur_root(), capture_output=True, text=True)
        if r.returncode == 0 and c.returncode == 0:
            return
        time.sleep(10)
    event(f"WARNING git revert incomplete (locked files?): {(r.stderr + c.stderr).strip()[:300]}")


def save_patch(checkpoint: str, path: Path) -> None:
    """Keep the work of a failed task as a patch (incl. new files) so a later attempt can reuse it.

    Also copies every changed/untracked file into a `<patch name>_files/` folder. `git add` can fail on a single
    locked or over-long path and then stage nothing, which leaves the patch empty; the plain file copy still works.
    """
    root = cur_root()
    with git_lock():
        r = subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    if r.returncode != 0:
        event(f"WARNING git add failed while saving work ({r.stderr.strip()[:200]}); relying on the file copy")
    patch = git("diff", "--cached", "--binary", checkpoint, "--", ".", ":!project/board.json", check=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(patch + "\n", encoding="utf-8", newline="\n")  # CRLF on Windows breaks `git apply`
    copy_dir = path.with_name(path.stem + "_files")
    with git_lock():
        changed = subprocess.run(["git", "status", "--porcelain=v1", "-uall", "-z"], cwd=root,
                                 capture_output=True).stdout
    copied = 0
    for entry in changed.decode("utf-8", "replace").split("\0"):
        rel_path = entry[3:].strip() if len(entry) > 3 else ""
        src = root / rel_path
        if not rel_path or rel_path == "project/board.json" or not src.is_file():
            continue
        dst = copy_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    if copied:
        event(f"Saved {copied} changed file(s) to {rel(copy_dir)} (and patch {path.name}, {len(patch)} bytes)")


def diff_summary(checkpoint: str) -> str:
    stat = git("diff", "--stat", checkpoint, check=False)
    new_files = git("ls-files", "--others", "--exclude-standard", check=False)
    text = (stat or "(no changes to tracked files)")[-4000:]
    if new_files:
        lines = new_files.splitlines()
        text += f"\n\nNew untracked files ({len(lines)}):\n" + "\n".join(lines[:80])
    return text


# ----------------------------------------------------------------------------- board

def load_board() -> dict:
    return json.loads(BOARD_PATH.read_text(encoding="utf-8"))


def save_board(board: dict) -> None:
    with BOARD_LOCK:
        for _ in range(5):
            try:
                text = json.dumps(board, indent=2)
                break
            except RuntimeError:  # the other lane changed a list mid-dump; try again
                time.sleep(0.2)
        tmp = BOARD_PATH.with_suffix(".tmp")
        for i in range(10):  # OneDrive / an editor can hold board.json for a moment
            try:
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, BOARD_PATH)
                break
            except PermissionError:
                time.sleep(1 + i)
        else:
            BOARD_PATH.write_text(text, encoding="utf-8")
        write_status(board)


def task_by_id(board: dict, tid: str) -> dict | None:
    return next((t for t in board["tasks"] if t["id"] == tid), None)


def pickable(board: dict) -> list[dict]:
    finished = {t["id"] for t in board["tasks"] if t["status"] in ("done", "dropped")}
    ready = [t for t in board["tasks"] if t["status"] == "ready" and all(d in finished for d in t["depends_on"])]
    return sorted(ready, key=lambda t: (ms_index(t["milestone"]),
                                        t.get("priority", 3), t["id"]))


def add_task(board: dict, spec: dict, source: str) -> dict | None:
    with BOARD_LOCK:
        return _add_task(board, spec, source)


def _add_task(board: dict, spec: dict, source: str) -> dict | None:
    if not isinstance(spec, dict) or not spec.get("title"):
        return None
    tid = f"T-{board['next_id']:03d}"
    board["next_id"] += 1
    task = {
        "id": tid, "title": str(spec["title"])[:120], "milestone": spec.get("milestone", "M5"),
        "type": spec.get("type", "code"), "owner": spec.get("owner", "coder"),
        "priority": int(spec.get("priority", 3)), "depends_on": list(spec.get("depends_on", [])),
        "description": spec.get("description", ""), "acceptance": list(spec.get("acceptance", [])),
        "scenario": spec.get("scenario", "default"),
        "skip_qa": bool(spec.get("skip_qa", False)),
        "status": spec.get("status", "backlog") if spec.get("status") in ("backlog", "ready") else "backlog",
        "attempts": 0, "history": [], "source": source,
    }
    if task["owner"] not in CONFIG["agents"] and task["owner"] not in CODER_OWNERS:
        task["owner"] = "coder" if task["type"] == "code" else resolve_owner("codex") if task["type"] in ("asset", "qa") else resolve_owner("claude")
    board["tasks"].append(task)
    event(f"NEW TASK {tid} ({task['owner']}, {task['milestone']}) from {source}: {task['title']}")
    return task


def ensure_brief(task: dict) -> Path:
    path = TASKS_DIR / f"{task['id']}.md"
    if not path.exists():
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        crit = "\n".join(f"- {a}" for a in task["acceptance"])
        path.write_text(
            f"# {task['id']}: {task['title']}\n\nMilestone: {task['milestone']} | Type: {task['type']} | "
            f"Owner: {task['owner']} | Scenario: `{task['scenario']}`\n\n## Goal\n\n{task['description']}\n\n"
            f"## Acceptance criteria\n\n{crit}\n\n## Log\n", encoding="utf-8")
    return path


def append_task_log(task: dict, text: str) -> None:
    path = ensure_brief(task)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n### {now()}\n{text}\n")


# ----------------------------------------------------------------------------- status page

def lanes_status() -> str:
    rows = []
    for ln in WORKTREE_LANES:
        k = ln.lower()
        cur = _state.get(f"task_{k}")
        rows.append(f"**Lane {ln}:** {cur or 'idle'}{' - ' + _state[f'now_{k}'] if cur and _state.get(f'now_{k}') else ''}")
    if planner_busy():
        rows.append(f"**Planner:** {_state.get('now_p') or 'planning'} ({_planner.get('reason') or ''})")
    return "\n".join(rows) or "**Lane B:** off"


def write_status(board: dict) -> None:
    counts = {}
    for t in board["tasks"]:
        counts.setdefault(t["milestone"], {}).setdefault(t["status"], 0)
        counts[t["milestone"]][t["status"]] += 1
    rows = []
    for m in all_milestones(board):
        c = counts.get(m, {})
        total = sum(c.values())
        done = c.get("done", 0) + c.get("dropped", 0)
        rows.append(f"| {m} | {done}/{total} | {c.get('ready', 0)} | {c.get('in_progress', 0)} | "
                    f"{c.get('blocked', 0)} | {c.get('backlog', 0)} |")
    try:
        recent = EVENTS_PATH.read_text(encoding="utf-8").splitlines()[-20:]
    except OSError:
        recent = []
    notes = PM_NOTES.read_text(encoding="utf-8") if PM_NOTES.exists() else "(none yet)"
    cur = _state["task"]
    text = f"""# {{GAME_NAME}}: Live Status

Updated: {now()}

**Now:** {_state['now']}
**Current task:** {cur or '-'}
{lanes_status()}

| Milestone | Done | Ready | In progress | Blocked | Backlog |
|---|---|---|---|---|---|
{chr(10).join(rows)}

## Recent events
```
{chr(10).join(recent)}
```

## Notes from Claude (PM)

{notes}

---
To stop: create an empty file `project/STOP` (it stops after the current step) or close the orchestrator window.
To resume: delete `project/STOP` and run `start.bat`.
To play the latest build: run `play.bat`.
"""
    try:
        STATUS_PATH.write_text(text, encoding="utf-8")
    except OSError:
        pass  # the status page is cosmetic; a OneDrive lock must never stop the team


# ----------------------------------------------------------------------------- agents

# OpenCode's free tier is rate-limited per model, so each free model is its own "account"; paid Muse is the Meta API.
ACCOUNT = {name: a.get("account", name) for name, a in CONFIG["agents"].items()}


def parse_reset_minutes(text: str) -> float | None:
    """Best-effort parse of 'resets in 1h15m34s' / 'try again in 2 hours 5 minutes' / 'resets 3am' / '|<epoch>'."""
    t = text.lower()
    m = re.search(r"(?:resets?|again|retry)\s+(?:in|after)\s+((?:\d+\s*(?:hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\s*,?\s*(?:and\s*)?)+)", t)
    if m:
        total = 0.0
        for n, unit in re.findall(r"(\d+)\s*(h|m|s)", m.group(1).replace("hour", "h").replace("min", "m").replace("sec", "s")):
            total += int(n) * {"h": 60, "m": 1, "s": 1 / 60}[unit]
        if total > 0:
            return total
    m = re.search(r"\|(\d{10})\b", text)
    if m:
        return max(1.0, (int(m.group(1)) - time.time()) / 60)
    m = re.search(r"(?:resets?|again)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)", t)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        now_ = dt.datetime.now()
        target = now_.replace(hour=h, minute=int(m.group(2) or 0), second=0, microsecond=0)
        if target <= now_:
            if now_ - target < dt.timedelta(hours=3):
                return 1.0  # the stated reset time just passed: the limit should already be lifted
            target += dt.timedelta(days=1)
        return (target - now_).total_seconds() / 60
    return None


CODEX_SESSIONS = Path.home() / ".codex" / "sessions"


def codex_usage() -> dict | None:
    """Latest OpenAI rate-limit snapshot that the Codex CLI writes into its session logs
    ({"primary": {"used_percent", "window_minutes", "resets_at"}, "secondary": {...}})."""
    try:
        days = [dt.date.today() - dt.timedelta(days=i) for i in (0, 1)]
        recent = [f for d in days for f in (CODEX_SESSIONS / f"{d:%Y}" / f"{d:%m}" / f"{d:%d}").glob("rollout-*.jsonl")]
        files = sorted(recent, key=lambda f: f.stat().st_mtime, reverse=True)[:3]
    except OSError:
        return None
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"rate_limits"' not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            stack = [obj]
            while stack:  # the snapshot sits a few levels deep; find it without depending on the exact schema
                cur = stack.pop()
                if isinstance(cur, dict):
                    rl = cur.get("rate_limits")
                    if isinstance(rl, dict) and "primary" in rl:
                        return rl
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
    return None


def openai_under_thresholds() -> bool:
    th = CONFIG.get("handoff_at_percent") or {}
    rl = codex_usage() or {}
    for key in ("primary", "secondary"):
        w = rl.get(key) or {}
        resets = w.get("resets_at")
        live = resets and dt.datetime.fromtimestamp(int(resets)) > dt.datetime.now()
        if live and th.get(key) is not None and float(w.get("used_percent", 0)) >= float(th[key]):
            return False
    return True


PROBE_AGENT: dict[str, str] = {}
for _name, _acct in ACCOUNT.items():  # the first agent listed for an account is the one probed
    PROBE_AGENT.setdefault(_acct, _name)


def start_quota_prober(every_minutes: int = 15) -> None:
    """While a subscription is marked limited, poke it every few minutes so an early reset (e.g. the owner using a
    Codex limit reset) is noticed even when fallbacks are covering and nothing is sleeping."""
    def loop() -> None:
        while True:
            time.sleep(every_minutes * 60)
            for acct, until in list(_state.get("limited_until", {}).items()):
                if until and until > dt.datetime.now() and acct in PROBE_AGENT:
                    try:
                        probe_agent(PROBE_AGENT[acct])
                    except Exception:  # noqa: BLE001
                        pass
    threading.Thread(target=loop, daemon=True, name="quota-prober").start()


def preemptive_handoff() -> None:
    """Hand OpenAI work to the fallbacks *before* the limit hits, using Codex's own usage numbers."""
    th = CONFIG.get("handoff_at_percent") or {}
    rl = codex_usage()
    if not rl or unavailable(QA):
        return
    for key in ("primary", "secondary"):
        w = rl.get(key) or {}
        used, limit_pct, resets = w.get("used_percent"), th.get(key), w.get("resets_at")
        if used is None or limit_pct is None or not resets:
            continue
        if float(used) >= float(limit_pct):
            until = dt.datetime.fromtimestamp(int(resets))
            if until > dt.datetime.now():
                _acct = ACCOUNT.get(QA, QA)
                _state.setdefault("limited_until", {})[_acct] = until
                _state.setdefault("preemptive", set()).add(_acct)
                window = "5-hour" if key == "primary" else "weekly"
                event(f"PREEMPTIVE HANDOFF {_acct} at {used:.0f}% of its {window} window (threshold {limit_pct}%); "
                      f"routing its work to fallbacks until {until:%a %H:%M}")
                notify("openai-limit", "{{GAME_NAME}}: Codex limit almost reached",
                       f"OpenAI is at {used:.0f}% of its {window} limit. Backups are covering until {until:%a %b %d %H:%M}. "
                       f"Use a Codex limit reset if you want OpenAI back sooner (the team notices within ~15 min).",
                       email=True, priority="high")
                return


def limited_until(agent: str) -> dt.datetime | None:
    until = _state.setdefault("limited_until", {}).get(ACCOUNT.get(agent, agent))
    return until if until and until > dt.datetime.now() else None


def benched(agent: str) -> bool:
    """True when the owner benched this position from the Office (live, no restart)."""
    try:
        return agent in (CONFIG.get("disabled_agents") or [])
    except Exception:  # noqa: BLE001
        return False


def unavailable(agent: str) -> bool:
    """A benched agent is skipped like a limited one, so the existing fallback chain takes over."""
    return benched(agent) or bool(limited_until(agent))


def persist_disabled_agents() -> None:
    """Persist CONFIG["disabled_agents"] to config.json with the Office's atomic-write + backup rules."""
    cfg_path = Path(__file__).parent / "config.json"
    try:
        raw = cfg_path.read_text(encoding="utf-8")
        cfg = json.loads(raw)
    except (OSError, ValueError):
        return
    cfg["disabled_agents"] = list(CONFIG.get("disabled_agents") or [])
    text = json.dumps(cfg, indent=2)
    try:
        backup_dir = Path(__file__).parent / "config.backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (backup_dir / f"config-{stamp}.json").write_text(raw, encoding="utf-8")
        existing = sorted(backup_dir.glob("config-*.json"), key=lambda p: p.name)
        for old in existing[:-20]:
            try:
                old.unlink()
            except OSError:
                pass
        tmp = cfg_path.with_name(cfg_path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, cfg_path)
    except OSError:
        pass


# ----------------------------------------------------------------------------- opencode spend parser
# NOTE: this copy is kept identical to template/office/stats.py:parse_opencode_stats
# (the orchestrator must stay a single file). Both copies parse `opencode stats --models` output.

_SPEND_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SPEND_BOX_RE = re.compile(r"[│┃║─━┌┐└┘├┤┬┴┼╭╮╯╰]")


def _spend_num_tokens(s: str) -> int | None:
    s = (s or "").strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([KkMm])?$", s)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    suf = (m.group(2) or "").upper()
    if suf == "K":
        v *= 1000
    elif suf == "M":
        v *= 1000000
    return int(round(v))


def _spend_money(s: str) -> float | None:
    m = re.search(r"\$\s*([\d,]+\.\d+|[\d,]+)", s or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_opencode_stats(text) -> dict:
    """Parse `opencode stats --models` box-drawing output.

    Returns {"total": float|None, "models": {name: {messages, input_tokens,
    output_tokens, cost}}}. Garbage input gives {"total": None, "models": {}}.
    """
    try:
        if not isinstance(text, str) or not text:
            return {"total": None, "models": {}}
        clean = _SPEND_ANSI_RE.sub("", text)
        clean = _SPEND_BOX_RE.sub(" ", clean)
        lines = [ln.strip() for ln in clean.splitlines()]
        lines = [ln for ln in lines if ln]
        total = None
        for ln in lines:
            if "total cost" in ln.lower():
                total = _spend_money(ln)
                break
        models: dict = {}
        cur: str | None = None
        buf: dict = {}
        keywords = ("messages", "input tokens", "output tokens", "cost")

        def flush():
            if cur and buf:
                models[cur] = dict(buf)

        for ln in lines:
            low = ln.lower()
            if "total cost" in low:
                continue
            if any(k in low for k in keywords):
                if cur is None:
                    continue
                if "messages" in low:
                    m = re.search(r"(\d[\d,]*)\s*$", ln)
                    if m:
                        try:
                            buf["messages"] = int(m.group(1).replace(",", ""))
                        except ValueError:
                            pass
                elif "input tokens" in low:
                    m = re.search(r"([\d.,]+\s*[KkMm]?)\s*$", ln)
                    if m:
                        v = _spend_num_tokens(m.group(1))
                        if v is not None:
                            buf["input_tokens"] = v
                elif "output tokens" in low:
                    m = re.search(r"([\d.,]+\s*[KkMm]?)\s*$", ln)
                    if m:
                        v = _spend_num_tokens(m.group(1))
                        if v is not None:
                            buf["output_tokens"] = v
                elif "cost" in low:
                    v = _spend_money(ln)
                    if v is not None:
                        buf["cost"] = v
                continue
            stripped = ln.strip()
            if "/" in stripped and " " not in stripped and len(stripped) < 120:
                if re.match(r"^[\w.\-/:@+]+$", stripped):
                    flush()
                    cur = stripped
                    buf = {}
                    continue
        flush()
        models = {k: v for k, v in models.items() if v}
        return {"total": total, "models": models}
    except Exception:
        return {"total": None, "models": {}}


def opencode_stats_today():
    """Today's OpenCode spend (`opencode stats --days 1 --models`, no --project: money is
    spent across all projects). Cached for 5 min. Returns the parsed dict or None."""
    now_t = time.time()
    cached = _state.get("spend_cap_cache")
    if cached and now_t - cached.get("t", 0) < 5 * 60:
        return cached.get("data")
    exe = shutil.which("opencode")
    data = None
    if exe:
        try:
            r = subprocess.run([exe, "stats", "--days", "1", "--models"], cwd=ROOT,
                               capture_output=True, text=True, timeout=60, encoding="utf-8",
                               errors="replace")
            if r.returncode == 0:
                data = parse_opencode_stats(r.stdout)
            else:
                data = None
        except Exception:  # noqa: BLE001
            data = None
    _state["spend_cap_cache"] = {"t": now_t, "data": data}
    return data


def agent_model(agent: str) -> str:
    """The agent's model id: its "model" field, else the value after -m/--model in its cmd."""
    a = (CONFIG.get("agents") or {}).get(agent) or {}
    if a.get("model"):
        return a["model"]
    cmd = a.get("cmd") or []
    for i, part in enumerate(cmd[:-1]):
        if part in ("-m", "--model"):
            return cmd[i + 1]
    return ""


def spend_capped_agents() -> list[str]:
    cfg = CONFIG.get("spend_cap") or {}
    agents = cfg.get("agents") or CONFIG.get("paid_agents") or []
    return [a for a in agents if a in CONFIG.get("agents", {})]


def check_spend_cap(agent: str) -> None:
    """Park pay-per-use accounts until local midnight when today's spend hits the cap."""
    cfg = CONFIG.get("spend_cap") or {}
    try:
        cap = float(cfg.get("daily_usd") or 0)
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0:
        return
    capped = spend_capped_agents()
    if agent not in capped:
        return
    data = opencode_stats_today()
    if not data or data.get("total") is None and not data.get("models"):
        last = _state.get("spend_cap_fail_logged", 0)
        if time.time() - last > 3600:
            _state["spend_cap_fail_logged"] = time.time()
            event(f"SPEND CAP check failed: could not read opencode stats")
        return
    agents_cfg = CONFIG.get("agents") or {}
    models = {agent_model(a) for a in capped} - {""}
    parsed_models = data.get("models") or {}
    total = 0.0
    for mname, mdata in parsed_models.items():
        if mname in models:
            try:
                total += float((mdata or {}).get("cost") or 0)
            except (TypeError, ValueError):
                pass
    if total < cap:
        return
    midnight = (dt.datetime.now() + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for a in capped:
        acct = ACCOUNT.get(a, a)
        cur = _state.setdefault("limited_until", {}).get(acct)
        if not (cur and cur > dt.datetime.now()):
            _state.setdefault("limited_until", {})[acct] = midnight
        _state.setdefault("spend_parked", {})[acct] = midnight
    today = dt.date.today().isoformat()
    if _state.get("spend_cap_day") != today:
        _state["spend_cap_day"] = today
        event(f"SPEND CAP {agent} ${total:.2f} >= ${cap:.2f} today - parked until 00:00")
        notify(f"spend-cap-{today}", "{{GAME_NAME}}: spend cap reached",
               f"Today's OpenCode spend is ${total:.2f} (cap ${cap:.2f}). "
               f"Pay-per-use agents are parked until midnight.", email=True)


def approval_gate_cfg() -> dict:
    cfg = CONFIG.get("approval_gate") or {}
    return {"enabled": bool(cfg.get("enabled", False)),
            "types": list(cfg.get("types") or []),
            "workers": list(cfg.get("workers") or []),
            "timeout_minutes": float(cfg.get("timeout_minutes") or 0)}


def task_needs_approval(task: dict, worker: str) -> bool:
    """A task needs approval when the gate is enabled AND (type/worker/flag match), or when
    its per-task needs_approval flag is set explicitly (works even with the gate off)."""
    if task.get("needs_approval") is True:
        return True
    gate = approval_gate_cfg()
    if not gate["enabled"]:
        return False
    if task.get("type") in gate["types"]:
        return True
    if worker in gate["workers"]:
        return True
    return False


def await_approval(task: dict, n: int, lane: str, worker: str = "", summary: str = "",
                   review_summary: str = "", qa_verdict: str = "", checks_summary: str = "",
                   patch: str = "", screenshot: str = "",
                   sleep=time.sleep, clock=time.time) -> tuple[str, str]:
    """Wait for the owner's approval decision. Returns (decision, feedback).

    The request file project/approvals/<task>.json must already exist (written by run_task).
    Polls every 10 s for project/approvals/<task>.decision.json. check_stop() runs on every
    poll so STOP still works. Afterwards both files move to project/approvals/done/.
    """
    tid = task.get("id", "")
    gate = approval_gate_cfg()
    try:
        timeout_s = float(gate.get("timeout_minutes") or 0) * 60
    except (TypeError, ValueError):
        timeout_s = 0
    req_path = PROJECT / "approvals" / f"{tid}.json"
    dec_path = PROJECT / "approvals" / f"{tid}.decision.json"
    done_dir = PROJECT / "approvals" / "done"
    try:
        t0 = clock()
    except Exception:  # noqa: BLE001
        t0 = time.time()
    while True:
        check_stop()
        raw = None
        try:
            if dec_path.is_file():
                raw = dec_path.read_text(encoding="utf-8")
        except OSError:
            raw = None
        if raw:
            try:
                dec = json.loads(raw)
            except ValueError:
                dec = None
            if isinstance(dec, dict) and dec.get("decision") in ("approve", "revise"):
                decision = dec["decision"]
                feedback = str(dec.get("feedback") or "")
                try:
                    done_dir.mkdir(parents=True, exist_ok=True)
                    for src in (req_path, dec_path):
                        try:
                            if src.is_file():
                                (done_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                                src.unlink(missing_ok=True)
                        except OSError:
                            pass
                except Exception:  # noqa: BLE001
                    pass
                event(f"APPROVAL {tid} {decision}")
                return decision, feedback
        if timeout_s > 0:
            try:
                elapsed = clock() - t0
            except Exception:  # noqa: BLE001
                elapsed = 0
            if elapsed >= timeout_s:
                try:
                    done_dir.mkdir(parents=True, exist_ok=True)
                    for src in (req_path, dec_path):
                        try:
                            if src.is_file():
                                (done_dir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                                src.unlink(missing_ok=True)
                        except OSError:
                            pass
                except Exception:  # noqa: BLE001
                    pass
                event(f"APPROVAL TIMEOUT {tid} - auto-approved")
                return "approve", ""
        sleep(10)


def fallback_for(agent: str, step_kind: str, avoid: str | None = None) -> list[str]:
    """Fallback agents for a step, in order of preference (free/subscriptions first, paid API last).
    `avoid` (e.g. the model that wrote the code being QA'd) moves behind the other free agents but stays ahead of
    paid ones: the owner allows the paid API only once the free tier is exhausted."""
    fb = CONFIG.get("fallback", {})
    chain = fb.get(f"{agent}:{step_kind}") or fb.get(f"{agent}:*") or []
    chain = [chain] if isinstance(chain, str) else list(chain)
    if avoid in chain:
        paid = set(CONFIG.get("paid_agents", []))
        rest = [a for a in chain if a != avoid]
        cut = next((i for i, a in enumerate(rest) if a in paid), len(rest))
        chain = rest[:cut] + [avoid] + rest[cut:]
    return chain

def probe_agent(agent: str) -> None:
    """Send a tiny prompt to a rate-limited agent. If it answers, the limit was lifted early
    (e.g. the owner used a Codex limit reset), so clear it and resume at once."""
    if benched(agent):
        return  # a benched agent is never probed
    parked = _state.get("spend_parked", {}).get(ACCOUNT.get(agent, agent))
    if parked and parked > dt.datetime.now():
        return  # parked by the spend cap: answering a probe must not resume paid work before midnight
    cmd = [("Reply with exactly: OK" if part == "{prompt}" else part)
           for part in CONFIG["agents"][agent]["cmd"] if part != "{images}"]
    rc, out, timed_out = run_proc(cmd, 300, watch_rate_limit=CONFIG["agents"][agent].get("watch_rate_limit", False))
    acct = ACCOUNT.get(agent, agent)
    if rc == 0 and not timed_out and "OK" in out[-500:] and not RATE_LIMIT_RE.search(out[-1500:]):
        if acct in _state.get("preemptive", set()):
            if not openai_under_thresholds():
                return  # still close to the limit; keep the early handoff
            _state["preemptive"].discard(acct)
            event(f"QUOTA RESTORED {acct}: usage is back under the handoff thresholds (limit reset?)")
        else:
            event(f"QUOTA RESTORED {acct}: {agent} answered a probe before the stated reset time")
        _state["limited_until"].pop(acct, None)


def call_agent(agent: str, prompt_file: Path, out_file: Path, log_name: str, board: dict,
               images: list[Path] | None = None, step_kind: str = "*", avoid: str | None = None) -> dict | None:
    """Run an agent on a prompt file and return its output JSON (or None on repeated failure).

    Quota handling: when a subscription reports its usage limit, remember when it resets and route
    work to the configured fallback agent (on another subscription) until then. Sleep only when
    neither the agent nor its fallback is available.
    """
    infra_failures = 0
    while True:
        check_stop()
        try:
            preemptive_handoff()
        except Exception:  # noqa: BLE001 - usage peeking must never break a task
            pass
        try:
            check_spend_cap(agent)
            for _fb in fallback_for(agent, step_kind, avoid):
                check_spend_cap(_fb)
        except Exception:  # noqa: BLE001 - spend checks must never break a task
            pass
        use = agent
        if unavailable(agent):
            chain = fallback_for(agent, step_kind, avoid)
            free = [f for f in chain if not unavailable(f)]
            if free:
                use = free[0]
            else:
                uls = [limited_until(a) for a in [agent] + chain]
                uls = [u for u in uls if u]
                if not uls:
                    sleep_minutes(CONFIG.get("probe_every_minutes", 15), board,
                                  f"waiting for a benched agent to return ({log_name})")
                    continue
                until = min(uls)
                if CONFIG.get("stop_on_usage_limit"):
                    raise UsageLimitStop(agent)
                remaining = (until - dt.datetime.now()).total_seconds() / 60 + 1
                if remaining > 30:
                    notify("stalled", "{{GAME_NAME}}: team stalled on usage limits",
                           f"No agent can cover the next {step_kind} step until ~{until:%a %H:%M} "
                           f"({', '.join(sorted(_state.get('limited_until', {})))} limited). "
                           f"A Codex limit reset would get it moving again.", email=True, priority="high")
                sleep_minutes(min(remaining, CONFIG.get("probe_every_minutes", 15)), board,
                              f"waiting for {ACCOUNT.get(agent, agent)} usage limit to reset ({log_name})")
                for a in [agent] + chain:
                    if limited_until(a):
                        probe_agent(a)
                continue
        if use != agent and _state.get("last_fallback") != (agent, use):
            lu = limited_until(agent)
            if lu:
                when = f"{lu:%H:%M}" if lu.date() == dt.date.today() else f"{lu:%a %b %d %H:%M}"
            else:
                when = "benched"
            event(f"FALLBACK {agent} is limited until {when}; {use} handles {step_kind} steps")
        _state["last_fallback"] = (agent, use) if use != agent else None
        if out_file.exists():
            out_file.unlink()
        prompt = (f"Read the file {rel(prompt_file)} and carry out the instructions in it exactly. "
                  f"Finish by writing the JSON result file it names.")
        cmd = []
        for part in CONFIG["agents"][use]["cmd"]:
            if part == "{prompt}":
                cmd.append(prompt)
            elif part == "{images}":
                cmd += [f"--image={p}" for p in (images or []) if p.exists()]
            else:
                cmd.append(part)
        ov = CONFIG.get("model_override") or {}
        if ov.get("agent") == use and "-m" in cmd and now() < ov.get("until", ""):
            cmd[cmd.index("-m") + 1] = ov["model"]
        set_now(f"{AGENT_NAMES.get(use, use)} working on {log_name}", board)
        log_path = out_file.parent / f"{log_name}.{use}.log"
        started = time.time()
        rc, out, timed_out = run_proc(cmd, CONFIG["agent_timeout_minutes"] * 60, log_path,
                                      watch_rate_limit=CONFIG["agents"][use].get("watch_rate_limit", False))
        result = read_json(out_file)
        if isinstance(result, dict):
            return result
        tail = out[-3000:]
        # An agent that dies within seconds almost never did real work. Treat it as an unrecognised
        # usage limit (wait + probe) rather than burning task attempts on it.
        quick_fail = rc != 0 and not timed_out and time.time() - started < 45
        if rc != 0 and not timed_out and MODEL_GONE_RE.search(tail):
            until = dt.datetime.now() + dt.timedelta(minutes=MODEL_GONE_MINUTES)
            _state.setdefault("limited_until", {})[ACCOUNT.get(use, use)] = until
            event(f"MODEL GONE {use}: the provider no longer serves this model id; parked until ~{until:%a %H:%M} "
                  f"(owner: update its model in orchestrator/config.json). Evidence: {log_path.name}")
            notify("model-gone-" + use, f"{{GAME_NAME}}: {use} model id not found",
                   f"OpenCode says the model for '{use}' no longer exists. It is parked for 12h; fallbacks cover. "
                   f"Update orchestrator/config.json if you want it back.", email=True)
            continue
        if rc != 0 and not timed_out and PROVIDER_DOWN_RE.search(tail) and not RATE_LIMIT_RE.search(tail):
            until = dt.datetime.now() + dt.timedelta(minutes=30)
            _state.setdefault("limited_until", {})[ACCOUNT.get(use, use)] = until
            event(f"PROVIDER DOWN {use} (rc={rc} after {time.time() - started:.0f}s, server error): routing around it "
                  f"until ~{until:%H:%M}. Evidence: {log_path.name}")
            continue
        if not timed_out and (RATE_LIMIT_RE.search(tail) or quick_fail):
            if quick_fail and not RATE_LIMIT_RE.search(tail):
                event(f"QUICK FAIL {use} (rc={rc} in {time.time() - started:.0f}s): treating as a possible usage "
                      f"limit. Output: {tail.strip()[-160:]!r}")
            minutes = parse_reset_minutes(tail)
            guessed = minutes is None
            if minutes is None:
                minutes = 20 if quick_fail and not RATE_LIMIT_RE.search(tail) else CONFIG.get("default_limit_minutes", 60)
            minutes += 2
            until = dt.datetime.now() + dt.timedelta(minutes=minutes)
            _state.setdefault("limited_until", {})[ACCOUNT.get(use, use)] = until
            if ACCOUNT.get(use) == "openai":
                notify("openai-limit", "{{GAME_NAME}}: Codex limit reached",
                       f"OpenAI hit its usage limit (until ~{until:%a %H:%M}). Backups are covering. Use a Codex limit "
                       f"reset if you want OpenAI back sooner (the team notices within ~15 min).",
                       email=True, priority="high")
            event(f"USAGE LIMIT {use} ({ACCOUNT.get(use, use)}): limited until ~"
                  f"{until:%H:%M}{'' if until.date() == dt.date.today() else until.strftime(' on %a %b %d')}"
                  f"{' (reset time not stated; guessing)' if guessed else ''}. Evidence: {log_path.name}")
            continue
        infra_failures += 1
        event(f"AGENT FAIL {use} {log_name}: rc={rc} timed_out={timed_out} (no valid {out_file.name}); "
              f"failure {infra_failures}/2")
        if infra_failures >= 2:
            return None


def prompt_header(step: str, task: dict | None, role: str, role_file: str) -> str:
    title = f"{task['id']}: {task['title']}" if task else "project"
    return (f"# {step} step - {title}\n\nYou are {role} on the {{GAME_NAME}} team. Follow your role guide "
            f"`{role_file}` and the team protocol `project/PROTOCOL.md`.\nNo human is available: never ask "
            f"questions or wait for input. Decide, log assumptions in `project/assumptions.md`, and continue.\n"
            f"Never run git commit/reset/checkout/stash. Never edit project/board.json.\n\n")


def lane_note() -> str:
    """Lane B agents run in a separate worktree; some agents follow the absolute run-folder path back into the main
    checkout and edit files there, which blocks every later merge. Say where to work, explicitly."""
    if cur_root() == ROOT:
        return ""
    return (f"## Where to work (IMPORTANT)\n\nYour working copy is `{cur_root().as_posix()}` (a git worktree; it is your "
            f"current directory). Edit and create game files ONLY there. The main checkout `{ROOT.as_posix()}` belongs to "
            f"another agent: never edit, create or delete files under it, except writing into your run folder "
            f"(`project/runs/...`) as named below.\n\n")


def task_block(task: dict) -> str:
    crit = "\n".join(f"- {a}" for a in task["acceptance"])
    return (f"## Task\n\n- ID: {task['id']}\n- Title: {task['title']}\n- Milestone: {task['milestone']}\n"
            f"- Type: {task['type']}\n- Screenshot scenario: `{task['scenario']}` "
            f"(file `game/dev/scenarios/{task['scenario']}.gd`)\n- Brief (read it fully): `project/tasks/{task['id']}.md`\n\n"
            f"Acceptance criteria:\n{crit}\n\n")


def write_prompt(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ----------------------------------------------------------------------------- checks

def run_checks(d: Path, scenario: str, label: str) -> dict:
    godot = CONFIG["godot"]
    shot = d / f"screenshot_{label}.png"
    results = {}
    log = []

    def step(name, args, timeout, need_tests_line=False, screenshot=False):
        rc, out, to = run_proc(args, timeout)
        pattern = SCRIPT_ERROR_RE if need_tests_line else GODOT_ERROR_RE
        lines = out.splitlines()
        errors = []
        for i, ln in enumerate(lines):
            if pattern.search(ln):
                ahead = [x.strip() for x in lines[i + 1:i + 5]]
                where = next((x for x in ahead if "res://" in x), next((x for x in ahead if x.startswith("at:")), ""))
                errors.append(ln.strip() + (f"  ({where})" if where else ""))
        errors = list(dict.fromkeys(errors))  # de-duplicate repeated errors, keep order
        warnings = [e for e in errors if EXIT_LEAK_RE.search(e)]
        errors = [e for e in errors if not EXIT_LEAK_RE.search(e)]
        warnings += [ln.strip() for ln in lines if EXIT_LEAK_RE.search(ln) and ln.strip() not in warnings]
        ok = rc == 0 and not to and not errors
        if need_tests_line:
            m = re.search(r"TESTS: (\d+) passed, (\d+) failed", out)
            ok = ok and m is not None and m.group(2) == "0"
            results["tests_summary"] = m.group(0) if m else "no TESTS line (runner crashed?)"
            errors += [ln.strip() for ln in out.splitlines() if ln.startswith("FAIL") or ln.startswith("    - ")]
        if screenshot:
            ok = ok and shot.exists()
        results[name] = {"ok": ok, "rc": rc, "timed_out": to, "errors": errors[:40], "warnings": warnings[:5]}
        log.append(f"===== {name} (ok={ok}, rc={rc}, timed_out={to})\n$ {' '.join(args)}\n{out[-20000:]}\n")

    step("import", [godot, "--headless", "--path", "game", "--import"], 600)
    step("tests", [godot, "--headless", "--path", "game", "--script", "res://tests/run_tests.gd"], 600,
         need_tests_line=True)
    step("smoke", [godot, "--headless", "--path", "game", "--", "--quit-frames=300"], 180)
    step("capture", [godot, "--path", "game", "--resolution", "1280x720", "--", f"--scenario={scenario}",
                        f"--screenshot={shot}", "--frames=120"], 180, screenshot=True)
    passed = all(results[k]["ok"] for k in ("import", "tests", "smoke", "capture"))
    results["passed"] = passed
    results["screenshot"] = rel(shot) if shot.exists() else None
    (d / f"checks_{label}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (d / f"checks_{label}.log").write_text("\n".join(log), encoding="utf-8")
    return results


def checks_text(c: dict, label: str) -> str:
    lines = [f"Automatic checks ({label}): {'PASSED' if c['passed'] else 'FAILED'}"]
    for k in ("import", "tests", "smoke", "capture"):
        r = c[k]
        lines.append(f"- {k}: {'ok' if r['ok'] else 'FAIL'}" + (" (timed out)" if r["timed_out"] else ""))
        for e in r["errors"][:15]:
            lines.append(f"    {e}")
        for w in r.get("warnings", [])[:3]:
            lines.append(f"    warning (not a failure; fix if cheap): {w}")
    lines.append(f"- {c.get('tests_summary', '')}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- steps

def plan_step(board: dict, reason: str) -> dict | None:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = RUNS / "_plan" / stamp
    d.mkdir(parents=True, exist_ok=True)
    table = "\n".join(
        f"| {t['id']} | {t['milestone']} | {t['status']} | {t['owner']} | {t['type']} | "
        f"{','.join(t['depends_on'])} | {t['attempts']} | {t['title']} |" for t in board["tasks"])
    blocked = [t for t in board["tasks"] if t["status"] == "blocked"]
    blocked_txt = "\n".join(f"- {t['id']}: {t.get('blocked_reason', '')[:600]} (runs: project/runs/{t['id']}/)"
                            for t in blocked) or "(none)"
    try:
        recent = "\n".join(EVENTS_PATH.read_text(encoding="utf-8").splitlines()[-40:])
    except OSError:
        recent = ""
    shots = sorted(RUNS.glob("T-*/a*/screenshot_*.png"), key=lambda p: p.stat().st_mtime)[-5:]
    text = prompt_header("PLAN", None, "the quarterback (product/project manager and tech lead)", "project/roles/quarterback.md") + f"""## Why you are planning now
{reason}

## Board (id | milestone | status | owner | type | depends_on | attempts | title)
| id | ms | status | owner | type | deps | att | title |
|---|---|---|---|---|---|---|---|
{table}

Full task data: `project/board.json` (read-only for you). Briefs: `project/tasks/`.

## Blocked tasks
{blocked_txt}

## Recent events
```
{recent}
```

## Recent screenshots (read them to judge the game's real state)
{chr(10).join('- ' + rel(p) for p in shots) or '(none yet)'}

{EXPANSION if board.get("v1_complete") else ""}## Your job
Follow the PLAN step in your role guide: write or refresh sharp briefs in `project/tasks/T-###.md` for every task you
promote (keep the `## Log` section at the end if present), keep {3 * (1 + len(WORKTREE_LANES))}-{4 * (1 + len(WORKTREE_LANES))} tasks ready ({1 + len(WORKTREE_LANES)} lanes run in parallel, and only tasks whose briefs name different files can run side by side, so spread independent work and name every file a task touches), triage the backlog and QA bugs,
unblock or re-plan blocked tasks, mark milestones complete when they truly are, and update `project/PM_NOTES.md`.
Only tasks whose dependencies are all done or dropped can start. Make sure the next tasks in milestone order are ready.

## Output
Write the plan JSON (format: PROTOCOL.md "Plan") to: `{rel(d / 'plan.json')}`
"""
    pf = write_prompt(d / "prompt_plan.md", text)
    event(f"PLAN start ({reason}){' [background]' if cur_lane() == 'P' else ''}")
    plan = call_agent(QB, pf, d / "plan.json", "plan", board, step_kind="plan")
    if plan is None:
        event("PLAN failed (no plan.json)")
        return None
    apply_plan(board, plan)
    git_commit(f"PLAN: {str(plan.get('summary', ''))[:70]}", str(plan.get("summary", "")), paths=["project"])
    event(f"PLAN done: {str(plan.get('summary', ''))[:200]}")
    return plan


EXPANSION = """## EXPANSION MODE (v1 is complete)
The owner asked the team to keep improving the game after v1 until the owner stops it (project/STOP).
Follow the "EXPANSION mode" section of your role guide: keep the game shippable, plan the next expansion milestone
(M6, M7, ...) as a small batch of the most valuable features/polish + a QA task + a Windows re-export task, and
never set project_complete. Always keep at least 3 tasks ready.

"""


def apply_plan(board: dict, plan: dict) -> None:
    with BOARD_LOCK:
        _apply_plan(board, plan)


def _apply_plan(board: dict, plan: dict) -> None:
    for spec in plan.get("new_tasks", []) or []:
        add_task(board, spec, "plan")
    for upd in plan.get("update_tasks", []) or []:
        t = task_by_id(board, upd.get("id", "")) if isinstance(upd, dict) else None
        if not t:
            continue
        for k in TASK_FIELDS:
            if k in upd:
                t[k] = upd[k]
        if upd.get("status") in ("backlog", "ready", "dropped") and t["status"] != "done":
            if t["status"] == "blocked":
                t["attempts"] = 0
            t["status"] = upd["status"]
    for tid in plan.get("promote", []) or []:
        t = task_by_id(board, tid)
        if t and t["status"] in ("backlog", "blocked"):
            if t["status"] == "blocked":
                t["attempts"] = 0
            t["status"] = "ready"
    for t in board["tasks"]:
        if t["status"] == "ready":
            ensure_brief(t)
    ms = plan.get("milestone_complete")
    if ms and ms_index(ms) < 999 and ms not in board.setdefault("milestones_complete", []):
        board["milestones_complete"].append(ms)
        event(f"MILESTONE {ms} COMPLETE")
        notify(f"milestone-{ms}", f"{{GAME_NAME}}: milestone {ms} complete",
               f"{ms} is done. Report: project/milestones/{ms}.md", email=False)
        save_board(board)
        git_commit(f"MILESTONE {ms} complete", paths=["project"])
        git("tag", "-f", ms, check=False)
    stop_ms = CONFIG.get("stop_after_milestone")
    if stop_ms and stop_ms in board.get("milestones_complete", []) and not board.get("project_complete"):
        board["project_complete"] = True  # owner-chosen final milestone reached: the main loop exits cleanly
        event(f"FINAL MILESTONE {stop_ms} complete - stopping the team as the owner asked")
        notify("final", "{{GAME_NAME}}: finished!",
               f"The final milestone {stop_ms} is complete and the team has stopped. Play builds/{{EXE_NAME}}.exe. "
               f"Reports are in project/milestones/.", email=True, priority="high")
    if plan.get("project_complete"):
        if CONFIG.get("expansion_after_v1"):
            if not board.get("v1_complete"):
                board["v1_complete"] = True
                event("V1 COMPLETE - entering expansion mode (new features + QA until a usage limit is hit)")
                save_board(board)
                git_commit("v1.0 complete", paths=["project"])
                git("tag", "-f", "v1.0", check=False)
        else:
            board["project_complete"] = True
    save_board(board)


def work_prompt(task: dict, d: Path, n: int, checkpoint: str, feedback: str | None, agent: str) -> Path:
    role = ROLE_FOR_TYPE.get(task["type"], "project/roles/coder.md")
    job = {"code": "Implement the task.",
           "asset": "Job B (Assets) from your role guide: produce the assets for this task.",
           "qa": "Job C (QA playtest task) from your role guide.",
           "design": "WORK step (design task) from your role guide."}.get(task["type"], "Do the task.")
    if feedback and n > 1:
        fb = (f"## Feedback from the previous attempt (attempt {n - 1}) - address every point\n\n{feedback}\n\n"
              f"Your previous changes are still in the working tree; build on them.\n\n")
    elif feedback:
        fb = f"## Notes from earlier runs of this task - take them into account\n\n{feedback}\n\n"
    else:
        fb = ""
    text = prompt_header("WORK", task, ROLE_LABEL.get(task["type"], "the coder"), role) + lane_note() + task_block(task) + fb + f"""## What to do
{job}
This is attempt {n} of {CONFIG['max_attempts']}.

## Context
- State before this task = commit `{checkpoint}`. See changes so far: `git diff {checkpoint}` and `git status`.
- Your run folder for this attempt (contact sheets, extra screenshots, notes, bugs.json): `{rel(d)}/`
  (absolute: `{d}`)
- After you finish, the orchestrator runs: import, all tests, a 300-frame smoke run, and a screenshot of scenario
  `{task['scenario']}`. Any error fails the attempt, so run these yourself first (commands in project/ARCHITECTURE.md).

## Output
Write the work JSON (format: PROTOCOL.md "Work") to: `{rel(d / 'work.json')}`
"""
    return write_prompt(d / "prompt_work.md", text)


def qa_prompt(task: dict, d: Path, checkpoint: str, work: dict, checks: dict) -> Path:
    prev_qa = d.parent / f"a{task['attempts'] - 1}" / "qa.json"
    retest = (f" This is a RE-TEST: your previous report is `{rel(prev_qa)}`. Check that those issues are fixed "
              f"and nothing regressed; don't add new demands." if prev_qa.exists() else "")
    text = prompt_header("QA", task, "the QA engineer", "project/roles/qa_assets.md") + lane_note() + task_block(task) + f"""## What to do
Job A (QA) from your role guide. Verify this change against every acceptance criterion.
This is attempt {task['attempts']} of {CONFIG['max_attempts']}.{retest}

## Worker report (work.json)
```json
{json.dumps(work, indent=2)}
```

## Change summary (vs checkpoint `{checkpoint}`)
```
{diff_summary(checkpoint)}
```
Full diff: `git diff {checkpoint}` (+ `git status` for new files).

## {checks_text(checks, 'after work')}
Screenshot of scenario `{task['scenario']}`: `{checks.get('screenshot')}` (attached if available).
Run folder: `{rel(d)}/` (absolute: `{d}`)

## Output
Write the QA JSON (format: PROTOCOL.md "QA") to: `{rel(d / 'qa.json')}`
"""
    return write_prompt(d / "prompt_qa.md", text)


def review_prompt(task: dict, d: Path, checkpoint: str, work: dict, checks: dict, qa: dict | None) -> Path:
    extra = sorted(p for p in d.glob("*.png") if not p.name.startswith("screenshot_"))
    qa_txt = json.dumps(qa, indent=2) if qa else "(no QA step for this task type)"
    text = prompt_header("REVIEW", task, "the quarterback (final reviewer)", "project/roles/quarterback.md") + task_block(task) + f"""## What to do
REVIEW step from your role guide. You are the final gate before this is committed.

## Worker report (work.json)
```json
{json.dumps(work, indent=2)}
```

## QA report (qa.json)
```json
{qa_txt}
```

## {checks_text(checks, 'latest')}

## Change summary (vs checkpoint `{checkpoint}`)
```
{diff_summary(checkpoint)}
```
Inspect with `git diff {checkpoint}` and `git status`.

## Images to look at (read them)
- Scenario screenshot: `{checks.get('screenshot')}`
{chr(10).join('- ' + rel(p) for p in extra)}

Approving is only possible if the automatic checks passed.

## Output
Write the review JSON (format: PROTOCOL.md "Review") to: `{rel(d / 'review.json')}`
"""
    return write_prompt(d / "prompt_review.md", text)


LIGHT_TASK_RE = re.compile(r"^\s*(polish|cleanup|clean-up|chore|tidy|typing)(\b|:)", re.I)


def skips_qa(task: dict) -> bool:
    """Small cleanup/polish tasks go straight from the automatic checks to Claude's review (owner decision 2026-10-10)."""
    return bool(task.get("skip_qa")) or bool(LIGHT_TASK_RE.search(task.get("title", "")))


def add_bugs(board: dict, bugs, source: str, milestone: str) -> None:
    for b in bugs or []:
        if isinstance(b, dict) and b.get("title"):
            add_task(board, {"title": "BUG: " + str(b["title"]), "description": b.get("description", ""),
                             "milestone": milestone, "type": "code", "owner": "coder", "priority": 2,
                             "acceptance": ["Bug no longer reproduces", "Regression test added"]}, source)


def ensure_worktree(lane: str = "B") -> Path:
    """A worktree lane's separate checkout (outside OneDrive so it isn't synced)."""
    d = lane_dir(lane)
    if not (d / ".git").exists():
        with on_root(ROOT):
            git("worktree", "prune", check=False)
            git("worktree", "add", "--detach", str(d), "HEAD")
        event(f"LANE {lane} worktree created at {d}")
    return d


def sync_worktree(sha: str, lane: str = "B") -> None:
    """Point a worktree lane's checkout at ROOT's current HEAD, clean."""
    with on_root(lane_dir(lane)):
        git("checkout", "-q", "--detach", "--force", sha)
        git_revert_to(sha)


APPEND_LOGS = ["project/assumptions.md", "project/decisions.md"]


def divert_append_logs() -> None:
    """Lane B: copy its new lines in the shared append-only logs straight into ROOT's working copy and leave those
    files out of its commit. Lane A nearly always has unsaved additions there, which would block every merge."""
    for rp in APPEND_LOGS:
        diff = git("diff", "HEAD", "--unified=0", "--", rp, check=False)
        added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        if added:
            with MAIN_GIT_LOCK:  # do not append while lane A is committing
                with (ROOT / rp).open("a", encoding="utf-8") as f:
                    f.write("\n".join(added) + "\n")
        git("checkout", "HEAD", "--", rp, check=False)


def lane_a_working() -> bool:
    board = _state.get("board")
    if board is None:
        return bool(_state.get("task"))
    with BOARD_LOCK:
        return any(t["status"] == "in_progress" and t.get("lane", "A") == "A" for t in board["tasks"])


def clear_stray_main_edits(tid: str) -> bool:
    """If lane A has no task running, uncommitted game/ edits in ROOT can only be strays (a lane B agent that wrote into
    the main checkout). Save them next to the task's runs and remove them so the merge can proceed. True if cleared."""
    if lane_a_working():
        return False
    with MAIN_GIT_LOCK:
        if lane_a_working():
            return False
        stray = git("status", "--porcelain", "--", "game/", check=False)
        if not stray:
            return False
        d = RUNS / tid / f"stray_in_main_{dt.datetime.now():%Y%m%d-%H%M%S}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "tracked.patch").write_text(git("diff", "--binary", "--", "game/", check=False) + "\n", encoding="utf-8",
                                         newline="\n")
        for line in stray.splitlines():
            rp = line[3:].strip().strip('"')
            src = ROOT / rp
            if line.startswith("??") and src.is_file():
                (d / rp).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, d / rp)
        git("checkout", "--", "game/", check=False)
        git("clean", "-q", "-fd", "--", "game/", check=False)
    event(f"STRAY edits in main (lane A idle) blocked merging {tid}; saved to {rel(d)} and removed")
    return True


def merge_lane(tid: str, sha: str, lane: str = "B") -> bool:
    """Merge a worktree lane's approved commit into ROOT. Waits while lane A has uncommitted edits to the same files;
    gives up (False) on a real content conflict, saving the approved work as a patch."""
    deadline = time.time() + 60 * CONFIG.get("lane_b", {}).get("merge_wait_minutes", 120)
    last_note = 0.0
    with on_root(ROOT):
        while True:
            with MAIN_GIT_LOCK:
                r = subprocess.run(["git", "merge", "--no-ff", "--no-edit", "-m", f"Merge lane {lane}: {tid}", sha],
                                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
                out = r.stdout + r.stderr
                if r.returncode == 0:
                    event(f"LANE {lane} merged {tid} into main")
                    return True
                if "CONFLICT" in out or "Automatic merge failed" in out:
                    subprocess.run(["git", "merge", "--abort"], cwd=ROOT, capture_output=True)
                    p = RUNS / tid / f"lane_{lane.lower()}.patch"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(git("diff", "--binary", f"{sha}^", sha, check=False) + "\n", encoding="utf-8",
                                 newline="\n")
                    event(f"LANE {lane} merge conflict on {tid}; requeued for lane A. Approved work saved to {p.name}")
                    return False
            if clear_stray_main_edits(tid):
                continue
            if time.time() > deadline:
                event(f"LANE {lane} gave up waiting to merge {tid}: {out.strip()[:200]}")
                return False
            if time.time() - last_note > 600:
                event(f"LANE {lane} waiting to merge {tid} (lane A has uncommitted edits to the same files)")
                last_note = time.time()
            time.sleep(60)


def run_task(board: dict, task: dict, lane: str = "A") -> str:
    tid = task["id"]
    skey = "task" if lane == "A" else f"task_{lane.lower()}"
    brief = ensure_brief(task)
    with BOARD_LOCK:
        task["status"] = "in_progress"
        task["lane"] = lane
    save_board(board)
    with on_root(ROOT):  # brief + board live in ROOT; lane B must not sweep up lane A's uncommitted work
        git_commit(f"Start {tid}", paths=[brief.relative_to(ROOT).as_posix(), "project/board.json"])
        main_head = git_head()
    if lane != "A":
        sync_worktree(main_head, lane)
    checkpoint = "HEAD"  # agents never commit, so their work is always the diff against HEAD
    task["checkpoint"] = main_head
    _state[skey] = f"{tid} {task['title']} ({task['owner']})"
    save_board(board)
    event(f"START {tid} [lane {lane}] [{task['owner']}/{task['type']}] {task['title']}")
    feedback = task.pop("pending_feedback", None)
    max_attempts = CONFIG["max_attempts"]
    final_reason = ""

    while task["attempts"] < max_attempts:
        check_stop()
        task["attempts"] += 1
        n = task["attempts"]
        save_board(board)
        d = RUNS / tid / f"a{n}"
        if d.exists():  # left over from an earlier (blocked or interrupted) run of this task
            d.rename(d.with_name(f"a{n}_old_{dt.datetime.now():%Y%m%d-%H%M%S}"))
        d.mkdir(parents=True, exist_ok=True)
        hist = {"attempt": n, "at": now()}
        task["history"].append(hist)

        # WORK
        agent = resolve_worker(task, lane, n)
        hist["worker"] = agent
        work = call_agent(agent, work_prompt(task, d, n, checkpoint, feedback, agent), d / "work.json", "work", board,
                          step_kind=f"work-{task['type']}")
        if work is None:
            hist["work"] = "no output"
            feedback = "The worker produced no valid work.json (crash, timeout, or forgot). Finish the task and write it."
            event(f"{tid} a{n} WORK produced no result")
            save_board(board)
            continue
        hist["work"] = work.get("status")
        event(f"{tid} a{n} WORK {work.get('status')}: {str(work.get('summary', ''))[:160]}")

        # CHECKS
        set_now(f"{tid} a{n}: running Godot checks", board)
        checks = run_checks(d, task["scenario"], "work")
        hist["checks"] = checks["passed"]
        event(f"{tid} a{n} CHECKS {'pass' if checks['passed'] else 'FAIL'} ({checks.get('tests_summary', '')})")
        if not checks["passed"] and work.get("status") != "blocked" and n < max_attempts:
            feedback = checks_text(checks, "after your work") + f"\nFull log: {rel(d / 'checks_work.log')}"
            save_board(board)
            continue

        # QA (code tasks)
        qa = None
        if task["type"] == "code" and work.get("status") == "done" and checks["passed"] and not skips_qa(task):
            imgs = [ROOT / checks["screenshot"]] if checks.get("screenshot") else []
            qa = call_agent(QA, qa_prompt(task, d, checkpoint, work, checks), d / "qa.json", "qa", board, imgs,
                            step_kind="qa", avoid=agent)
            if qa:
                hist["qa"] = qa.get("verdict")
                event(f"{tid} a{n} QA {qa.get('verdict')}: {str(qa.get('summary', ''))[:160]}")
                add_bugs(board, qa.get("out_of_scope_bugs"), f"QA {tid}", task["milestone"])
            checks = run_checks(d, task["scenario"], "qa")
            hist["checks_after_qa"] = checks["passed"]
            if not checks["passed"] and n < max_attempts:
                feedback = ("Checks failed after QA added tests (QA may have caught a real bug):\n"
                            + checks_text(checks, "after QA") + "\n\nQA report:\n" + json.dumps(qa, indent=2))
                save_board(board)
                continue
            if qa and qa.get("verdict") == "fail" and n < max_attempts:
                feedback = "QA failed this attempt:\n" + json.dumps(qa, indent=2)
                save_board(board)
                continue
        if task["type"] == "qa":
            add_bugs(board, read_json(d / "bugs.json"), f"QA {tid}", task["milestone"])

        # REVIEW
        review = call_agent(QB, review_prompt(task, d, checkpoint, work, checks, qa), d / "review.json",
                            "review", board, step_kind="review")
        if review is None:
            ok = checks["passed"] and work.get("status") == "done" and (qa is None or qa.get("verdict") == "pass")
            review = {"verdict": "approve" if ok else "revise", "summary": "auto-decided (review unavailable)",
                      "feedback": "Reviewer unavailable; fix failing checks/QA issues." if not ok else ""}
            event(f"{tid} a{n} REVIEW unavailable -> auto {review['verdict']}")
        verdict = review.get("verdict")
        hist["review"] = verdict
        event(f"{tid} a{n} REVIEW {verdict}: {str(review.get('summary', ''))[:160]}")
        for spec in review.get("new_tasks", []) or []:
            add_task(board, spec, f"review {tid}")

        if verdict == "approve" and checks["passed"]:
            if task_needs_approval(task, agent):
                appr_dir = PROJECT / "approvals"
                try:
                    appr_dir.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                patch_path = d / "approval.patch"
                try:
                    save_patch(checkpoint, patch_path)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    patch_rel = patch_path.relative_to(ROOT).as_posix()
                except ValueError:
                    patch_rel = patch_path.as_posix()
                shot = ""
                try:
                    imgs = list(d.glob("*.png"))
                    if imgs:
                        shot = imgs[0].relative_to(ROOT).as_posix()
                except (OSError, ValueError):
                    shot = ""
                req = {"task": tid, "title": task.get("title", ""), "attempt": n, "lane": lane,
                       "worker": agent, "requested_at": now(),
                       "summary": str(work.get("summary", ""))[:2000],
                       "review_summary": str(review.get("summary", ""))[:2000],
                       "qa_verdict": str((qa or {}).get("verdict", "")),
                       "checks_summary": str(checks.get("tests_summary", ""))[:1000],
                       "patch": patch_rel, "screenshot": shot}
                (appr_dir / f"{tid}.decision.json").unlink(missing_ok=True)  # stale, from an interrupted wait
                try:
                    (appr_dir / f"{tid}.json").write_text(json.dumps(req, indent=2), encoding="utf-8")
                except OSError:
                    pass
                event(f"APPROVAL WAIT {tid} (lane {lane})")
                notify(f"approval-{tid}", "{{GAME_NAME}}: approval needed for " + tid,
                       f"{tid}: {task.get('title', '')} (attempt {n}, lane {lane}, worker {agent}) "
                       f"is waiting for owner approval.", email=True)
                set_now(f"waiting for owner approval of {tid}", board)
                decision, dec_feedback = await_approval(
                    task, n, lane, worker=agent, summary=req["summary"],
                    review_summary=req["review_summary"], qa_verdict=req["qa_verdict"],
                    checks_summary=req["checks_summary"], patch=patch_rel, screenshot=shot)
                if decision == "revise":
                    verdict = "revise"
                    hist["review"] = "revise"
                    feedback = f"Owner requested changes: {dec_feedback}"
                    final_reason = feedback
                    save_board(board)
                    continue
            title = f"{tid}: {task['title']}"
            body = f"{work.get('summary', '')}\n\nReview: {review.get('summary', '')}"
            if lane != "A":
                divert_append_logs()
                git_commit(title, body)  # in the worktree
                if not merge_lane(tid, git_head(), lane):
                    with BOARD_LOCK:  # real conflict: redo the task in lane A on top of current main
                        task.update(status="ready", lane="A", attempts=0,
                                    pending_feedback=f"Approved in lane {lane} but it conflicted with main when "
                                    f"merging. The approved version is saved in {rel(RUNS / tid / ('lane_' + lane.lower() + '.patch'))}.")
                    _state[skey] = None
                    save_board(board)
                    return "requeued"
            task["status"] = "done"
            task["completed_at"] = now()
            _state[skey] = None
            append_task_log(task, f"DONE on attempt {n} (lane {lane}, worker {agent}). Work: {work.get('summary', '')}\n\n"
                                  f"QA: {(qa or {}).get('summary', '-')}\n\nReview: {review.get('summary', '')}")
            save_board(board)
            if lane == "A":
                git_commit(title, body)
            else:
                with on_root(ROOT):
                    git_commit(f"Record {tid} done", paths=["project/board.json", brief.relative_to(ROOT).as_posix()])
            event(f"DONE {tid} (attempt {n}, lane {lane})")
            _state["done_since_plan"] = _state.get("done_since_plan", 0) + 1
            return "done"
        if verdict == "block":
            final_reason = f"Reviewer blocked: {review.get('feedback') or review.get('summary')}"
            break
        if verdict == "approve":
            feedback = "Reviewer approved but automatic checks failed:\n" + checks_text(checks, "latest")
        else:
            feedback = f"Reviewer verdict '{verdict}':\n{review.get('feedback', '')}"
        final_reason = feedback
        save_board(board)

    # exhausted attempts or blocked
    patch = RUNS / tid / f"blocked_after_a{task['attempts']}.patch"
    save_patch("HEAD", patch)
    git_revert_to("HEAD")  # never reset ROOT to an older commit: lane B may have merged since this task started
    task["status"] = "blocked"
    task["blocked_reason"] = ((final_reason or feedback or "attempts exhausted")[:1800]
                              + f"\n\nLast attempt's work saved as {rel(patch)} (re-apply with `git apply`).")
    _state[skey] = None
    append_task_log(task, f"BLOCKED after {task['attempts']} attempt(s); changes reverted. Reason:\n{task['blocked_reason']}")
    save_board(board)
    with on_root(ROOT):
        git_commit(f"BLOCKED {tid}: {task['title']}",
                   paths=None if lane == "A" else ["project/board.json", brief.relative_to(ROOT).as_posix()])
    event(f"BLOCKED {tid}: {task['blocked_reason'][:200]}")
    _state["blocked_since_plan"] = tid
    return "blocked"


# ----------------------------------------------------------------------------- main loop

def recover(board: dict, lanes: tuple | None = None) -> None:
    """Reset any task interrupted mid-flight (crash / window closed / stop) so it restarts cleanly.
    Each lane's unfinished work is saved (patch + file copies) before its checkout is reset."""
    try:
        (PROJECT / "commands" / "done").mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    lanes = lanes or ("A", *WORKTREE_LANES)
    interrupted = [t for t in board["tasks"] if t["status"] == "in_progress" and t.get("lane", "A") in lanes]
    for t in interrupted:  # an approval wait died with its task: drop the request so the Office stops offering it
        for f in (PROJECT / "approvals" / f"{t['id']}.json", PROJECT / "approvals" / f"{t['id']}.decision.json"):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
    by_root: dict[Path, list[dict]] = {ROOT: []}
    for t in interrupted:
        ln = t.get("lane", "A")
        wt = ln != "A" and ln in WORKTREE_LANES and (lane_dir(ln) / ".git").exists()
        by_root.setdefault(lane_dir(ln) if wt else ROOT, []).append(t)
    for root, tasks in by_root.items():
        with on_root(root):
            patch = None
            if git("status", "--porcelain", check=False):
                if tasks:
                    patch = RUNS / tasks[0]["id"] / f"interrupted_{dt.datetime.now():%Y%m%d-%H%M%S}.patch"
                    save_patch("HEAD", patch)
                git_revert_to("HEAD")
            for t in tasks:
                t["status"] = "ready"
                t["attempts"] = max(0, t["attempts"] - 1)
                if patch and (patch.exists() and patch.stat().st_size > 10 or patch.with_name(patch.stem + "_files").exists()):
                    t["pending_feedback"] = (
                        f"This task was interrupted (usage limit / restart) mid-attempt. The unfinished work is saved in "
                        f"{patch.relative_to(ROOT).as_posix()} and the folder next to it ({patch.stem}_files/). Review "
                        f"it and reuse what is good; see earlier attempt folders in project/runs/{t['id']}/ for "
                        f"QA/review feedback.")
                event(f"RECOVER {t['id']}: was interrupted; work saved, checkout reset, back to ready")
    save_board(board)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run at most one task then exit")
    ap.add_argument("--plan", action="store_true", help="run one planning step then exit")
    ap.add_argument("--task", help="run this ready task id once (no planning), then exit")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    prevent_sleep()
    start_godot_watchdog(CONFIG.get("godot_watchdog_minutes", 10))
    start_quota_prober(CONFIG.get("probe_every_minutes", 15))
    board = load_board()
    _state["board"] = board
    recover(board)
    event("ORCHESTRATOR START")
    if args.task:
        t = task_by_id(board, args.task)
        if not t or t not in pickable(board):
            print(f"{args.task} is not a startable ready task")
            return 1
        try:
            run_task(board, t)
        except StopRequested:
            set_now("STOPPED (project/STOP file present)", board)
        return 0
    try:
        return loop(board, args)
    except UsageLimitStop as e:
        set_now(f"STOPPED: {e} reached its subscription usage limit (owner's stop condition). "
                f"Run start.bat to resume once limits reset.", board)
        return 0
    except StopRequested:
        set_now("STOPPED (project/STOP file present)", board)
        event("STOP requested - exiting cleanly")
        return 0
    except KeyboardInterrupt:
        set_now("STOPPED (Ctrl+C)", board)
        event("Interrupted by Ctrl+C")
        return 130


def loop(board: dict, args) -> int:
    """Main loop. Unexpected errors are logged, then the loop recovers and carries on."""
    errors_in_a_row = 0
    while True:
        try:
            return run_loop(board, args)
        except (StopRequested, KeyboardInterrupt):
            raise
        except Exception:
            import traceback
            errors_in_a_row += 1
            err_dir = RUNS / "_errors"
            err_dir.mkdir(parents=True, exist_ok=True)
            tb = traceback.format_exc()
            (err_dir / f"{dt.datetime.now():%Y%m%d-%H%M%S}.txt").write_text(tb, encoding="utf-8")
            event(f"ORCHESTRATOR ERROR ({errors_in_a_row} in a row): {tb.strip().splitlines()[-1][:200]}")
            if errors_in_a_row >= 3:
                notify("errors", "{{GAME_NAME}}: orchestrator keeps failing",
                       f"{errors_in_a_row} errors in a row. Last: {tb.strip().splitlines()[-1][:200]}", email=True,
                       priority="high")
            if args.once or args.plan:
                return 1
            save_board(board)
            sleep_minutes(5 if errors_in_a_row < 5 else 60, board, "recovering from an orchestrator error")
            recover(board, lanes=("A",))  # lane B may still be mid-task in its own thread


_drain = threading.Event()
_lanes: dict[str, dict] = {ln: {"thread": None, "busy": False, "idle_since": None} for ln in WORKTREE_LANES}
_planner: dict = {"thread": None, "reason": None}
LANE_B_EXCLUDE_RE = re.compile(r"export|windows build|release", re.I)


def unlocked_backlog(board: dict) -> bool:
    """True when some backlog task has all its dependencies finished (so planning could promote it)."""
    finished = {t["id"] for t in board["tasks"] if t["status"] in ("done", "dropped")}
    return any(t["status"] == "backlog" and all(d in finished for d in t["depends_on"]) for t in board["tasks"])


def lane_b_enabled() -> bool:
    return bool(WORKTREE_LANES)


def lane_b_ok(task: dict) -> bool:
    """Lane B takes ordinary feature/art work; integration-sensitive tasks (milestone QA, exports, tasks
    sent back after a merge conflict) stay in lane A."""
    return (task.get("lane") != "A" and task["type"] in ("code", "asset")  # design tasks edit the GDD, as planning does
            and not LANE_B_EXCLUDE_RE.search(task["title"]))


BRIEF_PATH_RE = re.compile(r"game/[A-Za-z0-9_./-]+\.(?:gd|tscn|tres|json|png|cfg|godot|ttf)")
SHARED_DIRS = {"game/tests", "game/dev/scenarios"}  # nearly every task adds tests/scenarios: not a conflict signal


def task_areas(task: dict) -> set[str]:
    """Files a task's brief says it will touch (used to keep the two lanes out of each other's way).
    File-level, not folder-level: git only conflicts on the same file, and folder-level matching serialized whole
    milestones whose tasks each add their own file to one folder (e.g. sim/haven). A brief that misses a file it
    edits can still conflict; merge_lane then requeues that task for lane A."""
    try:
        text = (TASKS_DIR / f"{task['id']}.md").read_text(encoding="utf-8")
    except OSError:
        return set()
    return {f for f in BRIEF_PATH_RE.findall(text) if f.rsplit("/", 1)[0] not in SHARED_DIRS}


def overlaps_others(board: dict, task: dict, me: str) -> bool:
    """Does `task` touch the same files as a task another lane is running?
    QA tasks only add tests, scenarios and bug reports (shared folders); design tasks edit project documents,
    not game files. Neither should block game work just because its brief names no writable game paths."""
    if task.get("type") in ("qa", "design"):
        return False
    mine = task_areas(task)
    for t in board["tasks"]:
        if (t is not task and t["status"] == "in_progress" and t.get("lane", "A") != me
                and t.get("type") not in ("qa", "design")):
            theirs = task_areas(t)
            if not mine or not theirs or mine & theirs:
                return True  # unknown areas count as overlapping: idle beats a wasted task
    return False


def claim_task(board: dict, lane: str) -> dict | None:
    """Pick the next startable ready task for a lane and mark it in progress, atomically."""
    with BOARD_LOCK:
        ready = pickable(board)
        if lane != "A":
            ready = [t for t in ready if lane_b_ok(t) and can_start_now(t) and not overlaps_others(board, t, lane)]
            task = ready[0] if ready else None
        else:
            if not ready:
                return None
            # Lane A never idles, but it prefers work away from the other lanes' tasks (fewer merge conflicts).
            startable = [t for t in ready if can_start_now(t)]
            task = next((t for t in startable if not overlaps_others(board, t, "A")), None) or \
                (startable[0] if startable else ready[0])
            if task is not ready[0]:
                why = (f"{ready[0]['owner']}'s usage limit" if not can_start_now(ready[0])
                       else "another lane's current task (touches the same files)")
                event(f"SKIP AHEAD {ready[0]['id']} waits for {why}; starting {task['id']} instead")
        if task is not None:
            task["status"] = "in_progress"
            task["lane"] = lane
        return task


def lane_main(board: dict, lane: str) -> None:
    """A worktree lane: runs ready tasks in parallel with lane A, in its own checkout."""
    import traceback
    _tl.root = lane_dir(lane)
    _tl.lane = lane
    st = _lanes[lane]
    try:
        ensure_worktree(lane)
    except Exception as e:  # noqa: BLE001
        event(f"LANE {lane} disabled: could not create worktree ({e})")
        return
    event(f"LANE {lane} started (worktree {lane_dir(lane)})")
    while not _drain.is_set():
        task = None
        try:
            check_stop()
            task = claim_task(board, lane)
            if task is None:
                st["idle_since"] = st["idle_since"] or time.time()
                # Ask for a re-plan from here too: the main loop only checks between lane A's tasks, so a long lane-A
                # task (e.g. a milestone QA run) used to leave the other lanes idle for its whole duration.
                if CONFIG.get("background_planning", True) and time.time() - st["idle_since"] > 600:
                    with BOARD_LOCK:
                        if not planner_busy() and unlocked_backlog(board):
                            st["idle_since"] = time.time()
                            start_planner(board, f"lane {lane} has been idle for 10+ minutes; promote more "
                                                 f"independent ready tasks")
                time.sleep(30)
                continue
            st["idle_since"] = None
            st["busy"] = True
            run_task(board, task, lane=lane)
        except StopRequested:
            return
        except Exception:  # noqa: BLE001
            tb = traceback.format_exc()
            err_dir = RUNS / "_errors"
            err_dir.mkdir(parents=True, exist_ok=True)
            (err_dir / f"lane{lane}-{dt.datetime.now():%Y%m%d-%H%M%S}.txt").write_text(tb, encoding="utf-8")
            event(f"LANE {lane} ERROR: {tb.strip().splitlines()[-1][:200]}")
            if task is not None and task.get("status") == "in_progress":
                with on_root(lane_dir(lane)):
                    git_revert_to("HEAD")
                with BOARD_LOCK:
                    task.update(status="ready", lane="A")
                save_board(board)
            time.sleep(120)
        finally:
            st["busy"] = False
    event(f"LANE {lane} stopped (draining for restart)")


def start_lanes(board: dict) -> None:
    for i, ln in enumerate(WORKTREE_LANES):
        if _lanes[ln]["thread"] is None:
            if i:
                time.sleep(5)  # stagger worktree creation and first claims
            t = threading.Thread(target=lane_main, args=(board, ln), daemon=True, name=f"lane{ln}")
            _lanes[ln]["thread"] = t
            t.start()


def planner_busy() -> bool:
    """A background planner thread is alive, or the main loop is running a synchronous plan step."""
    return bool(_state.get("sync_planning")) or (_planner["thread"] is not None and _planner["thread"].is_alive())


def start_planner(board: dict, reason: str) -> bool:
    """Run a PLAN step in its own thread so lane A keeps working. One planner at a time."""
    if planner_busy():
        return False

    def run() -> None:
        import traceback
        _tl.lane = "P"
        try:
            plan_step(board, reason)
        except StopRequested:
            pass
        except Exception:  # noqa: BLE001
            tb = traceback.format_exc()
            err_dir = RUNS / "_errors"
            err_dir.mkdir(parents=True, exist_ok=True)
            (err_dir / f"planner-{dt.datetime.now():%Y%m%d-%H%M%S}.txt").write_text(tb, encoding="utf-8")
            event(f"PLANNER ERROR: {tb.strip().splitlines()[-1][:200]}")
        finally:
            _state.pop("now_p", None)

    _state["done_since_plan"] = 0
    t = threading.Thread(target=run, daemon=True, name="planner")
    _planner.update(thread=t, reason=reason)
    t.start()
    return True


def can_start_now(task: dict) -> bool:
    """False when the task's owner is rate-limited and no fallback can cover its work step."""
    owners = coders() if task["owner"] in CODER_OWNERS else [resolve_owner(task["owner"])]
    for owner in owners:
        if not unavailable(owner) or any(not unavailable(f) for f in fallback_for(owner, f"work-{task['type']}")):
            return True
    return False

def start_plan_now_watcher(board: dict) -> None:
    """Owner/supervisor switch: create project/PLAN_NOW to start a background plan within ~30 s, even while every
    lane is busy (the main loop only looks for planning triggers between lane A's tasks)."""
    flag = PROJECT / "PLAN_NOW"

    def watch() -> None:
        while not _drain.is_set():
            time.sleep(30)
            try:
                if flag.exists() and not planner_busy():
                    flag.unlink(missing_ok=True)
                    with BOARD_LOCK:
                        start_planner(board, "owner asked for a plan now (project/PLAN_NOW)")
            except Exception as e:  # noqa: BLE001 - the watcher must never take the orchestrator down
                event(f"PLAN_NOW watcher error: {e!r}"[:200])

    threading.Thread(target=watch, daemon=True, name="plan-now").start()


def process_commands(board: dict) -> None:
    """One inbox pass: apply project/commands/*.json oldest first (by name).

    Factored out so tests can call it directly. Never raises: malformed files
    and per-file errors are moved to done/ with a refused result and logged.
    """
    cmd_dir = PROJECT / "commands"
    done_dir = cmd_dir / "done"
    try:
        done_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        files = sorted((p for p in cmd_dir.glob("*.json") if p.is_file()), key=lambda p: p.name)
    except Exception as e:  # noqa: BLE001
        event(f"COMMAND watcher error: {e!r}"[:200])
        return
    for path in files:
        try:
            _process_command_file(board, path, done_dir)
        except Exception as e:  # noqa: BLE001 - never fatal
            event(f"COMMAND watcher error: {e!r}"[:200])


def _finish_command(path: Path, done_dir: Path, data: dict | None, raw_text: str | None,
                    cid: str, action: str, task_label: str, result: str) -> None:
    try:
        done_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(data, dict):
            data = dict(data)
        else:
            data = {"raw": (raw_text or "")[:2000]} if raw_text else {}
            if cid:
                data["id"] = cid
            if action:
                data["action"] = action
        data["result"] = result
        data["done_at"] = now()
        (done_dir / path.name).write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        event(f"COMMAND watcher error: {e!r}"[:200])
        return
    try:
        event(f"COMMAND {cid} {action} {task_label} {result}"[:300])
    except Exception:  # noqa: BLE001
        pass


def _process_command_file(board: dict, path: Path, done_dir: Path) -> None:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        event(f"COMMAND watcher error: {e!r}"[:200])
        return
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        _finish_command(path, done_dir, None, raw, path.stem, "?", "new", "refused: malformed")
        return
    if not isinstance(data, dict):
        _finish_command(path, done_dir, None, raw, path.stem, "?", "new", "refused: malformed")
        return
    cid = data.get("id")
    action = data.get("action")
    if not isinstance(cid, str) or not cid or not isinstance(action, str) or not action:
        _finish_command(path, done_dir, data, raw, str(cid) if cid else path.stem,
                        str(action) if isinstance(action, str) and action else "?",
                        "new", "refused: malformed")
        return
    if action not in ("set_priority", "set_status", "retry", "add_task",
                      "bench", "unbench", "set_approval"):
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return
    # Missing required keys -> malformed; bad values -> refused.
    if action in ("set_priority", "set_status", "retry") and "task" not in data:
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return
    if action in ("bench", "unbench") and "agent" not in data:
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return
    if action == "set_approval" and ("task" not in data or "required" not in data):
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return
    if action == "set_priority" and "priority" not in data:
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return
    if action == "set_status" and "status" not in data:
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return
    if action == "add_task" and "task" not in data:
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return

    if action == "set_priority":
        tid = data.get("task")
        prio = data.get("priority")
        if not isinstance(tid, str):
            _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
            return
        t = task_by_id(board, tid)
        if not t:
            _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: unknown task")
            return
        try:
            if isinstance(prio, bool):
                raise ValueError()
            p = int(prio)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: bad priority")
            return
        if p < 1 or p > 5:
            _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: bad priority")
            return
        apply_plan(board, {"update_tasks": [{"id": tid, "priority": p}]})
        try:
            git_commit(f"OWNER: set {tid} priority to {p}", paths=["project"])
        except Exception:  # noqa: BLE001
            pass
        _finish_command(path, done_dir, data, raw, cid, action, tid, "applied")
        return

    if action == "set_status":
        tid = data.get("task")
        st = data.get("status")
        if not isinstance(tid, str):
            _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
            return
        if st not in ("backlog", "ready", "dropped"):
            if "status" not in data or not isinstance(st, str):
                _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: malformed")
            else:
                _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: bad status")
            return
        t = task_by_id(board, tid)
        if not t:
            _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: unknown task")
            return
        with BOARD_LOCK:  # check + apply atomically: a lane may claim the task in between
            busy = t.get("status") in ("in_progress", "done")
            if not busy:
                apply_plan(board, {"update_tasks": [{"id": tid, "status": st}]})
        if busy:
            _finish_command(path, done_dir, data, raw, cid, action, tid,
                            f"refused: task is {t.get('status')}")
            return
        try:
            git_commit(f"OWNER: set {tid} status to {st}", paths=["project"])
        except Exception:  # noqa: BLE001
            pass
        _finish_command(path, done_dir, data, raw, cid, action, tid, "applied")
        return

    if action == "retry":
        tid = data.get("task")
        if not isinstance(tid, str):
            _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
            return
        t = task_by_id(board, tid)
        if not t:
            _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: unknown task")
            return
        with BOARD_LOCK:
            blocked = t.get("status") == "blocked"
            if blocked:
                apply_plan(board, {"promote": [tid]})
        if not blocked:
            _finish_command(path, done_dir, data, raw, cid, action, tid,
                            "refused: only blocked tasks can be retried")
            return
        try:
            git_commit(f"OWNER: retry {tid}", paths=["project"])
        except Exception:  # noqa: BLE001
            pass
        _finish_command(path, done_dir, data, raw, cid, action, tid, "applied")
        return

    if action == "bench":
        agent_name = data.get("agent")
        if not isinstance(agent_name, str):
            _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
            return
        if agent_name not in CONFIG.get("agents", {}):
            _finish_command(path, done_dir, data, raw, cid, action, agent_name, "refused: unknown agent")
            return
        reason = data.get("reason") if isinstance(data.get("reason"), str) else ""
        disabled = set(CONFIG.get("disabled_agents") or [])
        if agent_name in disabled:
            _finish_command(path, done_dir, data, raw, cid, action, agent_name, "applied")
            return
        if agent_name in coders():
            others = [c for c in coders() if c != agent_name and c not in disabled]
            if not others:
                _finish_command(path, done_dir, data, raw, cid, action, agent_name,
                                "refused: cannot bench the last available coder")
                return
        disabled.add(agent_name)
        CONFIG["disabled_agents"] = sorted(disabled)
        persist_disabled_agents()
        event(f"BENCH {agent_name}" + (f" ({reason})" if reason.strip() else ""))
        _finish_command(path, done_dir, data, raw, cid, action, agent_name, "applied")
        return

    if action == "unbench":
        agent_name = data.get("agent")
        if not isinstance(agent_name, str):
            _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
            return
        if agent_name not in CONFIG.get("agents", {}):
            _finish_command(path, done_dir, data, raw, cid, action, agent_name, "refused: unknown agent")
            return
        disabled = set(CONFIG.get("disabled_agents") or [])
        disabled.discard(agent_name)
        CONFIG["disabled_agents"] = sorted(disabled)
        persist_disabled_agents()
        event(f"UNBENCH {agent_name}")
        _finish_command(path, done_dir, data, raw, cid, action, agent_name, "applied")
        return

    if action == "set_approval":
        tid = data.get("task")
        req = data.get("required")
        if not isinstance(tid, str):
            _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
            return
        if not isinstance(req, bool):
            _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: bad required")
            return
        t = task_by_id(board, tid)
        if not t:
            _finish_command(path, done_dir, data, raw, cid, action, tid, "refused: unknown task")
            return
        with BOARD_LOCK:
            t["needs_approval"] = req
        save_board(board)
        try:
            git_commit(f"OWNER: set {tid} needs_approval to {req}", paths=["project"])
        except Exception:  # noqa: BLE001
            pass
        _finish_command(path, done_dir, data, raw, cid, action, tid, "applied")
        return

    # add_task
    spec = data.get("task")
    if not isinstance(spec, dict):
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: malformed")
        return
    title = spec.get("title")
    if not isinstance(title, str) or not title.strip():
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: bad title")
        return
    typ = spec.get("type", "code")
    if typ not in ("code", "asset", "design", "qa"):
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: bad type")
        return
    if "priority" in spec:
        try:
            p = spec["priority"]
            if isinstance(p, bool):
                raise ValueError()
            p = int(p)
            if p < 1 or p > 5:
                raise ValueError()
        except Exception:  # noqa: BLE001
            _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: bad priority")
            return
    if "acceptance" in spec and (not isinstance(spec["acceptance"], list)
                                 or not all(isinstance(x, str) for x in spec["acceptance"])):
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: bad acceptance")
        return
    if "depends_on" in spec and (not isinstance(spec["depends_on"], list)
                                 or not all(isinstance(x, str) for x in spec["depends_on"])):
        _finish_command(path, done_dir, data, raw, cid, action, "new", "refused: bad depends_on")
        return
    before = {t["id"] for t in board.get("tasks", [])}
    apply_plan(board, {"new_tasks": [spec]})
    new_tasks = [t for t in board.get("tasks", []) if t["id"] not in before]
    new_id = new_tasks[-1]["id"] if new_tasks else "new"
    if new_tasks:
        try:
            with BOARD_LOCK:
                new_tasks[-1]["source"] = "owner"
            save_board(board)
        except Exception:  # noqa: BLE001
            pass
    try:
        git_commit(f"OWNER: add task {new_id}", paths=["project"])
    except Exception:  # noqa: BLE001
        pass
    _finish_command(path, done_dir, data, raw, cid, action, new_id, "applied")


def start_command_watcher(board: dict) -> None:
    """Office inbox: apply project/commands/*.json every 5 s (oldest first). Never fatal."""

    def watch() -> None:
        while not _drain.is_set():
            time.sleep(5)
            try:
                process_commands(board)
            except Exception as e:  # noqa: BLE001 - the watcher must never take the orchestrator down
                try:
                    event(f"COMMAND watcher error: {e!r}"[:200])
                except Exception:  # noqa: BLE001
                    pass

    threading.Thread(target=watch, daemon=True, name="commands").start()


def run_loop(board: dict, args) -> int:
    need_plan = "first run of this session" if not args.once else None
    empty_plans = 0
    background = bool(CONFIG.get("background_planning", True)) and not args.once and not args.plan
    if not args.once and not args.plan:
        start_lanes(board)
        if background:
            start_plan_now_watcher(board)
        start_command_watcher(board)
    while True:
        check_stop()
        restart_flag = PROJECT / "RESTART"
        if restart_flag.exists():
            # Reload the orchestrator's code between tasks (no task is interrupted, in any lane).
            event("RESTART requested - reloading the orchestrator between tasks")
            _drain.set()
            while any(st["busy"] for st in _lanes.values()) or planner_busy():
                set_now("restart pending: waiting for the other lanes and the planner to finish", board)
                check_stop()
                time.sleep(15)
            restart_flag.unlink(missing_ok=True)
            save_board(board)
            return RESTART_EXIT_CODE  # start.bat relaunches on this code
        if board.get("project_complete"):
            set_now("PROJECT COMPLETE", board)
            event("PROJECT COMPLETE - nothing left to do")
            return 0
        idle = [ln for ln, st in _lanes.items() if st["idle_since"] and time.time() - st["idle_since"] > 600]
        if not need_plan and idle and unlocked_backlog(board) and not planner_busy():
            need_plan = f"lane {idle[0]} has been idle for 10+ minutes; promote more independent ready tasks"
            for ln in idle:
                _lanes[ln]["idle_since"] = time.time()
        if not need_plan and _state.get("blocked_since_plan"):
            need_plan = f"task {_state.pop('blocked_since_plan')} was blocked"
        if not need_plan and _state.get("done_since_plan", 0) >= CONFIG["plan_every_n_done"]:
            need_plan = f"routine re-plan after {_state['done_since_plan']} completed tasks"
        ready = pickable(board)
        if need_plan and background and ready:
            start_planner(board, need_plan)  # if one is already running, it covers this reason too
            need_plan = None
        elif need_plan or not ready or args.plan:
            if planner_busy():
                set_now("waiting for the background planner", board)
                time.sleep(15)
                continue
            if not ready and not need_plan and not args.plan and any(st["busy"] for st in _lanes.values()):
                set_now("waiting: the ready work is in another lane (or depends on it)", board)
                time.sleep(30)
                continue
            reason = need_plan or "no task is ready to start"
            _state["sync_planning"] = True
            try:
                plan_step(board, reason)
            finally:
                _state["sync_planning"] = False
            _state["done_since_plan"] = 0
            need_plan = None
            if args.plan:
                return 0
            if board.get("project_complete"):
                continue
            if not pickable(board):
                empty_plans += 1
                if empty_plans >= 2:
                    sleep_minutes(CONFIG["stuck_retry_minutes"], board, "STUCK: planning produced no ready tasks")
                    empty_plans = 0
                continue
            empty_plans = 0
        task = claim_task(board, "A")
        if task is None:
            time.sleep(15)
            continue
        run_task(board, task, lane="A")
        if args.once:
            return 0


if __name__ == "__main__":
    sys.exit(main())
