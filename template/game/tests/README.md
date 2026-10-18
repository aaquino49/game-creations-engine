# Tests

Minimal built-in test framework (no addons).

- Put tests in `res://tests/test_<area>.gd` (subfolders allowed); each file `extends TestCase`.
- Every method named `test_*` runs with a fresh instance. Use `before_each()` / `after_each()` for setup/cleanup.
- Assertions: `assert_true/false/eq/ne/almost_eq/gt/lt/not_null/has`, `fail(msg)`.
- Assertions record failures and continue; `return` early if later code depends on an earlier check.
- Tests are synchronous. Test simulation logic (pure `RefCounted` classes in `scripts/sim/`) by stepping it manually, e.g. `sim.tick(0.1)` in a loop. Don't rely on real frames or timers.
- `tree` is the SceneTree if a test needs to instantiate nodes. Free everything you create.
- Autoloads aren't guaranteed in test mode. Sim classes must not depend on them.

Run all tests (from the repo root):

```
godot --headless --path game --script res://tests/run_tests.gd
```

Run a subset: append `-- --filter=test_resources`.

## Testing scenes and Node scripts

The runner calls every test synchronously from `SceneTree._initialize()`, before any frame runs. This has consequences:

- **Don't add nodes to `tree.root`.** Nodes added there never get `_ready()` during the test, so `@onready` vars stay `null`. They also keep running `_process` after `TESTS:` is printed, and any error they hit fails the run.
- **Instantiate the scene without adding it to the tree.** Set its `@onready` vars yourself, then call `_ready()` and `bind()` by hand. For example:
  ```gdscript
  _screen = (load("res://scenes/<area>/<screen>.tscn") as PackedScene).instantiate() as Control
  _screen.set("grid", _screen.get_node("Grid"))   # one line per @onready var
  _screen.call("_ready")
  _screen.call("bind", _state)
  ```
  Or write the script so it doesn't need `@onready` (look nodes up inside `bind()` or a small getter).
- **Free with `free()` in `after_each()`, not `queue_free()`.** `queue_free()` never runs here because no frame follows.
- **When a view removes a child, call `remove_child(node)` before `node.queue_free()`.** Then `get_child_count()` is correct immediately, both in tests and in game.
- Nodes outside the tree have no viewport. Don't call `get_global_mouse_position()`, `get_viewport()` or `get_tree()` on them. Put the logic behind input handlers in public methods (e.g. `place_at(origin)`) and test those instead.
- To refresh per-frame visuals, call `node._process(0.0)` directly.
- Use `GameData.load_default()` for real data. `GameData.new()` is empty.
- **Use asserts, not return values.** Tests are `func test_x() -> void` and use `assert_*`. The runner ignores return values.
- A runtime `SCRIPT ERROR` inside a test fails that test, and the runner prints the file:line. Deliberate `push_error()` calls do not fail tests.
