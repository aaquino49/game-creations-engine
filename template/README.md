# {{GAME_NAME}}

{{PITCH}}

Design: [project/GDD.md](project/GDD.md). Architecture: [project/ARCHITECTURE.md](project/ARCHITECTURE.md). Art: [project/ART_GUIDE.md](project/ART_GUIDE.md).

## Play

- **From source:** double-click `play.bat` (runs `builds/{{EXE_NAME}}.exe` if it exists, otherwise `godot --path game`). Needs Godot 4 on PATH.
- **Windows build** (from the release milestone): `builds/{{EXE_NAME}}.exe`.

## The AI team

Built by an autonomous team driven by `orchestrator/orchestrator.py` (plain Python, no AI):

{{TEAM_TABLE}}

Each task goes **work → automatic checks (import, tests, smoke, screenshot) → QA → Claude review → commit**, up to 3 attempts, in several parallel lanes (lane A in this folder, the others in git worktrees). Planning runs in the background. `orchestrator/supervisor.py` relaunches a dead orchestrator and calls a headless AI fixer when the team stalls.

## Running it

| What | How |
|---|---|
| Start the team | `start.bat` (auto-restarts on crashes) |
| Keep it alive and unstuck | `supervise.bat` |
| Stop after the current step | `stop.bat` (creates `project/STOP`) |
| Reload orchestrator code between tasks | create an empty `project/RESTART` |
| Plan right now (after adding an owner request) | create an empty `project/PLAN_NOW` |
| Live status | `project/STATUS.md` |
| Full event log | `project/events.log` |
| Phone alerts | subscribe in the ntfy app to the topic in `orchestrator/config.local.json` (untracked: anyone who knows the topic can read and send alerts) |
| Steer the team | write a request under **Open** in `project/OWNER_REQUESTS.md` |
| Change models | edit `coders` / `fallback` in `orchestrator/config.json`, commit, create `project/RESTART` |

One-offs: `python orchestrator/orchestrator.py --plan` (one planning step), `--once` (one task), `--task T-007`.
