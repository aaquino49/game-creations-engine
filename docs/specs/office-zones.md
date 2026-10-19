# Office zones: separate the work floor, planning office and break room

**Goal:** at a glance, anyone in the office scene is clearly either working or not working. Working agents are at a
desk, in the planning office, or at the supervisor's desk. Everyone else (idle, napping, benched) is in the
break room. Keep the existing art: no new sprites or packs. Rearrange the existing props and paint floors and walls
with the existing palette (Sweetie 16: #1a1c2c #5d275d #b13e53 #ef7d57 #ffcd75 #a7f070 #38b764 #257179 #29366f
#3b5dc9 #41a6f6 #73eff7 #f4f4f4 #94b0c2 #566c86 #333c57).

Follow shared conventions C1-C9 in `docs/specs/office-phase1.md`. Read `template/office/office.js` (layout,
`buildLayout`, `paintBackground`, `route`, `spotFor`, `applyState`, `pickIdle`, pets, `drawScene`, overlays) and
`office.css` first. W stays 320. The office uses a 3/4 top-down view: the back wall is y < 46 (`FLOOR_Y`), and
characters' feet sit at their (x, y).

## Layout (coordinates are for the 2-row case; keep the existing `rows` formula)

Desk rows move down by 20 px: pair tops at y = 90 + r*42 (was 70), and `H = max(202, 90 + rows*42 + 34)`.
The canvas has three zones:

1. **Planning office**: x 0-97, y 46-85, in the top-left corner.
   - **Walls.** The back wall is the existing wall. A glass right wall at x = 97 runs y 46-85, with a door gap
     at y 50-63. A glass front wall at y = 85 runs x 0-97. Draw glass as a 2 px #73eff7 strip at 45% alpha
     with a 1 px #566c86 frame line; door gaps get a 1 px #566c86 post on each side. The front glass wall must
     sort with characters at y = 85, so it draws over the feet of anyone standing inside near it.
   - **Floor.** Carpet instead of planks: #333c57, with a 1 px #566c86 dot every 4 px in a checker offset.
   - **Whiteboard.** Move it from x 105 to x 26-72 on the back wall, and move every whiteboard drawing in
     `drawScene` (the progress bar and the planning scribbles) with it, along with any milestone label overlay.
     Use one constant `WB = {x, y, w, h}` so they can't drift apart again.
   - **Furniture.** Put the large table (`R.tableL`) in the room as a meeting table at about (34, 64), with the
     chair sprite beside it.
   - **The planner.** It stands at `PLAN_SPOT` in front of the whiteboard, at about (49, 58).
   - **Lights.** When nobody is in the room (no job with station "plan"), overlay it with #1a1c2c at 35% alpha:
     the lights are off. When someone is planning, there's no overlay. Fade over 400 ms, or switch instantly
     under reduced motion.
   - **Who may enter.** Nobody enters unless they hold a planning job. Pets never enter.

2. **Work floor**: x 0-187 below the planning office (y ≥ 86), plus the corridor strip x 98-187, y 46-85.
   - **Floor.** Keep the blue planks here.
   - **Desks.** Pairs keep x = 8 and x = 98.
   - **Back wall.** Its section x 98-187 keeps the front door (`DOOR` 168,50) and the clock. Move `R.window2`
     from x 76 to x 108, and the calendar from x 62 to x 136, so both stay clear of the planning office.
   - **Supervisor corner.** Move the boss table, computer, paper and chair, plus the fixer's seat, from the lounge
     to the bottom-left of the work floor, below the last desk row: table at about (34, H − 24), chair to its left,
     and the `boss` station seat updated to match. Move the corgi's bed next to it at about (88, H − 12). It's the
     supervisor's dog: it naps there and patrols the desks as it does today.
   - **Plate.** Add the overlay text plate "Supervisor" under the table, styled like the lane plates.

3. **Break room**: x 192-319, the full height (y 46 to H).
   - **Partition wall.** Separate it from the work floor with a 4 px low wall at x 188-191, from y 46 to H. Fill
     it #566c86, with a 1 px #94b0c2 highlight on its left edge and a 1 px #333c57 shadow on its right. Leave
     doorway gaps at y 50-63 (the top corridor) and y 118-135 (the aisle between desk rows), each with a 1 px
     post at its ends.
   - **Floor.** Warm wood planks instead of blue: base #ef7d57, a top highlight line #ffcd75, a bottom line and
     plank seams #b13e53, with the same plank pattern as the work floor. Keep the pink lounge rug on top.
   - **Back wall, left to right:** vending machine (x 194), water cooler (x 221), orange couch (x 236), plant
     (x 272), fridge (x 292). Put the small window above the couch, at about x 240 on the wall. Tall props stand
     with their bottom edge at about y 50.
   - **Lounge, unchanged:** rug, blue and green couches, small table and mug, plant at (302, 128).
   - **Coffee station.** Move the small table with the coffee machine and mug to the lower-left of the break
     room, at about (198, H − 40).
   - **Bin.** Move the green bin to about (306, H − 18).
   - **Plate.** Add the overlay plate "Break room" near the top of the room, just right of the partition.

Nothing may overlap: no prop footprint intersects another prop, a desk, the glass walls or the partition.

## Who goes where
- **Working jobs:**
  - `work`, `qa` and `review` go to the lane desk, as today
  - `plan` goes to `PLAN_SPOT` inside the planning office
  - `fix` goes to the supervisor seat
- **Idle agents:** a random free spot from `IDLE_SPOTS`, which must ALL be inside the break room and not on top
  of props. Give it at least 12 spots, each with a label:
  - vending, cooler and coffee spots in front of those props
  - a fridge spot
  - about 6 lounge spots on and around the rug
  - a window spot
- **Napping (rate-limited) and benched agents:** `NAP_SEATS` covers the orange couch (2 seats) and the blue and
  green couches (2 seats each). `NAP_FLOOR` has 4 spots, all inside the break room. Benched agents also stay in
  the break room.
- **Pets:**
  - The cat's random spots are on the work floor or in the break room, never in the planning office.
  - The corgi's patrol stops are the desks, and it returns to its new bed.
- **Arriving and leaving:** agents still come and go through the front door at (168, 50).

## Routing (the core of this change: nobody walks through walls)
Move the layout data and pathfinding into a new DOM-free file, `template/office/layout.js`. It sets
`window.OfficeLayout` in the browser and `module.exports` under Node. Load it from `index.html` before
`office.js`, and have `office.js` use it.

- **API.** `buildLayout(nLanes)` returns the layout object: zones, wall segments, door gaps, desks, props,
  spots, `WB`, `PLAN_SPOT`, `DOOR`, boss and bed. `route(layout, from, to)` returns a list of waypoints.
- **Model.** Walkable space is a small graph of corridor nodes:
  - the aisles (y = 56 for x ≥ 100 only; then one aisle below each desk row; then H − 6)
  - vertical corridors at x = 3 (only for y ≥ 90), x = 100 and x = 184 (just left of the partition)
  - one node on each side of every doorway: planning door at (92, 56) and (102, 56); partition doorways at
    (184, 56)/(196, 56) and (184, 126)/(196, 126)

  Inside the break room and inside the planning office, movement is free: a straight line between any two points
  in the same room. Find the path with BFS or Dijkstra over the graph. The start and end connect to the nearest
  reachable node in their own zone, by a vertical move to the nearest aisle (as the current code does) or a
  straight line inside a room.
- **Guarantee.** No path segment crosses a wall segment (planning glass, partition) except through a door gap.

## Tests
Add `tests/office_layout.test.js`, plain Node with `assert` and no packages, plus `tests/test_office_layout.py`,
which runs `node tests/office_layout.test.js` and skips if `node` isn't on PATH. The Node test runs for nLanes in
{1, 3, 6}:
1. Every `IDLE_SPOT`, `NAP_SEAT` and `NAP_FLOOR` spot is in the break room. `PLAN_SPOT` is in the planning
   office. Desks and the boss seat are on the work floor. The cat's spots are never in the planning office.
2. No two props overlap, and no prop overlaps a wall or a desk (use their rectangles).
3. For 300 seeded random pairs drawn from all spots, desks, `PLAN_SPOT`, the boss seat, `DOOR` and the bed: every
   route segment avoids every wall segment except through door gaps (a segment-intersection test), and the route
   ends at the target.
4. A route from any desk to any idle spot passes through a partition doorway. A route from a desk to `PLAN_SPOT`
   passes through the planning door.

All existing tests must still pass.

## Docs
Add one paragraph to the README Office section: the three zones, what they mean, and that the planning office's
lights are on only while planning. Add a CHANGELOG entry under a new `## 1.2.1 (unreleased)` heading.
