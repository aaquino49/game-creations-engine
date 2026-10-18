#!/usr/bin/env python3
"""One-screen health view of a running game project.

  python ops/status.py "C:/path/to/My Game"

Shows: whether the orchestrator and supervisor are running, STOP/RESTART/PLAN_NOW flags, what each lane is doing,
the milestone table, which models are currently routed around (limits, outages), and the last events.
"""
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path


def processes() -> list[str]:
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
          "Where-Object { $_.CommandLine -like '*orchestrator.py*' -or $_.CommandLine -like '*supervisor.py*' } | "
          "ForEach-Object { $_.CommandLine }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout
    except Exception:  # noqa: BLE001
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


def main() -> int:
    project = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    p = project / "project"
    procs = processes()
    print(f"== {project.name}  ({dt.datetime.now():%Y-%m-%d %H:%M})")
    print(f"orchestrator: {'RUNNING' if any('orchestrator.py' in x for x in procs) else 'down'}   "
          f"supervisor: {'RUNNING' if any('supervisor.py' in x for x in procs) else 'down'}")
    flags = [f for f in ("STOP", "RESTART", "PLAN_NOW") if (p / f).exists()]
    print(f"flags: {', '.join(flags) or 'none'}")
    status = (p / "STATUS.md").read_text(encoding="utf-8", errors="replace") if (p / "STATUS.md").exists() else ""
    for line in status.splitlines():
        if line.startswith(("**Now:**", "**Current task:**", "**Lane ", "**Planner:**")) or line.startswith("| M"):
            print(line)
    try:
        board = json.loads((p / "board.json").read_text(encoding="utf-8"))
        from collections import Counter
        print("tasks:", dict(Counter(t["status"] for t in board["tasks"])),
              "| complete" if board.get("project_complete") else "")
    except (OSError, ValueError):
        pass
    try:
        events = (p / "events.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        events = []
    now = dt.datetime.now()
    routed = {}  # agent -> (kind, account, until)
    for line in events[-600:]:
        m = re.match(r"(\S+ \S+)\s+(USAGE LIMIT|PROVIDER DOWN|MODEL GONE|PREEMPTIVE HANDOFF|QUOTA RESTORED) ([\w-]+)(?: \(([\w-]+)\))?", line)
        if not m:
            continue
        when = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        if m.group(2) == "QUOTA RESTORED":  # names an account: clear every agent on it
            routed = {k: v for k, v in routed.items() if v[1] != m.group(3)}
            continue
        u = re.search(r"until ~(?:\w{3} )?(\d{1,2}):(\d{2})", line)
        until = when.replace(hour=int(u.group(1)), minute=int(u.group(2)), second=0) if u else when + dt.timedelta(hours=1)
        if until < when:
            until += dt.timedelta(days=1)
        routed[m.group(3)] = (m.group(2), m.group(4) or m.group(3), until)
    live = {k: v for k, v in routed.items() if v[2] > now}
    if live:
        print("routed around now:", ", ".join(f"{k} ({v[0].lower()} until ~{v[2]:%H:%M})" for k, v in live.items()))
    print("\nlast events:")
    for line in events[-15:]:
        print("  " + line[:160])
    return 0


if __name__ == "__main__":
    sys.exit(main())
