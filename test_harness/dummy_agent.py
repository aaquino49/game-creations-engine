"""Dummy agent for orchestrator tests: does each step instantly-ish and writes the JSON the prompt asks for."""
import json
import os
import random
import re
import sys
import time
from pathlib import Path

msg = sys.argv[-1]
m = re.search(r"Read the file (\S+) and carry out", msg)
prompt_path = Path(m.group(1))
if not prompt_path.is_absolute():
    prompt_path = Path.cwd() / prompt_path
text = prompt_path.read_text(encoding="utf-8")
out = re.findall(r"to: `([^`]+\.json)`", text)[-1]
out_path = Path(out) if Path(out).is_absolute() else Path.cwd() / out
step = re.match(r"# (\w+) step", text).group(1)
tid = (re.search(r"- ID: (T-\d+)", text) or [None, None])[1]

if step == "WORK":
    time.sleep(random.uniform(3, 6))
    f = Path.cwd() / "game" / "scripts" / "sim" / "dummy" / f"{tid}.gd"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"# {tid} written in {Path.cwd().name} pid {os.getpid()}\n", encoding="utf-8")
    shared = re.search(r"game/scripts/sim/dummy/(shared\.gd)", text)
    if shared:
        sf = f.parent / "shared.gd"
        sf.write_text((sf.read_text(encoding="utf-8") if sf.exists() else "") + f"# {tid}\n", encoding="utf-8")
    result = {"status": "done", "summary": f"dummy work for {tid} in {Path.cwd()}", "files_changed": [str(f)],
              "notes_for_qa": ""}
elif step == "QA":
    time.sleep(1)
    result = {"verdict": "pass", "summary": "dummy qa", "issues": [], "tests_added": [], "out_of_scope_bugs": []}
elif step == "REVIEW":
    time.sleep(1)
    result = {"verdict": "approve", "summary": f"dummy approve {tid}", "feedback": "", "new_tasks": []}
elif step == "PLAN":
    time.sleep(25)  # long enough to prove lane A keeps working meanwhile
    result = {"summary": "dummy plan", "promote": [], "new_tasks": [], "update_tasks": [], "milestone_complete": None,
              "project_complete": False}
else:
    result = {"status": "done", "summary": "dummy"}
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(result), encoding="utf-8")
print("OK")
