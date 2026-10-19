# Handoff: The Office feature build (v1.2.0)

Written 2026-10-18 at the end of the session that added 22 features to The Office, the live web view of the AI
studio. Read this before continuing the work. Specs, code and tests are in the repo; this file covers what they
don't: current state, decisions, what QA caught, and what's left.

## Where things stand

- **All 22 features are built, tested and committed locally.** VERSION is 1.2.0. **Nothing has been pushed:
  publishing to GitHub is on hold until the owner explicitly says to go ahead.**
- 58 unit tests pass: `python -m unittest discover -s tests -t .` (about 10 s).
- The end-to-end orchestrator test passes: `python ops/test_orchestrator.py`. It takes about 3 minutes and uses
  dummy agents on a throwaway scaffold in `C:\Users\<you>\gce_test`.
- Commits, oldest first:

  | Commit | What |
  |---|---|
  | `72af314` | 1.1.0 baseline (positions as roles, read-only Office) |
  | `4622f8a` | Phase 1: manage mode, control bar, owner requests, health tools; plus `setup.py` and `ops/build_feature.py` |
  | `9e7b287` | Phase 2: task drawer, live logs, screenshot timeline, board/graph, task actions (command inbox) |
  | `21e87e4` | Phase 3 spec |
  | `7d7b49d` | Phase 3: Stats and Notes views, incident log, build + Play, demo data; Phase 4 spec |
  | `d606fa2` | Phase 4: Settings, bench, approval gate, spend cap; bump to 1.2.0 |
  | `1267afd` | Polish: graph fit, chart axes, consistent demo roster |

## How the work was done (reuse this workflow)

The owner wanted **Claude to write the specs and do QA, while Muse Spark 1.3 Contributor (via OpenCode,
`--variant high`) writes all the code and tests**, keeping Claude's token use low.

1. Claude writes a compact spec in `docs/specs/<name>.md`: requirements plus numbered acceptance tests. The
   shared conventions C1-C9 live in `office-phase1.md`; later specs refer back to them instead of repeating them.
2. `python ops/build_feature.py docs/specs/<name>.md` runs Muse with a one-line prompt that points at the spec,
   then runs the tests. It prints only Muse's REPORT section, `git status`, the diffstat and the tail of the test
   run. The full transcript goes to `ops/build_logs/` (gitignored). `--feedback <file>` runs a fix round, and
   `--tests-only` skips the coder.
3. Claude's QA:
   - read the summary
   - review only the risky diffs: anything that writes files, auth, the orchestrator, subprocess launches
   - do one headless browser check per phase
   - fix small bugs directly (cheaper than a feedback round), and fold cosmetic issues into the next phase's spec
4. Commit locally after each phase, then check in with the owner before starting the next.

- **Time:** Muse took 4-20 minutes per phase.
- **Cost:** about $1.90 of OpenCode spend for the whole day. That figure is from `opencode stats --days 1`, so
  it includes anything else that ran through OpenCode.

### Browser QA recipe
- Demo mode: `python template/office/server.py --demo --no-browser --port 879x`.
- Real data: build a project with `tests/office_fixture.make_project()`, copy `template/office` into it, and run
  `server.py --project <dir> --manage --token X`.
- Screenshot with headless Edge:
  `msedge --headless=new --window-size=1400,900 --virtual-time-budget=9000 --screenshot=out.png "http://localhost:879x/?token=X&view=stats"`
- Deep links: `?view=office|board|graph|stats|notes|settings` and `?task=T-12`.
- **Gotcha:** headless Edge never renders narrower than 496 px. A `--window-size=390` screenshot is laid out at
  496 px and then cropped, so it looks like horizontal overflow when there is none. Use 500 px for narrow checks.
- Stop servers afterwards:
  `Get-NetTCPConnection -LocalPort <port> -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }`.

## What was built (by phase)

The full requirements are in `docs/specs/office-phase1..4.md` and `office-polish1.md`.

- **Safety model** (C1-C9, all phases):
  - The Office is read-only unless started with `--manage` (`office-manage.bat`). Every write then needs the
    token from the URL printed in the console (`X-Office-Token` header), and requests must come from localhost
    or, with `--lan`, the LAN IP.
  - The Office never edits `board.json`. Changes go through flag files, `OWNER_REQUESTS.md`, or the command inbox
    `project/commands/*.json`, which the orchestrator applies every 5 s.
  - Settings never accepts a free-form agent `cmd`. It only replaces the value after `-m` / `--model`.
- **Phase 1:** a control bar (Plan now, Restart, Stop, Start, with cancellable flag chips), a Requests panel that
  writes to `OWNER_REQUESTS.md`, and a Health panel (probe models, test notification, start supervisor).
- **Phase 2:** a task drawer (brief, acceptance, attempts with verdicts, diffs and screenshots, and a Live log
  tail), a screenshot timeline, a Board view, a dependency Graph view, and task actions.
  - Orchestrator changes: agent output streams to `<step>.<agent>.live.log`, and the command inbox
    (`process_commands`).
- **Phase 3** (`template/office/stats.py`):
  - A Stats view: scorecards and leaderboard, throughput, burndown with ETA, lane Gantt with limit naps,
    routing flow, quota and Codex usage, OpenCode spend, and the incident log.
  - A Notes view: plans, `decisions.md`, `assumptions.md`, `PM_NOTES.md`, and milestone reports.
  - `/api/build` and ▶ Play.
  - Full demo-mode data for every view (`demo.py`).
- **Phase 4:**
  - A Settings view: a roster editor, a fallback chain editor and a lane count. Each save is validated, refused
    if the file changed since it was loaded, and backed up to `orchestrator/config.backups/` (newest 20 kept).
  - Live bench/unbench through the inbox. Benched agents count as unavailable, so the existing fallback chains
    route around them.
  - The approval gate: `project/approvals/`, `await_approval()`, and an Approvals modal in the Office.
  - A daily spend cap that parks pay-per-use accounts until midnight, using `opencode stats` with no
    `--project`, because money is spent across all projects.
- **Also:**
  - `setup.py` / `setup.bat`: one-step machine setup. It checks the tools, prints install commands for anything
    missing, and installs the skill.
  - `tests/test_office_html.py`: balanced tags and unique ids.

## Bugs QA caught that Muse's own tests missed

Keep these failure modes in mind when reviewing future work:

1. **Probe models:** `Popen(["opencode", ...])` can't launch npm `.cmd` shims on Windows. Resolve the command
   with `shutil.which` first, as the orchestrator does.
2. **Command inbox race:** the status check and the change weren't atomic, so a lane could claim a task in
   between and a running task could be dropped. The check and the apply now run under `BOARD_LOCK`.
3. **Pending command files** would have been committed into game repos. `project/commands/` and
   `project/approvals/` are now in `template/.gitignore`.
4. **Duplicated header block** in `index.html`, including a stray `</div>`. It caused a stuck "connecting…"
   pill and broke the header layout. The HTML structure test now guards against this.
5. **Spend cap bypass:** the quota prober clears a limit when an agent answers a probe, and a paid agent always
   answers. Spend-parked accounts (`_state["spend_parked"]`) are now never probed.
6. **Stale approvals:** a leftover `T-x.decision.json` from an interrupted wait could auto-approve a new
   version. Stale decisions are deleted before a new request is written, and `recover()` clears approval files
   for interrupted tasks.
7. **Spend cap model lookup:** configs without a `model` field couldn't be matched. `agent_model()` now falls
   back to the value after `-m` in `cmd`.
8. **Model ids** could start with `-` and be read as an extra CLI flag. They're rejected now.
9. **New OpenCode positions** from Settings were missing `watch_rate_limit`, so a rate limit would hang until
   timeout.
10. **Clipped throughput chart:** its wrapper cropped the x labels and the 0 baseline. The SVG height is capped
    instead.

## Known limitations / open items

- **Untested against a live game.** Everything has been verified with fixtures, demo data and the dummy-agent
  end-to-end test, but not yet with `office-manage.bat` on a real running studio. Recommended next step: run it
  for a session and watch the inbox, the live logs and the approval gate.
- **Older game projects need syncing.** The command inbox, live logs, bench, approval gate and spend cap live in
  the orchestrator, so existing games only get them after syncing `orchestrator.py` from the engine. Without
  that, the Office shows a toast when a command stays pending for more than 90 s.
- **Config edits apply on restart.** Settings saves say so and offer **Restart now**. Bench/unbench is the
  exception: it applies live.
- **Approval waits idle the lane.** While a task waits for approval, its lane does nothing.
- **`server.py` is about 1900 lines**, past the ~900-line split point that convention C9 suggests. Muse kept one
  file to avoid breaking the test fixtures' imports. Splitting out `manage.py` is a reasonable later refactor.
- **One flaky test in Phase 3** (one error in seven runs). Phase 4 made the timing-sensitive tests deterministic,
  and it hasn't recurred, but watch for it.

## Publishing checklist (on hold; do not push without the owner's go-ahead)

The owner chose a **public repo of the whole engine** with an MIT license and a one-command setup. Before the
first push:

1. Rewrite the commit author email on all local commits to the owner's GitHub noreply address. This is safe
   while nothing is pushed. Also set it as this repo's `user.email`, and suggest enabling "Block command line
   pushes that expose my email" on GitHub. **Ask the owner first**; they haven't decided yet.
2. Add a Quick Start at the top of the README (clone → `setup.bat` → `/ai-game-studio`), with a GIF of
   `office.bat --demo`.
3. Add an MIT `LICENSE`. The bundled art (CC0) and font (OFL) already allow redistribution, and their licenses
   are in `template/office/assets/`.
4. Do a fresh-clone test: clone into an empty folder, run `setup.bat`, then open the Office demo.
5. Final sweep for personal data. The git history has been scanned and is clean of tokens and ntfy topics; the
   personal paths in `examples/grim-haven/config.json` are already replaced with `<you>`.
6. Decide whether this `HANDOFF.md` ships. It's written for whoever continues the work, so consider moving it to
   `docs/` or leaving it out of the public repo.

Suggested repo name: `game-creations-engine`. Suggested topics: `ai-agents`, `claude-code`, `godot`,
`multi-agent`.

## Key files

| Path | What |
|---|---|
| `template/office/server.py` | The Office HTTP server: all endpoints, manage mode, config editor |
| `template/office/stats.py` | Stats/notes parsers: pure functions, plus `parse_opencode_stats` |
| `template/office/demo.py` | Seeded demo data for every view |
| `template/office/office.js`, `index.html`, `office.css` | The front end: no libraries, works offline |
| `template/orchestrator/orchestrator.py` | Inbox, live logs, bench, approval gate, spend cap. The `parse_opencode_stats` copy must stay identical to the one in `stats.py` (comments mark both) |
| `docs/specs/` | The phase specs, the source of truth for requirements |
| `ops/build_feature.py` | The spec → Muse → tests driver |
| `tests/` | Unit tests (`office_fixture.py` builds throwaway projects) |
| `setup.py` / `setup.bat` | One-step machine setup |
