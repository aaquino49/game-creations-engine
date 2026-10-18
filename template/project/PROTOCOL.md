# Team Protocol

How the agents and the orchestrator work together. All agents read this.

## The team

{{TEAM_TABLE}}

Code tasks are owned by **`coder`**. The orchestrator gives each lane a model from the `coders` list in `orchestrator/config.json` and **alternates models between attempts** when there is more than one, so a task one model fails gets a fresh pair of eyes. QA of a code task never goes to the model that wrote it.

There is no human in the loop. Never ask questions or wait for a reply. When something is ambiguous, choose the option most consistent with the GDD, write it to `project/assumptions.md` (one line: date, task, assumption), and continue.

## Task lifecycle

```
backlog --(Claude plans)--> ready --(orchestrator picks)--> in_progress
in_progress: WORK (coder) -> CHECKS (automatic) -> QA (Codex, code tasks only) -> CHECKS -> REVIEW (Claude)
   approve -> commit -> done
   revise  -> next attempt (max 3, models alternate), feedback passed back to the worker
   block / 3 failed attempts -> changes reverted -> blocked -> Claude re-plans
done | blocked | dropped
```

- Several lanes run in parallel. Lane A works in the repo; the other lanes (B, C, ...) each work in their own git worktree and are merged after approval. Two tasks run side by side only when their briefs name different files. Planning runs in the background.
- **Agents never run `git commit`, `git reset`, `git checkout` or `git stash`.** The orchestrator owns git. Agents may run `git diff` and `git status`.
- **Agents never edit `project/board.json`.** They report results through their output JSON file.

## Files

| Path | Writer | Purpose |
|---|---|---|
| `project/GDD.md` | Claude | Game design (source of truth for what to build) |
| `project/ARCHITECTURE.md` | Claude | Code conventions and commands |
| `project/ART_GUIDE.md` | Claude | Art style and asset pipeline |
| `project/board.json` | orchestrator | All tasks and statuses |
| `project/tasks/T-###.md` | Claude (brief), orchestrator (log section) | Task brief and history |
| `project/decisions.md` | Claude | Decisions with reasons |
| `project/assumptions.md` | any agent (append only) | Assumptions made instead of asking |
| `project/PM_NOTES.md` | Claude | Running narrative for the human owner |
| `project/OWNER_REQUESTS.md` | owner | Requests the quarterback must turn into tasks |
| `project/STATUS.md` | orchestrator | Live status page (not in git) |
| `project/milestones/M#.md` | Claude | Milestone report |
| `project/runs/T-###/a#/` | orchestrator + agents | Prompts, logs, screenshots, result JSON for each attempt (not in git) |

## Output contracts

Each step's prompt names an exact output path. Write **valid JSON only** to that path, as the last thing you do.

**Work** (`work.json`):
```json
{"status": "done" | "blocked", "summary": "what you did (2-5 sentences)",
 "files_changed": ["game/..."], "notes_for_qa": "how to verify / what to look at",
 "blocked_reason": "only if blocked"}
```

**QA** (`qa.json`):
```json
{"verdict": "pass" | "fail", "summary": "...",
 "issues": [{"severity": "blocker" | "major" | "minor", "description": "..."}],
 "tests_added": ["game/tests/..."],
 "out_of_scope_bugs": [{"title": "...", "description": "..."}]}
```
Fail only for blocker or major issues that are *within this task's acceptance criteria*. Minor issues and out-of-scope bugs don't fail a task.

**Review** (`review.json`):
```json
{"verdict": "approve" | "revise" | "block", "summary": "one line for the log",
 "feedback": "specific instructions for the next attempt (if revise)",
 "new_tasks": [ <task objects, see below> ]}
```

**Plan** (`plan.json`):
```json
{"summary": "...", "promote": ["T-###"],
 "new_tasks": [ <task objects> ],
 "update_tasks": [ {"id": "T-###", "<field>": "<value>"} ],
 "milestone_complete": "M1" | null, "project_complete": false}
```

**Task object** (for new tasks):
```json
{"title": "...", "milestone": "M2", "type": "code" | "asset" | "qa" | "design",
 "owner": "coder" | "codex" | "claude", "priority": 1-5 (1 = most urgent),
 "depends_on": ["T-###"], "description": "...", "acceptance": ["testable criterion", "..."],
 "scenario": "default", "skip_qa": false}
```
- `owner`: `coder` for code (the orchestrator picks the coding model per lane), `codex` for asset and qa tasks, `claude` for design tasks. Naming a specific coding agent from `coders` pins a code task's first attempt to it.
- `skip_qa: true` (or a title starting with "Polish:", "Cleanup:", "Chore:") skips the QA step for small, low-risk tasks.
- Updatable fields: title, description, acceptance, priority, depends_on, owner, type, scenario, milestone, skip_qa, and status (only to `backlog`, `ready` or `dropped`).

## Quality bar for any change

- The project imports, all tests pass, and the 300-frame smoke run shows no errors. The orchestrator checks this and won't commit otherwise.
- Follow `project/ARCHITECTURE.md`. Stay within the task's scope. Note other problems you find as out-of-scope bugs instead of fixing them.
- Visible changes are shown in the task's screenshot scenario (`game/dev/scenarios/<scenario>.gd`).
