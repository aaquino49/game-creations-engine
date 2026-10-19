# Changelog

## 1.2.1 (unreleased)

Office zones: the work floor, planning office and break room are separate zones with
glass/partition walls and doorways (`template/office/layout.js` with BFS routing, loaded
before `office.js`). Working agents sit at lane desks, `PLAN_SPOT` or the supervisor seat;
idle/napping/benched agents stay in the break room; pets never enter planning. Routes never
cross walls except through door gaps, the planning lights fade off when nobody plans, and
`tests/office_layout.test.js` (+ Python wrapper) covers zones, overlaps and routing.

Phone-alert topics stay out of git: `scaffold.py` writes the ntfy topic to
`orchestrator/config.local.json`, which the template's `.gitignore` excludes, and leaves
`notify.ntfy_topic` empty in `config.json`. The orchestrator, supervisor, Office notify test and
`ops/sync_from_project.py` read the local file first and still accept a topic in `config.json`
for older projects. The generated game README no longer prints the topic. Added an MIT `LICENSE`.

## 1.2.0 (2026-10-18)

The Office grows a manage mode (`office-manage.bat` / `office/server.py --manage`): token-URL auth
plus a localhost-only host check, a header control bar (Plan now, Restart, Stop, Start, cancellable
flag chips), a Requests panel writing to `project/OWNER_REQUESTS.md`, and a Health panel (model
probes grouped by account, test phone notification, supervisor start). Without `--manage` the
server is read-only exactly as before; `--demo` shows the new UI but rejects every write.

Phase 2: task drawer (Brief/Acceptance/Attempts + Live tail of `.live.log`), screenshot timeline,
Board and dependency-graph views, and manage-mode task actions via `project/commands/` (priority,
status, retry, add-task, with pending chips). The orchestrator streams live logs and runs a command
inbox watcher; the Office fixes the 390 px horizontal scroll.

Phase 3: Stats and Notes views (Office | Board | Graph | Stats | Notes, `?view=` deep links),
incidents, build and polish, demo coverage. Stats (`/api/stats?hours=6|24|72|168`, 30 s cache,
offline hand-drawn SVG): agent scorecards/leaderboard with this-window toggle, DONE-per-hour and
burndown charts with ETAs, lane Gantt with account-limit naps and a now line (bars open the drawer),
FALLBACK routing flow, quota/Codex-meters/OpenCode-spend tables, and a paired supervisor incident log.
Notes (`/api/notes` + `/api/file` extended to the notes docs and milestone reports only) shows every
PLAN pair with duration plus the team reasoning docs. Build (`/api/build`, exe from `play.bat` else
newest `builds/*.exe`, `git describe` tag) adds a manage-mode ▶ Play button that launches `play.bat`
while the team runs. Polish: drawer ✕ is a small top-right icon, one shared button style (danger
variant for Drop/Stop), done/in-progress drawers show the real disabled status with no Drop, graph
nodes show id + ~18 chars of title. `--demo` returns seeded data (30 tasks, growing tail, 3 days of
stats, notes, spend) for every Phase 2/3 read endpoint while keeping the timeline empty and POSTs 409.

Phase 4: Settings, approvals and spend cap. The manage-mode header gains a **Settings** view
(Team, Fallbacks, Lanes, Approval gate, Spend cap; `?view=settings`) backed by `GET`/`POST
/api/config` (stale-write 409, `config.backups/` newest 20, atomic write, `OFFICE config changed`
event; model edits only replace the value after `-m`/`--model`). `bench`/`unbench` inbox
commands park positions live (no restart; 🪑 lounge bubble, fallback cover, `BENCH`/`UNBENCH`
events, persisted to config.json). The approval gate (`approval_gate` + per-task
`needs_approval` via `set_approval`) pauses lane commits on `APPROVAL WAIT`, waits on
`project/approvals/T-x.json` with STOP-aware polling (`await_approval`, auto-approve on
`timeout_minutes`), and records `APPROVAL`/`APPROVAL TIMEOUT` events; the Office adds an ✋
badge with an Approvals modal (`GET /api/approvals` read-only, `POST /api/approval`) and a
"Require my approval" drawer checkbox. The spend cap (`spend_cap`, `opencode stats --days 1
--models` cached 5 min) parks pay-per-use accounts until midnight with one `SPEND CAP` event
per day (💸 bubble, amber/red meter in Stats → Quota and cost). Polish: throughput 0 at the
baseline with gridlines (≤220 px), burndown axes/legend/ticks, lane timeline without the stray
header and "now" on top, content-sized curved routing ribbons, demo spend rows that sum to the
total, inline ▶ Play, left→right graph layers with edge-to-edge routing and fit-to-width, and
deterministic tests (deadline polling, explicit `os.utime`).

## 1.1.0 (2026-10-18)

Positions are roles now, not models. Agents are `quarterback` / `qa_lead` / `coder_1..5`;
the model under each is one swappable field, two positions may share a model as long as
they share its `account`, and `roles` maps the appointed quarterback/QA (legacy
`claude`/`codex` ids and owner tags still resolve). Fallback chains are documented as
the priority order per position. The office shows a Subscriptions panel (one badge per
usage-limit bucket, worst state first) and each agent's model; `probe_models.py` probes
once per account. The office also collapses task and lane bubbles until hovered/tapped,
click to pin.

## 1.0.0 (2026-10-18)

First capture of the engine, taken from Grim Haven while its v2.0 overhaul was running.

- Template: orchestrator (3 lanes, background planner, PLAN_NOW, fallback chains, account-shared limits, OpenAI preemptive handoff, OpenCode live rate-limit abort, PROVIDER DOWN / MODEL GONE parking, `stop_after_milestone`), supervisor (relaunch, stall detection, headless fixer chain), role guides (art = image generation only), Godot 4 scaffold (test runner, DevTools scenarios/screenshots, GameData, Dice).
- Agent tables are config-driven (`label`, `account` per agent) instead of hard-coded.
- `presets/default.json`: the Grim Haven team (Claude plans/reviews, paid Muse codes, Codex QA + art with no art fallback, Codex Luna and free OpenCode models as fallbacks).
- `scripts/scaffold.py` uses the default preset unless told otherwise.
- Ops: `status.py`, `probe_models.py`, `test_orchestrator.py` (dummy-agent end-to-end test), `sync_from_project.py`.
- Docs: README how-to, PLAYBOOK with lessons log, supervising guide with the check-in prompt.
- Examples from Grim Haven. Claude Code skill (`/ai-game-studio`) now reads from this folder.
