#!/usr/bin/env python3
"""Ask every agent in a project's config (or a preset) to "Reply with exactly: OK", in parallel.

  python ops/probe_models.py "C:/path/to/My Game"        # agents from orchestrator/config.json
  python ops/probe_models.py presets/default.json         # agents from a preset

Reports OK / RATE-LIMITED / PROVIDER DOWN / MODEL GONE / FAILED per agent. Runs from a temp folder so agents
can't touch any project. For "can it actually code?", use scripts/benchmark_models.py instead.
"""
import concurrent.futures as cf
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from scaffold import agent_spec  # noqa: E402

LIMIT = re.compile(r"rate.?limit|usage limit|hit your (\w+ )?limit|too many requests|quota", re.I)
DOWN = re.compile(r"Internal Server Error|Service Unavailable|Bad Gateway|Gateway Timeout|overloaded", re.I)
GONE = re.compile(r"ProviderModelNotFoundError|Model not found")


def agents_from(arg: str) -> dict:
    p = Path(arg)
    if p.is_dir():
        return json.loads((p / "orchestrator" / "config.json").read_text(encoding="utf-8"))["agents"]
    preset = json.loads(p.read_text(encoding="utf-8"))
    return {n: agent_spec(n, s) for n, s in preset["agents"].items()}


def probe(name: str, agent: dict, cwd: str) -> tuple[str, str]:
    cmd = [("Reply with exactly: OK" if c == "{prompt}" else c) for c in agent["cmd"] if c != "{images}"]
    exe = shutil.which(cmd[0]) or cmd[0]
    try:
        r = subprocess.run([exe] + cmd[1:], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=150)
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        return name, "TIMEOUT" + (" (rate-limited?)" if LIMIT.search(out) else "")
    if GONE.search(out):
        return name, "MODEL GONE"
    if LIMIT.search(out[-3000:]):
        return name, "RATE-LIMITED"
    if DOWN.search(out[-3000:]):
        return name, "PROVIDER DOWN"
    return name, "OK" if "OK" in out[-600:] else f"FAILED (rc={r.returncode})"


def main() -> int:
    agents = agents_from(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "presets" / "default.json"))
    with tempfile.TemporaryDirectory(prefix="gce_probe_") as tmp, cf.ThreadPoolExecutor(len(agents)) as pool:
        results = list(pool.map(lambda kv: probe(kv[0], kv[1], tmp), agents.items()))
    for name, verdict in sorted(results):
        print(f"  {name:12} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
