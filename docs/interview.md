# Setup interview

Ask with the AskUserQuestion tool, at most 4 questions per call, 2–3 rounds. Put your recommended option first with "(Recommended)". Tailor the options to the pitch: these are the questions that mattered for Grim Haven, generalized. Skip anything the user already answered.

## Round 1: the game

1. **Core loop / genre mechanics.** Offer 2–3 concrete interpretations of their pitch, e.g. for "Darkest Dungeon meets XCOM": hybrid (room-graph crawl + grid fights with cover), pure DD (ranked side-view), pure XCOM (grid maps). Describe what each means to play and how hard it is to build.
2. **Setting and tone.** 3–4 options that fit the mechanics.
3. **Signature systems** (multiSelect): the 3–5 systems from their reference games that define the feel (e.g. stress/afflictions, quirks, Death's Door, a light meter).
4. **Session and campaign length / win condition.** e.g. 1–2 h replayable runs vs 3–5 h campaign with a final boss vs open-ended.

## Round 2: the team and pipeline

1. **Which models do what.** Defaults that worked: Claude quarterback; Codex QA + art; coders = the user's choice (a strong subscription model like Codex GPT-6-Luna is most reliable; free OpenCode models are fine as coders only with a fallback chain).
2. **Fallbacks and money.** Which agent covers when a model is rate-limited; is a paid API allowed, and only as the last resort?
3. **Art source.** CC0 packs + procedural (no image generation; recommend Kenney packs recolored to a palette), Codex image generation, or reuse of an existing library.
4. **Run mode.** Autonomous with phone alerts and keep expanding after v1 (recommended), autonomous but stop at v1, or stop after each milestone for review.

## Round 3: scope details (only what the GDD needs)

E.g. character/class structure, the base or meta layer, the pressure mechanic (doom clock, upkeep), multiplayer (usually no), engine (default Godot 4 + GDScript; see `other_engines.md` otherwise), lanes (default 3).

## Before scaffolding, check

- `godot --version`, `claude --version`, `codex --version`, `opencode --version`, `git --version`, `python --version` (only for the tools the lineup uses).
- `opencode models` for exact model ids (free ones end in `-free`). Benchmark the candidate free models with `scripts/benchmark_models.py` before putting them in a chain.
- The target folder is empty (or ask before using `--force`).
- Worktree lanes go outside OneDrive/Dropbox (default: the user's home folder).
