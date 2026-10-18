# Office Phase 3: Stats and Notes views, incidents, build, polish, demo coverage

Follow shared conventions C1-C9 in `docs/specs/office-phase1.md`. Phases 1-2 are implemented. Read
`template/office/` (all files) and `tests/` first. In the orchestrator, read the `event(...)` calls; their exact
formats are listed below. Do not change the orchestrator in this phase.

## Architecture
- New module `template/office/stats.py` (stdlib only), with pure functions that take a project root and `now`. No
  HTTP code in it. `build_stats(root: Path, now: datetime, hours: int) -> dict` parses the WHOLE
  `project/events.log` (not the 800-line tail) and `project/board.json`. `server.py` caches the result for 30 s
  per `hours` value.
- `GET /api/stats?hours=6|24|72|168` (default 24; other values → 400) is read-only and needs no token.
- Two new views in the switcher, giving **Office | Board | Graph | Stats | Notes**. Deep link `?view=stats|notes`
  works like the existing ones.
- Charts are inline SVG drawn by hand. No libraries or CDNs: the Office must work offline. Chart rules:
  - Every axis is labelled, and every mark has a `<title>` tooltip with the exact value.
  - Use the existing CSS colour variables so light and dark themes both work.
  - Status colours match the board's badges. For agents, reuse each agent's shirt colour from `LOOKS` / `PALETTE`
    in office.js, so a person is the same colour everywhere.
  - Each chart has a one-line caption saying what it shows, and an empty state ("No completed tasks in the last
    24 h") instead of a blank box.
  - At 500 px wide, charts scale to the container width and tables scroll horizontally inside their own box.

## Event formats (from orchestrator.py / supervisor.py; lines are `YYYY-mm-dd HH:MM:SS  <text>`)
```
START T-12 [lane B] [coder/code] Title
T-12 a1 WORK done: summary        T-12 a1 WORK produced no result
T-12 a1 CHECKS pass (12 passed)   T-12 a1 CHECKS FAIL (...)
T-12 a1 QA pass: ...              T-12 a1 QA fail: ...
T-12 a1 REVIEW approve: ...       T-12 a1 REVIEW revise: ...     T-12 a1 REVIEW unavailable -> auto approve
DONE T-12 (attempt 2, lane B)     BLOCKED T-12: reason           LANE B merged T-12 into main
NEW TASK T-13 (coder, M2) from plan: Title
PLAN start (reason)               PLAN done: summary             MILESTONE M2 COMPLETE
FALLBACK coder_1 is limited until 14:05; coder_3 handles work steps
USAGE LIMIT coder_2 (openai): limited until ~14:05 ...           QUOTA RESTORED openai: ...
PREEMPTIVE HANDOFF openai at 97% of its 5h window (threshold 97%)
PROVIDER DOWN coder_4 (rc=1 after 61s, server error): ...        MODEL GONE coder_5: ...
QUICK FAIL coder_3 (rc=1 in 4s): ...                             AGENT FAIL coder_3 work: rc=1 ...
SUPERVISOR-AI claude called: <reason> (log ...)                  SUPERVISOR-AI claude done: <summary>
SUPERVISOR-AI claude timed out after 20 min                      SUPERVISOR-AI claude unavailable (...)
SUPERVISOR-AI claude finished without a report (rc=1)            SUPERVISOR relaunched start.bat (...)
ORCHESTRATOR ERROR (...)  LANE B ERROR: ...  PLANNER ERROR: ...  WATCHDOG killed Godot ...  RECOVER T-12: ...
```
The board's task `history[]` entries are `{attempt, at, worker, work, checks, qa, checks_after_qa, review}`.
Write the parsers defensively: an unknown or malformed line is skipped and must never raise.

## Stats view: sections, top to bottom (with a 6 h / 24 h / 3 d / 7 d window selector)
S1. **Agent scorecards and leaderboard.** Build one row per agent that appears as a `worker` in board histories,
    plus every agent in config. Columns:
    - attempts
    - first-pass approvals (tasks approved on attempt 1)
    - approval rate (review approve ÷ attempts that reached review)
    - checks pass rate
    - QA pass rate
    - median work minutes: time from the step's start to its `T a<n> WORK` event. The start is the task's
      `START` event for attempt 1, or the previous event for the same task for later attempts.
    - tasks it was the worker on that ended BLOCKED
    - times it stood in for another agent (substitute in a FALLBACK line)

    Sort by first-pass approvals, then approval rate. The top row gets a small 🏆. Leaderboard columns count all
    time; a "this window" toggle restricts them to the selected window.
S2. **Throughput and burndown.**
    - Bar chart of DONE events per hour (bucket by hour, or by 6 h for 3 d and 7 d windows).
    - Line chart of open tasks per milestone over the window. A task counts as open from its creation (its
      NEW TASK time, or the first event in the log if it has no NEW TASK line) until its DONE time. Dropped tasks
      count as closed when their status changed; if that's unknown, they are excluded.
    - ETA for the current milestone and for the whole board: remaining ÷ (DONE count over the last 12 h ÷ 12).
      Show it as "~3.5 h" and add "(low confidence)" when there were fewer than 5 DONEs in those 12 h. Show "—"
      when the rate is 0.
S3. **Lane timeline (Gantt).** One row per lane. Each bar runs from `START T [lane X]` to that task's next DONE,
    BLOCKED or RECOVER event, or to now if it is still running. Bar colour is the outcome; the label is the task
    id, and the tooltip shows id, title, duration and attempts. Below the lanes, add one row per account with
    hatched bars for limited periods: from a USAGE LIMIT / PREEMPTIVE HANDOFF / PROVIDER DOWN line to its
    "until ~HH:MM", or to a QUOTA RESTORED line for that account, whichever comes first. Reuse the existing
    `limits()` logic for parsing "until". Draw a vertical "now" line. Clicking a bar opens the task drawer.
S4. **Routing flow.** A two-column SVG flow diagram: limited agents on the left, substitutes on the right, and a
    band between each pair with width proportional to the FALLBACK count, coloured by the left agent. Underneath,
    a small table counts, per agent, USAGE LIMIT, PREEMPTIVE HANDOFF, PROVIDER DOWN, MODEL GONE, QUICK FAIL and
    AGENT FAIL events in the window.
S5. **Quota and cost.**
    - Per account: current state (from `limits()`), number of limits in the window, and total hours limited.
    - **Codex usage**: port `codex_usage()` from the orchestrator (it reads `~/.codex/sessions/YYYY/MM/DD/
      rollout-*.jsonl` for the latest `rate_limits`). Show primary and secondary `used_percent` as meters, with the
      reset time.
    - **OpenCode spend**: a background thread runs `opencode stats --days 1 --models --project ""` and
      `... --days 7 ...` (cwd=ROOT, resolve opencode with `shutil.which`, 60 s timeout, UTF-8) at most every
      10 min. It parses the box-drawing text: "Total Cost", and for each model block its "Messages",
      "Input Tokens", "Output Tokens" and "Cost". Strip box characters and ANSI codes first. Show one table per
      period, with paid agents' models (`paid` in config) flagged. If opencode is missing or parsing fails, show
      "spend unavailable" plus the reason. Put the parser in `stats.py` as
      `parse_opencode_stats(text) -> {"total": float|None, "models": {name: {...}}}` and test it against the
      sample below.
S6. **Incident log** (newest first). Pair each `SUPERVISOR-AI X called: <reason>` with the next outcome line for
    the same agent: done / timed out / unavailable / finished without report. Show time, reason, outcome, summary
    and duration. "SUPERVISOR relaunched", ORCHESTRATOR ERROR, LANE ERROR, PLANNER ERROR, WATCHDOG and RECOVER
    lines are single-row incidents. Show a count per type above the table.

## Notes view (the team's reasoning)
- On the left, a list of documents; on the right, the selected document rendered as text (pre-wrap; turn `#`
  headings into bold lines, and nothing more). The documents are:
  - **Plans**: every `PLAN start` / `PLAN done` pair from the events, newest first, with time, reason, duration
    and summary.
  - `project/decisions.md`, `project/assumptions.md`, `project/PM_NOTES.md`.
  - Every `project/milestones/*.md` (milestone reports).
- `GET /api/notes`: `{"plans": [...], "docs": [{"name", "path", "mtime"}]}`. Fetch file contents through the
  existing `/api/file`, extended to allow those exact files plus `project/milestones/*.md`. Nothing else under
  project/ becomes readable: keep the existing traversal tests passing and add ones for the new allowance.

## Build and Play
- `GET /api/build`: `{"exe": "builds/<name>.exe" | null, "exists", "mtime", "size_mb", "tag"}`. Find the exe
  name in `play.bat` (`builds\X.exe`); otherwise use the newest `builds/*.exe`. Get the tag from
  `git describe --tags --abbrev=0` (cwd=ROOT, 10 s timeout, "" on failure).
- Header: a "▶ Play" button with a tooltip like "Build from 14:02, v1.0". It appears in manage mode only, when
  the exe exists. `POST /api/control {"action":"play"}` launches `play.bat` detached, like `start`, and is
  allowed while the team runs. In read-only mode, show the build time as text.

## Polish from Phase 2 QA
P1. The drawer close button is a full-width grey bar. Make it a small square ✕ icon button in the drawer header's
    top-right, with `aria-label="Close"`.
P2. Several buttons use browser defaults: Timeline, + Add task, Drop, zoom −/+, the drawer ✕ and the lightbox
    controls. Give every button one shared style that matches the control bar buttons, with a danger variant for
    Drop and Stop.
P3. In the drawer for a done or in_progress task, the status select wrongly shows "Backlog" and Drop is offered.
    Show the real status (disabled) and hide Drop. Retry stays blocked-only.
P4. Graph nodes show only the id. Make nodes wide enough for the id plus the title truncated to about 18 chars,
    and put the full title in a `<title>` tooltip.

## Demo coverage (the public showcase runs `--demo`)
In `--demo`, every read endpoint from Phases 2-3 returns generated, plausible data instead of 404. Put the
generators in `demo.py` and make them deterministic (seeded):
- About 30 tasks over 3 milestones with dependencies and all statuses, and task details with 1-3 attempts,
  histories and review summaries.
- A fake `.log` that `/api/tail` grows by a few lines per call, so the Live tab animates.
- 3 days of stats (scorecards, throughput, a Gantt with naps, a few fallbacks and two incidents), and an
  OpenCode spend table.
- Notes with two plans and a short decisions.md.
- Screenshots: keep the timeline's empty state. Demo POSTs still return 409.

## Tests (`tests/test_office_phase3.py`; add a realistic `events.log` to the fixture covering every format above)
1. Scorecards: attempts, first-pass approvals and rates are correct for a hand-computed fixture; a fallback
   counts for the substitute.
2. Throughput buckets and ETA are correct: rate 0 gives "—", and fewer than 5 DONEs gives low confidence.
3. Gantt bars: one per START. A still-running task ends at `now`. Nap bars end at QUOTA RESTORED when that comes
   before "until".
4. Routing flow counts from→to correctly.
5. `parse_opencode_stats` on this exact sample gives total 0.16 and the muse model with cost 0.1622, messages 282,
   output tokens 193400:
   ```
   │Total Cost                                        $0.16 │
   │ meta/muse-spark-1.3-contributor                        │
   │  Messages                                          282 │
   │  Input Tokens                                   674.3K │
   │  Output Tokens                                  193.4K │
   │  Cost                                          $0.1622 │
   ```
   (K = ×1000, M = ×1,000,000). Garbage input gives `{"total": None, "models": {}}`.
6. Incidents: called + done pair up with a duration; a called line with no outcome shows as "in progress".
7. Malformed lines anywhere don't raise. `/api/stats?hours=5` returns 400.
8. `/api/file` allows `project/decisions.md` and a milestone report, and still refuses `project/board.json` and
   `orchestrator/config.json`.
9. `/api/build` finds the exe named in play.bat. `play` is refused without the token and calls Popen with the token.
10. Every Phase 2/3 GET in demo mode returns 200 with non-empty data. Consecutive `/api/tail` calls in demo
    return new text.

## Docs
README Office section: add the Stats and Notes views and Play. Add to the CHANGELOG under 1.2.0.
