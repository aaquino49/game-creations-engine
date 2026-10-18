# Architecture and Code Conventions

Engine: **Godot 4.7** (match the installed version; check with `godot --version`). Language: **GDScript**, statically typed. Renderer: GL Compatibility.
Godot executable: `godot` (on PATH). The Godot project root is `game/`.

<!-- SETUP: adapt the folder layout under scripts/sim/ and the "Screens and flow" section to this game. Keep the rules. -->

## Commands (run from the repo root)

**Windows: run Godot through its console wrapper** (`godot_console` when installed with WinGet, or `Godot_v4.x_win64_console.exe`) instead of `godot`. `godot.exe` is a GUI program: PowerShell (which Codex uses) returns immediately without waiting for it or capturing its output, so tests look like they printed nothing. If the project uses the console wrapper, write it in every command below.

| Purpose | Command |
|---|---|
| Re-import assets (after adding files or new `class_name` scripts) | `godot --headless --path game --import` |
| Run all unit tests | `godot --headless --path game --script res://tests/run_tests.gd` |
| Run ONE test file or test | `godot --headless --path game --script res://tests/run_tests.gd -- --filter=test_dice` (never pass a `test_*.gd` file to `--script`: test files aren't runnable and Godot hangs) |
| Smoke run (300 frames, headless) | `godot --headless --path game -- --quit-frames=300` |
| Screenshot | `godot --path game --resolution 1280x720 -- --scenario=<name> --screenshot=<ABSOLUTE path>.png --frames=120` |
| Syntax-check one script | `godot --headless --path game --check-only --script res://path/to/file.gd` (always include `--path game`) |
| Export Windows build | `godot --headless --path game --export-release "Windows Desktop" ../builds/{{EXE_NAME}}.exe` |
| Play (humans only) | `godot --path game` |

**Never start Godot without a way to quit.** Every automated run must be headless + `--quit-frames`, a `--screenshot` run, or the test runner. `godot --path game` with no flags opens the game and never returns, and that hangs you. So does `--script` on a script that doesn't extend SceneTree, or any Godot command without `--path game`. DevTools force-kills automated runs after 120 s and prints `ERROR: DevTools failsafe`. If you see that line, your code has an infinite loop or never finishes a frame.

The pipeline runs import, tests, smoke and screenshot after every work step. Any `SCRIPT ERROR`, `Parse Error` or `ERROR:` line in the import, smoke or screenshot output fails the attempt.
In the **unit-test** run, only `SCRIPT ERROR` and `Parse Error` fail. Negative tests that deliberately call `push_error` print `ERROR:` lines by design.

## Folder layout

```
game/
  project.godot
  scenes/
    main.tscn          entry point: hosts the current screen (Game autoload swaps screens)
    ui/                title, shared widgets
    <area>/            one folder per screen family (e.g. world/, battle/, base/)
  scripts/
    autoload/          DevTools (pipeline harness), Events (signal bus), Game (screen router + shared state)
    sim/               PURE LOGIC. RefCounted classes, no Node/scene/autoload dependencies -> unit-testable
      core/            GameData (JSON loader), Dice (seeded RNG wrapper)
      <system>/        one folder per game system
    <area>/  ui/       Node scripts (thin views over sim)
  data/                JSON balance and content data (see GDD)
  assets/              curated art and audio the game actually uses (see project/ART_GUIDE.md)
  dev/scenarios/       screenshot scenarios: <name>.gd with `static func setup(main: Node) -> void`
  tests/               test_*.gd extending TestCase (see tests/README.md)
asset_library/         (repo root, outside game/) raw downloaded packs. Godot can't see it; copy what you use into game/assets/.
```

## Rules

1. **The simulation is separate from the view.** All game rules live in `scripts/sim/` as `class_name` RefCounted classes. Nodes read sim state, draw it, and send commands to it. Nothing in `sim/` may reference a Node, a scene, an autoload, `Input`, or `get_tree()`.
2. **Deterministic randomness.** Every sim class that rolls dice takes a `Dice` (seeded wrapper around `RandomNumberGenerator`). Never call the global `randi()`/`randf()` in `sim/`. Tests use a fixed seed or `Dice.forced([...])` to script exact rolls.
3. **Data-driven.** No balance numbers in scripts. Load them from `game/data/*.json` through `GameData` (`GameData.load_default()` reads every file once). Ids in data are `snake_case` strings and are used exactly.
4. **Command-based state changes.** Views never mutate sim state directly. They call sim methods that validate, apply, and return a list of event Dictionaries (e.g. `{"type": "damage", "target": id, "amount": 7}`) that the view animates in order. This keeps rules testable and lets bots play the game headlessly for balance testing.
5. **Save data.** Every persistent sim class implements `to_dict()` / `from_dict()`. Saves are JSON under `user://`. Tests use `TestCase.temp_path()`.
6. **Static typing everywhere:** `var x: int`, `func f(a: Vector2i) -> bool`, typed arrays. `class_name` for every reusable class.
7. **Naming:** files `snake_case.gd/.tscn`; classes `PascalCase`; constants `UPPER_SNAKE`; signals in the past tense.
8. **Signals for decoupling.** `Events` holds cross-screen signals. No `get_node("../../..")` chains.
9. **UI** uses the shared theme `res://assets/ui/theme.tres` once it exists. The sim emits ids and numbers; the view formats text.
10. **Every logic change ships with tests.** Every visible change keeps or adds a `dev/scenarios/` scenario so a screenshot shows it. Testing a Node script? Read "Testing scenes and Node scripts" in `game/tests/README.md` first.
11. Keep files under ~400 lines. Split by responsibility.
12. Don't edit `tests/run_tests.gd`, `tests/test_case.gd` or `scripts/autoload/dev_tools.gd` without a task that says to. The pipeline depends on them.
13. No third-party addons or plugins unless Claude approves (logged in decisions.md).
14. `.import` and `.uid` files ARE committed. `.godot/` is not.

## Godot 4 only

No Godot 3 syntax: no `yield`, `export var`, `onready var`, `KinematicBody2D`, `instance()`, `PoolStringArray`. Use `await`, `@export`, `@onready`, `CharacterBody2D`, `instantiate()`, `PackedStringArray`. `TileMap` is deprecated: use `TileMapLayer`.

## Screens and flow

`Game` (autoload) owns shared state and swaps screens under `main.tscn`'s `ScreenRoot` with `Game.goto_screen(path: String, args: Dictionary = {})`. Each screen's root script implements `func open(args: Dictionary) -> void`.

<!-- SETUP: draw this game's screen flow here, e.g. title -> world -> battle -> results -> world -->

## Input map

| Action | Keys |
|---|---|
| `ui_cancel` (built in) | Esc: back / cancel |
| `pause_menu` | Esc (when nothing to cancel) |

Add new actions to `project.godot` and list them here.
