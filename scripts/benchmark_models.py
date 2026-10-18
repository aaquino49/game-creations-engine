#!/usr/bin/env python3
"""Benchmark OpenCode models on a tiny agentic coding task, in parallel.

Each model gets its own folder with a buggy GDScript function and must fix it to match its doc comment, then write
result.json. This tests the three things a coder needs: it is available (not rate-limited), it can use tools to
edit files, and it reads a rule correctly.

  python benchmark_models.py                      # all free OpenCode models (names ending in -free)
  python benchmark_models.py opencode/beam-free meta/muse-spark-1.3-contributor
  python benchmark_models.py --dir C:/tmp/bench --timeout 240

Run it from a short path (Windows path-length limits) and never inside a project repo.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import re
import shutil
import subprocess
import time
from pathlib import Path

BUGGY = '''class_name CombatRules
extends RefCounted

## hit% = clamp(skill_acc + attacker_acc - target_dodge - cover, 5, 95); cover is 0 when flanked or melee.
static func hit_chance(skill_acc: int, attacker_acc: int, target_dodge: int, cover: int, flanked: bool, melee: bool) -> int:
\tvar c := cover
\tif flanked:
\t\tc = cover
\tvar hit := skill_acc + attacker_acc + target_dodge - c
\treturn clamp(hit, 0, 100)
'''
PROMPT = ("The function hit_chance in combat_rules.gd does not follow its doc comment. Fix it so it matches the "
          "documented formula exactly (cover counts as 0 when flanked or when melee; clamp to 5..95; keep the return type "
          "int). Then create result.json containing {\"status\": \"done\"}. Do not create any other files.")


def judge(code: str) -> bool:
    body = code.split("-> int:", 1)[-1]
    return ("- target_dodge" in body and "+ target_dodge" not in body and re.search(r"clampi?\(\s*hit\s*,\s*5\s*,\s*95", body)
            is not None and re.search(r"flanked\s+or\s+melee|melee\s+or\s+flanked", body) is not None)


def run(model: str, root: Path, timeout: int) -> dict:
    d = root / re.sub(r"[^A-Za-z0-9._-]", "_", model)
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    (d / "combat_rules.gd").write_text(BUGGY, encoding="utf-8")
    exe = shutil.which("opencode") or "opencode"
    start = time.time()
    try:
        out = subprocess.run([exe, "run", "--auto", "--print-logs", "--log-level", "ERROR", "-m", model, PROMPT], cwd=d,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        log, timed_out = out.stdout + out.stderr, False
    except subprocess.TimeoutExpired as e:
        log, timed_out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), True
    secs = time.time() - start
    correct = judge((d / "combat_rules.gd").read_text(encoding="utf-8"))
    return {"model": model, "secs": round(secs), "correct": correct, "result_json": (d / "result.json").exists(),
            "rate_limited": "Rate limit" in log or "Too Many Requests" in log, "timed_out": timed_out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*")
    ap.add_argument("--dir", default=str(Path.home() / "model_bench"))
    ap.add_argument("--timeout", type=int, default=240)
    a = ap.parse_args()
    models = a.models
    if not models:
        listing = subprocess.run([shutil.which("opencode") or "opencode", "models"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=120).stdout
        models = sorted(m for m in listing.split() if m.endswith("-free"))
    root = Path(a.dir)
    root.mkdir(parents=True, exist_ok=True)
    with cf.ThreadPoolExecutor(max_workers=max(1, len(models))) as pool:
        results = list(pool.map(lambda m: run(m, root, a.timeout), models))
    results.sort(key=lambda r: (not r["correct"], r["timed_out"], r["secs"]))
    print(f"{'model':45} {'verdict':12} {'secs':>5}  notes")
    for r in results:
        verdict = "GOOD" if r["correct"] and r["result_json"] and not r["timed_out"] else \
            "SLOW/HANGS" if r["correct"] else "RATE-LIMITED" if r["rate_limited"] else "FAILED"
        notes = ", ".join(k for k in ("rate_limited", "timed_out") if r[k])
        print(f"{r['model']:45} {verdict:12} {r['secs']:>5}  {notes}")


if __name__ == "__main__":
    main()
