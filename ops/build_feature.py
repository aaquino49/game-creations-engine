#!/usr/bin/env python3
"""Spec-driven build: a coding model implements a spec, then the tests run. Claude only reads the short summary.

  python ops/build_feature.py docs/specs/office-phase1.md
  python ops/build_feature.py docs/specs/office-phase1.md --feedback docs/specs/office-phase1.qa1.md
  python ops/build_feature.py SPEC --model opencode/deepseek-v4.1-flash-free --variant ""   (any OpenCode model)

The split keeps the expensive reviewer's tokens down: a planner (Claude) writes a compact spec with acceptance
criteria, the coder (default: Muse Spark via OpenCode, high reasoning) writes the code AND the tests, and this script
prints only what QA needs: the coder's REPORT, `git status`, the diffstat and the tail of the test run. The full coder
transcript is saved under ops/build_logs/ for when something needs a closer look. Nothing is committed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOGS = REPO / "ops" / "build_logs"
DEFAULT_MODEL = "meta/muse-spark-1.3-contributor"
DEFAULT_TEST = "python -m unittest discover -s tests -t ."
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

PROMPT = """You are the coder on this repository. A reviewer wrote a spec; implement it completely.

Spec: `{spec}` (read it first, then read the code it names before changing anything).
{feedback}
Rules:
- Implement every requirement and acceptance criterion in the spec. Match the surrounding code's style, comment
  density and naming. Standard library only unless the spec says otherwise.
- Write the tests the spec asks for. Run `{test}` from the repository root and fix things until it passes.
- Stay inside the spec's scope: don't refactor unrelated code, don't touch files the spec doesn't call for.
- Do NOT commit, push, or change git state. Leave your changes in the working tree.
- Finish your final message with a section that starts with the line `REPORT` containing, briefly: files changed,
  tests added and the last test result, any requirement you could not meet (and why), and any decision you made
  that the spec left open.
"""


def run(cmd: list[str], timeout: float | None = None, log: Path | None = None) -> tuple[int, str]:
    exe = shutil.which(cmd[0]) or cmd[0]
    p = subprocess.Popen([exe] + cmd[1:], cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        out, _ = p.communicate()
        out += b"\n[build_feature] TIMED OUT\n"
    text = ANSI_RE.sub("", out.decode("utf-8", errors="replace"))
    if log:
        log.write_text(f"$ {' '.join(cmd)}\n(rc={p.returncode})\n\n{text}", encoding="utf-8")
    return p.returncode, text


def tail(text: str, n: int) -> str:
    lines = text.rstrip().splitlines()
    return "\n".join((["..."] if len(lines) > n else []) + lines[-n:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="spec file (Markdown), relative to the repo root")
    ap.add_argument("--feedback", help="QA notes from a previous round for the coder to address")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenCode provider/model (default {DEFAULT_MODEL})")
    ap.add_argument("--variant", default="high", help="reasoning effort; empty string to omit (default high)")
    ap.add_argument("--test", default=DEFAULT_TEST, help=f"test command (default: {DEFAULT_TEST})")
    ap.add_argument("--timeout", type=float, default=120, help="minutes before the coder is stopped (default 120)")
    ap.add_argument("--tests-only", action="store_true", help="skip the coder; just print the summary and tests")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # coder reports contain arrows etc.; cp1252 can't

    spec = Path(a.spec)
    if not (REPO / spec).is_file():
        print(f"No spec at {spec}")
        return 2
    LOGS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = spec.stem + ("-fix" if a.feedback else "")
    started = time.time()

    if not a.tests_only:
        fb = (f"\nQA feedback from the reviewer is in `{Path(a.feedback).as_posix()}`. Address every item in it; the "
              f"rest of your earlier work is already in the working tree.\n") if a.feedback else ""
        prompt_file = LOGS / f"{name}-{stamp}.prompt.md"
        prompt_file.write_text(PROMPT.format(spec=spec.as_posix(), feedback=fb, test=a.test), encoding="utf-8")
        cmd = ["opencode", "run", "--auto", "--print-logs", "--log-level", "ERROR", "-m", a.model]
        if a.variant:
            cmd += ["--variant", a.variant]
        cmd += ["--title", name, f"Read the file {prompt_file.relative_to(REPO).as_posix()} and carry out "
                                 f"the instructions in it exactly."]
        log = LOGS / f"{name}-{stamp}.log"
        print(f"Coder: {a.model} {a.variant or ''} - log: {log.relative_to(REPO).as_posix()}", flush=True)
        rc, out = run(cmd, timeout=a.timeout * 60, log=log)
        report = out[out.rfind("REPORT"):] if "REPORT" in out else "(no REPORT section; see the log)\n" + tail(out, 25)
        print(f"\n== CODER (rc={rc}, {(time.time() - started) / 60:.0f} min) ==\n{tail(report, 60)}")
        if re.search(r"rate.?limit|429|insufficient.?(quota|credit)", out, re.I) and rc != 0:
            print("!! the coder output mentions a rate/credit limit")

    _, status = run(["git", "status", "--short"])
    _, stat = run(["git", "diff", "--stat", "HEAD"])
    print(f"\n== CHANGES ==\n{status.rstrip() or '(none)'}\n{tail(stat, 3)}")
    rc, out = run(["cmd", "/c", a.test] if sys.platform == "win32" else ["sh", "-c", a.test], timeout=1800)
    (LOGS / f"{name}-{stamp}.tests.log").write_text(out, encoding="utf-8")
    print(f"\n== TESTS ({'PASS' if rc == 0 else 'FAIL'}, rc={rc}) ==\n{tail(out, 15 if rc == 0 else 40)}")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
