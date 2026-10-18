# Office Phase 2: task drawer, live logs, screenshot timeline, board + graph, task actions

Follow the shared conventions C1-C9 in `docs/specs/office-phase1.md`. Phase 1 is already implemented; read it first in
`template/office/` (server.py, manage.py if present, office.js, index.html, office.css) and `tests/`.
Orchestrator parts to read: `template/orchestrator/orchestrator.py` lines 1-70, 120-130, 295-340 (`run_proc`),
431-500 (board, `add_task`, `ensure_brief`), 1012-1066 (`_apply_plan`), 1282-1440 (`run_task`: run-folder layout),
1719-1760 (`start_plan_now_watcher`, `run_loop`).

Run-folder facts: attempt N of task T writes to `project/runs/T/aN/`: `work.json`, `qa.json`, `review.json`,
`<step>.<agent>.log` (step = work|qa|review), `screenshot_<label>.png`, other `*.png`, optional `bugs.json`.
Patches can appear at `project/runs/T/*.patch` and `project/runs/T/aN/*.patch`. Plans go to `project/runs/_plan/<stamp>/`.
Task briefs are `project/tasks/T-xxx.md`. Each board task has `history`: a list of
`{attempt, at, worker, work, checks, qa, checks_after_qa, review}`.

## New read-only endpoints (they work without --manage, like /api/state)
- `GET /api/board`: `{"tasks": [{id, title, status, milestone, priority, type, owner, depends_on, attempts}],
  "milestones": [ids in order]}`.
- `GET /api/task/<id>` (id must match `T-\d+`, else 400; unknown id returns 404): the full board task (all fields,
  including history), `brief` (text of `project/tasks/<id>.md`, or ""), and `attempts`: one entry per `aN` folder,
  in order: `{n, files: [{name, size, kind: json|log|image|patch|other}], work, qa, review}`. `work`, `qa` and
  `review` are the parsed JSON, or null. Strings longer than 4000 chars are truncated with "…".
- `GET /api/file?path=<repo-relative path>`: serves one file. Allowed only if the resolved path is inside
  `ROOT/project/runs` or `ROOT/project/tasks`, and the suffix is .png .json .log .md .patch .txt. Otherwise 403,
  and the check must also beat `..`, absolute paths and symlinks. `.log`, `.patch` and `.txt` are served as
  text/plain; if the file is bigger than 512 KB, serve only the last 512 KB, starting at a line start.
- `GET /api/tail?path=<same rules>&offset=<int>`: `{"text": str, "offset": new_offset, "size": int, "done": bool}`
  returns the bytes from offset to the end (max 64 KB per call, cut at the last newline). If offset > size (the file
  was replaced), start over from 0. `done` is true when `path` ends in `.log` and is not a `.live.log` (see O1).
- `GET /api/screenshots`: every `project/runs/T-*/a*/*.png`, sorted by mtime:
  `[{task, attempt, name, path, t: "YYYY-mm-dd HH:MM", title: board title}]`. Cache the result for 10 s.
- `/api/state` lane entries gain `log`: repo-relative path of the log the lane's agent is writing right now
  (the `.live.log` if one exists, otherwise the newest `<step>.<agent>.log` in the latest attempt), or null.

## O1. Orchestrator: live logs
In `run_proc`, when `log_path` is given, also stream output as it arrives to
`log_path.with_name(log_path.stem + ".live.log")`: open it once, write `$ <cmd>\n(running)\n\n`, then each line with
ANSI codes stripped, flushed per line. After the process ends, write the final log exactly as today, then delete the
.live file. Any error with the live file is swallowed: it must never break an agent call. The existing
`newest_log` regex in server.py must not match `.live.log` files (check it, and add a test).

## O2. Orchestrator: command inbox
A watcher thread started next to `start_plan_now_watcher`, called `start_command_watcher(board)`. Every 5 s it
processes `project/commands/*.json` oldest first (by name). Each file is
`{"id": str, "at": iso, "source": "office", "action": ..., ...}`:
- `set_priority` `{task, priority: 1-5}`
- `set_status` `{task, status: backlog|ready|dropped}`. Refused if the task is in_progress or done.
- `retry` `{task}`: only for blocked tasks. Status goes to ready and attempts to 0 (same as `promote`).
- `add_task` `{task: {title, description, milestone, type: code|asset|design|qa, priority, acceptance: [str],
  depends_on: [ids]}}`. Goes through `add_task(board, spec, "owner")`.
Apply the changes through `apply_plan(board, {...})` (it takes BOARD_LOCK and saves the board), then
`git_commit("OWNER: <summary>", paths=["project"])`. Move the file to `project/commands/done/<same name>` with
`"result": "applied" | "refused: <reason>"` and `"done_at"` added, and log the event
`COMMAND <id> <action> <task> applied|refused: <reason>`. A malformed file is moved to done/ with
`refused: malformed`. Exceptions are caught and logged as `COMMAND watcher error: ...` (never fatal). Add
`commands/` and `commands/done/` handling to `recover()` only if it's needed.

## F1. Task drawer (UI)
Clicking a task anywhere (a lane plate, a worker bubble, the board, the graph, ticker items that mention `T-\d+`)
opens a right-side drawer (full-screen under 600 px) with:
- A header: id, title, status badge, milestone, type, owner, priority, attempts. Then a "Depends on" list of chips
  that open those tasks.
- Tabs: **Brief** (pre-wrapped text), **Acceptance** (list), and **Attempts**. Attempts has one collapsible card per
  attempt: worker, the history verdicts as coloured badges (work / checks / QA / review), the review summary,
  QA bugs, image thumbnails (click to enlarge in a lightbox), and links to its logs and patches. A link opens the
  file in a text viewer inside the drawer, with patches syntax-coloured (+ lines green, - lines red, @@ lines blue).
- Esc or ✕ closes it. While open, the drawer refreshes every 5 s, keeping the scroll position and the open tab.

## F2. Live log tail (UI)
In the drawer, if the task is running on a lane with `log`, show a **Live** tab that is selected by default. It
polls `/api/tail` every 1.5 s and appends to a monospace pane. It auto-scrolls when the user is already at the
bottom, and otherwise shows a "↓ new output" pill. When `done` is true or the lane moves on, show "finished".
Also show a **Watch** button on each busy lane plate in the office that opens the drawer on Live.

## F3. Screenshot timeline (UI)
A **Timeline** button in the header opens a full-width modal with: the big image (`image-rendering: pixelated`,
fit to width), a caption (task, title, attempt, time), a range slider over all screenshots, ◀ ▶ buttons, ← → keys,
and a ▶ Play button that advances every 700 ms and loops. A milestone filter dropdown narrows the list. Clicking the
caption opens the task drawer. It shows an empty state when there are no screenshots.

## F4. Board and graph views (UI)
Header view switcher: **Office | Board | Graph** (remember the choice in localStorage, wrapped in try/catch). The
side panels stay visible.
- Board: columns Backlog, Ready, In progress, Blocked, Done, Dropped. Cards show id, title, a type icon, priority
  and the attempts count. There's a milestone filter, and Done is collapsed after 20 cards ("show all").
- Graph: inline SVG of the dependency DAG. Each node's layer is its longest depends_on path from a root; within a
  layer, order by id. Edges are cubic curves from dependency to dependent. Nodes are colored by status, using the
  same colors as the board's status badges. Same milestone filter; pan by dragging, zoom with buttons. Skip a
  dependency id that isn't on the board, and lay out cycles by ignoring the back-edge. Must stay readable for
  200 tasks.
Clicking any card or node opens the drawer.

## F5. Task actions (manage mode)
- In the drawer header, manage mode only: a priority select (1-5), a status select (Backlog / Ready / Dropped;
  disabled for in-progress or done tasks), a **Retry** button (blocked tasks only), and **Drop** (with confirm).
- An **+ Add task** button in the Board view opens a form for the add_task fields. Milestone is a select of
  existing milestones, depends_on is a multi-select of task ids, and acceptance is one line per item.
- `POST /api/command` `{action, ...}`: validate exactly as O2 does (400 on bad input, 409 if the task's current
  status makes it impossible), then write `project/commands/<YYYYmmdd-HHMMSS>-<6 hex>.json` atomically and
  return `{"ok": true, "id": ...}`. `GET /api/commands`: `{"pending": [...], "done": [last 20, newest first]}`.
- The drawer and board show a "⏳ pending" chip on a task with a pending command. If a command has been pending
  longer than 90 s while the orchestrator is running, show a toast: "The orchestrator isn't picking up commands;
  it may be older than 1.2. Sync it from the engine."

## Fix: phone width (pre-existing bug)
At 390 px wide the page scrolls horizontally: the header title ("<game> · The Office") doesn't wrap and pushes the
layout wider, so the stage and the right edge of the side panels are cut off. Make the title wrap or shrink, and make
sure nothing exceeds the viewport (`min-width: 0` on grid/flex children, the canvas scales to 100% width). Check
every new view at 390 px too.

## Docs
README Office section: describe the views, the drawer and the manage-mode task actions. Add a CHANGELOG entry
under 1.2.0.

## Acceptance (each one tested; extend `tests/office_fixture.py` with run folders: two attempts with
json/log/png/patch, a blocked task, a dependency chain, and a cycle)
1. `/api/task/T-1` returns brief, history and attempts with their files. `T-x` returns 400 and `T-999` returns 404.
2. `/api/file` serves an allowed png and log. `..\..\orchestrator\config.json`, an absolute path, a
   `project/board.json` path and a `.py` file all return 403.
3. `/api/tail` with an offset returns only new text. An offset greater than size restarts from 0. A 1 MB log is
   capped at 64 KB per call.
4. `/api/screenshots` is sorted by mtime and includes titles.
5. `POST /api/command` without --manage is refused. With --manage, a valid set_priority writes one JSON file in
   project/commands. Retry on a ready task returns 409. Priority 9 returns 400.
6. Orchestrator inbox: the test copies `template/orchestrator/orchestrator.py` into the fixture project, imports it
   with `importlib` (stub git with a no-op), runs one watcher pass synchronously (factor the pass out as
   `process_commands(board)` so it can be called directly), and asserts that the board changed, the file moved to
   done/ with its result, and the event was logged, for each action plus one refused and one malformed command.
7. `run_proc` with a log path: the .live.log exists while a slow child process runs (`python -c` that prints, sleeps
   and prints) and is gone afterwards. The final log is byte-identical to the old format.
8. The `newest_log` regex ignores `work.coder_1.live.log`.
