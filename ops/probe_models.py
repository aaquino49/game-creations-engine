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
    by_account: dict = {}
    for name, agent in agents.items():
        by_account.setdefault(agent.get("account", name), []).append((name, agent))
    firsts = [(acct, members[0][0], members[0][1], [m[0] for m in members]) for acct, members in by_account.items()]
    with tempfile.TemporaryDirectory(prefix="gce_probe_") as tmp, cf.ThreadPoolExecutor(len(firsts)) as pool:
        results = list(pool.map(lambda t: (t[0], t[3], t[1], probe(t[1], t[2], tmp)[1]), firsts))
    for acct, members, name, verdict in sorted(results):
        model = agents[name].get("model", "?")
        shared = "" if members == [name] else f" (shared by {', '.join(members)})"
        print(f"  {acct:12} {verdict:12} {name} [{model}]{shared}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
