# Using another engine

The orchestrator is engine-agnostic except for `run_checks()` (and the Godot watchdog). Godot was chosen because everything runs headless from the command line: import, unit tests, a smoke run and screenshots, so every attempt is verified automatically. Any engine works if you can provide the same four checks as commands that exit non-zero on failure:

| Check | Godot (template) | Web/TypeScript (e.g. Phaser + Vite) | Unity |
|---|---|---|---|
| import / build | `godot --headless --path game --import` | `npm run build` (tsc + vite) | `Unity -batchmode -quit -projectPath game -buildTarget ...` |
| tests (must print a summary line) | `run_tests.gd` → `TESTS: N passed, M failed` | `vitest run` (adapt the summary regex) | `-runTests -testPlatform EditMode` + parse XML |
| smoke | 300 headless frames, no `ERROR:` | headless browser (Playwright) loads the page, no console errors | play-mode test that runs N frames |
| screenshot | `--scenario=<name> --screenshot=<png>` | Playwright `page.screenshot` with a `?scenario=` URL param | play-mode test capturing a RenderTexture |

To switch: edit `run_checks()` in `orchestrator/orchestrator.py` (keep the result dict shape: `import/tests/smoke/capture` each with `ok/rc/timed_out/errors/warnings`, plus `passed`, `screenshot`, `tests_summary`), adjust `GODOT_ERROR_RE`/`SCRIPT_ERROR_RE`, replace `game/` with the new project, and rewrite `project/ARCHITECTURE.md` and the role guides' command lists. Keep the principles: pure-logic sim separated from the view, seeded randomness, data-driven balance, scenario-based screenshots, and a failsafe so no automated run can hang.

Test a modified orchestrator on a scratch clone with dummy agents before the real run (see PLAYBOOK §4).
