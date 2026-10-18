---
name: ai-game-studio
description: Set up and run an autonomous multi-agent "AI game studio" (the Game Creations Engine) that designs and builds a complete Godot game unattended. Claude is the quarterback (plans, writes briefs, reviews); coding models (paid Muse via OpenCode, Codex, free OpenCode models) code in parallel git-worktree lanes; Codex does QA and image-generated art; a Python orchestrator runs work → Godot checks → QA → review → commit, with fallback chains, rate-limit handling, a stall-fixing supervisor and phone alerts. Use this whenever the user wants to build a new game (or a similarly large software project) with an autonomous AI team or agents, mentions the game creations engine, wants to reuse the Grim Haven / Zombie Siege setup, asks for an orchestrator that runs coding agents unattended overnight, or says things like "start a new game project like the last one", "spin up the agent team for a new game", or "build me a game autonomously". Also use it to diagnose, supervise or tune a running studio (stalls, rate limits, lanes, model fallbacks), or to sync improvements from a game back into the engine.
---

# AI Game Studio (Game Creations Engine)

Everything lives in the engine folder, which is the master copy:

**ENGINE = `{{ENGINE_PATH}}`**

Read `ENGINE/README.md` for the owner-facing guide and `ENGINE/docs/PLAYBOOK.md` before your first setup. The playbook explains how the machine works and the failure modes that are fixed in the template; knowing why things are the way they are stops you from "simplifying" a fix away. Proven on Grim Haven (Darkest Dungeon × XCOM tactics: 300+ tasks, v1.0 plus expansions and a v2.0 art overhaul).

## Map

```
ENGINE/presets/default.json     the default team (Grim Haven lineup); scaffold uses it when no --agent flags are given
ENGINE/template/                project skeleton (orchestrator, supervisor, roles, Godot scaffold, .bat files)
ENGINE/scripts/scaffold.py      create a project: --target --name --pitch --lane-root [--preset | --agent ...]
ENGINE/scripts/write_board.py   load the first backlog from a JSON list
ENGINE/scripts/benchmark_models.py   can a model really fix a bug right now?
ENGINE/ops/status.py            health of a running game
ENGINE/ops/probe_models.py      is each agent OK / rate-limited / down / gone?
ENGINE/ops/test_orchestrator.py dummy-agent end-to-end test (engine, or a project's patched orchestrator)
ENGINE/ops/sync_from_project.py bring a game's machinery improvements back into template/
ENGINE/docs/                    PLAYBOOK, supervising (check-in prompt), interview, briefs, gdd/art templates, other_engines
ENGINE/examples/grim-haven/     a real GDD, art guide, owner requests, decisions, config, task briefs, milestone reports
```

## Setup workflow

Track these as todos; each step's output feeds the next.

1. **Interview** the owner (`ENGINE/docs/interview.md`): mechanics, setting, signature systems, length, art style; then the team. Offer `presets/default.json` as the recommended lineup and say what costs money (paid Muse is pay-per-use). Use AskUserQuestion with recommended options first. Don't skip it: the design answers shape every brief, and model and money choices are the owner's to make.

2. **Check tools and models.** `godot_console`, `git`, `python`, and the CLIs in the lineup (`claude`, `codex`, `opencode`). Confirm model ids (`opencode models`) and run `python ENGINE/ops/probe_models.py ENGINE/presets/default.json` (or the chosen preset). Benchmark candidate free models with `scripts/benchmark_models.py` from a short path outside any repo. Never make a free model the only option for a role.

3. **Scaffold** into the empty target folder:
   ```
   python ENGINE/scripts/scaffold.py --target "<dir>" --name "<Game>" --pitch "<one sentence>" --lane-root C:/Users/<you>
   ```
   Add `--preset <file>` for a non-default team, or `--no-preset` with `--agent/--coders/--fallback/--paid` flags (see `--help`). If the owner's team differs from a preset only slightly, write a preset file into `ENGINE/presets/` so it's reusable. Keep `codex:work-asset` with **no fallback** when art needs image generation. Lanes must be outside OneDrive.

4. **Write the design docs** in the new project: `project/GDD.md` (from `docs/gdd_template.md`; `examples/grim-haven/GDD.md` shows the detail level that works), `project/ART_GUIDE.md` (`docs/art_guide_template.md`), the SETUP sections of `project/ARCHITECTURE.md`, and `project/decisions.md` (every interview answer with its reason). Download CC0 art backbones into `asset_library/` if the art guide calls for them.

5. **Write the M1 backlog** (`docs/briefs.md`, real examples in `examples/grim-haven/tasks/`): 10–15 tasks with sharp briefs and consistent APIs. Every brief names every file it touches; that is how lanes run in parallel. Write a tasks JSON and run `scripts/write_board.py <dir> tasks.json`.

6. **Verify** (all must pass), then look at the screenshot:
   ```
   godot_console --headless --path game --import
   godot_console --headless --path game --script res://tests/run_tests.gd      (TESTS: N passed, 0 failed)
   godot_console --headless --path game -- --quit-frames=300                   (no ERROR / SCRIPT ERROR lines)
   godot_console --path game --resolution 1280x720 -- --scenario=default --screenshot=<abs path>.png --frames=60
   ```

7. **Commit and launch.** `git init -b main`, commit (with the user's attribution lines), tag `M0`. Launch with `explorer.exe start.bat` and `explorer.exe supervise.bat` (separate windows that outlive this session). Watch `project/events.log` until the first PLAN and the first coder task both complete.

8. **Hand over.** Tell the owner how to watch (`ops/status.py`, STATUS.md, the ntfy topic), steer (OWNER_REQUESTS.md + `project/PLAN_NOW`), stop (stop.bat, or `stop_after_milestone`), and what costs money. Offer a 20-minute check-in using the prompt in `docs/supervising.md`, and explain it's a second layer: `supervisor.py` catches stalls on its own.

## Supervising a running studio

Follow `ENGINE/docs/supervising.md`. Principles:
- Fix the **machinery** (orchestrator, config, tooling, a broken brief), not game code. Steer content through `project/OWNER_REQUESTS.md`. Never edit `project/board.json` while the orchestrator runs.
- Check the boring explanation first: an idle lane is often a real dependency chain, and a paid fallback is often a real rate limit.
- Test non-trivial orchestrator changes with `python ENGINE/ops/test_orchestrator.py "<project>" --orchestrator <patched copy>`. **Never run a second orchestrator inside the real repo.** Use absolute paths.
- Delete a pending `project/RESTART` before editing the orchestrator, then commit and recreate it.
- Model changes are the owner's call. Write them into config `coders`/`fallback` with a dated `_notes` line.

## Improving the engine

When a game's machinery improves (a fix during supervision, a new feature), bring it home: `python ENGINE/ops/sync_from_project.py "<project>"` (dry run), then `--apply`, then `python ENGINE/ops/test_orchestrator.py`, review `git diff` in ENGINE, commit, and add the lesson to the log at the end of `ENGINE/docs/PLAYBOOK.md` (and CHANGELOG/VERSION). Engine-owned docs (PROTOCOL, ARCHITECTURE, README/CLAUDE/AGENTS templates) are edited in `ENGINE/template/` directly. Edit this skill in `ENGINE/skill/SKILL.md` and re-run `ENGINE/skill/install_skill.py`.

## Adapting

- Other engines: `docs/other_engines.md` (only `run_checks()` is Godot-specific).
- Non-game projects: keep the protocol and roles, replace the GDD with a product spec, and swap the checks for the project's build/test/smoke commands.
