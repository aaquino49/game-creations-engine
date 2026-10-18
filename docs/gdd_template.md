# GDD skeleton (write project/GDD.md from this)

The GDD is the team's source of truth, and the coders are mid-tier models: write **concrete numbers, formulas, tables and worked examples**, not intentions. Grim Haven's GDD was ~350 lines; aim for 250–450. Only Claude edits it (changes logged in `decisions.md`).

```markdown
# <Game>: Game Design Document

Owner: Claude (product manager). Agents follow this doc. If something is unclear, make the choice most consistent
with it, log it in project/assumptions.md, and keep going.

## 1. Pitch            (2 paragraphs; session length; input; resolution)
## 2. Pillars          (3–4, each one sentence + why)
## 3. Core loop        (ASCII diagram of the layers and how they feed each other)
## 4..N. Systems       one section per system:
                       - the rules as formulas with named data keys
                       - a table of the content (classes, enemies, buildings...) with key numbers
                       - edge cases (ties, zero, death, overflow)
                       - which data file holds the numbers
## N+1. Presentation   screens list, feedback (damage numbers, barks), look (link ART_GUIDE), audio
## N+2. Data files     table: file -> contents (every balance number lives in game/data/*.json)
## N+3. Campaign / progression / win and lose conditions / save
## N+4. Milestones     table M0..Mn: goal + "done when" (M0 = scaffold, M1 = smallest playable core loop,
                       last v1 milestone = content + balance + audio + Windows export v1.0.0)
                       + "Out of scope for v1 (expansion candidates)" list
## N+5. Glossary
```

Milestone shape that worked (5 milestones to v1): M1 the core interaction playable from the title screen; M2 the signature systems; M3 the next layer out (the dungeon/run/level); M4 the meta layer (base, progression, saves); M5 content, bosses, balance bot + pass, How to Play, audio, credits, export.
