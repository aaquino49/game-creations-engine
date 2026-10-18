# Supervising a running game

The team runs without you. Two things watch it:

1. **`supervisor.py`** (launched by `supervise.bat`). Plain Python, runs every 2 minutes, no chat window needed. It relaunches a dead orchestrator, notices stalls (no progress for `supervisor.stall_minutes`, a lane idle for `lane_idle_minutes` while work is ready), sends a phone alert, and calls a headless "fixer" agent (`supervisor.agents`, e.g. claude → codex → a paid agent) with `project/roles/supervisor.md` as its guide.
2. **A Claude check-in** (optional, a second layer). While a Claude Code chat stays open, ask Claude to schedule a recurring check-in. Session cron jobs only fire while that chat is open and idle, so they're a convenience, not a guarantee.

## Starting the check-in

Paste this into Claude Code, after filling in the angle brackets:

> Set a check-in every 20 minutes to supervise the autonomous team in `<project folder>`. Use the prompt in `<engine>/docs/supervising.md`.

Claude will call CronCreate with a schedule such as `7,27,47 * * * *` (off the round minutes) and the prompt below.

## The check-in prompt (template)

Replace `<...>` with the game's details. Keep the project-specific policy lines in step 3 and 4 current as the owner changes their mind, and recreate the cron job when you do.

```text
<Game> 20-minute health check (supervising the autonomous team in <project folder>). Current goal: <milestones in
flight, open owner requests>. supervisor.py also auto-detects stalls and calls a headless fixer; this check is the
second layer.

1. Alive? `python ... orchestrator.py` and `pythonw ... supervisor.py`. If the orchestrator is down and project/STOP
   doesn't exist, relaunch with `explorer.exe start.bat`; if supervisor.py is down, `explorer.exe supervise.bat`.
   If project/RESTART has existed 70+ minutes, find out why.
   (Shortcut: python <engine>/ops/status.py "<project folder>")
2. Read the tail of project/events.log (~40 lines) and the top of project/STATUS.md. Since the last check, has at
   least one WORK/CHECKS/QA/REVIEW/DONE happened? Trouble signs: repeated AGENT FAIL/timeouts, "WORK produced no
   result", ORCHESTRATOR/LANE/PLANNER ERROR, QUICK FAIL loops, STUCK, repeated BLOCKED, CHECKS failing every attempt,
   "waiting to merge" repeating, lanes idle 20+ min while ready tasks exist, no events for 30+ min, false "blocked"
   reports.
3. Model policy (owner, <date>; see orchestrator/config.json): coders = <agents>, fallback <chain>. <Who does QA and
   art>. Art tasks have NO fallback and wait for an agent with image generation; if an art task ever runs on another
   agent, that's a bug: fix it. Don't change which models code unless the owner says so.
4. Art quality: when an asset task finishes, look at its contact sheet (project/runs/<task>/a<n>/contact_sheet.png)
   and tell the owner if the style drifts from project/ART_GUIDE.md (<one-line style summary>).
5. Real problem: diagnose from project/runs/<task>/a<n>/ logs and fix the root cause (orchestrator/config/tooling/
   broken brief). Never edit project/board.json while the orchestrator runs. Test non-trivial orchestrator changes
   with `python <engine>/ops/test_orchestrator.py "<project folder>" --orchestrator <patched copy>` (it works on a
   throwaway clone). Commit fixes before touching project/RESTART; log a "SUPERVISOR ..." line in events.log.
   To force a plan (e.g. after adding an owner request) create project/PLAN_NOW.
6. Report to the owner in 2-4 lines: progress (tasks done, milestone), which models are working, any fix made. If
   all is healthy and nothing notable changed, one line.
```

An optional hourly companion check, useful when free models are in the lineup:

```text
Hourly: run `python <engine>/ops/probe_models.py "<project folder>"`. If a free model the owner prefers for coding is
OK again and the coders list is on a fallback, switch `coders` back in orchestrator/config.json, commit, and create
project/RESTART. Tell the owner in one line.
```

## What to check, in order

1. Processes alive (`ops/status.py` shows both).
2. `events.log` since the last check: any DONE? Repeated AGENT FAIL, QUICK FAIL, "waiting to merge", ERROR, STUCK, BLOCKED loops?
3. `STATUS.md`: idle lanes while ready tasks exist? Check the ready tasks' dependencies before calling it a bug. Often it's a real chain.
4. Who is coding (STATUS lane lines, FALLBACK lines). A paid agent coding for 2+ hours when it should be a fallback → probe the free models.
5. Diagnose from `project/runs/<task>/a<n>/` (prompt, agent logs, checks log, JSON results). Fix the machinery, not the game code.

## Rules that kept Grim Haven healthy

- Fix the **machinery** (orchestrator, config, tooling, a broken brief), not game code. Steer content through `project/OWNER_REQUESTS.md`.
- Never edit `project/board.json` while the orchestrator runs. Never start a second orchestrator inside the real repo.
- Before calling something a bug, check the boring explanation: an idle lane is often a real dependency chain, and a paid fallback is often a real rate limit.
- Delete a pending `project/RESTART` before editing the orchestrator, then commit and recreate it. Use a hard restart (kill the process tree, relaunch `start.bat`) only when a lane is wedged; recovery saves in-flight work as patches.
- Model and money changes are the owner's call. Write them into config (`coders`, `fallback`, `paid_agents`) with a dated `_notes` line.
- When the game is done, or at a milestone, bring improvements home: `python ops/sync_from_project.py "<project folder>" --apply` in the engine, then log the lesson in `docs/PLAYBOOK.md`.
