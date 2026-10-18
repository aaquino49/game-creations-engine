# Architecture and Code Conventions

Engine: **Godot 4.7.2**. Language: **GDScript**, statically typed. Renderer: GL Compatibility.
Godot executable: `godot_console` (on PATH; console wrapper for `godot`). The Godot project root is `game/`.

## Commands (run from the repo root)

**Windows: run Godot as `godot_console`**, not `godot`. `godot.exe` is a GUI program: PowerShell (which Codex uses) returns immediately without waiting for it or capturing its output, so tests look like they printed nothing. `godot_console` is the console wrapper and behaves normally in every shell.

| Purpose | Command |
|---|---|
| Re-import assets (after adding files or new `class_name` scripts) | `godot_console --headless --path game --import` |
| Run all unit tests | `godot_console --headless --path game --script res://tests/run_tests.gd` |
| Run ONE test file or test | `godot_console --headless --path game --script res://tests/run_tests.gd -- --filter=test_grid` (never pass a `test_*.gd` file to `--script`: test files aren't runnable and Godot hangs) |
| Smoke run (300 frames, headless) | `godot_console --headless --path game -- --quit-frames=300` |
| Screenshot | `godot_console --path game --resolution 1280x720 -- --scenario=<name> --screenshot=<ABSOLUTE path>.png --frames=120` |
| Syntax-check one script | `godot_console --headless --path game --check-only --script res://path/to/file.gd` (always include `--path game`) |
| Export Windows build | `godot_console --headless --path game --export-release "Windows Desktop" ../builds/GrimHaven.exe` |
| Play (humans only) | `godot_console --path game` |

**Never start Godot without a way to quit.** Every automated run must be headless + `--quit-frames`, a `--screenshot` run, or the test runner. `godot_console --path game` with no flags opens the game and never returns, and that hangs you. So does `--script` on a script that doesn't extend SceneTree, or any Godot command without `--path game`. `--screenshot` needs a windowed run; headless `--screenshot` runs skip the PNG and quit. DevTools force-kills automated runs after 120 s and prints `ERROR: DevTools failsafe`. If you see that line, your code has an infinite loop or never finishes a frame.

The pipeline runs import, tests, smoke and screenshot after every work step. Any `SCRIPT ERROR`, `Parse Error` or `ERROR:` line in the import, smoke or screenshot output fails the attempt.
In the **unit-test** run, only `SCRIPT ERROR` and `Parse Error` fail. Negative tests that deliberately call `push_error` print `ERROR:` lines by design; that's expected, not a bug.

## Folder layout

```
game/
  project.godot
  scenes/
    main.tscn          entry point: hosts the current screen (Game autoload swaps screens)
    ui/                title, shared widgets (panels, bars, tooltips)
    tactical/          combat screen, expedition screen
    base/              Haven screens (hub, building panels, hero sheet, embark)
  scripts/
    autoload/          DevTools (pipeline harness), Events (signal bus), Game (screen router + current campaign)
    sim/               PURE LOGIC. RefCounted classes, no Node/scene/autoload dependencies -> unit-testable
      core/            GameData, Dice (seeded RNG wrapper), Stats helpers
      combat/          BattleGrid, LineOfSight, Pathing, CombatUnit, BattleState, CombatRules, SkillResolver, EnemyAI, StatusEffect
      heroes/          Hero, Roster, Quirks, StressRules, Leveling
      expedition/      DungeonGenerator, ExpeditionState, RoomContent, Provisions
      haven/           HavenState, Buildings, Economy, WeekCycle, DoomTrack, Recruiting
      campaign/        CampaignState (top-level save object), SaveGame
    tactical/          Node scripts for combat/expedition screens (thin views over sim)
    base/              Node scripts for Haven screens
    ui/                shared UI node scripts
  data/                JSON balance and content data (see GDD §12)
  assets/              curated art and audio the game actually uses (see project/ART_GUIDE.md)
  dev/scenarios/       screenshot scenarios: <name>.gd with `static func setup(main: Node) -> void`
  tests/               test_*.gd extending TestCase (see tests/README.md)
asset_library/         (repo root, outside game/) raw downloaded packs. Godot can't see it; copy what you use into game/assets/.
```

## Rules

1. **The simulation is separate from the view.** All rules (grid, LOS, cover, hit chance, damage, statuses, stress, Death's Door, AI, dungeon generation, economy, the week cycle, doom) live in `scripts/sim/` as `class_name` RefCounted classes. Nodes read sim state, draw it, and send commands to it. Nothing in `sim/` may reference a Node, a scene, an autoload, `Input`, or `get_tree()`.
2. **Deterministic randomness.** Every sim class that rolls dice takes a `Dice` (seeded wrapper around `RandomNumberGenerator`) in its constructor or method. Never call the global `randi()`/`randf()` in `sim/`. Tests pass a fixed seed, or use `Dice.forced([...])` to script exact rolls.
3. **Data-driven.** No balance numbers in scripts. Load them from `game/data/*.json` through `GameData` (`GameData.load_default()` reads every file once). Ids in data are `snake_case` strings and are used exactly (`gut_stab`, not `GutStab`).
4. **Combat is command-based.** The view never mutates combat state directly. It calls `BattleState` methods (`move_unit(unit_id, tile)`, `use_skill(unit_id, skill_id, target_tile)`, `end_turn(unit_id)`) that validate, apply and return a result (an `Array` of event Dictionaries, e.g. `{"type": "damage", "target": id, "amount": 7, "crit": true}`). The view animates the events in order. This keeps the rules testable and lets the balance bot play fights headlessly.
5. **Save data.** `CampaignState.to_dict()` / `CampaignState.from_dict(d, data)` round-trip everything (heroes, Haven, week, doom, RNG seed/state). Every persistent sim class implements `to_dict()`/`from_dict()`. Save as JSON at `user://campaign.save`. Tests use `TestCase.temp_path()`.
6. **Static typing everywhere:** `var x: int`, `func f(a: Vector2i) -> bool`, typed arrays (`Array[CombatUnit]`). `class_name` for every reusable class.
7. **Naming:** files `snake_case.gd/.tscn`; classes `PascalCase`; constants `UPPER_SNAKE`; signals in the past tense (`unit_moved`).
8. **Signals for decoupling.** `Events` holds cross-screen signals. No `get_node("../../..")` chains.
9. **Grid constants in one place:** `BattleGrid.TILE_PX := 48` (16 px art at 3×) and the tile/world conversion helpers live in `BattleGrid`. Grid coordinates are `Vector2i`, origin at the top left.
10. **Pathing:** breadth-first search over the grid (`Pathing` class): 4-neighbour moves; melee adjacency is 8-neighbour. Units block tiles except the moving unit's own.
11. **UI:** build screens from `Control` nodes with the shared theme `res://assets/ui/theme.tres` once it exists. Keep text in UI scripts or data, not in sim code (the sim emits ids and numbers; the view formats them).
12. **Every logic change ships with tests.** Every visible change keeps or adds a `dev/scenarios/` scenario so a screenshot shows it. Testing a Node script? Read "Testing scenes and Node scripts" in `game/tests/README.md` first.
13. Keep files under ~400 lines. Split by responsibility.
14. Don't edit `tests/run_tests.gd`, `tests/test_case.gd` or `scripts/autoload/dev_tools.gd` without a task that says to. The pipeline depends on them.
15. No third-party addons or plugins unless Claude approves (logged in decisions.md).
16. `.import` and `.uid` files ARE committed. `.godot/` is not.

## Godot 4 only

No Godot 3 syntax: no `yield`, `export var`, `onready var`, `KinematicBody2D`, `instance()`, `PoolStringArray`. Use `await`, `@export`, `@onready`, `CharacterBody2D`, `instantiate()`, `PackedStringArray`. `TileMap` is deprecated: use `TileMapLayer`.

## Screens and flow

`Game` (autoload) owns the current `CampaignState` and swaps screens under `main.tscn`'s `ScreenRoot` with `Game.goto_screen(path: String, args: Dictionary = {})`. Each screen's root script implements `func open(args: Dictionary) -> void`.

```
title -> (New Campaign) haven_hub -> embark -> expedition <-> combat -> results -> haven_hub ...
title -> (Skirmish, dev/M1) combat with a test party
```

## Display and layout

`project.godot` uses stretch mode `canvas_items`, aspect `expand`, scale mode `fractional` (decision T-015). Design every screen for a **1280×720 logical** viewport. The window scales it (1.5× on 1080p). With `expand`, the logical area can also be wider or taller (e.g. 1280×800 on 16:10, 1310×720 in a maximised window), so root Controls use full-rect anchors and anchor panels to an edge or the centre. Never hard-code 1280/720 in positions. Keep node scales and font sizes whole numbers (fonts 22/44 preferred, see ART_GUIDE).
To check a screen at 1080p, add `--fullscreen` to the screenshot command (the PNG comes out 1920×1080 on a 1080p monitor).

## Input map

| Action | Keys |
|---|---|
| `ui_cancel` (built in) | Esc: back / cancel targeting |
| `skill_1`..`skill_4` | 1–4 |
| `move_mode` | M |
| `camera_left` / `camera_right` / `camera_up` / `camera_down` | Arrow keys: pan the combat board |
| `toggle_log` | L: show or hide the combat log |
| `end_turn` | Space |
| `flee` | F: flee through exit tile |
| `pause_menu` | Esc (when nothing to cancel) |

Add new actions to `project.godot` in the same style and list them here.
