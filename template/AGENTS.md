# {{GAME_NAME}}: Agent Instructions

This repository is built by an autonomous team of AI agents run by `orchestrator/orchestrator.py`.

- Your role and exact instructions are in the prompt file the orchestrator gave you. Role guides:
  - Coders: `project/roles/coder.md`
  - QA and assets (Codex): `project/roles/qa_assets.md`
  - Quarterback (Claude): `project/roles/quarterback.md`
  - Supervisor (stall fixer): `project/roles/supervisor.md`
- Team rules and output formats: `project/PROTOCOL.md`
- Game design: `project/GDD.md`. Code conventions and commands: `project/ARCHITECTURE.md`. Art: `project/ART_GUIDE.md`.

Hard rules:
- No human is available. Never ask questions. Log assumptions in `project/assumptions.md`.
- Never run `git commit/reset/checkout/stash` (exception: the supervisor role commits its own `orchestrator/` fixes). Never edit `project/board.json`.
- Always finish by writing the JSON output file named in your prompt.
