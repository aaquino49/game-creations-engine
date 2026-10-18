# Office Phase 4: Settings (roster, fallbacks, lanes), bench, approval gate, spend cap

Follow shared conventions C1-C9 in `docs/specs/office-phase1.md`. Phases 1-3 are implemented. Read
`template/office/` and `tests/` first, then these parts of `template/orchestrator/orchestrator.py`:
- lines 30-160: CONFIG, lanes, `resolve_owner`, `CODER_OWNERS`, `coders`, `resolve_worker`
- `limited_until`, `fallback_for`, `probe_agent`, `call_agent`
- `run_task`: the review → approve → commit/merge block
- `process_commands` (the Phase 2 command inbox)

Also read `scripts/scaffold.py` (how `cmd` arrays are built per kind) and `examples/grim-haven/config.json`
(a real config: note the `_notes` keys and the `lanes` list of `{name, dir}`).

Everything in this phase is manage-mode only, except the read-only displays that are called out.

## Safety rules for editing config.json (apply to F1-F3)
- The Office never accepts a free-form `cmd`. A model change replaces only the value after `-m` / `--model`
  inside the agent's existing `cmd`. If the cmd has no such flag, the model can't be edited from the Office
  (shown read-only with a note). Model ids must match `^[\w./:@-]{1,100}$`.
- New positions may only be of kind `opencode`, `claude` or `codex`. Their `cmd` is copied from an existing agent
  of the same kind with the model replaced; if there is none, build it the way `scaffold.py` does. Labels are
  plain text up to 40 chars; account ids match `^[\w-]{1,40}$`.
- `POST /api/config` takes `{"base_mtime": <mtime from GET>, "changes": {...}}`.
  - Validate the whole resulting config: every agent named in coders, paid_agents, roles, fallback chains and
    disabled_agents exists; chains have no duplicates; there is at least one coder; lanes are within limits.
  - Return 409 if the file changed since `base_mtime`.
  - Before writing, copy the current file to `orchestrator/config.backups/config-<YYYYmmdd-HHMMSS>.json` and keep
    only the newest 20.
  - Write atomically, preserving key order and unknown keys (including `_notes`), `indent=2`.
  - Append the event `OFFICE config changed: <short summary>` and return
    `{"ok": true, "restart_needed": bool, "mtime": ...}`.
- `GET /api/config` (manage only) returns the parsed config plus its `mtime`, and `models`: a list from
  `opencode models` cached for 1 h in a background thread (resolve the exe with `shutil.which`, 60 s timeout,
  `[]` on failure). It also returns `paid` and `kinds` per agent.
- After a save that needs a restart, the UI shows a banner: "Saved. Restart the team to apply", with a
  **Restart now** button that uses the existing control action.

## F1. Roster editor: Settings view, "Team" section
The view switcher gains **Settings** (manage mode only; deep link `?view=settings`). The Team section has one card
per position showing the sprite, id, label, kind, model, account, a coder toggle, a paid toggle, and its role if
it is the quarterback or QA lead (`roles`).
- **Model** is a combobox (`<input list>`) offering `models` for opencode, or free text for claude/codex.
- **Account** is a select of existing accounts plus "new…".
- **+ Add position**: kind, id (`^[a-z][a-z0-9_]{1,30}$`, must be unique), model, account.
- **Remove position**: refused if the position is a role holder, the only coder, or currently busy on a lane
  (per `/api/state` jobs). Removing it also deletes it from every list and chain.
- Coder order (the `coders` list) can be reordered with ▲▼ buttons. It decides which lane starts with which coder.
- A **Save** button (disabled until something changes) with a summary of the pending changes, and **Revert**.

## F2. Fallback chain editor: Settings view, "Fallbacks" section
- One row per `fallback` key (`agent:step`, step = `*`, `work`, `qa`, `plan`, `review`, `work-qa`, `work-asset`).
  Each chain shows as chips with ▲▼ ✕ buttons and an "+ add" select of the agents not already in it.
- **Paid last**: a checkbox per row, on by default, that keeps paid agents at the end.
- **+ Add rule**: pick an agent and a step.
- Uses the same save flow and backups as F1. A read-only preview line under each row reads, for example:
  "If coder_2 is limited, work goes to coder_3, then coder_4, then coder_1 (paid)".

## F3. Lane count: Settings view, "Lanes" section
- A stepper from 1 to 6 total lanes. Lane A is the main checkout, and the rest are worktrees listed in
  `lanes: [{name, dir}]`.
- Adding a lane appends the next letter, with a `dir` that is a sibling of the last existing lane dir with its
  final letter replaced (e.g. `.../gh_laneC` → `.../gh_laneD`). If there's no existing worktree lane, show a dir
  input, which must be an absolute path outside OneDrive (reject paths containing "OneDrive" with an explanation).
- Removing a lane removes only the last one, and is refused (409) while that lane is busy.
- Always restart_needed. Don't create or delete worktrees; the orchestrator does that at start.

## F4. Bench and unbench (live, no restart)
- Command inbox actions `bench {agent, reason?}` and `unbench {agent}`. The orchestrator keeps
  `CONFIG["disabled_agents"]` in memory and also persists it to config.json, using the same atomic write and
  backup rules. Refuse to bench the last available coder, or an agent that doesn't exist.
- Orchestrator routing: add `unavailable(agent) -> bool` (benched, or `limited_until(agent)`) and use it
  wherever routing currently checks `limited_until`. The effects:
  - A benched agent is skipped like a limited one, so the existing fallback chain takes over.
  - It is never probed (`probe_agent`), and `resolve_worker` skips benched coders in the pool. If every coder is
    benched, ignore the bench and log a warning event.
  - Benching never interrupts a running step; it applies from the next step.
- Events: `BENCH coder_3 (reason)` and `UNBENCH coder_3`.
- Office: in the Team panel and the Settings cards, a **Bench** / **Unbench** toggle (manage mode). Benched agents
  show a "benched" badge. In the office scene, a benched person sits in the lounge with a 🪑 bubble (the
  read-only view shows this too, from `/api/state` `agents[].benched`).

## F5. Approval gate (human in the loop)
Config: `"approval_gate": {"enabled": false, "types": [], "workers": [], "timeout_minutes": 0}`, plus a per-task
board field `needs_approval: true` set through the new command `set_approval {task, required: bool}`.
A task needs approval when the gate is enabled AND (its type is in `types`, OR its worker is in `workers`, OR
`needs_approval` is set). The per-task flag on its own also works when `enabled` is false: the flag is an
explicit request.
- **Orchestrator.** In `run_task`, when the review says approve and the checks pass, and approval is needed, do
  this BEFORE committing or merging:
  1. Save the diff against the attempt's checkpoint to `runs/T/aN/approval.patch`.
  2. Write `project/approvals/T-x.json` with `{task, title, attempt, lane, worker, requested_at, summary,
     review_summary, qa_verdict, checks_summary, patch, screenshot}` (repo-relative paths).
  3. Log the event `APPROVAL WAIT T-x (lane B)`, call `notify("approval-T-x", ...)` and `set_now("waiting for
     owner approval of T-x")`.
  4. Poll every 10 s for `project/approvals/T-x.decision.json` = `{decision: approve|revise, feedback}`. Call
     `check_stop()` on every poll so STOP still works; an interrupted task is recovered as today.
  5. On approve, continue exactly as today (commit/merge, DONE). On revise, treat it as reviewer verdict revise,
     with `feedback = "Owner requested changes: <feedback>"`; it counts as an attempt.
  6. With `timeout_minutes > 0` and no decision in time, continue as approved and log
     `APPROVAL TIMEOUT T-x - auto-approved`.
  7. Afterwards, move both files to `project/approvals/done/` and log `APPROVAL T-x approve|revise`.

  Factor the wait into `await_approval(task, n, lane, ..., sleep=time.sleep, clock=time.time)` so tests can drive
  it without waiting. Add `project/approvals/` to `template/.gitignore`.
- **Office.**
  - `GET /api/approvals` (read-only) returns the pending requests.
  - `POST /api/approval {task, decision, feedback}` (manage mode) writes the decision file atomically. It returns
    409 if no request is pending, and 400 if decision is revise with empty feedback.
  - A header badge "✋ 2 awaiting approval" opens an Approvals modal, one card per request: title, worker,
    review summary, QA verdict, checks, the screenshot, and the patch in the existing diff viewer. Buttons are
    **Approve** and **Request changes**; the latter needs feedback text. In read-only mode the cards show without
    buttons.
  - The waiting lane's plate in the office scene shows ✋. The drawer gains a "Require my approval" checkbox that
    sends `set_approval`.
  - Settings gets an "Approval gate" section: enabled, types multi-select, workers multi-select, timeout.

## F6. Spend cap for pay-per-use agents
Config: `"spend_cap": {"daily_usd": 0, "agents": []}`, where 0 means off and `agents` defaults to `paid_agents`.
- **Orchestrator.** Before calling an agent in `spend_cap.agents`, get today's OpenCode spend:
  - Run `opencode stats --days 1 --models` with NO `--project`, because money is spent across all projects.
  - Copy `parse_opencode_stats` from `template/office/stats.py` into the orchestrator: the orchestrator must stay a
    single file. Keep the two copies identical and say so in a comment on both.
  - Cache the result for 5 min.
  - If the total for the models of capped agents is at or over `daily_usd`, park their accounts until the next
    local midnight through the existing `_state["limited_until"]` mechanism. Log
    `SPEND CAP coder_1 $5.12 >= $5.00 today - parked until 00:00` and call `notify` once per day.
  - If the stats can't be read, don't block: log `SPEND CAP check failed: ...` at most once per hour.
- **Office.** In the Stats → Quota and cost section: today's spend against the cap as a meter (amber at 80%, red
  at 100%) and "parked until 00:00" when it applies. Settings gets a "Spend cap" section: the daily USD amount
  and which agents it applies to. It takes effect at restart; say so.
- The Office's `limits()` parser must treat SPEND CAP lines like USAGE LIMIT, so the person naps with a 💸 bubble
  instead of 💤.

## Polish from Phase 3 QA (check each one in `--demo` at 1400 px and 500 px wide)
Q1. Stats › throughput bar chart: the y-axis labels are inverted (0 at the top, max at the bottom). Draw 0 at the
    baseline, and add 3-5 gridlines with values. Cap the chart height at about 220 px; it is far too tall now.
Q2. Stats › burndown: add a y-axis with values, a legend that maps each line colour to its milestone, and 4-6
    time ticks along the x-axis instead of one.
Q3. Stats › lane timeline: drop the stray "lane" header row label. The "time →" caption overlaps the "now" label;
    move "now" to the top of its line. Demo data should give every lane 3-6 bars across 24 h, and at least one
    hatched nap bar on an account row.
Q4. Stats › routing flow: size the SVG to its content (a large empty area sits below the bands). Draw each band as
    a curved ribbon from left to right.
Q5. Demo › OpenCode spend, last 7 days: the table is empty while the total says $1.2. Generate model rows that
    add up to the total.
Q6. Header: the ▶ Play button sits on its own row under the control bar. Put it inline at the end of the control
    bar (and the build-time text at the end of the pills row in read-only mode).
Q7. Graph: edges pass through nodes, and the canvas is wider than its box at 30 tasks. Lay layers out left→right
    with nodes stacked vertically per layer. Route edges from a node's right edge to the next node's left edge.
    Fit-to-width on load (the zoom buttons still work).
Q8. Tests: one run in seven had a single test error that didn't reproduce. Look for timing-sensitive tests
    (threads, sleeps, the 2 s state cache, mtime ordering) and make them deterministic: poll with a deadline
    instead of fixed sleeps, and set mtimes explicitly with `os.utime`.

## Tests (`tests/test_office_phase4.py`)
1. Config API: GET without the token returns 403. Changing a model rewrites only the value after `-m`. A cmd
   without `-m` is refused. An invalid model id returns 400. A stale `base_mtime` returns 409. A backup file is
   created, there are never more than 20, and unknown keys and `_notes` survive byte-for-byte as values.
2. Validation: removing the only coder, a role holder, or an agent referenced in a chain without also removing
   it from the chain is refused; a valid removal cleans every list.
3. Lanes: adding a lane derives the right dir; a OneDrive path is refused; removing a busy lane returns 409.
4. Bench through the orchestrator inbox (the importlib pattern from Phase 2): bench, then `unavailable()` is true,
   `resolve_worker` skips the agent, `probe_agent` isn't called, and config.json persists the bench. Benching the
   last coder is refused. Unbench restores everything.
5. `await_approval` with a fake clock and sleep: approve continues; revise returns the feedback; timeout
   auto-approves and logs the event; and STOP raises `StopRequested`. The files move to done/.
6. Office approvals: GET lists pending; POST approve writes the decision; revise without feedback returns 400;
   with nothing pending, 409.
7. Spend cap: a stats sample over the cap parks the account until midnight with exactly one event; a sample under
   the cap doesn't; unreadable stats don't block; the two parser copies give identical results on the same samples.
8. `limits()` handles SPEND CAP lines.
9. Demo mode: Settings and Approvals render from demo data, with one pending approval and one benched agent, and
   every POST returns 409.

## Docs
- README: a "Settings, approvals and spend cap" subsection.
- `docs/PLAYBOOK.md`: a short note on when to use the approval gate (e.g. milestone-closing or paid-agent work).
- CHANGELOG: under 1.2.0. Bump `VERSION` to 1.2.0 and change the CHANGELOG heading from "(unreleased)" to today's
  date.
