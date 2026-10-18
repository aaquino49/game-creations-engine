"""Build a throwaway clone of a studio repo wired to dummy agents, 3 lanes and a synthetic 10-task board.

  python setup_test.py <real repo> <orchestrator.py to test> <short base dir, e.g. C:/Users/me/studio_test>
  cd <base>/clone && python orchestrator/orchestrator.py      (create <base>/clone/project/STOP to end it)

Then check project/events.log: tasks spread across lanes A/B/C, a [background] PLAN, every lane merged, all 10
dummy files on main (git ls-files game/scripts/sim/dummy), no ERROR lines. (T-009/T-010 share a file: worktree lanes never take them together; lane A may, since it never idles, and the merge logic handles it.)
Never run the test orchestrator inside the real repo.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1])          # real repo
NEW_ORCH = Path(sys.argv[2])     # patched orchestrator.py
BASE = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE
BASE.mkdir(parents=True, exist_ok=True)
T = BASE / "clone"
for p in (T, BASE / "wt_B", BASE / "wt_C"):
    if p.exists():
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(p)], capture_output=True)
subprocess.run(["git", "clone", "-q", str(SRC), str(T)], check=True)
subprocess.run(["git", "-C", str(T), "config", "user.email", "test@example.com"], check=True)
subprocess.run(["git", "-C", str(T), "config", "user.name", "lane test"], check=True)
shutil.copy2(NEW_ORCH, T / "orchestrator" / "orchestrator.py")
(HERE / "fake_godot.cmd").write_text(f'@python "{HERE / "fake_godot.py"}" %*\r\n', encoding="utf-8")

cfg = json.loads((T / "orchestrator" / "config.json").read_text(encoding="utf-8"))
dummy = ["python", str(HERE / "dummy_agent.py"), "{prompt}"]
for a in list(cfg["agents"]):
    cfg["agents"][a] = {"cmd": dummy}
cfg.update(godot=str(HERE / "fake_godot.cmd"), handoff_at_percent={}, notify={}, plan_every_n_done=4,
           agent_timeout_minutes=5, lanes=[{"name": "B", "dir": str(BASE / "wt_B")}, {"name": "C", "dir": str(BASE / "wt_C")}])
(T / "orchestrator" / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

tasks = []
for i in range(1, 11):
    tid = f"T-{i:03d}"
    files = [f"game/scripts/sim/dummy/{tid}.gd"]
    if i in (9, 10):  # these two name the same file: must never run at the same time
        files.append("game/scripts/sim/dummy/shared.gd")
    tasks.append({"id": tid, "title": f"Dummy task {i}", "milestone": "M1", "type": "code", "owner": "coder",
                  "priority": 3, "depends_on": [], "description": "dummy", "acceptance": ["file exists"],
                  "scenario": "default", "skip_qa": False, "status": "ready", "attempts": 0, "history": [],
                  "source": "test"})
    (T / "project" / "tasks").mkdir(parents=True, exist_ok=True)
    (T / "project" / "tasks" / f"{tid}.md").write_text(
        f"# {tid}: Dummy task {i}\n\nFiles: {', '.join(files)}\n\n## Log\n", encoding="utf-8")
board = {"project": "test", "next_id": 11, "tasks": tasks, "milestones_complete": [], "v1_complete": False,
         "project_complete": False}
(T / "project" / "board.json").write_text(json.dumps(board, indent=2), encoding="utf-8")
for f in ("events.log", "STATUS.md", "STOP", "RESTART"):
    (T / "project" / f).unlink(missing_ok=True)
subprocess.run(["git", "-C", str(T), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(T), "commit", "-q", "-m", "test setup"], check=True)
print(T)
