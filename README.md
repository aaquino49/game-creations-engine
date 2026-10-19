# Game Creations Engine

A reusable, autonomous AI game studio. You describe a game; a team of AI agents designs, codes, tests, illustrates and ships it in Godot 4, around the clock, while you steer from a text file.

It is the exact machinery that built **Grim Haven** (a Darkest Dungeon × XCOM tactics game: v1.0 plus four expansion milestones and a v2.0 graphics overhaul, 300+ tasks), captured on 2026-10-18 so the next game starts from where that one ended.

---

## Contents

1. [How it works](#1-how-it-works)
2. [Prerequisites](#2-prerequisites)
3. [Start a new game (the easy way: ask Claude)](#3-start-a-new-game-the-easy-way-ask-claude)
4. [Start a new game by hand](#4-start-a-new-game-by-hand)
5. [Running, watching and steering](#5-running-watching-and-steering)
6. [Models, money and the default team](#6-models-money-and-the-default-team)
7. [Troubleshooting](#7-troubleshooting)
8. [Keeping the engine up to date](#8-keeping-the-engine-up-to-date)
9. [What's in this folder](#9-whats-in-this-folder)

---

## 1. How it works

```
orchestrator.py (plain Python, no AI) ── owns the task board (project/board.json) and git
  lane A (main checkout) ─┐
  lane B (git worktree) ──┼─ each task: WORK (coder) → CHECKS (Godot import, tests, smoke run, screenshot)
  lane C (git worktree) ──┘             → QA (Codex) → CHECKS → REVIEW (Claude) → commit / merge to main
  planner thread ──────────── PLAN (Claude): writes briefs, promotes tasks, closes milestones, re-plans blocked work
supervisor.py (plain Python) ─ every 2 min: relaunch a dead orchestrator; on a stall, phone alert + headless AI fixer
```

| Role | Default agent | Does |
|---|---|---|
| Quarterback | Claude Opus | Plans milestones, writes task briefs, reviews every change, design and data tasks |
| Coders | Paid Muse Spark 1.3 (OpenCode), one per lane | Implements briefs, runs tests |
| QA + art | Codex (GPT-6.1-Sol) | Tests and playtests changes; makes all art with image generation |
| Fallbacks | Codex Luna, then free OpenCode models | Take over automatically when a model hits a limit or goes down |
| Fixer | Claude → Codex → paid Muse | Called by the supervisor when the team stalls |

Agents never commit and never touch the board; they write a JSON result. A task gets up to 3 attempts, with feedback from checks, QA and review fed into the next one. After 3 failures the work is saved as a patch and the planner rewrites or splits the task. Two tasks run side by side only when their briefs name different files.

The full story (why each piece exists, the failure modes that shaped it) is in [docs/PLAYBOOK.md](docs/PLAYBOOK.md).

## 2. Prerequisites

Windows 11 (the batch files and process handling assume it; see [docs/other_engines.md](docs/other_engines.md) for adapting).

| Tool | Check | Notes |
|---|---|---|
| Python 3.11+ | `python --version` | Standard library only |
| Git | `git --version` | |
| Godot 4.x | `godot --version` and `godot_console --version` | `winget install GodotEngine.GodotEngine` provides both. Agents must use `godot_console`: PowerShell doesn't wait for the GUI `godot.exe` |
| Claude Code | `claude --version` | The quarterback. Logged in to your plan |
| Codex CLI | `codex --version` | QA + art (needs built-in image generation). Logged in to your ChatGPT plan |
| OpenCode | `opencode --version`, `opencode models` | Coders. Paid models need the provider key configured in OpenCode |
| ntfy app (optional) | | Phone alerts: subscribe to the topic the scaffold prints |

Put this folder anywhere. Put **game projects anywhere**, but the worktree lanes (`--lane-root`) must be in a short path **outside OneDrive** (e.g. `C:\Users\<you>`), because of Windows' 260-character path limit and OneDrive file locking.

## 3. Start a new game (the easy way: ask Claude)

1. Once per machine, install the Claude Code skill that points at this folder:
   ```
   python "<this folder>\skill\install_skill.py"
   ```
2. Open Claude Code in an **empty folder** for the new game and type either:
   ```
   /ai-game-studio
   ```
   or just describe it: *"Build me a new game with the game creations engine: a cozy farming roguelike..."*
3. Claude will:
   1. **Interview you** (design, setting, length, art style, which models and what you're willing to pay for). Answer the questions; recommended options come first.
   2. Check your tools and probe the models.
   3. Scaffold the project from this engine using the default team (or the one you chose).
   4. Write the game design document, art guide and first backlog of 10–15 tasks.
   5. Verify that Godot imports, tests pass, the smoke run is clean, and a screenshot renders.
   6. Commit, launch `start.bat` and `supervise.bat` in their own windows, and watch the first tasks go through.
   7. Hand over: how to watch, steer and stop. Offer a 20-minute check-in.

From then on the team runs without the chat. You can close Claude Code.

## 4. Start a new game by hand

```powershell
$E = "<this folder>"
python "$E\scripts\scaffold.py" --target "C:\Games\My Game" --name "My Game" `
    --pitch "One sentence about the game." --lane-root C:\Users\<you>
```

- With no `--agent` flags it uses [presets/default.json](presets/default.json) (the Grim Haven team). Use `--preset <file>` for another preset, or `--no-preset` plus `--agent`/`--coders`/`--fallback`/`--paid` flags to define a team from scratch. `python scaffold.py --help` lists everything.
- It prints the push-alert topic and fails if any template placeholder is left unfilled.

Then, in the new folder:

1. Write `project/GDD.md` (start from [docs/gdd_template.md](docs/gdd_template.md); [examples/grim-haven/GDD.md](examples/grim-haven/GDD.md) shows the level of detail that works: numbers, formulas, tables, milestones with "done when").
2. Write `project/ART_GUIDE.md` ([docs/art_guide_template.md](docs/art_guide_template.md)), fill in the SETUP sections of `project/ARCHITECTURE.md`, and record your choices in `project/decisions.md`.
3. Write the first backlog as a JSON list and load it: `python "$E\scripts\write_board.py" . tasks.json`. How to write briefs: [docs/briefs.md](docs/briefs.md) and the real ones in [examples/grim-haven/tasks/](examples/grim-haven/tasks/). **Every brief must name every file it touches**; that's how lanes run in parallel.
4. Verify (all must pass):
   ```
   godot_console --headless --path game --import
   godot_console --headless --path game --script res://tests/run_tests.gd
   godot_console --headless --path game -- --quit-frames=300
   godot_console --path game --resolution 1280x720 -- --scenario=default --screenshot=C:\tmp\shot.png --frames=60
   python "$E\ops\probe_models.py" .
   ```
5. `git init -b main`, `git add -A`, `git commit -m "M0 scaffold"`, `git tag M0`.
6. Double-click `start.bat` and `supervise.bat` (or `explorer.exe start.bat` from a terminal).

## 5. Running, watching and steering

| I want to… | Do this |
|---|---|
| See how it's going | `python "<engine>\ops\status.py" "<game>"`, or open `project/STATUS.md` (lanes, planner, milestones) and `project/events.log` |
| Get phone alerts | Subscribe to the ntfy topic in `orchestrator/config.local.json` → `notify.ntfy_topic`. That file is git-ignored on purpose: anyone who knows the topic can read and send your alerts |
| Ask for a change | Add a line under **Open** in `project/OWNER_REQUESTS.md` (see [the Grim Haven one](examples/grim-haven/OWNER_REQUESTS.md)). Then create an empty file `project/PLAN_NOW` so it's planned within ~30 seconds instead of at the next routine plan |
| Stop after the current step | `stop.bat` (creates `project/STOP`). Delete `project/STOP` and run `start.bat` to resume |
| Stop at a milestone | Set `"stop_after_milestone": "M8"` in `orchestrator/config.json`, commit, create `project/RESTART` |
| Reload changed orchestrator code or config | Commit, then create `project/RESTART` (reloads between tasks) |
| Change which models code | Edit `coders` / `fallback` in `orchestrator/config.json`, commit, create `project/RESTART` |
| Play the current build | `play.bat` |
| Have Claude watch it | In a Claude Code chat: *"Set a 20-minute check-in for `<game>` using the engine's docs/supervising.md"* |

**Never** edit `project/board.json` while the orchestrator runs, and never start a second orchestrator in the same project.

**Manage mode (the Office).** `office.bat` is read-only. Double-click `office-manage.bat` (or `python office/server.py --manage`) for controls: the console prints a token URL like `http://localhost:8765/?token=...` — open that (the page keeps the token for the session). The header bar offers **Plan now** (plans within ~30 s), **Restart** (reloads orchestrator code between tasks), **Stop** (finishes the current step then stops; **Start** re-launches via `start.bat` when the team is offline), each pending flag shown as a chip you can cancel; the **Requests** panel sends a line to `project/OWNER_REQUESTS.md` for the next plan; the **Health** panel probes each model, sends a test phone notification, and can start the supervisor. Security: every write needs the token header and only `localhost` may call — `--lan` (phone on the same Wi-Fi) additionally allows the machine's LAN IP, which exposes the controls to your Wi-Fi, so keep the token URL private.

**Settings, approvals and spend cap.** In manage mode the header has a **Settings** view (Team, Fallbacks, Lanes, Approval gate, Spend cap) and an **✋ approvals** badge. Team edits (model/account/label, coder and paid toggles, add/remove positions, coder order ▲▼), fallback chains (chips with ▲▼ ✕, paid-last kept at the end, per-row preview), lane count (1–6; lane A is the main checkout, the rest are worktree lanes), the approval gate (enabled, types, workers, timeout) and the spend cap (daily USD, agents) all save through `POST /api/config` with a stale-write check (409), a `config.backups/` copy (newest 20) and an atomic write; lane additions and most roster changes print "Saved. Restart the team to apply" with a **Restart now** button. **Bench** / **Unbench** (Team panel, Settings cards, or `bench`/`unbench` commands) parks a position live with no restart — benched workers sit in the lounge with a 🪑 bubble and fallbacks cover their steps. When review approves a task that needs approval, the lane waits (✋ on its plate, "waiting for owner approval" in the header) until you **Approve** or **Request changes** in the Approvals modal (`GET /api/approvals` is read-only; timed-out waits auto-approve). The Stats → Quota and cost section shows today's OpenCode spend against the cap (amber at 80%, red at 100%, "parked until 00:00" when capped); capped accounts nap with a 💸 bubble. Free-form `cmd` editing is never allowed: a model change only replaces the value after `-m` / `--model`.

**Views, drawer, task actions.** The header switches **Office | Board | Graph | Stats | Notes | Settings** (Settings is manage-only; remembered locally, deep-linkable as `?view=settings` / `?view=stats` / `?view=notes`). Click any task — a lane plate, worker bubble, board card, graph node, or ticker `T-123` — to open the task drawer: header (status, milestone, type, owner, priority, attempts, depends-on chips), tabs **Brief / Acceptance / Attempts** (per-attempt worker, verdict badges, review summary, QA bugs, screenshot thumbnails, log/patch links with a patch-coloured file viewer), plus a **Live** tab when the task runs on a lane (tails the agent's `.live.log`, auto-scrolls, Watch via the lane plate). **Timeline** plays every `project/runs` screenshot in mtime order with slider, ▶/◀, arrow keys, Play (700 ms loop) and a milestone filter. **Board** groups by Backlog/Ready/In progress/Blocked/Done/Dropped with milestone filter (Done collapses after 20). **Graph** draws the dependency DAG (layers by longest chain, cycles ignored, pan/zoom; nodes show id plus ~18 chars of title). In manage mode the drawer offers priority/status selects, **Retry** (blocked only) and **Drop**, and Board has **+ Add task**; all go through `project/commands/` for the orchestrator (pending ⏳ chips; a 90 s stale warning means the orchestrator predates 1.2).

**Stats, Notes, Play.** **Stats** (`/api/stats?hours=6|24|72|168`, read-only, offline hand-drawn SVG) has a 6 h / 24 h / 3 d / 7 d selector: agent scorecards + leaderboard (all-time, with a "this window" toggle, 🏆 for the top row), DONE-per-hour bars and open-tasks-per-milestone lines with milestone/whole-board ETAs, a lane Gantt (bars START → DONE/BLOCKED/RECOVER/now, click opens the drawer; hatched account-limit rows; now line), a FALLBACK routing flow + per-agent incident counters, per-account quota/limits plus Codex usage meters and OpenCode spend tables (paid models flagged, "spend unavailable" with reason otherwise), and a newest-first incident log pairing each `SUPERVISOR-AI called` with its outcome. **Notes** pairs every `PLAN start/done` with duration and summary alongside `decisions.md`, `assumptions.md`, `PM_NOTES.md` and `project/milestones/*.md` (served through the existing `/api/file`, which still refuses everything else under `project/`). **Play**: the header shows a **▶ Play** button (manage mode only, when the exe exists; tooltip e.g. "Build from 14:02, v1.0") that launches `play.bat` via `POST /api/control {"action":"play"}` — allowed while the team runs; read-only mode shows the build time as text. The exe is the `builds\X.exe` named in `play.bat` (else the newest `builds/*.exe`), tagged with `git describe`.

**Office zones.** The office has three zones so working vs resting reads at a glance: the **planning office** (top-left glass room with whiteboard and meeting table) holds only the planner at `PLAN_SPOT`; the **work floor** (blue planks, lane desks, supervisor corner with the fixer's seat and the corgi's bed) holds `work`/`qa`/`review` at lane desks and `fix` with the supervisor; the **break room** (warm wood, lounge rug, couches, vending/cooler/fridge/coffee) holds everyone idle, napping or benched, with pets wandering the work floor and break room but never entering planning. Walkers route through the planning door and the two partition doorways and never cross walls. The planning office's lights are on only while someone is planning, fading dark over 400 ms otherwise (instant under reduced motion).

More on supervising, including the check-in prompt: [docs/supervising.md](docs/supervising.md).

## 6. Models, money and the default team

[presets/default.json](presets/default.json) is the Grim Haven lineup as of 2026-10-18.
Positions are roles; the model under each is one swappable field:

| Position | Model | Used for | Cost |
|---|---|---|---|
| `quarterback` | Claude Opus 5.5 | plan, review, design | your Claude plan |
| `qa_lead` | GPT-6.1-Sol | QA, all art | your ChatGPT plan |
| `coder_2` | GPT-6-Luna | first coding fallback | same ChatGPT plan (shares its limit) |
| `coder_1` | Muse Spark 1.3 Contributor (OpenCode) | coding, all lanes | **pay per use** |
| `coder_3`, `coder_4`, `coder_5` | free OpenCode models | coding fallbacks | free, often rate-limited |

Rules baked into the preset (each one learned the hard way):

- **Art has no fallback** (`"qa_lead:work-asset": []`). Models without image generation will "paint" portraits with code and they look terrible. Art tasks wait for the QA lead instead.
- **Paid positions go last** in every chain (`paid_agents`), except where you deliberately make one a coder.
- **QA avoids the model that wrote the code.**
- **Shared accounts share limits.** `qa_lead` and `coder_2` both draw on one OpenAI plan; the orchestrator hands work off early at 97% / 98% usage. The office sidebar shows every subscription's state.
- **Free models are unreliable.** Benchmark them before relying on them (`python scripts/benchmark_models.py`), and never make one the only option for a role.
- **Priority order = fallback chains.** Each `"position:step"` list in `fallback` is tried in order when a subscription runs out (e.g. quarterback falls back to `qa_lead`, then `coder_1`). Edit them in `orchestrator/config.json`, commit, create `project/RESTART`.

To make your own lineup, copy `presets/default.json` to `presets/<name>.json`, edit it, and scaffold with `--preset presets/<name>.json`. Agent specs are `claude:<model>`, `codex:<model>`, `opencode:<provider/model>` or `cmd:<JSON argv with {prompt}>`, each optionally `@account`, or a `{"kind", "model", "account"?, "label"?}` dict. Model ids change; check `opencode models` and `ops/probe_models.py` before a new game. To swap a model, edit its position's `model` (and `cmd` follows automatically on next scaffold — for a running project, edit both `model` and the `-m` in `cmd`).

## 7. Troubleshooting

| Symptom | Likely cause → fix |
|---|---|
| `status.py` says orchestrator down | Crashed or stopped. If `project/STOP` exists, that's why. Otherwise `supervise.bat` relaunches it within 2 minutes; check it's running |
| Lots of `USAGE LIMIT` / `FALLBACK` lines | Normal: a model hit its limit and the next in its chain took over. If the paid agent is doing everything for hours, run `ops/probe_models.py` |
| `PROVIDER DOWN` / `MODEL GONE` | A provider is erroring (parked 30 min) or a model was withdrawn (parked 12 h; remove it from the config) |
| A lane is idle while tasks are ready | Usually the ready tasks depend on unfinished ones, or name the same files as running tasks. A real bug if it lasts 20+ min with independent work available; the supervisor will flag it |
| Art tasks waiting a long time | They're waiting for Codex (by design). Check your ChatGPT usage |
| `BLOCKED T-###` | 3 attempts failed. The planner will rewrite or split it. Read `project/runs/T-###/a3/` to see why |
| `RESTART` file sits there for an hour | The reload waits for every lane to finish its current task; a long task delays it |
| Changed the orchestrator and want to know it still works | `python ops/test_orchestrator.py "<game>" --orchestrator <your copy>` (dummy agents, throwaway clone, ~3 min) |

Deeper diagnosis: everything an agent saw and produced is in `project/runs/<task>/a<attempt>/` (prompt, logs, check output, screenshots, result JSON). The failure-mode table in [docs/PLAYBOOK.md §4](docs/PLAYBOOK.md) lists every problem we've hit and its fix.

## 8. Keeping the engine up to date

Each game improves the machinery as problems come up (the supervisor and the check-ins fix the orchestrator live). Bring those fixes home so the next game starts with them:

```powershell
cd "<this folder>"
python ops\sync_from_project.py "<game folder>"            # dry run: what would change
python ops\sync_from_project.py "<game folder>" --apply    # copy machinery in, turning names back into placeholders
python ops\test_orchestrator.py                            # scaffold a fresh game and run it with dummy agents
git diff                                                   # review
git commit -am "Sync from <game>: <what improved>"
```

Then add what you learned to the lessons log at the bottom of [docs/PLAYBOOK.md](docs/PLAYBOOK.md), bump [VERSION](VERSION) and note it in [CHANGELOG.md](CHANGELOG.md).

Only machinery is synced (orchestrator, supervisor, batch files, role guides, test runner, DevTools, core helpers). Game code and content never are. `project/PROTOCOL.md`, `ARCHITECTURE.md`, `README`/`CLAUDE`/`AGENTS` templates are owned by the engine: improve them here directly.

The Claude skill reads everything from this folder, so there's nothing to re-install after an update.

## 9. What's in this folder

```
README.md                 this guide
VERSION, CHANGELOG.md     engine version history
presets/default.json      the default team (agents, coders, fallbacks, paid agents, lanes)
template/                 the project skeleton scaffold.py copies ({{PLACEHOLDERS}} filled in)
  orchestrator/           orchestrator.py, supervisor.py (config.json is generated)
  project/                PROTOCOL.md, ARCHITECTURE.md, OWNER_REQUESTS.md, decisions.md, roles/*.md
  game/                   Godot 4 scaffold: test runner, DevTools (scenarios, screenshots, failsafe), GameData, Dice
  *.bat                   start / stop / supervise / play
scripts/
  scaffold.py             create a game project from the template + a preset
  write_board.py          load the first backlog (board.json + briefs) from a JSON list
  benchmark_models.py     can this model actually fix a bug right now?
ops/
  status.py               one-screen health view of a running game
  probe_models.py         is each agent answering, rate-limited, down or gone?
  test_orchestrator.py    end-to-end orchestrator test with dummy agents on a throwaway clone
  sync_from_project.py    pull machinery improvements from a game back into template/
test_harness/             dummy agent + fake Godot used by test_orchestrator.py
docs/
  PLAYBOOK.md             how the machine works, failure modes and fixes, tuning knobs, lessons log
  supervising.md          supervising a running game; the 20-minute check-in prompt
  interview.md            questions to ask the owner before a new game
  briefs.md               how to write task briefs that cheap models can execute
  gdd_template.md, art_guide_template.md, other_engines.md
examples/grim-haven/      real artifacts from Grim Haven: GDD, art guide, owner requests, decisions,
                          architecture, config, sample task briefs and milestone reports
skill/
  SKILL.md                master copy of the Claude Code skill (/ai-game-studio)
  install_skill.py        installs it to ~/.claude/skills/ai-game-studio, pointing at this folder
```

## License

MIT; see [LICENSE](LICENSE). The bundled Office art (CC0) and font (SIL OFL 1.1) keep their own licences, included in `template/office/assets/`.
