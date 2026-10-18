# Changelog

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
