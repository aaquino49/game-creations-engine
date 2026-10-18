# Grim Haven: Game Design Document

Owner: Claude (product manager). Agents follow this doc. If something is unclear, make the choice most consistent with it, log it in `project/assumptions.md`, and keep going. Only Claude changes this file and records why in `project/decisions.md`.

## 1. Pitch

A turn-based tactical roguelite for Windows, styled after **Darkest Dungeon** (stress, afflictions, quirks, Death's Door, a doomed roster) and **XCOM** (grid combat with cover, flanking, hit chances, a strategic base and a doom clock).

Thirty years after the Blight, you run **Haven**, the last free settlement in the Ashlands. You recruit drifters, kit them out and send squads of four into the ruins to scavenge, rescue and fight. Most of them come back changed, and some don't come back at all. Meanwhile the warlord **Saint Ferro** and his Blight-touched **Rust Legion** creep closer every week. Break his four lieutenants, then storm his Citadel before the Legion storms Haven.

- One campaign: about **3–5 hours**, about **18–24 in-game weeks**.
- One expedition: **10–20 minutes** (4–9 rooms, 2–4 fights).
- Mouse-driven, with keyboard shortcuts. 1280×720 base resolution, scales up.

## 2. Pillars

1. **Every decision costs something.** Scrap spent on gear isn't spent on stress relief. A hero resting in the Saloon can't go on this week's mission. Retreating saves lives but fails the mission.
2. **Readable tactics.** The player always sees the hit chance, the cover, the threat and the turn order before committing. The randomness is in the dice, never in hidden information.
3. **Heroes are people, not stat blocks.** Names, quirks, afflictions, a memorial wall. Losing a level-4 Medic you've had for ten weeks should hurt.
4. **Small and finished beats big and broken.** Cut scope before cutting quality. Every milestone leaves the game playable.

## 3. The two layers

```
HAVEN (strategic, one "week" per visit)            EXPEDITION (tactical)
- collect weekly income, pay upkeep (food)          - party of 4 enters a ruin: a graph of rooms
- treat stress (Saloon/Chapel), quirks (Clinic)     - move room to room; fog hides unvisited rooms
- upgrade gear (Workshop), skills (Training Yard)   - rooms: fights, loot, curios, traps, rest, objective
- recruit (Gate), upgrade buildings                 - fights are XCOM-style grid battles with cover
- pick a mission from the Radio Tower               - stress, afflictions, Death's Door, permadeath
- choose 4 heroes + provisions -> EMBARK            - finish the objective, or retreat
                     ^                                             |
                     +---- results: loot, XP, quirks, dead --------+
```

After each expedition the week ends: the doom track advances, upkeep is paid, and new recruits and missions appear.

## 4. Heroes

### 4.1 Stats

| Stat | Meaning | Typical L1 |
|---|---|---|
| HP | Hit points. At 0 the hero is at Death's Door (§6). | 20–34 |
| ACC | Added to a skill's base accuracy. | 0–10 |
| DODGE | Subtracted from attackers' hit chance. | 0–15 |
| CRIT | Added to a skill's crit chance (%). | 2–8 |
| PROT | Percent of incoming damage blocked (from armor). | 0–25 |
| SPD | Initiative. Also sets move range: `MOVE = 3 + floor(SPD / 3)` tiles. | 3–8 |
| DMG | Weapon damage range `[min, max]`. | e.g. 4–8 |
| Resists | Bleed, Blight, Stun, Debuff, Death Blow (%). | 20–40 |

### 4.2 Classes (6)

Each class has **7 combat skills**. A hero has **4 equipped** at a time (swapped in Haven) and starts with 4 of them unlocked. The other 3 unlock at levels 2, 3 and 4. Each class also has a **weapon line** and an **armor line**, each with 4 tiers (§9.4).

| Class | Role | Weapon | Signature skills |
|---|---|---|---|
| **Scavenger** | Mobile skirmisher, loot and traps | Shiv + sling | *Gut Stab* (bleed), *Slip Away* (move after attacking), *Disarm* (traps; +loot), *Smoke Pot* (−ACC area) |
| **Medic** | Healer and cleanser | Scalpel + flare pistol | *Field Dressing* (heal, cures bleed), *Adrenaline* (+SPD, exits Death's Door), *Triage* (small heal, 2 allies), *Sedate* (stun) |
| **Bruiser** | Tank and melee anchor | Rebar maul | *Smash* (knockback 1), *Taunt* (enemies must target you), *Brace* (+PROT, Guard an ally), *Charge* (move + hit) |
| **Sharpshooter** | Long-range damage, overwatch | Bolt-action rifle | *Aimed Shot* (+crit), *Overwatch* (reaction shot), *Suppress* (target −ACC, can't move), *Mark* (+dmg taken) |
| **Mechanic** | Gadgets and area control | Nailgun + tools | *Deploy Turret* (summon, 2 rounds), *Pipe Bomb* (area dmg), *Scrap Shield* (+PROT ally), *Rewire* (stun mechanical enemies) |
| **Preacher** | Stress healer and buffer | Censer + revolver | *Sermon* (−stress party), *Rebuke* (damage; +50% vs Blighted), *Bless* (+ACC/+CRIT ally), *Last Rites* (big heal to a Death's Door ally) |

Exact skill numbers live in `game/data/classes.json` and `game/data/skills.json`. The design task that creates them follows §12.

### 4.3 Levels

- Levels **1–5**. XP comes from expeditions: `XP = base_by_mission_length × difficulty_mult`, split evenly among survivors. Thresholds: L2 = 10, L3 = 25, L4 = 45, L5 = 70 (cumulative).
- A level-up is applied **in Haven**, for free, when the hero has the XP: +HP, +ACC, +DODGE, +SPD as listed in `classes.json`, and the next skill unlocks.
- **Level cap** is set by the Training Yard tier (§9.3): tier 0 = L3, tier 1 = L4, tier 2 = L5. XP over the cap is banked.
- **Skill ranks** (1–3) are bought at the Training Yard. Each rank adds damage/healing/accuracy as listed in `skills.json`.

### 4.4 Names, look and identity

- Random first name + nickname ("Mara 'Rust' Venn"). The name pools live in `game/data/names.json`.
- A portrait built from layers (§11.4): class silhouette, gear tint, plus a scar overlay after surviving Death's Door.
- The **Memorial** lists every dead hero: name, class, level, week of death, and cause ("Killed by a Legion Flayer in the Drowned Mall").

## 5. Stress, afflictions and virtues

- **Stress** runs 0–200 per hero and carries over between expeditions until it's treated.
- **Gaining stress:** being hit by a crit (+10), an ally reaching Death's Door (+8 to the others), an ally dying (+20), enemy stress skills (various), traps and curios, starving on an expedition (+15), entering a room with an unseen ambush (+5), taking a turn while afflicted next to other heroes (§5.2).
- **Losing stress:** landing a crit (−4 to self), killing a boss (−15 to party), Preacher skills, curios, the Saloon/Chapel in Haven.
- **Resolve check at 100.** The first time a hero reaches 100 stress in an expedition, roll: **25% virtue, 75% affliction** (Chapel and Saloon upgrades and some quirks shift this). After the roll, stress is set to 100 and keeps climbing.
- **Heart attack at 200.** The hero drops straight to **Death's Door**. If they are already at Death's Door, they die. Stress then resets to 150.
- Afflictions and virtues end when the expedition ends. Their stress stays.

### 5.1 Virtues (pick one at random; lasts the expedition)

| Virtue | Effect |
|---|---|
| Stalwart | +15 PROT, −50% stress taken |
| Focused | +10 ACC, +5 CRIT |
| Courageous | Stress −5 for the whole party at the start of each round |
| Vigorous | Heals 2 HP at the start of each turn, +20% Death Blow resist |
| Steadfast | Immune to stun; −20 stress immediately |

### 5.2 Afflictions (pick one at random; lasts the expedition)

At the start of an afflicted hero's turn there is a **25% chance of an "acting out"** that replaces part of the turn, as listed.

| Affliction | Passive | Acting out (25%) |
|---|---|---|
| Paranoid | −10 DODGE when next to an ally; refuses heals from allies 50% of the time | Moves 1–2 tiles away from allies; +5 stress to the nearest |
| Hopeless | −10 ACC, −10% damage | Skips the action ("What's the point?"), +3 stress to self |
| Abusive | +10% damage | Insults an ally: +8 stress to a random ally |
| Fearful | +10 DODGE, −20% damage | Retreats toward the room's exit and ends the turn |
| Selfish | Won't use skills that target allies 50% of the time | Takes the best cover tile even if it means abandoning a flank; +5 stress to allies |
| Irrational | +5 CRIT | Uses a random equipped skill on a random valid target (may waste it) |

Each acting-out shows a bark (a short line of floating text) and a log entry.

## 6. Death's Door and permadeath

- When a hero's HP hits 0 they are **at Death's Door**: HP stays at 0, they stay on the field and can still act, with −10 ACC and −10 SPD.
- **Every hit taken at Death's Door** triggers a **Death Blow check**: survive with `death_blow_resist`% (base 67%, modified by class, quirks, trinkets and the Vigorous virtue). On a failed check the hero **dies permanently**.
- DoT damage (bleed, blight) at Death's Door also triggers the check.
- Any heal above 0 HP takes the hero off Death's Door. They then carry **Deathly Shaken** until the expedition ends: −10% max HP, −5 SPD, +10% stress taken. Doesn't stack.
- **A dead hero is gone.** Their equipped trinkets are lost, unless an ally ends the fight next to the body (then the trinkets go to the expedition loot). Their weapon and armor tiers are lost with them. They go to the Memorial.
- Enemies have no Death's Door: they die at 0 HP.
- **Total party kill:** the expedition fails, all four are dead, and the loot is lost. The campaign continues if Haven has heroes or can recruit more. With no heroes and no scrap to recruit, the Gate always offers one free recruit per week, so the campaign can always go on until the doom track fills.

### 6.1 Combat transition order (M2 integration contract)

- A first lethal hit enters Death's Door without a Death Blow roll; overkill never adds a second hit. Each later positive hit or individual DoT tick checks separately. Zero damage does not check. A heart attack at the Door kills directly without a resistance roll.
- A cure explicitly listing `deaths_door` restores at least 1 HP when normal healing has not already recovered the hero. Deathly Shaken is applied once on recovery; round down the 10% maximum-HP reduction (minimum max HP 1), clamp HP to that cap, and do not reduce the cap again on later recoveries. Door and Shaken penalties add if both are present. Movement uses mathematical floor and cannot fall below 0 tiles.
- Stress from one damage transition is ordered: damage/crit (target's crit stress, then attacker's crit relief), Door/death notifications to other living heroes in id order, then the skill's target stress and status effects. Self effects occur after all targets. Chained heart attacks finish before the enclosing command finalizes victory/defeat.
- Mental passives are recalculated without changing base stats. Round-start virtue effects occur before initiative; at turn start virtue healing occurs after `turn_started` and before DoTs/stun. Steadfast prevents new stuns without removing an already-applied stun. Resolve is checked once per expedition; gaining Steadfast applies its immediate relief once.

These clarify existing rules for T-046 through T-050; they do not remove acting out, refusals or any of the remaining 42-skill effects from M2.

### 6.2 Remaining M2 execution contract

- Uniform `~` tiles in v1 are fire. Each entered tile deals3 damage ignoring PROT, and a unit starting a turn there takes3 again. Passing through several tiles applies each entry; normal movement, bonus moves, rushes and pushes share this rule. Turn start is virtue healing, hazard, bleed/blight, stun, then acting out. Damage and stress finish before outcome checks.
- Overwatch uses the watcher's first equipped ranged damaging single-enemy skill at minus10 ACC, bypassing its Action/cooldown as a reaction. Watchers fire in id order at the first traversed tile in range/LOS. Ordinary moves, Dash, Slip Away bonus moves and afflicted moves trigger it; Charge and knockback do not. Reactions still use Guard and ordinary damage/life rules.
- Taunt restricts single-enemy skill targeting only when its source is a legal target; area effects are unrestricted. Guard replaces the primary single-enemy victim, including the primary of an enemy skill with splash, without changing the splash anchor or redirecting secondary victims. No guard chain or duplicate hit occurs. Preview numbers identify and describe the actual protector.
- Afflicted turns roll acting out once after surviving the turn-start effects and stun gate. Data controls which resources are spent, including when movement has no legal improvement. Fearful moves toward an exit (hero spawn fallback) and ends that turn; it does not automatically flee the battle. Irrational selects one equipped currently legal skill and target; no option wastes the Action. Behavioral execution never recursively rolls another act-out.
- Selfish may refuse a validated ally-target skill (including using that ally skill on self); the Action and cooldown remain free but that skill is disabled for the rest of the turn. Paranoid may refuse another hero's healing or explicit Door recovery: skip that victim's effects while the healer spends the normal Action/cooldown. Self-heals are exempt. Other area-heal victims resolve normally. Queries and previews never roll refusals. Barks use data, with no extra cosmetic random draw.

- Scrap Trap is a nonblocking tile record, visible to its owner and independent of that owner's survival. Place it on an empty walkable tile in data range/LOS, including fire or exits, with no other trap there. A turret cannot deploy onto it. An ally can cross without triggering it. The first opposing entry consumes it, deals its data damage ignoring PROT without hit/crit/Guard, then applies its data statuses through normal resistances if the target survives and combat continues. Each entry resolves fire, then trap, then permitted Overwatch; stationary turn-start fire never triggers a trap. A trap placed in round R with lifetime T expires before initiative at round R+T+1, matching summon lifetime boundaries. Exact event and dice order are in T-068.

These clarify the shipped data and GDD5.2/10 rules for T-059..T-070; they do not complete the milestone or remove summons, barks or status-aware AI from it. Exact movement ties, event order and probability consumption are fixed in each task brief.

## 7. Quirks

- Each hero has up to **5 positive and 5 negative quirks**. A new recruit starts with 1–2 of each.
- **Gaining quirks:** at expedition end, each survivor has a 40% chance of one new quirk (60/40 positive/negative on success, 30/70 on a retreat or failure). Some curios grant specific quirks.
- If a hero is full on one side, a new quirk replaces a random unlocked one.
- **Locked** quirks can't be replaced. Positive quirks can be locked at the Clinic.
- About **16 positive and 16 negative** quirks for v1, in `game/data/quirks.json`. Examples:

| Positive | Effect | Negative | Effect |
|---|---|---|---|
| Eagle Eye | +5 ACC with ranged skills | Twitchy | −5 ACC |
| Tough as Nails | +10% max HP | Frail | −10% max HP |
| Quick Reflexes | +2 SPD | Sluggish | −2 SPD |
| Hard Noggin | +15% stun resist | Bleeder | −15% bleed resist |
| Iron Will | −10% stress taken | Nervous | +10% stress taken |
| Scrounger | +10% loot scrap | Kleptomaniac | 10% of the loot vanishes |
| Night Owl | +5 DODGE in dark rooms | Claustrophobic | +5 stress per turn in small rooms |
| Survivor | +10% Death Blow resist | Death Wish | −10% Death Blow resist |
| Blight-Hardened | +20% blight resist | Blight-Sensitive | +5 stress when hit by blight |
| Teetotaler (no Saloon) | +5 ACC | Gambler | Saloon "Cards" only; may lose scrap |
| Medic's Hands | +15% healing done | Hemophobe | +5 stress when an ally bleeds |
| Loyal | −5 stress when an ally hits Death's Door (instead of +8) | Lone Wolf | −5 ACC with 2+ allies adjacent |

- v1 adds 8 more (T-057): positive Thick Skin (+5 PROT), Quick Clotter (+20% bleed resist), Back to Back (+4 DODGE next to an ally), Brawler (+1 max damage with melee skills); negative Clumsy (−5 DODGE), Glass Jaw (−15% stun resist), Gun-Shy (−1 max damage with ranged skills), Haunted (+5 stress when an ally dies). Exact data: `game/data/quirks.json`, schema in `game/data/SCHEMA.md`.
- Quirks with conditions (e.g. "in dark rooms") are tagged in data; the sim checks tags, never quirk names.

## 8. Expeditions (the dungeon crawl)

### 8.1 Structure

- An expedition is a **graph of rooms** linked by corridors, generated from a seed: Short = 4–5 rooms, Medium = 7–9, Long = 11–13 (Long is post-v1).
- The **Expedition screen** shows the room graph as a minimap (top right), the current room on a grid (center), and the party panel (bottom).
- Unvisited rooms are hidden behind fog: shown as "?". Adjacent rooms become visible as icons once the party is in a neighbouring room. A Radio Tower upgrade reveals room types on the whole map.
- Moving to an adjacent room costs **1 step**. Every **4 steps** the party eats 1 ration per hero. With no rations each hero takes 5 HP damage and +15 stress (starving).
- Each corridor traversal has a **15% chance of a corridor event** (ambush fight on a small map, a find of loot, or a scare: +stress). A Scavenger in the party halves ambush chance.

### 8.2 Room types

| Type | What happens |
|---|---|
| Entrance | Start. Retreating from here ends the expedition at no extra cost. |
| Combat | A grid battle (§10). Cleared rooms stay cleared. |
| Loot | A cache: scrap, food, medicine, maybe a trinket. |
| Curio | An interactable with a choice: e.g. "Rotting Pantry" (search: food or +blight; use provisions to make it safe), "Shrine of the Old Saints", "Military Locker" (needs a crowbar). Results in `game/data/curios.json`. |
| Trap | A hazard on entering: a Scavenger can disarm it (chance), otherwise damage and stress to the party. Tool kits auto-disarm. |
| Rest site | Once per expedition (Medium+): camp. Each hero heals 20% HP and loses 15 stress. Costs 1 ration per hero. (Full DD camping skills are an expansion feature.) |
| Objective | The mission goal (§8.4). Often a guarded combat room or a boss. |

### 8.3 Provisions (bought in Haven before embarking)

| Item | Cost | Use |
|---|---|---|
| Ration | 5 scrap | Food on the march; a small heal outside combat |
| Bandage | 10 scrap | Out of combat: heal 6, cure bleed |
| Antitoxin | 10 scrap | Out of combat: cure blight; some curios |
| Tool Kit | 15 scrap | Disarm a trap automatically; open lockers |
| Crowbar | 10 scrap | Open locked curios |

Leftover provisions are sold back at 50% when the expedition ends.

### 8.4 Missions

- The Radio Tower offers **3 missions per week** (4 at tier 2). Each has a region, length, difficulty level (1–4), objective and preview of rewards. Missions disappear at week end.
- Objectives: **Scavenge** (explore 80% of rooms), **Purge** (win every combat room), **Retrieve** (find the item in the Objective room), **Rescue** (free a captive: they join the roster at level 1–2 for free), **Sabotage** (destroy a Legion cache: doom −6), **Lieutenant** (boss mission, one per region, §13).
- *Build order (2026-10-16):* in M4 every mission is won by clearing its Objective room, and rewards come from `game/data/missions.json` by difficulty and length. The distinct objective rules above, Haven raid effects and the Siege are M5 work.
- **Success:** the full reward plus the loot found. **Retreat:** keep the loot found, no reward, +4 doom. **Total party kill:** nothing, +4 doom.
- Retreat is possible from any room not in combat. In combat, a hero standing on an exit tile can Flee (ends their part in the fight). If all living heroes flee, the party is back in the previous room with the fight unresolved.

### 8.5 M3 expedition execution contract

- Out of combat, damage (traps, starving, curios) never kills: HP stops at 1, and a hero already at 0 HP from a Death's Door fight stays at 0. Out-of-combat stress uses the normal stress rules (quirks, affliction and Deathly Shaken scale it; one resolve check per expedition). An out-of-combat heart attack drops the hero to 0 HP, so they start the next fight at Death's Door; a hero already at 0 HP dies.
- Statuses (bleed, blight, buffs) end with the fight. Bandages and rations heal outside combat; Antitoxin is a curio key in v1.
- An affliction or virtue, the resolve check and Deathly Shaken carry between the fights of one expedition and clear when it ends.
- Order on each move: step and hunger, then the corridor event (an ambush fight happens in the corridor and clears no room), then the room's entry effect (trap) or offer (cache, curio, rest, fight).
- XP is banked at the end (short 4, medium 7, +1 per fight won; half the base on a retreat). Levels are applied in Haven (M4). Exact numbers live in `game/data/expeditions.json` and `curios.json`.

## 9. Haven (the strategic layer)

### 9.1 Resources

| Resource | Use | Source |
|---|---|---|
| **Scrap** | Main currency: gear, buildings, recruits, provisions, treatments | Expedition loot and rewards, Scrapyard income |
| **Food** | Weekly upkeep: 1 per hero on the roster | Loot, Greenhouse, rewards |
| **Medicine** | Clinic treatments, some upgrades | Loot, rewards |
| **Relics** | Rare old-world tech: tier-2+ building upgrades, best gear tiers | Lieutenant kills, rare loot |

Start: 300 scrap, 12 food, 4 medicine, 0 relics, 4 heroes (Bruiser, Medic, Sharpshooter, Scavenger, all level 1), roster cap 9.

### 9.2 The week

1. **Return** from the expedition: results screen, loot banked, XP, quirks, deaths. Survivors come home at full HP; stress, quirks and XP carry over. "Return to Haven" then runs the week end (step 2) at once; the hub's End Week button skips a week without an expedition. A run interrupted by quitting counts as a retreat on Continue.
2. **Week end:** upkeep (food), building income, doom track advances (§13), heroes in Saloon/Chapel finish treatment, a new recruit pool and missions are rolled, Haven raid check.
3. **Haven turn:** the player spends resources and assigns heroes. Assigning a hero to a stress treatment, Clinic treatment or training makes them **unavailable for this week's expedition**.
4. **Embark:** pick a mission, choose 4 available heroes (at least 1), buy provisions. Auto-save, then start.

**Starvation:** if food runs out at week end, each hero gains +20 stress, and any hero at 100+ stress has a 30% chance to desert (leave the roster, and their gear goes back to stock).

### 9.3 Buildings

Every building has tiers 0–2 (some start at 0). Upgrade costs and exact numbers are in `game/data/buildings.json`.

| Building | Tier 0 | Tier 1 | Tier 2 |
|---|---|---|---|
| **Radio Tower** | 3 missions; region + objective shown | Enemy faction preview | 4 missions; full room-type map |
| **Recruitment Gate** | 3 recruits/week, level 1, cap 9 | 4 recruits, cap 12 | 5 recruits, 30% are level 2, cap 15 |
| **Saloon** | Drink (−40 stress, 20 scrap), 2 slots | 3 slots, Cards (−60 stress, 30 scrap, 20% chance of a negative event) | 4 slots, −20% costs |
| **Chapel** | Prayer (−45 stress, 25 scrap), 2 slots | 3 slots, Confession (−70 stress, 35 scrap) | 4 slots, +10% virtue chance for the next expedition |
| **Clinic** | Remove a negative quirk (40 scrap + 1 medicine), 1 slot | Lock a positive quirk (60 scrap), 2 slots | 3 slots, −25% costs |
| **Workshop** | Weapon/armor tier 2 | Tier 3 | Tier 4 (needs relics) |
| **Training Yard** | Level cap 3; skill rank 2 | Cap 4; skill rank 3 | Cap 5; −25% costs |
| **Greenhouse** | Not built | +4 food/week | +8 food/week |
| **Scrapyard** | +30 scrap/week | +50 | +80 |
| **Watchtower** | Raid defense 0 | Raid defense 1 | Raid defense 2 |
| **Memorial** | The list of the fallen. Free; no upgrades. | | |

Buildings with a "not built" tier 0 are shown dimmed until built.

### 9.4 Gear

- **Weapon** and **armor** tiers 1–4 per hero (upgraded at the Workshop): each tier gives the class's listed bonus (damage/ACC for weapons, HP/PROT for armor). Costs rise per tier.
- **Two trinket slots.** Trinkets come from loot and rewards, have a rarity (common/uncommon/rare/legendary), usually have one upside and sometimes one downside, and can be restricted to a class. Unequipped trinkets live in Haven's stock. About **24 trinkets** for v1, in `game/data/trinkets.json`.

### 9.5 Recruiting

- The Gate shows the week's recruits: class, level, quirks and a short backstory line. Hiring costs scrap (level 1: 60, level 2: 120).
- Dismissing a hero is free and permanent (a confirm dialog).

## 10. Tactical combat

### 10.1 The battlefield

- A rectangular grid, about **14×9 tiles** (from 10×7 to 16×10). Tiles are **48 px** on screen (16 px art at 3×).
- Tile types: `floor`, `wall` (blocks movement and line of sight), `half_cover` (crates, car doors: −25 to hit), `full_cover` (concrete barriers, pillars: −45 to hit), `hazard` (fire or toxic pools: 3 damage or blight when entered or at turn start), `exit` (heroes can Flee from it).
- Rooms come from hand-made **templates** in `game/data/room_templates.json` (ASCII layouts), mirrored and with random cover scattered on top.
- Heroes deploy on one edge, enemies on the other (or in an ambush layout).

### 10.2 Turn order

- **Rounds.** At the start of each round every living unit rolls initiative: `SPD + randi(0, 2)`. Ties go to heroes, then to the higher base SPD.
- A **turn-order bar** at the top shows the order for this round and the next.
- On their turn a unit gets **one Move and one Action**, in either order. It may give up the Action to **Dash** (a second Move). Some skills say "free action" or "ends turn".
- A Move goes up to `MOVE` tiles along a path that avoids walls and units. The reachable tiles are highlighted; hovering shows the path and the cover at the destination.
- **Overwatch** and **Guard** last until the start of the unit's next turn.

### 10.3 Hit, crit and damage

```
hit%  = clamp(skill.acc + attacker.ACC − target.DODGE − cover + mods, 5, 95)
cover = 0 if flanked, else 25 (half) / 45 (full)   -- the best cover between the target and the attacker
crit% = clamp(skill.crit + attacker.CRIT + (25 if flanked else 0) + mods, 0, 100)
dmg   = round(randi_range(weapon.min, weapon.max) × skill.dmg_mult × (1.5 if crit else 1) × (1 − target.PROT/100))
```

- **Cover** counts when a cover tile is adjacent to the target and lies between the target and the attacker (the cover tile is on the attacker's side). A unit is **flanked** when no cover on its tile edge faces the attacker.
- **Line of sight:** a supercover line from tile center to tile center. Walls block it; cover and units don't. Where the line passes exactly through a tile corner, it is blocked only if both tiles beside that corner are walls. The map edge counts as a wall.
- **Melee** skills need an adjacent target (8-neighbour). Melee ignores cover.
- The hit% and crit% preview is shown before confirming. Combat log lines follow the formula.
- A crit against a hero: +10 stress to them. A crit by a hero: −4 stress to them.

### 10.4 Statuses

| Status | Effect | Notes |
|---|---|---|
| Bleed | N damage at turn start for T turns | Resisted by bleed resist |
| Blight | N damage at turn start for T turns | Resisted by blight resist |
| Stun | Skips the next turn | Then +50% stun resist for 1 round |
| Mark | Takes +25% damage from the next hit | Some skills do more against marked targets |
| Guard | A Bruiser takes hits aimed at the guarded ally | |
| Taunt | Enemies in range must target the taunter | |
| Buff/Debuff | ±ACC/DMG/DODGE/SPD/PROT for T turns | Debuff resisted by debuff resist |
| Overwatch | Reaction shot at the first enemy that moves in LOS (−10 ACC) | |
| Suppressed | −15 ACC, can't Move | |

### 10.5 Enemies

Factions (v1 has three; numbers in `game/data/enemies.json`):

- **Scavver Raiders** (region 1+): humans with guns, use cover, flank. *Raider Thug* (melee), *Raider Gunner* (ranged, seeks cover), *Raider Medic* (heals allies), *Raider Boss* (buffs allies, lieutenant variant).
- **Blighted** (region 2+): mutated rushers that ignore cover and spread blight and stress. *Shambler* (slow, tough), *Spitter* (ranged blight), *Wailer* (stress attacks), *Bloater* (explodes on death, area blight).
- **Rust Legion** (region 3+, and everywhere once doom ≥ 25): armored zealots. *Legion Flayer* (melee, bleed), *Legion Marksman* (long-range, overwatch), *Legion Preacher* (stress + buff), *Iron Hound* (fast mechanical, Mechanic's Rewire stuns it).

**Enemy AI** (one sim class, data-driven per archetype): each enemy scores candidate moves (cover at destination, flank opportunities, distance preference by archetype, hazards) and candidate actions (expected damage = hit% × average damage, kill chance, stress dealt, statuses), then takes the best Move + Action pair, with a small random factor so it's not predictable. Archetypes: `rusher`, `gunner`, `support`, `caster`, `boss`.

### 10.6 Fight end

- **Victory** when all enemies are dead. Loot drops into the room's cache. XP is granted at expedition end.
- **Defeat** when every hero is dead or has fled.
- After the fight, heroes keep their HP, statuses end, and stress stays.

## 11. Presentation

### 11.1 Look

Grim and readable. A dark, desaturated palette (ash, rust, bone, bruise purple, blight green for accents), heavy vignette, hard pixel edges. **One consistent CC0 pixel style**: see `project/ART_GUIDE.md`.

### 11.2 Screens

- **Title:** New Campaign, Continue, Settings, Credits, Quit.
- **Haven:** a settlement panorama with clickable buildings (or a grid of building cards in v1), a resource bar on top, a roster list on the right, and a "Week N, Doom X%" header. Clicking a building opens its panel.
- **Hero sheet:** portrait, stats, skills (equip 4), gear, quirks, stress bar, level and XP, history.
- **Mission select / Embark:** the mission list, party slots (drag heroes in), provisions shop, Embark button.
- **Expedition:** room minimap, room view, party bar (portrait, HP, stress, statuses per hero), inventory, Retreat button.
- **Combat:** grid, turn-order bar, skill bar for the active hero (4 skills + Move/Dash/End Turn/Flee), target preview (hit%, crit%, damage range, cover icon), combat log, floating damage/stress/barks.
- **Results:** per hero XP, level-ups ready, quirks gained, stress change, deaths. Loot list.
- **Memorial**, **Campaign over** (victory or defeat summary).

### 11.3 Feedback

Damage numbers (white), crits (yellow, larger), stress (purple, "+10 stress"), heals (green), misses ("MISS"), a resolve check banner ("**Mara's resolve is tested...** ABUSIVE"), screen shake on crits and deaths.

### 11.4 Portraits

Built from layers: a background plate (class colour), a class silhouette, gear tint per tier, and overlays (scar after Death's Door, stress cracks at 100+, affliction or virtue frame).

### 11.5 Audio

CC0 sound effects for hits, misses, crits, UI clicks, the resolve check sting and death. One ambient loop for Haven, one for expeditions and one for combat (CC0 or CC-BY with credit).

## 12. Data files (all balance numbers live here)

| File | Contents |
|---|---|
| `game/data/classes.json` | Per class: base stats, per-level gains, skill ids (in unlock order), weapon/armor lines (per-tier bonuses), Death Blow resist, resists |
| `game/data/skills.json` | Per skill: id, name, class, target type (`enemy`, `ally`, `self`, `tile`, `area`), range (min, max), `melee` flag, acc, crit, dmg_mult, heal, statuses applied (type, amount, turns, chance), stress, cooldown, `ends_turn`, ranks (per-rank changes), description template |
| `game/data/enemies.json` | Per enemy: faction, archetype, stats, skills (inline, same schema), loot table, sprite id |
| `game/data/quirks.json` | id, name, positive flag, effects (stat mods, conditional tags) |
| `game/data/afflictions.json` | Afflictions and virtues with effects and acting-out weights |
| `game/data/trinkets.json` | id, name, rarity, class restriction, effects |
| `game/data/buildings.json` | Tiers, upgrade costs, effects |
| `game/data/regions.json` | Regions, enemy weights by faction, room template pools, lieutenant |
| `game/data/room_templates.json` | ASCII room layouts (`#` wall, `.` floor, `h` half cover, `F` full cover, `~` hazard, `H` hero spawn, `E` enemy spawn, `X` exit) |
| `game/data/curios.json` | Curios, choices, outcomes |
| `game/data/balance.json` | Global tunables: stress thresholds, Death Blow base, doom per week, XP table, prices, starting resources |
| `game/data/names.json` | Name and nickname pools, backstory lines |

## 13. Campaign, regions and the doom track

### 13.1 Regions

| # | Region | Enemies | Lieutenant (boss) | Unlocks |
|---|---|---|---|---|
| 1 | **The Scrapfields** (junkyards, wrecked cars) | Raiders | *Gutter King Vasko* (Raider Boss + 2 adds) | Start |
| 2 | **The Hollows** (flooded metro tunnels) | Blighted, some Raiders | *The Mother Bloat* | Week 3 or region 1 lieutenant dead |
| 3 | **The Glass Wastes** (fused desert, ruined mall) | Legion, Blighted | *Marshal Iron-Jaw* | Week 7 or region 2 lieutenant dead |
| 4 | **The Rust Cathedral** outskirts | Legion | *The Choir of Saint Ferro* | Week 11 or region 3 lieutenant dead |
| — | **The Citadel** (final assault) | Legion elite | **Saint Ferro** (2 phases) | All four lieutenants dead |

- Mission difficulty levels 1–4 follow the region number, and +1 at doom ≥ 50.
- A lieutenant mission is a Medium expedition ending in a boss fight. Killing a lieutenant: doom −15, +2 relics, a guaranteed rare trinket.
- **The final assault** is a Long expedition (9 rooms) with the 2-phase Saint Ferro fight. Victory wins the campaign.

### 13.2 The doom track ("Legion Threat", 0–100)

- **+6 per week**, +4 per failed or retreated mission. Sabotage missions −6, lieutenants −15.
- **25:** Legion units can appear in every region's fights.
- **50:** **Haven raids.** Each week end there is a 40% chance of a raid, −15% per Watchtower tier. A raid steals 20% of scrap and food, or hits a random hero with +30 stress.
- **75:** recruit prices +50%, and one fewer mission per week.
- **100: The Siege of Haven.** A forced defense battle next week with every available hero (up to 4, chosen by the player). Win: doom drops to 80 and the campaign continues. Lose: **campaign over.**
- **Weekly upkeep** (food) and the doom track together create the pressure.

### 13.3 Save and difficulty

- Auto-save at every week start and every expedition start (one campaign slot in v1, `user://campaign.save`, JSON).
- **Continue** on the title screen loads the latest save.
- Difficulty: **Drifter** (doom +4/week, Death Blow base 75%) and **Grim** (doom +6/week, Death Blow base 67%, default). Ironman: saves are auto only, always.

## 14. Milestones (v1)

| M | Goal | Done when |
|---|---|---|
| **M0** | Scaffold (done by the setup session) | Project boots, test runner, DevTools, GameData loader, title screen stub |
| **M1** | **Combat core:** a playable skirmish | Grid + LOS + cover + pathing sim; units, initiative, Move/Action/Dash; hit/crit/damage; basic enemy AI; combat screen with placeholder art; win/lose; "Skirmish" button on title |
| **M2** | **Heroes & the DD layer** | 6 classes, 42 skills from data, statuses, stress, afflictions/virtues, Death's Door, permadeath; Raider faction; combat UI (turn bar, skill bar, previews, floating text, log); first art pass (CC0 tiles + unit sprites) |
| **M3** | **Expeditions** | Room-graph generator, fog, room types, provisions/hunger, corridor events, curios, traps, rest site, retreat, results screen with XP/loot/quirks; quirks system |
| **M4** | **Haven** | Roster, recruiting, all buildings, stress treatments, Clinic, Workshop gear tiers, Training Yard levels/skill ranks, trinkets, mission board, embark flow, the weekly cycle, upkeep, doom track, save/continue |
| **M5** | **Campaign & ship v1.0** | 4 regions, Blighted + Legion factions, 4 lieutenants + Saint Ferro, Haven raids + Siege, balance bot + balance pass, How to Play, audio, credits, Windows export `builds/GrimHaven.exe` v1.0.0 |

**Out of scope for v1 (expansion candidates):** DD-style camping skills; Long expeditions beyond the finale; diseases; hero relationships and bonding; more classes (e.g. Hound Master, Plague Witch); trinket sets; region modifiers (sandstorms, flooding); New Game+; additional factions; a settlement panorama with animated buildings; controller support.

## 15. Glossary

- **Expedition**: one dungeon run (the tactical layer). **Mission**: an expedition offered by the Radio Tower.
- **Room**: a node in the expedition graph. **Fight**: a grid battle inside a room.
- **Week**: one Haven turn plus one expedition.
- **Doom**: the Legion Threat track.

## 16. Expansions after v1 (M6–M8, final)

The owner set M8 as the last milestone (OWNER_REQUESTS R-1). Each expansion ends with a Codex QA playtest and a Windows re-export with a version bump. The owner later reopened the project for the v2.0 graphics overhaul (§17, M9-M11).

| M | Goal | Version | Contents |
|---|---|---|---|
| **M6** | **Settings, difficulty & feel** | 1.1.0 | Settings screen (master/SFX/music volume, window scale, `user://settings.cfg`); Drifter difficulty (§13.3) chosen at New Campaign; combat feel (hit flash, death fade, knockback slide, screen shake on crits and deaths); splitting the oversized expedition screen; QA-scenario tightening |
| **M7** | **Camping, diseases & content** | 1.2.0 | Camping skills at rest sites (§16.1); diseases (§16.2); more content: +1 room template per region, +4 curios, +4 trinkets |
| **M8** | **Wrap-up** | 1.3.0 | Final balance pass from the balance bot, full regression QA over every screen and system, final Windows export, `project/milestones/M8.md` final report |

### 16.1 Camping (M7)

Replaces the plain rest-site camp (§8.2) with a DD-style camp. Camping still costs 1 ration per hero and still heals 20% HP and removes 15 stress. Then the party gets **12 respite points**. Each class has **2 camp skills** (cost 2–4 points, at most once per hero per camp), such as a heal, stress relief for one ally or the whole party, a disease cure (bleed and blight end with each battle, so camp skills don't cure them), or a buff for the next fight (+ACC, +PROT, +SPD, lasting 1 fight). Data: `game/data/camping.json`. The sim lives in `sim/expedition/`, and the UI is a panel on the expedition screen.

### 16.2 Diseases (M7)

A disease is a negative quirk flagged `"disease": true` in `quirks.json`. There are 6 diseases with stat mods (for example Rot Lung: −10% max HP; The Shakes: −5 ACC). Each blight tick on a hero has a 5% chance to infect them, and some curios can infect. Diseases persist after the expedition. They don't count toward the 5-negative cap, and a hero can carry at most 2. The Clinic cures a disease for 1 medicine, and a camp skill can cure one in the field. Diseases never come from the ordinary quirk rolls: recruit quirks, expedition-end quirk gains and the Clinic's Remove Quirk skip them, and they never count toward a quirk side cap. A hero only catches a disease through an infection hook (blight ticks, flagged curios).

M7 execution contract: one infection opportunity follows each positive-amount blight status tick if the hero survives it (including Death's Door); bleed, status application, hazards, enemies and summons never infect. Each opportunity picks uniformly from sorted disease ids the hero does not carry. At the two-disease cap, with no eligible diseases, or at a zero chance, consume no disease dice. Roll chance first, then the disease index only on success. Disease modifiers acquired during a fight begin with the next battle; the current battle's HP cap, initiative and modifiers stay stable. Store acquisitions on the combat unit and merge them into the persistent hero during the normal battle settlement, including fleeing and siege settlement.

Curio outcome effects may contain `one_disease_pct` (0–100): it shares the existing one-hero damage/stress/quirk target, rolls after those effects if that hero survives, and selects one living hero only when no other one-hero effect already chose one. Ordinary unflagged outcomes use the same dice sequence as before. The Clinic offers a separate Cure Disease action at every tier: choose the disease, spend exactly 1 medicine and no scrap, and occupy one Clinic slot for the week using the existing busy/slot rules. Disease cures leave ordinary quirks alone. Field cures follow the camp skill's count and quirk gain order.

### 16.3 M6 settings, difficulty and feedback contract

Settings store master/SFX/music volumes (0-100%, default 100%) independently of the campaign, in `user://settings.cfg`. Window scale choices are 1x, 1.5x and 2x (default 1x) over the existing 1280x720 logical layout; physical window size is bounded to the monitor's usable area. Bus attenuation preserves each audio cue's manifest gain, and zero volume mutes exactly.

Difficulty is chosen before creating a New Campaign save, stays fixed for that campaign, and persists through Continue. Old saves use Grim. Drifter changes weekly doom from 6 to 4 and Death Blow base from 67% to 75%, preserving class offsets and all existing quirk/trinket/virtue modifiers: an unmodified Bruiser uses 80% in Drifter versus 72% in Grim. Failed-mission doom, raids, boss rewards, siege thresholds and siege-win doom do not change. Effective difficulty data is scoped to each campaign; the shared content tables stay unchanged. Settings and Drifter remain post-v1 work.

M6 improves the existing combat playback: 0.10-second hit flash, 0.40-second death fade and 0.15 seconds per tile for Charge/knockback. Actor sprites remain available until their committed events finish, while HUD state updates promptly; animations never alter the simulation outcome. Existing flash/fade/movement code is reused rather than layered with duplicate effects. Crits that deal damage shake the board 4 px and deaths shake it 6 px, each for 0.20 seconds with a fixed (non-random) pattern; flee, summon expiry and boss phase changes never shake. On enemy turns the skill bar shows the acting unit's own skills, disabled, as a read-only telegraph.

## 17. v2.0 graphics overhaul (M9-M11, owner R-3)

The owner reopened the project after M8 for a graphics overhaul: richer, more colourful, more detailed art with **every system unchanged**. It supersedes the art parts of §11.1 (look) and §11.4 (portraits); `project/ART_GUIDE.md` v2 is the style source of truth. The team stops after M11.

- **Hybrid style.** Detailed 32x32 pixel art, 3/4 top-down, on the battlefield and in dungeons; painted graphic-novel portraits, region/mission art and a painted Haven panorama.
- **Battlefield at 64 px tiles** (32 px art at 2x, integer scale only; legacy 16 px art shows at 4x until replaced). The combat screen gets a **pan-only board camera** (arrow keys, middle-drag, auto-follow of the acting unit, clamped to the board) and a **combat log the player hides with L**, so a 16x10 room fits at 1280x720. No zoom: integer scale only.
- **Animation.** Every unit has idle, attack, hurt and death key poses played from the existing combat events (`skill_used`/`overwatch_shot` → attack, positive `damage` → hurt, `died` → death then the fade). Sheet format: ART_GUIDE v2.
- **Portraits.** Painted 512 px busts shown at 128/256 px with the scar and stress/affliction/virtue overlays on top; a pixel bust is the fallback; two busts per class (a man and a woman, T-277), and each hero shows the one that matches their first name. **Enemies (T-291):** one painted bust per enemy id (all 17: 12 ordinary enemies, the four lieutenants and Saint Ferro; the Choir is one group bust, Saint Ferro one bust for both phases), shown in combat by a view-only **enemy inspect panel** (128 px bust, name, faction, rank, HP) in a corner of the board view: it shows the acting enemy during its turn, the enemy under the pointer, or an enemy pinned with **I** (press again for the next, past the last to clear the pin). It uses the first zero-overlap board corner, protecting the inspected enemy, the tile under the pointer (including empty move/area-target tiles), the active unit and valid targets; if no corner fits, it hides while retaining a valid pin and restores automatically when space returns. Pointer tracking runs before HUD input consumption; docking and the enemy under the actual pointer refresh after hover-tile changes, arrow pan, middle drag, I-key focus and HUD/layout changes. It never covers the bars or log, takes mouse input or changes the fight. Missing art falls back to the enemy's sprite at integer scale, then a faction plate. Contract: `project/design/enemy_portraits.md`.
- **Sources.** CC0 and CC-BY packs first (credited in CREDITS.md and the Credits screen; no CC-BY-SA), with ChatGPT image generation for gaps, post-processed to the palette and grid. Each asset task writes its own licence-ledger fragment `game/assets/ledger/T-###.json`.

| M | Goal | Contents |
|---|---|---|
| **M9** | Foundation and characters | Pack research, ART_GUIDE v2, 64 px tiles, camera + log toggle, animation sheets and playback, painted-portrait support; a vertical slice (Bruiser, Raider Thug, Scrapfields tiles, Bruiser portrait) reviewed before scaling; then all 6 classes, 3 factions, 4 lieutenants, Saint Ferro and the summons, animated; M9 QA |
| **M10** | Worlds and illustration | Region tile and prop kits (Scrapfields, Hollows, Glass Wastes, Rust Cathedral, Citadel, Haven) chosen by the battle's region; all portraits (classes, enemies, lieutenants, Saint Ferro); region and mission art; the painted Haven panorama with clickable building hotspots replacing the card grid; expedition room art; M10 QA |
| **M11** | UI, VFX, polish and ship | Ornate dark UI theme, icons and a better font (spec: `project/design/ui_v2.md`; Departure Mono retained with a 44/33/22/14 hierarchy; icons 16 px at 2x: 42 skills, 11 afflictions/virtues, 4 curios, 28 trinkets, 12 camp, 6 disease); VFX (hit, crit, blood, blight, fire, heal, stress, Death's Door — met procedurally by T-268/T-269, no art supplement); hide the title's developer buttons; fit the expedition screen's bottom panel at 1280x720; credits for every CC-BY asset; full regression QA with a visual review of every screen at 720p and 1080p; the **v2.0.0** Windows export; `project/milestones/M11.md` final report |
