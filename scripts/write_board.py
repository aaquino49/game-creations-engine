#!/usr/bin/env python3
"""Write the initial backlog: project/board.json plus one brief per task in project/tasks/.

Only for setup, before the orchestrator first runs (afterwards the orchestrator owns board.json and the
quarterback adds tasks through plan.json).

  python write_board.py <project dir> <tasks.json>

tasks.json is a list of task objects:
  {"id": "T-001", "title": "...", "milestone": "M1", "type": "code|asset|qa|design",
   "owner": "coder|codex|claude", "priority": 1, "depends_on": [], "scenario": "default",
   "acceptance": ["testable criterion", ...], "status": "ready|backlog", "skip_qa": false,
   "brief": "## Goal\\n\\n... full markdown brief (Files, API, Rules, Tests, Pitfalls) ..."}
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
specs = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
board_path = root / "project" / "board.json"
board = json.loads(board_path.read_text(encoding="utf-8")) if board_path.exists() else \
    {"project": root.name, "next_id": 1, "tasks": [], "milestones_complete": ["M0"], "v1_complete": False,
     "project_complete": False}
existing = {t["id"] for t in board["tasks"]}
for s in specs:
    tid = s["id"]
    if tid in existing:
        raise SystemExit(f"{tid} already exists")
    task = {"id": tid, "title": s["title"], "milestone": s.get("milestone", "M1"), "type": s.get("type", "code"),
            "owner": s.get("owner", "coder"), "priority": int(s.get("priority", 3)),
            "depends_on": list(s.get("depends_on", [])), "description": s.get("description", s["title"]),
            "acceptance": list(s.get("acceptance", [])), "scenario": s.get("scenario", "default"),
            "skip_qa": bool(s.get("skip_qa", False)), "status": s.get("status", "backlog"),
            "attempts": 0, "history": [], "source": "setup"}
    board["tasks"].append(task)  # a "ready" task with open dependencies waits until they are done
    crit = "\n".join(f"- {a}" for a in task["acceptance"])
    (root / "project" / "tasks").mkdir(parents=True, exist_ok=True)
    (root / "project" / "tasks" / f"{tid}.md").write_text(
        f"# {tid}: {task['title']}\n\nMilestone: {task['milestone']} | Type: {task['type']} | Owner: {task['owner']} | "
        f"Scenario: `{task['scenario']}` | Depends on: {', '.join(task['depends_on']) or '-'}\n\n{s.get('brief', '').strip()}\n\n"
        f"## Acceptance criteria\n\n{crit}\n\n## Log\n", encoding="utf-8", newline="\n")
nums = [int(t["id"].split("-")[1]) for t in board["tasks"] if t["id"].startswith("T-")]
board["next_id"] = max(nums, default=0) + 1
board_path.write_text(json.dumps(board, indent=2), encoding="utf-8")
print(f"{len(specs)} task(s) written; next_id = {board['next_id']}")
