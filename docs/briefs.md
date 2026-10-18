# Writing briefs and the first backlog

The coders are often fast, cheap, mid-tier models. They follow sharp briefs well and struggle with vague goals, big scope, cross-cutting refactors and guessing at APIs. **The brief is the main lever on quality.** Claude writes the M1 briefs during setup; afterwards the quarterback writes them during PLAN steps (its role guide carries the same rules).

## Every code brief has

- **Goal**: one paragraph, plus the GDD section(s) it implements.
- **Files**: exact paths to create or modify, with `class_name`s. Name *every* file the task touches: the orchestrator compares these paths to decide which tasks can run in parallel lanes, and a brief with no paths blocks the other lanes.
- **API**: public method signatures with types. Name the existing classes/methods to call, and check they exist.
- **Rules**: exact formulas and numbers, or the data keys they come from, plus one worked example with real numbers.
- **Tests**: specific cases (inputs → expected outputs), using `Dice.forced([...])` where rolls matter.
- **Scenario**: name and what the screenshot must show (visible work only).
- **Acceptance criteria**: 3–6 testable bullets.
- **Pitfalls**: known traps (JSON numbers are floats, typed arrays, nodes outside the tree in tests, Godot 3 syntax).

## Sizing and shape

- About 1–2 hours of human work, at most ~4 files besides tests. Split anything bigger.
- Prefer chains: sim class → tests → view → scenario. Sim tasks first; screens after the sim they show.
- Spread independent work across folders/files so 3 lanes stay busy. Data tables (`classes.json`, balance) are `claude` design tasks that unblock many code tasks: queue them early.
- Each milestone ends with a Codex QA playtest task (type `qa`) and, for release milestones, an export task.
- Small low-risk tasks: `"skip_qa": true` or a title starting with "Polish:", "Cleanup:" or "Chore:".

## The first backlog (setup)

Write M1 as about 10–15 tasks: 1–2 Codex art tasks (art foundation first: palette, pipeline, base tiles/sprites), 1 Claude data/design task (the schema everything reads), 6–10 coder tasks building the core loop sim-first, a "make it reachable from the title screen" task, and an M1 QA task. Mark tasks with no dependencies `ready`; the rest `backlog` (the first PLAN step promotes them). Write them with `scripts/write_board.py <project> tasks.json`.

Define the core APIs consistently across all M1 briefs before writing them (class names, method signatures, event dictionaries). Inconsistent APIs between briefs are the most common cause of blocked tasks.

## Example: a real M1 brief from Grim Haven (approved on the first attempt)

# T-008: CombatRules and SkillResolver: hit, crit, damage, healing

Milestone: M1 | Type: code | Owner: coder | Scenario: `default` | Depends on: T-004, T-007

## Goal

The attack and heal resolution of GDD §10.3 for the M1 skill set (damage + heal; statuses come in M2).

## Files

- Create `game/scripts/sim/combat/combat_rules.gd` (`class_name CombatRules`, static functions).
- Create `game/scripts/sim/combat/skill_resolver.gd` (`class_name SkillResolver extends RefCounted`).
- Modify `game/scripts/sim/combat/battle_state.gd`: add `use_skill` and `valid_targets` (delegating to SkillResolver), and a `skill_def(unit, skill_id) -> Dictionary` lookup (hero skills from `skills.json`; enemy skills inline in `enemies.json`).
- Tests: `game/tests/test_combat_rules.gd`, `game/tests/test_skill_resolver.gd`.

## API

```gdscript
# CombatRules
static func distance(a: Vector2i, b: Vector2i) -> int        # Chebyshev: max(|dx|, |dy|)
static func cover_value(data: GameData, grid: BattleGrid, attacker: CombatUnit, target: CombatUnit, skill: Dictionary) -> int  # 0 for melee or flanked; balance cover_half / cover_full
static func hit_chance(data: GameData, grid: BattleGrid, attacker: CombatUnit, target: CombatUnit, skill: Dictionary) -> int
static func crit_chance(data: GameData, grid: BattleGrid, attacker: CombatUnit, target: CombatUnit, skill: Dictionary) -> int
static func roll_damage(data: GameData, attacker: CombatUnit, target: CombatUnit, skill: Dictionary, crit: bool, dice: Dice) -> int
# BattleState additions
func skill_def(unit: CombatUnit, skill_id: String) -> Dictionary
func valid_targets(unit_id: String, skill_id: String) -> Array[Vector2i]
func use_skill(unit_id: String, skill_id: String, target_tile: Vector2i) -> Array
```

## Rules (GDD §10.3)

```
hit%  = clamp(skill.acc + attacker.acc - target.dodge - cover, hit_chance_min, hit_chance_max)
cover = 0 if skill.melee or flanked, else cover_half / cover_full (from LineOfSight.cover_against)
crit% = clamp(skill.crit + attacker.crit + (flank_crit_bonus if flanked and not melee else 0), 0, 100)
dmg   = round(dice.range_i(dmg_min, dmg_max) * skill.dmg_mult * (crit_damage_mult if crit else 1) * (1 - target.prot / 100.0)), minimum 1 if dmg_mult > 0
heal  = dice.range_i(heal_min, heal_max), capped at max_hp
```
Order of dice calls in `use_skill` for an enemy-target skill: hit roll `dice.roll(hit%)`, then (if hit) crit roll `dice.roll(crit%)`, then damage `range_i`. Heals never miss: one `range_i`.

Targeting: `target "enemy"` → a living opposing unit; `"ally"` → a living same-team unit (including self unless the skill says otherwise); `"self"` → own tile. Range: `range_min <= distance <= range_max`; melee = distance 1 (8-adjacent). `needs_los` → `LineOfSight.has_los`.

Events: `{"type":"skill_used","unit","skill","target"}`, then per target `{"type":"miss","target"}` or `{"type":"damage","target","amount","crit":bool,"hp":new_hp}` or `{"type":"heal","target","amount","hp"}`, and `{"type":"died","unit"}` at 0 HP (enemies; heroes too until M2 adds Death's Door). Then `action_used = true`; if `skill.ends_turn`, append the events of `end_turn`. Always call `check_outcome()`; if the battle ended, append `battle_ended`.

Worked example: attacker acc 5, skill acc 85, crit 5; target dodge 10 behind half cover (25) → hit 55%. Flanked instead → hit 80%, crit 5 + attacker crit 3 + 25 = 33%. Damage: weapon 4–8, roll 6, dmg_mult 1.0, crit → 6 × 1.5 = 9, target prot 20 → 9 × 0.8 = 7.2 → 7.

## Tests

Hit chance with no cover / half / full / flanked / melee; clamps at 5 and 95; crit with flank bonus and clamp at 100; damage example above with `Dice.forced([6])`; minimum 1 damage; a full `use_skill` with `Dice.forced([1, 100, 6])` (hit, no crit, roll 6); miss with `Dice.forced([100])`; out-of-range target → []; no LOS → []; second action in one turn → []; killing the last enemy emits died + battle_ended VICTORY.

## Pitfalls

- JSON numbers load as floats: `int(data.balance("move_base"))`.
- Typed arrays: `var a: Array[Vector2i] = []`; don't assign an untyped Array to a typed variable (use `.assign()`).
- No Node, scene, autoload or `get_tree()` in `scripts/sim/`. No global `randi()`/`randf()` there either: use the `Dice` you're given.
- Godot 4 only (`@export`, `@onready`, `await`, `instantiate()`).
- `round()` returns float in GDScript: wrap with `int()`.

## Acceptance criteria

- CombatRules.hit_chance / crit_chance / roll_damage implement GDD §10.3 exactly with numbers from balance.json, verified by worked examples
- Melee skills require 8-adjacency and ignore cover; ranged skills require range and LOS when needs_los
- BattleState.use_skill validates (active unit, action available, valid target) and returns hit/miss/crit/damage/heal/died events; a used skill sets action_used and, if ends_turn, ends the turn
- valid_targets(unit_id, skill_id) returns the tiles a skill can target, used later by the UI
- tests/test_combat_rules.gd and tests/test_skill_resolver.gd cover the worked examples and edge clamps (5/95, 0/100)

