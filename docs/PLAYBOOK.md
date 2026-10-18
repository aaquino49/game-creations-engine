# AI Game Studio Playbook

What we learned running Grim Haven (Darkest Dungeon × XCOM, Godot 4.7, October 2026): 300+ tasks across 11 milestones (v1.0 in about 2 days, then expansions and a v2.0 graphics overhaul), built by Claude + Codex + several OpenCode models. Read this before setting up a new studio, and again whenever the team stalls.

## Contents
1. How the machine works
2. Roles and model choice
3. Throughput: lanes, overlap, planning
4. Failure modes we hit (and the fix now built in)
5. Operating the run
6. Tuning knobs (config.json)
7. Supervising: what to check, in order
8. Lessons log (add to it after every game)

---

## 1. How the machine works

```
orchestrator.py (plain Python, no AI) ── owns board.json + git
  lane A (main checkout) ─┐
  lane B (worktree) ──────┼─ each: WORK (coder) → CHECKS (Godot import/tests/smoke/screenshot)
  lane C (worktree) ──────┘        → QA (Codex) → CHECKS → REVIEW (Claude) → commit / merge to main
  planner thread ──────────── PLAN (Claude): briefs, promotions, milestones, re-plans after blocks
supervisor.py (plain Python) ─ every 2 min: relaunch a dead orchestrator; on a stall, alert + call a headless fixer
```

- Agents never commit and never touch `board.json`. They write a JSON result file named in their prompt.
- Up to 3 attempts per task. Feedback from checks/QA/review goes into the next attempt's prompt. After 3 failures the task is reverted, saved as a patch and marked blocked; the planner rewrites or splits it.
- Worktree lanes merge into main after approval. If a merge conflicts, the task is requeued for lane A with the approved patch as a hint.
- `project/OWNER_REQUESTS.md` is how the owner steers a running team.

## 2. Roles and model choice

| Role | What it needs | What worked |
|---|---|---|
| Quarterback (plan, review, design/data tasks) | Judgment, long context, good at writing briefs | Claude Opus |
| QA + assets | Skeptical testing, writing tests, PIL scripting for sprites | Codex (GPT-6.1-Sol) |
| Coders | Follow a sharp brief, use tools reliably, run tests | Anything decent; quality comes from the briefs. Codex GPT-6-Luna was the most reliable; free DeepSeek V4.1 Flash and Muse Spark 1.3 were fine when available |
| Fallbacks | Availability | Free OpenCode models first (Beam and LongCat 2.5 preview benchmarked well), paid API last |

- **Benchmark free models before trusting them** (`scripts/benchmark_models.py`). In our run 7 of 11 free OpenCode models were rate-limited or hung on a one-function fix.
- **Free tiers get rate-limited for hours.** DeepSeek and Muse free were limited for most of a day. Never make a free model the only coder; give every coder a fallback chain ending in something that's always available.
- **Shared accounts share limits.** A Codex coder and Codex QA on one OpenAI plan burn the same window. The orchestrator hands work off early at `handoff_at_percent` (97% worked better than 90%).
- Claude's own limit will hit during long runs; `claude:*` falls back to Codex, then a paid agent.
- Retries alternate between coders when there are several, so a task one model can't do gets a different model. QA of a fallback-written task avoids the model that wrote it.

## 3. Throughput: lanes, overlap, planning

- **3 lanes** (A + two worktrees) gave about 1.5× the throughput of 2 lanes. More lanes need more independent ready work and burn quotas proportionally faster.
- Two tasks run side by side only if their briefs name **different files** (`task_areas` parses `game/...` paths in the brief). Folder-level matching serialized whole milestones; file-level fixed it. **Briefs must name every file they touch.** A brief that names no files counts as touching everything.
- QA playtest tasks never block other lanes (they only add tests/scenarios).
- Planning runs in a background thread so lane A keeps working. The planner keeps 3–4 ready tasks per lane.
- Typical pace once tuned: 4–6 tasks/hour, most approved on attempt 1.

## 4. Failure modes we hit (and the fix now built in)

| Symptom | Cause | Fix in the template |
|---|---|---|
| Every coder attempt "timed out" after 60 min, 5 hours lost overnight | OpenCode retries a rate-limited model silently forever and never exits | OpenCode runs with `--print-logs --log-level ERROR`; `run_proc` streams output and kills on the first rate-limit line (`abort_output_re`, OpenCode agents only via `watch_rate_limit`), then the normal fallback kicks in |
| OpenAI marked "rate-limited" for no reason | The abort pattern matched Codex printing `config.json` in a diff | Live watching applies only to OpenCode agents, and the pattern requires OpenCode's own `level=ERROR ... message="stream error"` line format |
| Approved lane-B task waited 1 h to merge while lane A was idle | A worktree agent followed the absolute run-folder path and edited the **main** checkout | Worktree prompts say where to work; a waiting merge clears stray `game/` edits in main when lane A has no task (saved as a patch first) |
| A lane idle 40 min with 6 independent tasks ready | A QA task's brief named no files, so the overlap rule blocked everything | QA tasks never count as overlapping |
| Lanes serialized within one milestone | Overlap compared folders | Overlap compares files |
| Lane A paused 5–10 min at every plan | Planning was synchronous | Background planner; plan commits only touch `project/` |
| Supervisor's AI fixer crashed on first use | `where claude` returned npm's sh shim first (WinError 193) | `shutil.which` (honours PATHEXT) everywhere |
| Coders reported "blocked: Godot printed nothing" although the pipeline's checks passed | Codex runs commands in PowerShell, which doesn't wait for the GUI `godot.exe` | Docs use the console wrapper `godot_console`; the orchestrator's own subprocess calls were never affected |
| Two lanes idle for 45+ min during a long milestone QA run | The idle-lane re-plan trigger only ran between lane A's tasks | Idle worktree lanes start the background planner themselves |
| A free provider's 5xx errors burned task attempts; a withdrawn free model was retried every 20 min | OpenCode retried for about 75 s, then exited, which is too slow for the quick-fail rule; "Model not found" wasn't recognised | PROVIDER DOWN (park 30 min, fall back) and MODEL GONE (park 12 h, notify) handling. The stall fixer wrote this one itself |
| "Painted" portraits came out as crude geometric shapes and still passed review | The art fallback chain included models without image generation (paid Muse), which drew them procedurally while OpenAI was rate-limited | **No fallback for art tasks** (`codex:work-asset: []`); role guides say painted art must be generated, never drawn procedurally, and reviewers compare against an approved portrait at game size |
| Stall fixer called overnight but did nothing | Claude and Codex were both rate-limited at once | Paid agents are appended to `supervisor.agents` as the last resort |
| My 20-min check-ins arrived 8 at a time | Session cron only fires while that chat is open and idle | Stall detection lives in `supervisor.py`, independent of any chat |
| Batch of tasks "SKIP AHEAD ... usage limit" when nothing was limited | Misleading log line (it was lane overlap) | Message now says which |
| Two planners could run at once after adding PLAN_NOW | The watcher thread didn't know about the main loop's synchronous plan | `planner_busy()` checks a `sync_planning` flag as well as the background thread |

Lessons that aren't code:
- **Test orchestrator changes on a scratch clone with dummy agents** before swapping them into a live run: `python ops/test_orchestrator.py "<project>" --orchestrator <patched copy>` (a dummy agent writes the JSON a step asks for; a fake `godot` passes checks). The clone goes in a short path outside OneDrive (Windows MAX_PATH).
- **Never start a second orchestrator in the real repo.** Use absolute paths in test commands; a failed `cd` plus `&&` chaining is what saved us once.
- `project/RESTART` reloads code between tasks; a hard restart (kill tree + `start.bat`) is fine when a lane is wedged: recovery saves in-flight work as patches.
- Remove a pending `project/RESTART` before editing the orchestrator, or it may reload a half-edited file.
- Writing Python through a shell heredoc can turn `\n` escapes into real newlines. Use the Edit/Write tools for code with escapes.

## 5. Operating the run

| Do | How |
|---|---|
| Start | `start.bat` (auto-restarts on crash, exit code 75 = reload) and `supervise.bat` |
| Stop after the current step | `stop.bat` (creates `project/STOP`) |
| Reload code between tasks | create `project/RESTART` (commit orchestrator changes first) |
| Plan right now (e.g. after adding an owner request) | create `project/PLAN_NOW`; a background plan starts within ~30 s even if every lane is busy |
| Watch | `project/STATUS.md` (lanes, planner, milestones, PM notes), `project/events.log`, ntfy topic in config |
| Steer | add a line under **Open** in `project/OWNER_REQUESTS.md` |
| Change models | edit the position's `model` (and matching `-m` in its `cmd`) in `orchestrator/config.json`, commit, `project/RESTART`; reorder `coders` / `fallback` for priority |
| Never | edit `project/board.json` while the orchestrator runs |

## 6. Tuning knobs (config.json)

| Key | Meaning | Grim Haven value |
|---|---|---|
| `coders` | positions that code; lane i starts with coders[i], retries alternate | `["coder_1"]` (was free coder_5/coder pool, then coder_2) |
| `fallback` | `"position:step"` → priority chain; steps: `*`, `plan`, `review`, `qa`, `work-code`, `work-asset`, `work-qa`, `work-design` | free models first, paid last |
| `paid_agents` | kept behind free agents even when reordering for QA | `["coder_1"]` |
| `roles` | appointed positions: quarterback (plans/reviews) and qa (QA/assets) | `{"quarterback": "quarterback", "qa": "qa_lead"}` |
| `accounts` | usage-limit buckets; positions on one account share its limit (office shows each) | anthropic, openai, meta_api |
| `lanes` | worktree lanes (dirs outside OneDrive) | B, C |
| `background_planning` | plan in a thread | true |
| `plan_every_n_done` | routine re-plan cadence | 6 |
| `max_attempts`, `agent_timeout_minutes` | per task / per agent call | 3, 60 |
| `handoff_at_percent` | early OpenAI handoff (Codex usage logs) | 97 / 98 |
| `abort_output_re`, `abort_after_matches` | live rate-limit kill for OpenCode agents | stream-error line, 1 |
| `supervisor.*` | stall thresholds, cooldown, fixer agents | 40 / 20 / 45 min |
| `expansion_after_v1` | keep adding milestones after v1 | true |
| `stop_after_milestone` | optional hard stop after this milestone closes | `"M8"`, later `"M11"` |

## 7. Supervising: what to check, in order
8. Lessons log (add to it after every game)

1. Processes alive (`orchestrator.py`, `supervisor.py`).
2. `events.log` since the last check: any DONE? Repeated AGENT FAIL, QUICK FAIL, "waiting to merge", ERROR, STUCK, BLOCKED loops?
3. `STATUS.md`: idle lanes while ready tasks exist? Check ready tasks' dependencies before calling it a bug (often it's a real chain).
4. Who is coding (STATUS "Now"/lane lines, FALLBACK lines). Paid agent for 2+ hours → probe the free models.
5. Diagnose from `project/runs/<task>/a<n>/` (prompt, agent logs, checks log, JSON results). Fix the machinery, not the game code.

Full check-in prompt and rules: `docs/supervising.md`. Quick view: `python ops/status.py "<project>"`.

## 8. Lessons log

Add a dated entry after every game (or whenever something surprising happens), newest first. Say what happened, why, and what changed in the engine.

### 2026-10-18: Grim Haven v2.0 overhaul (engine captured as v1.0.0)
- **Art needs image generation, full stop.** With OpenAI rate-limited, art fell back to paid Muse, which drew "painted" portraits with code; they passed review. Fixed with `codex:work-asset: []`, guide rules, and reviewers comparing against an approved portrait at game size. All 17 busts were repainted through image generation.
- **Give the owner a "plan now" button.** Owner requests waited up to an hour for the next routine plan. `project/PLAN_NOW` starts a background plan within 30 s.
- **One OpenAI window can't serve coding, QA and art at once.** Moving coding to paid Muse left Codex free for QA and art and removed most waiting.
- **Owner follow-ups belong in OWNER_REQUESTS.md with an explicit gate** ("gates T-293/T-294"), so the planner won't ship before they're done.
- **A hard stop is a config key** (`stop_after_milestone`), not a manual kill.

### 2026-10-16/17: Grim Haven v1.0 to M8
- Free OpenCode tiers were rate-limited for most of a day; silent OpenCode retries cost 5 hours overnight until the live abort was added.
- File-level lane overlap, background planning and three lanes took throughput from ~2 to 4–6 tasks/hour.
- See the failure-mode table in §4 for the rest.

