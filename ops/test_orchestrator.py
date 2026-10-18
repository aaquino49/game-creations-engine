#!/usr/bin/env python3
"""End-to-end test of the orchestrator with dummy agents and a fake Godot (no real models, about 3 minutes).

  python ops/test_orchestrator.py                          # test the ENGINE: scaffold a fresh project and run it
  python ops/test_orchestrator.py "C:/path/to/My Game"     # test a live project's orchestrator (on a throwaway clone)
  python ops/test_orchestrator.py "C:/path/to/My Game" --orchestrator C:/tmp/orchestrator_new.py

Checks: 10 dummy tasks all DONE; lanes A, B and C all used; worktree merges land on main; at most one planner at a
time; PLAN_NOW triggers a background plan; no ERROR events. The clone lives in a short path outside OneDrive
(default C:/Users/<you>/gce_test) and is deleted afterwards (--keep to inspect it).
It never touches the project you name: it clones it.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
HARNESS = ENGINE / "test_harness"


def rmtree(p: Path) -> None:
    if p.exists():
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(p)], capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", nargs="?")
    ap.add_argument("--orchestrator", help="orchestrator.py to test (default: the project's own)")
    ap.add_argument("--base", default=str(Path.home() / "gce_test"))
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    base = Path(a.base)
    rmtree(base)
    base.mkdir(parents=True)
    if a.project:
        src = Path(a.project).resolve()
    else:  # scaffold a fresh project from the engine and commit it, so the test exercises the template itself
        src = base / "src"
        subprocess.run([sys.executable, str(ENGINE / "scripts" / "scaffold.py"), "--target", str(src), "--name", "Engine Test",
                        "--pitch", "Orchestrator self-test.", "--lane-root", str(base)], check=True, capture_output=True)
        for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q", "-m", "scaffold"]):
            subprocess.run(cmd, cwd=src, check=True, capture_output=True)
    orch = Path(a.orchestrator) if a.orchestrator else src / "orchestrator" / "orchestrator.py"
    subprocess.run([sys.executable, str(HARNESS / "setup_test.py"), str(src), str(orch), str(base)], check=True,
                   capture_output=True)
    clone = base / "clone"
    if not (clone / "project" / "tasks" / "T-010.md").exists():
        print("FAIL: harness clone was not built")
        return 1

    def poke() -> None:
        time.sleep(45)
        (clone / "project" / "PLAN_NOW").touch()
        time.sleep(95)
        (clone / "project" / "STOP").touch()
    threading.Thread(target=poke, daemon=True).start()
    print(f"Running the orchestrator on {clone} (about 2.5 minutes)...")
    subprocess.run([sys.executable, str(clone / "orchestrator" / "orchestrator.py")], cwd=clone, capture_output=True,
                   timeout=420)
    lines = (clone / "project" / "events.log").read_text(encoding="utf-8").splitlines()
    done = len({l.split("DONE ")[1].split()[0] for l in lines if "  DONE T-" in l})
    lanes = {ln for ln in ("A", "B", "C") if any(f"[lane {ln}]" in l for l in lines)}
    merged = sum(1 for l in lines if re.search(r"LANE [BC] merged T-", l))
    active = peak = 0
    for l in lines:
        if "PLAN start" in l:
            active += 1
            peak = max(peak, active)
        if "PLAN done" in l or "PLAN failed" in l:
            active -= 1
    plan_now = any("PLAN_NOW" in l and "PLAN start" in l for l in lines)
    errors = [l for l in lines if "ERROR" in l]
    files = subprocess.run(["git", "ls-files", "game/scripts/sim/dummy"], cwd=clone, capture_output=True,
                           text=True).stdout.split()
    checks = [("10 dummy tasks DONE", done >= 10, done), ("lanes A, B, C used", lanes == {"A", "B", "C"}, sorted(lanes)),
              ("worktree merges", merged >= 2, merged), ("10 files on main", len(files) >= 10, len(files)),
              ("max one planner", peak <= 1, peak), ("PLAN_NOW triggered", plan_now, plan_now),
              ("no ERROR events", not errors, errors[:2])]
    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}  ({detail})")
    if not a.keep:
        rmtree(base)
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
