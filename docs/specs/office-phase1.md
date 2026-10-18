# Office Phase 1: manage mode, control bar, team messages, health tools

Read first: `template/office/server.py`, `template/office/office.js`, `template/office/index.html`,
`template/office/office.css`, `template/office/demo.py`, and `template/orchestrator/orchestrator.py` lines 1-60,
195-240, 1467-1510, 1719-1760 (STOP / RESTART / PLAN_NOW handling). `template/orchestrator/supervisor.py` lines 1-60.
`template/project/OWNER_REQUESTS.md`.

## Shared conventions (all Office phases follow these; later specs refer back here)

C1. **Read-only by default.** `server.py` with no new flag must behave exactly as today and never write anything.
    A new `--manage` flag enables every write feature. Update the module docstring to say so.
C2. **Token.** In manage mode the server generates `secrets.token_urlsafe(16)` at startup (or uses `--token X`)
    and prints the URL as `http://localhost:PORT/?token=TOKEN` (and the LAN URL with the token when `--lan`).
    Every POST and every manage-only GET must carry header `X-Office-Token: TOKEN`; otherwise 403 JSON
    `{"error": "bad token"}`. Compare with `hmac.compare_digest`. The page reads `?token=` once, keeps it in
    `sessionStorage` (wrapped in try/catch), and removes it from the address bar with `history.replaceState`.
C3. **Host check.** In manage mode reject (403) any request whose `Host` header hostname is not `localhost`,
    `127.0.0.1`, or (with `--lan`) the machine's LAN IP. Prevents DNS-rebinding attacks.
C4. **API shape.** JSON in and out. `POST` bodies are capped at 64 KB (413 above that). Errors are
    `{"error": "..."}` with 400/403/404/409/413. `/api/state` gains `"manage": true|false`. After any successful
    write, invalidate the 2-second state cache so the next poll shows the change.
C5. **Never edit `project/board.json` directly** (the orchestrator owns it). Only use channels the orchestrator
    already reads: flag files in `project/`, `project/OWNER_REQUESTS.md`, or (later phases) a command inbox.
    Writes to text files are atomic: write `name.tmp` beside the file, then `os.replace`.
C6. **Demo mode.** With `--demo`, manage features show in the UI (so the demo can show them off) but every POST
    returns 409 `{"error": "demo mode"}` and the UI shows that message as a toast.
C7. **UI.** Reuse the existing look: `.panel` sections, Departure Mono font, existing CSS colour variables.
    Manage-only UI is hidden unless `state.manage`. Every action button disables itself while its request is in
    flight and shows the result as a small toast (new `#toast` element, `role="status"`, auto-hides after 4 s).
    Destructive actions (Stop, Restart) need a `confirm()` first. Must work at 375 px wide (phone, `--lan`).
C8. **Tests.** Python `unittest`, standard library only, under `tests/` at the repository root (create
    `tests/__init__.py` and `tests/office_fixture.py`). The fixture builds a throwaway game project in a
    `tempfile.TemporaryDirectory()`: `project/` with `STATUS.md`, `events.log`, `board.json` (3-4 tasks across two
    milestones), `OWNER_REQUESTS.md` copied from `template/project/`, and `orchestrator/config.json` with 2-3
    agents whose `cmd` is a harmless Python one-liner. Tests start the real `ThreadingHTTPServer` with `Handler` on
    port 0 in a thread, set the module globals (ROOT, manage, token...) directly, and call it with
    `urllib.request`. Never launch real agents or `start.bat` in tests: patch `subprocess.Popen` / `subprocess.run`.
    The whole suite must pass with `python -m unittest discover -s tests -t .` in under 60 seconds.
C9. Keep `server.py` standard-library only. If it grows past ~900 lines, move the manage endpoints into a new
    `template/office/manage.py` that `server.py` imports.

## Features

### F1. Control bar
- A new bar in the header (manage mode only) with buttons: **Plan now**, **Restart**, **Stop**, and **Start**.
  The **Start** button appears only when `state.orchestrator === false`. Show existing flags (`state.flags`) as
  chips, e.g. "STOP pending", and give each one a small ✕ to cancel it (delete the flag file).
- `POST /api/control` `{"action": "plan_now" | "restart" | "stop" | "start" | "cancel", "flag": "STOP"|...}`
  - `plan_now` / `restart` / `stop`: create `project/PLAN_NOW` / `project/RESTART` / `project/STOP` (contents:
    `requested from the Office at <ISO time>`), and append the event line
    `<YYYY-mm-dd HH:MM:SS>  OFFICE <action> requested` to `project/events.log`, matching the existing format.
  - `cancel`: delete the named flag file. Only `STOP`, `RESTART` and `PLAN_NOW` are allowed (400 otherwise).
  - `start`: return 409 if the orchestrator is running (`_procs["orchestrator"] is True`). Otherwise delete
    `project/STOP` if present, then launch `start.bat` from ROOT detached in its own console window
    (`subprocess.Popen(["cmd", "/c", "start", "", "start.bat"], cwd=ROOT)`). If
    `--with-supervisor` was passed in the body (`{"action":"start","supervisor":true}`), also launch
    `supervise.bat` the same way when the supervisor isn't running.
- Response: `{"ok": true, "flags": [...]}`.

### F2. Message the team (owner requests)
- A new side panel **Requests** (manage mode only) with a textarea (max 2000 chars) and a **Send to the team**
  button, then two lists: **Open** and **Handled**. A handled item shows the task IDs it mentions (`T-\d+`) as chips.
- `GET /api/requests` returns `{"open": [str], "handled": [str]}` by parsing `project/OWNER_REQUESTS.md`: items are
  the non-empty, non-"(none...)" paragraphs or bullet items under `## Open` and `## Handled` respectively.
- `POST /api/requests` `{"text": "..."}`: strip it, then reject empty text or text over 2000 chars (400). Collapse
  newlines to spaces, then insert `- <text> _(from the Office, YYYY-mm-dd HH:MM)_` as the last item under
  `## Open`, replacing a `(none)` placeholder if there is one. Leave the rest of the file byte-for-byte unchanged.
  Re-read the file right before writing, then write atomically (C5). If the file or the `## Open` heading is
  missing, create the heading at the end. Also append event line `OFFICE request added`.
- Optional checkbox **Plan now too**: also does F1 `plan_now`.

### F3. Health tools
- A new side panel **Health** (manage mode only) with three buttons:
  - **Probe models**: `POST /api/probe` starts one background thread (409 if a probe is already running) that,
    for each agent in `orchestrator/config.json`, runs its `cmd` with `{prompt}` replaced by
    `Reply with exactly: OK`, with cwd=ROOT, a 120 s timeout (kill the process tree on timeout), and stdin closed.
    Agents sharing an `account` run one after another; different accounts run in parallel.
    `GET /api/probe` returns `{"running": bool, "results": {agent: {"state": "pending|ok|fail|timeout",
    "seconds": float, "detail": "<last 200 chars of output>"}}}`. `ok` means the exit code is 0 and the output
    contains `OK`. The panel polls every 2 s while running and shows one row per agent: label, model, state badge,
    seconds, and the detail in a `title` tooltip.
  - **Test notification**: `POST /api/notify-test` posts to `https://ntfy.sh/<notify.ntfy_topic>` using the
    same headers as the orchestrator's `notify()` (Title "<game>: test from the Office", Priority default).
    Returns 409 `{"error": "no ntfy_topic in config"}` when there is no topic. Uses a 15 s timeout.
    Tests must patch `urllib.request.urlopen`.
  - **Start supervisor**: shown only when `state.supervisor === false`. Calls F1 `start` with only the
    supervisor part (`{"action": "start_supervisor"}`; add that action).

## Docs
- `template/office.bat`: unchanged. Add `template/office-manage.bat`, which is the same but passes `--manage`.
- In `README.md`, extend the Office section with a short "Manage mode" subsection: how to start it, the token URL,
  what each control does, and the security note (token + host check; `--lan` exposes it to your Wi-Fi).
- Add a `CHANGELOG.md` entry under a new `## 1.2.0 (unreleased)` heading.

## Acceptance (each one must be covered by a test)
1. Without `--manage`: all POST endpoints return 403 or 404, `/api/state.manage` is false, and the fixture
   project's files are byte-identical after the test.
2. With `--manage`: a POST without the token returns 403, a wrong token returns 403, and a bad Host returns 403.
3. `plan_now`, `stop` and `restart` create their flag file and an `OFFICE` event line. `cancel` removes it.
   `cancel` with flag `../x` returns 400.
4. `start` while the orchestrator is running returns 409. When it isn't running, it removes `STOP` and calls Popen
   with `start.bat` (patched).
5. The requests round trip: POST, then GET shows the request under open; `(none)` is replaced; everything outside
   the inserted line is unchanged; empty or oversize text returns 400.
6. A probe with one agent whose cmd prints OK and one that exits 1 ends with ok and fail. A second concurrent
   POST returns 409.
7. A notify test with no topic returns 409. With a topic, it calls urlopen once with the right URL.
8. In demo mode, every POST returns 409 `demo mode`.
9. Body over 64 KB returns 413.
