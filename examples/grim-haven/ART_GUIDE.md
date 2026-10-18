# Art and Audio Guide (v2)

**v2.0 (owner request R-3, GDD §17, written in T-247).** Grim Haven uses a **hybrid style**: detailed **32 px, 3/4 top-down pixel art** on the battlefield and in dungeons, and **painted graphic-novel** portraits, region/mission art and the Haven panorama. Systems do not change; only the art does. This guide is binding for every v2 asset task (T-253 slice, T-255..T-260 scale-up, M10, M11). When something is not covered here, pick the option closest to the chosen pack's look, log it in `project/assumptions.md` and continue.

> **v2.1 (T-254 slice review + owner R-4, 2026-10-17).** The T-253 slice was right on detail level, outline, light and animation set, and the painted portrait is the approved target. It was **not colourful or readable enough**: both units were rust-brown, they filled about half the tile, half their pixels were `void`, and the `soot` floor with `void` rock blobs swallowed the outlines. v2.1 changes §1 (faction colours), §2 (40-colour palette with faction hue families, value rules), §3 (unit fill, outline, contact shadow, floor/cover values) and §10 (Scrapfields colour key). Everything else stands. Every rule marked **(v2.1)** is checked by the slice revision and the scale-up reviews.

> **v1 legacy.** The Kenney 1-Bit 16 px art (recoloured to the 16-colour "Ash and Rust" palette) stays in the game until each asset is replaced. It renders at **4x** (16 px → 64 px tiles) next to v2 art at 2x. Don't edit legacy sprites; replace them file by file with v2 art under the same name. The v1 recolour tool (`game/tools/recolor.py`, `sprite_manifest.json`) is legacy-only. Legacy 16 px icons and pixel portrait layers keep their own tests until M11 replaces them.

## 0. Sources: chosen packs per need

Researched in T-246 (`project/art/PACK_RESEARCH.md`, measurements in `project/art/PACK_MEASUREMENTS.json`). Originals live in `asset_library/<folder>/original/` and never go into `game/` unedited. Every pack below is **CC0-1.0** unless stated.

| Need | Chosen source (licence) | Use | Gap → image generation (§7) |
|---|---|---|---|
| Ground, walls, masonry (Hollows, Rust Cathedral, Citadel) | **Lucifer Dungeon Tileset**, Foozle (CC0-1.0), `asset_library/foozle_lucifer_dungeon/` | Floors, broken floors, walls, grates, doors, gothic props | Metro tiles, rails, platform edges, flooded floors; rusted metal floors, pipes, industrial altars; fortified steel walls, machinery |
| Ground, fences, rock (Scrapfields, Haven) | **Lucifer Exterior Tileset**, Foozle (CC0-1.0), `asset_library/foozle_lucifer_exterior/` | Earth/dirt, rock, stone cover, fences, graves, wood structures | Junkyard overlays, wrecked cars, scrap walls, tyre stacks; scrap palisades, patched shacks |
| Sand, bones, fire, camp (Glass Wastes, Scrapfields) | **Lucifer Desert Tileset**, Foozle (CC0-1.0), `asset_library/foozle_lucifer_desert/` | Sand/stone/wood ground, bones, tents, 4-frame campfire | Fused glass crust, vitrified cover, ruined shop fronts, mall floors |
| Human units (heroes, Raiders, Rust Legion) | **Lucifer Warrior**, Foozle (CC0-1.0), `asset_library/foozle_lucifer_warrior/` | Pose timing, proportions, outline and shading style; pixels reused where a pose fits 32x32 | Every class/faction outfit and weapon; all poses redrawn to fit the 32x32 frame |
| Blighted units | **Lucifer Possessed**, Foozle (CC0-1.0), `asset_library/foozle_lucifer_possessed/` | Shambler base: lurch, hurt and collapse poses | Spitter, Wailer, Bloater, Mother Bloat bodies; remove held equipment |
| Iron Hound, turret, scrap trap | none suitable (the CC0 robot dog is a 3D mesh) | — | Whole units, all four animations |
| VFX (M11) | **Lucifer Effects**, Foozle (CC0-1.0); Desert campfire | Hit/destroy puff (6f), waves (3f), pickup glint for heal | Blood burst and splat, poison cloud, strong crit flash, large heal ring, burning overlay |
| UI panels and icons (M11) | **Lucifer RPG UI**, Foozle (CC0-1.0), `asset_library/foozle_lucifer_rpg_ui/` | Bevel panels, 16 px skill icons as bases | Ornate dark industrial/gothic frame corners, missing class/status icons |
| Font | **Departure Mono 1.500**, Helena Zhang (**SIL OFL 1.1**, fonts only) | Already installed; 22/44 px | — |
| Portraits, region/mission art, Haven panorama | ChatGPT image generation (§5, §6) | Painted art | All of it |

Not chosen: **Tiny Top Down Pack** (CC0; direct-overhead rendered walls clash with Lucifer's 3/4 view; comparison only), **CodeManu Pixel Art Wasteland** (8 px, too small), **Curt's** character/zombie sets (CC0, reserve only: incomplete combat states), CodeManu Free VFX (unverified reserve). Credit line for the Lucifer packs: "Foozle; Baldur (archive credit)" as in `game/assets/ledger/T-246.json` (CC0 needs no credit, but we give it).

**Lucifer cell size decision (T-246 hand-off):** Lucifer characters ship in 48x48 cells with attacks that overhang. We do **not** use 48 px cells for normal units: every regular unit is redrawn into **32x32 frames** (§3). Lucifer frames are a reference for timing, proportion and shading, and individual pixels may be reused when the pose fits inside 32x32 after the body is scaled to our height. Only the two big bosses use 48x48 (§3).

## 1. Style bible

**The split.** Pixel art for everything that lives on a grid (battlefield tiles, units, props, traps, VFX, dungeon room map). Painted art for everything that is a "picture" (portraits, region and mission art, the Haven panorama, title art). The two meet through the palette: painted art uses the same hue families and the same dark grounds.

**Mood words:** grim, worn, salvaged, sun-bleached, smoky, defiant. Colour is richer than v1 but never candy (v2.1): **units carry clear, fairly saturated faction colours** (§2 faction ink table) on **calm, muted, mid-dark terrain**; the colour lives on the characters, cover and cues, not in the ground. Deep shadows stay, but as ramp shades, not black.

**References (for humans, never in prompts):** Darkest Dungeon (ink weight, value contrast, portrait framing), XCOM (cover you can read at a glance), the Lucifer packs (our pixel baseline: outline, shading density, proportions), Fallout 1/2 (post-apocalyptic colour), heavy-ink comic art with flat colour and spot blacks.

**"Not cartoonish" in practice:**
- Realistic proportions: head about 1/4 of body height (7-8 px of a 26-28 px figure), no oversized heads, hands or weapons beyond what 32 px forces.
- No big eyes, no smiles, no rosy cheeks, no pure primaries (no `#ff0000`-style colours; only palette colours).
- Wear everywhere: patches, rust, grime, bandages, mismatched armour. Nothing new or clean.
- Motion is weighty: anticipation and follow-through over 1-2 px shifts, no rubbery squash and stretch, no bouncing.
- Painted art: shading follows form with hard shadow shapes, faces are tired and lined, not glamorous; never photo-real (see §6).

**Faction silhouettes and colours (v2.1).** Every faction owns a **hue family** (§2 "Faction ink table") that no other faction uses as a main colour, so you can tell the teams apart from colour alone at 720p. The faction's main family covers **at least 35%** of a unit's opaque pixels; the faction marker (below) is always visible in idle frame 0.

| Faction | Silhouette | Hue family (main / marker) |
|---|---|---|
| Heroes | Upright, practical layered clothing; one class accent on a scarf, armband, satchel or weapon wrap | Bone/cream cloth and leather (`bone`, `sand`, `dust`) with a **`teal` team marker** (neckerchief, armband or shoulder patch, 4-10 px) and steel (`sky`, `legion_light`) on metal; class accent (below) on the signature item only |
| Scavver Raiders | Spiky scrap armour: shoulder spikes, tyre/plate pauldrons, mohawks, crude masks, asymmetric | Rust/orange/red (`rust`, `rust_light`, `ember`) with **`scarlet` war paint / rag** as the marker; dark metal in `rust_dark`, never grey steel |
| Blighted | Hunched, swollen, one oversized limb or growth, head low and forward, ragged clothes | Sickly yellow-green flesh/growths (`blight`, `toxic`, `blight_light`) with **`violet` veins, sores or rags** as the marker; pallid `skin_light` only in small patches |
| Rust Legion | Upright, uniform, symmetrical; helmets, plate, long coats, banners/chains | Cold steel-blue/grey plate (`legion_blue`, `legion`, `legion_light`) with **brass trim** (`gold`, `brass_light`) as the marker; `rust` only as stains (≤ 5%) |
| Bosses / lieutenants | Their faction's silhouette, bigger or more ornate, plus a `gold`/`brass_light` element (crown, halo, icon) | faction family + `gold` |

**Class accents stay** (`classes.json` `accent`), but on heroes they are a **small** signature colour (≤ 15% of opaque pixels: weapon wrap, satchel, hat band). In particular the Bruiser's `rust` accent is only the forearm wrap and maul grip; the Bruiser's body is bone/sand with the teal marker, so it never reads as a Raider.

**Class silhouettes** (each must be recognisable as a black silhouette at 32 px; class accent = `classes.json` `accent`):

| Class | Silhouette | Weapon (GDD §4) | Accent |
|---|---|---|---|
| Bruiser | Widest body, broad shoulders, plated forearm, big two-handed weapon over the shoulder | Rebar maul | `rust` |
| Sharpshooter | Lean; a long rifle longer than the body is tall, held diagonally; brimmed hat or hood | Bolt-action rifle | `sky` |
| Medic | Satchel at the hip with a cross, scarf, coat; slim | Scalpel + flare pistol | `heal` |
| Scavenger | Hood, crouched stance, short blade in front, sling on the belt | Shiv + sling | `dust` |
| Mechanic | Goggles on the head, tool belt, big wrench, nailgun | Nailgun + tools | `ember` |
| Preacher | Long robe to the feet, book or lantern-like censer held out | Censer + revolver | `gold` |

## 2. Palette v2.1 ("Ash and Rust", broadened to 40 with faction hue families)

Stored in `game/assets/palette.json` (name → hex); `Palette.color(name)` reads it. The 16 v1 names keep their exact hexes (the dark UI, icon and portrait tests depend on them; `bone` on `soot` is 10.0:1), and the 14 v2.0 names keep theirs. **v2.1 adds 10 colours** (marked ★) for brighter faction colours and a lighter ground. Every v2 pixel sprite and tile uses **only** these 40 colours plus full transparency. `L` is Oklab lightness (0 = black, 1 = white); the value rules below use it.

| Name | Hex | L | Use |
|---|---|---|---|
| void | `#121010` | 0.18 | Outer outline of units and props, deepest shadow, UI background. **Never** a floor colour |
| soot | `#231e1c` | 0.24 | UI panels; **contact shadow** under units (§3); thin floor cracks only |
| ash | `#3b3431` | 0.33 | Floor variation, dark cloth |
| earth ★ | `#524436` | 0.40 | **Floor base** (Scrapfields and any outdoor ground) |
| stone | `#5e5550` | 0.46 | Walls, cover, mid cloth, floor pebbles |
| dust | `#8d8178` | 0.61 | Light stone, worn cloth; Scavenger accent |
| bone | `#d8c8a8` | 0.84 | Heroes' main light colour, text |
| white | `#f0e8d8` | 0.93 | Specular glints, muzzle flash (a few pixels only) |
| rust_dark | `#5c261a` | 0.34 | Raider shade, rusted metal shade |
| rust | `#9c4a30` | 0.51 | Raiders, rusted metal; Bruiser accent |
| rust_light ★ | `#c25a30` | 0.59 | **Raider main light**, bright rust |
| ember | `#d9813a` | 0.69 | Raider highlight (orange), fire, sparks; Mechanic accent |
| scarlet ★ | `#d63a2a` | 0.58 | **Raider marker**: war paint, rags, mohawks |
| gold | `#c9a646` | 0.74 | Fire core, loot, bosses, Legion brass; Preacher accent |
| brass_light ★ | `#ecd47e` | 0.87 | Brass/gold highlight (Legion trim, crowns, halos) |
| blood | `#7a1f1f` | 0.39 | Blood, deep red cloth |
| blood_light | `#b8332a` | 0.52 | Fresh blood, wounds |
| skin_light | `#e2b48c` | 0.80 | Light skin; Blighted pallid patches |
| skin_mid | `#b57a52` | 0.63 | Skin mid-tone, light leather |
| skin_dark | `#6a3c2c` | 0.41 | Dark skin, skin shade, leather shade |
| wood | `#7a5a2a` | 0.49 | Wood, crates; brass shade |
| sand | `#bb9a6c` | 0.71 | Sand, straw, light wood; hero cloth mid |
| blight_dark | `#586224` | 0.47 | Blighted shade, sludge |
| blight | `#7fa04a` | 0.66 | Blighted flesh, poison |
| toxic ★ | `#b6d43c` | 0.82 | **Blighted light**: bright yellow-green growths, glow |
| blight_light | `#cfc85c` | 0.82 | Pus, sickly yellow |
| violet_dark ★ | `#3f2a4c` | 0.33 | Blighted marker shade, deep bruise |
| bruise | `#6a4a7a` | 0.46 | Stress, afflictions, Blighted veins |
| violet ★ | `#8c5aa8` | 0.55 | **Blighted marker**: veins, sores, rags |
| violet_light ★ | `#c48ed4` | 0.72 | Blighted marker light, glowing sores |
| moss | `#2f5a48` | 0.43 | Moss, grass, damp stone; teal shade |
| teal ★ | `#2f8c84` | 0.58 | **Hero team marker** (scarf, armband, patch) |
| glass | `#9cd3c8` | 0.83 | Fused glass, screens; teal highlight |
| heal | `#5fa868` | 0.67 | Healing; Medic accent |
| water | `#24587a` | 0.44 | Water, deep cold shade |
| sky | `#5a7a8a` | 0.56 | Water surface, cold light, hero steel; Sharpshooter accent |
| legion_dark | `#3a4452` | 0.38 | Legion shade, dark steel |
| legion_blue ★ | `#4a6c9c` | 0.53 | **Legion main**: steel-blue plate, coats |
| legion | `#8a96a0` | 0.67 | Legion grey steel |
| legion_light | `#c3ccd0` | 0.84 | Steel highlight |

**Ramps** (dark → light; shade with the ramp, never by darkening a hex): neutral `void soot ash earth stone dust bone white`; hero cloth `skin_dark wood sand bone`; rust `rust_dark rust rust_light ember`; red `blood blood_light scarlet`; brass `wood gold brass_light`; skin `skin_dark skin_mid skin_light`; blight `blight_dark blight toxic` (+ `blight_light` pus); violet `violet_dark bruise violet violet_light`; steel-blue `legion_dark legion_blue legion legion_light white`; teal `moss teal glass`; water `water sky glass`; green `moss heal`.

**Faction ink table (v2.1, binding).** Each unit uses its faction's colours below plus neutrals (`void` outline, skin ramp, `ash`/`stone`/`dust` for small dark gear) and at most one class/boss accent. A faction's **main** colours are never a main colour of another faction (shared colours like `gold` or `rust` may appear only as small details, ≤ 10%).

| Faction | Main (≥ 35% of opaque px) | Shade | Light (≥ 10%) | Marker (always visible) | Never as main |
|---|---|---|---|---|---|
| Heroes | `bone`, `sand` | `wood`, `skin_dark` | `bone`, `white` glints | `teal` (+ `glass` light, `moss` shade); steel = `sky`/`legion_light` | `rust`, `rust_light`, `legion_blue`, `blight`, `toxic` |
| Raiders | `rust`, `rust_light` | `rust_dark` | `ember` | `scarlet` | `bone`, `teal`, `legion_blue`, `blight`, `toxic` |
| Blighted | `blight`, `toxic` | `blight_dark` | `toxic`, `blight_light` | `violet` (+ `violet_dark`, `violet_light`) | `rust`, `teal`, `legion_blue` |
| Rust Legion | `legion_blue`, `legion` | `legion_dark` | `legion_light` | `gold` + `brass_light` trim | `rust_light`, `teal`, `blight`, `toxic` |

**Value rules (v2.1, binding).** They exist so a unit pops off any floor at 720p.
- **Floors** sit in the middle-dark band: base `earth` (L 0.40) or another colour with L 0.33-0.46; no floor pixel darker than `ash` except 1 px `soot` crack lines (≤ 3% of a tile, never a blob wider than 2 px); no `void` in floors at all.
- **Cover and walls** are the brightest static shapes after units: their lit top/left faces use L ≥ 0.55 colours (`dust`, `legion`, `rust_light`, `sand`, `bone` edges), and their shaded faces stay at or above floor value; they keep the `void` outline where they meet floor.
- **Units:** at least **25% of opaque pixels have L ≥ 0.58** (the light end of the faction ramp) and at most **20% are `void`** (outline only: the outer ring, not interior lines; interior separations use the darkest colour of the local ramp). The outer `void` outline is then a clear dark ring against the `earth` floor.
- **Hazards and exits** stay the warm cues (`ember`, `gold`, `white` core) and must be brighter than any floor scatter.

**Quantization method (binding):** map every opaque pixel to the **nearest palette colour in Oklab** (Euclidean distance on L, a, b after sRGB → linear → Oklab). **No dithering**, unless the source pack already uses a checker dither on that surface (then keep its pattern, mapped colour by colour). Alpha: `< 128 → 0`, `>= 128 → 255`. After quantizing, fix by hand any ramp that collapsed into one colour, then **recolour to the faction ink table** (quantizing alone leaves Lucifer's browns: swap them to the faction ramp step for step). Check: every opaque pixel's hex is in `palette.json`, and the main/light/void percentages above hold (report them per unit in `work.json`).

## 3. Pixel rules

- **Grid:** 32x32 px tiles, **3/4 top-down** (walls show their front face; floors are seen from above at an angle, as in the Lucifer packs).
- **Light from the top left.** Highlights on top and left edges, shade on bottom and right. Props and cover may carry a 1-2 px `soot`/darkest-ramp shadow on their lower-right inside their own tile.
- **Contact shadow (v2.1):** every unit frame bakes a flat `soot` ground shadow: 2 rows (rows 30-31 of a 32 px frame; 46-47 for 48 px bosses), 12-18 px wide (about the stance width + 2 px each side), centred on x = 16 (x = 24 for 48 px), drawn behind the feet so the feet outline sits on it. Symmetric, so `flip_h` keeps it centred. It stays in every frame, including attack and hurt; in the death row it widens under the corpse. (Code draws no shadow; the sprite owns it.)
- **Outline:** 1 px `void` outline around the **outer** silhouette of characters and props (on the lighter v2.1 floors it reads as a clear dark ring). **(v2.1) No interior `void`:** lines between body parts, straps, folds and the weapon in front of the body use the darkest colour of the local ramp (`rust_dark`, `legion_dark`, `blight_dark`, `wood`, `skin_dark`, `violet_dark`), never `void`; `void` ≤ 20% of a unit's opaque pixels (the T-253 slice had 46-51%, which is why the units looked dark and thin). Inside the outline, the top and left edge of head, shoulders and weapon carry a **1 px rim of the faction light colour** (`bone`, `ember`, `toxic`, `legion_light`), so the silhouette separates from the floor even where the outline touches a dark scatter pixel. Floors have no outline. Walls and cover are outlined where they meet floor.
- **No anti-aliasing**, no soft gradients, no semi-transparency: alpha is 0 or 255. Hard pixels only; never rotate sprites (projectiles excepted).
- **Integer scale only.** The battlefield draws **32 px art at 2x** = 64 px tiles (`BattleGrid.TILE_PX = 64`; `BoardView.art_scale(width)` gives 2 for 32/48 px art). **Legacy 16 px art renders at 4x until replaced.** Keep PNGs at native size; never pre-upscale. Nearest filtering (project default). Only the final window scale may be fractional.
- **Units (v2.1 fill):** every unit fits a **32x32 frame** and fills it: **body 26-30 px tall** from the top of the head (or helmet/hood/mohawk) to the soles, **not counting a raised weapon**; feet on rows 29-30; body centred on x = 16. Humanoid torso + arms at least **12 px wide** at the shoulders (Bruiser, Legion plate, Bloater: 16-20 px); opaque pixels of idle frame 0 **≥ 380** (≥ 450 for the wide classes). All unit counts and percentages in this guide exclude the contact shadow. Legs and arms are at least 2 px thick plus outline, never 1 px stick limbs. Weapons and attack poses may use the full frame but never leave it. A unit should read as "a figure standing in the tile", filling about 80-90% of the 64 px tile's height on screen. **Big bosses (`mother_bloat`, `saint_ferro`) may use 48x48 frames** (anchor `[24, 32]`, feet on rows 45-46). Units **face right** in the sheet; code flips enemies (`flip_h`).
- **Colour budget:** at most ~12 palette colours per unit, ~8 per floor tile (~6 is better). Readability over detail: every unit follows the §2 faction ink table and value rules (≥ 35% faction main, ≥ 25% light pixels, ≤ 20% `void`).
- **Value rule for terrain (v2.1):** floors are **mid-dark and quiet**: base `earth` (or a region base with L 0.33-0.46, §2), at most 3 colours per floor tile in large areas, **low-contrast scatter** (pebbles, scrap bits, oil stains) in `ash`/`stone`/`wood`, each ≤ 3x3 px and ≤ ~8% of the tile in total, plus at most 1-3 single bright specks (`dust`, `sand`, `rust`). **No dark blobs** (nothing darker than `ash` wider than 2 px: they read as pits/holes), no `void`, no `soot` areas. The floor must look calm in a 3x3 mosaic: no bright or dark repeating spot that makes a grid pattern. **Cover and walls are the brightest static shapes after units** (§2 value rules): lit faces L ≥ 0.55, `void` outline toward the floor. Hazards and exits use the warm accents (`ember`, `gold`, `white` core) so they read instantly. The move-range highlight (code) lightens floor tiles; check in the capture that highlighted vs plain floor still differ clearly on the lighter base.
- **Tiles:** floor variants tile seamlessly in any 3x3 mix (test with a 3x3 random mosaic); walls and cover sit inside one 32x32 tile; **half cover is visibly lower than full cover** (half cover ≤ ~14 px tall, full cover fills ≥ ~24 px).

## 4. Animation sheet format (binding contract; read by `UnitSheet`, T-250/T-251)

Files next to the unit's static sprite, where `<sprite>` is the unit's data `sprite` field (e.g. `units/unit_bruiser`):

- `game/assets/<sprite>_sheet.png` — one row per animation, frames left to right, **no spacing or padding**; sheet width = `frame_w` × the longest row; unused cells transparent.
- `game/assets/<sprite>_sheet.json` — exactly this shape:

```json
{"frame_w": 32, "frame_h": 32, "anchor": [16, 16],
 "animations": {
   "idle":   {"row": 0, "frames": 4, "fps": 4,  "loop": true},
   "attack": {"row": 1, "frames": 4, "fps": 12, "loop": false},
   "hurt":   {"row": 2, "frames": 3, "fps": 12, "loop": false},
   "death":  {"row": 3, "frames": 5, "fps": 10, "loop": false}}}
```

- `game/assets/<sprite>.png` — the **static sprite = idle frame 0**, pixel for pixel (32x32; 48x48 for the two 48 px bosses). Turn-order icons and legacy fallbacks use it.
- `anchor` is the frame pixel drawn at the tile centre: `[16, 16]` for 32x32 units, `[24, 32]` for 48x48 bosses.
- **Frame counts:** idle 2-4; attack, hurt, death 3-6. **Durations** (`frames / fps`): attack ≤ 0.5 s, death ≤ 0.6 s (playback caps them anyway), hurt ≤ 0.3 s. Idle fps 3-6.
- **Key poses:** idle = breathing, 1 px rise/fall of the torso **plus one secondary motion** (v2.1: head, weapon tip, scarf/rag or growth moves 1 px out of phase), so idle reads as alive at 2x; the T-253 idles were almost static. Weapon stays in the same grip. Attack = anticipation → strike → recovery; melee may draw a 1-2 px smear in `bone`/`white` on the strike frame; ranged shows a 2-4 px `white`/`gold` muzzle flash on the shot frame. Hurt = recoil away from the attacker (left), 1-2 px, back to idle pose (the white hit flash is done in code, don't paint it). Death = stagger → fall; **the last frame is the corpse pose** lying inside the frame, held by code until the fade.
- Directions: only the right-facing set. Use the Lucifer side-facing ("right") rows as reference.

## 5. Portrait rules (painted graphic-novel)

- **Look:** bold black ink outlines and spot blacks, **flat colour fills with simple painted shading** (2-3 tones per material), muted palette hues, simple **flat dark background** in the class/faction colour (table below), no scenery.
- **Framing:** bust, head and shoulders; head top about 40-60 px below the top edge, face centred horizontally, eyes around y = 200; the face sits inside x 150-360, y 90-330 so overlays line up. Head turned 3/4 toward the viewer's right. Shoulders cut by the bottom edge. Must read at **128 px**: test by downscaling with linear filtering; the class must still be clear from outfit/weapon/accent.
- **File:** `game/assets/portraits/painted/<id>.png`, **512x512 PNG**, fully opaque. Heroes use **two variants per class**, `<class>_<variant>.png` with `<variant>` = `a` or `b` (T-277), e.g. `bruiser_a.png`, `bruiser_b.png`; enemies use the enemy id with no variant (`raider_thug.png`, M10). Imported with mipmaps (`mipmaps/generate=true` in the `.import`) and shown downscaled with linear filtering (T-252). Not palette-quantized (painted), but keep the palette's hue families and the background hex below.
- **Hero variants (T-277):** heroes have mixed names (`game/data/names.json`), so each class has a man (`a`) and a woman (`b`) so the portrait matches the name. The hero's `portrait_variant` comes from its first name (`names.json` `first_variant` map); the art doesn't pick it.
  - **Same character design in both:** the same outfit pieces, weapon, accent placement, framing, background hex and ink style. Only the face, hair and build change. Side by side at 128 px they must read as the same class at once.
  - **Variant `a`:** a man; the approved Bruiser (`bruiser_a.png`, the T-253 painting, owner-approved in R-4) is the style reference for every bust.
  - **Variant `b`:** a woman of a similar age range and toughness, with no glamour, make-up or a softer style: weathered, scarred and as grim as `a`.
  - **Code lookup (Portrait):** `<class>_<variant>.png`, then `<class>_a.png`, then the legacy `<class>.png` (test fixtures only), then the pixel bust. Pixel busts (`bust_<class>.png`) stay one per class.
  - **Ship both variants together.** A class with only `_a` makes every `b` hero fall back to the man.
- **Enemy busts (T-291):** one per enemy id, all 17 ids in `enemies.json` (12 ordinary, lieutenants `gutter_king_vasko`, `mother_bloat`, `marshal_iron_jaw`, `choir_ferro`, and `saint_ferro`), file `painted/<enemy_id>.png` (no `enemy_` prefix, no variants). Same framing as the hero busts, faction background from the table below, appearance from the approved v2.1 sprite and the matrix in `project/design/enemy_portraits.md`. Lieutenants and Saint Ferro carry one `gold` element; the Raider Boss does not. **The Choir is one three-figure composition; Saint Ferro has one bust for both phases; the Iron Hound is an animal bust** with its eyes on y = 200. Enemy busts get no overlays.
  - **Shown in combat** by `EnemyInspectPanel` at **128 px** (192 physical px at 1080p) with linear filtering and mipmaps, on a 128 px plate in the faction background hex. When the PNG is missing the panel draws the enemy's static sprite nearest-neighbour at an integer scale (32 px → 4x, 48 px → 2x) on that plate, so art and code can land in any order. The optional panel uses only a zero-overlap board corner; if none fits, it hides without clearing a valid pin and restores automatically. It protects the hovered tile even when empty, and refreshes pointer/subject/docking after hover-tile and camera changes (including arrow pan, middle drag and I focus), or when leaving onto the HUD. See `project/design/enemy_portraits.md` section 2.
- **Overlays** (scar, stress crack, affliction frame, virtue frame) stay separate layers drawn on top by code; never paint them into the portrait.
- **Background hex** (class/faction colour mixed 35% into `void`), painted flat edge to edge:

| Subject | Background |
|---|---|
| Bruiser | `#42241b` |
| Medic | `#2d452f` |
| Sharpshooter | `#2b353b` |
| Scavenger | `#3d3834` |
| Mechanic | `#58381f` |
| Preacher | `#524423` |
| Raiders | `#361515` |
| Blighted | `#384224` |
| Rust Legion | `#3c3f42` |

- **Post-processing:** crop square on the bust, resize to 512x512 (Lanczos/area), repaint the background flat with the hex above (a clean mask edge around the ink outline), check at 128 px. Keep the generated original and its prompt (§7).

## 6. Portrait prompt template (ChatGPT image generation)

The T-246 probe (`asset_library/generated/originals/probe_medic_portrait.png`) came out too realistic and busy. The template below fixes that: flatter colour, heavier ink, flat background. Fill the `{…}` slots; keep everything else word for word. The template is also the first entry of "v2 templates" in `asset_library/generated/originals/PROMPTS.md`.

```text
Graphic novel character portrait, bust framing (head and shoulders), square 1:1.
Style: bold thick black ink outlines, heavy black spot shadows, flat colour fills with simple
painted cel shading (two or three tones per material), comic book illustration, gritty
post-apocalyptic survivor, worn and patched gear. Not photographic.
Subject: {age/build/face}, a {class or enemy role} of a post-apocalyptic wasteland,
wearing {outfit, 3-5 concrete items}, holding/carrying {signature weapon or item}.
Expression: {tired, grim, determined...}. Head turned three-quarters to the viewer's right,
face centred, top of the head fully in frame, shoulders cut by the bottom edge.
Colours: muted earthy palette of bone, dust grey, soot brown and rust, with one accent
colour {accent colour words} on {where}.
Background: a single flat solid {background colour words} colour, edge to edge, nothing else.
Avoid: photo-realism, realistic skin pores, detailed rendering, airbrushed gradients,
any text, letters, logos, watermark or signature, any scenery, ruins, sky, sunset or light
behind the head, gradients or glow in the background, frames or borders, extra people,
hands covering the face, cartoon, anime or chibi proportions, 3D render look.
```

**Filled example (Bruiser):**

```text
Graphic novel character portrait, bust framing (head and shoulders), square 1:1.
Style: bold thick black ink outlines, heavy black spot shadows, flat colour fills with simple
painted cel shading (two or three tones per material), comic book illustration, gritty
post-apocalyptic survivor, worn and patched gear. Not photographic.
Subject: a broad, heavy-set man in his forties with a shaved head, a broken nose and a short
grey beard, a Bruiser (frontline brawler) of a post-apocalyptic wasteland,
wearing a patched canvas coat, a car-tyre and scrap-plate shoulder guard, leather straps
and a rust-red cloth wrap on his forearm, carrying a heavy rebar maul over his shoulder.
Expression: grim and steady. Head turned three-quarters to the viewer's right,
face centred, top of the head fully in frame, shoulders cut by the bottom edge.
Colours: muted earthy palette of bone, dust grey, soot brown and rust, with one accent
colour deep rust red on the forearm wrap and the maul's grip.
Background: a single flat solid very dark reddish-brown colour, edge to edge, nothing else.
Avoid: photo-realism, realistic skin pores, detailed rendering, airbrushed gradients,
any text, letters, logos, watermark or signature, any scenery, ruins, sky, sunset or light
behind the head, gradients or glow in the background, frames or borders, extra people,
hands covering the face, cartoon, anime or chibi proportions, 3D render look.
```

Keep a hero's portrait consistent with its sprite (same outfit pieces and accent placement). For a hero's `b` variant, change only the `{age/build/face}` slot (e.g. Bruiser b: "a broad, heavy-set woman in her forties with a shaved head, a broken nose and a scarred jaw") and the pronouns in the outfit line; keep every other slot the same as that class's `a` prompt so both busts match. For enemies use the faction silhouette words from §1 and the faction background. Enemy prompts (T-291): the `{class or enemy role}` slot is the in-game name with the role in brackets ("a Raider Thug (scavver brawler)"); in the "Colours" line replace "with one accent colour {…} on {…}" by the faction words (Raiders: rust orange and dried-blood red with scarlet war paint and rags; Blighted: sickly yellow-green flesh with violet veins, sores and rags; Legion: cold steel-blue and grey plate with brass trim, rust only as small stains), adding the named gold element for lieutenants and Saint Ferro. Only `choir_ferro.png` drops "extra people, " from the Avoid line. Subjects per id: `project/design/enemy_portraits.md` §1.

## 7. Generated pixel sprites pipeline

Use generation only for gaps listed in §0; **consistency with the chosen Lucifer pack beats novelty.**

1. **Generate large** on a flat, single-colour background (e.g. "pixel art sprite, 3/4 top-down view, facing right, single character, flat plain magenta background, no shadow, no text"), with the outfit words from §1. One pose or tile per image; for animation, generate the key poses separately with the same description.
2. **Downscale** to the 32 px grid with nearest or box (area) filtering only, so the subject is 26-28 px tall (tiles: exactly 32x32). Never bilinear/bicubic.
3. **Remove the background** (key out the flat colour), threshold alpha to 0/255.
4. **Quantize** to the palette (§2: nearest Oklab, no dithering).
5. **Clean by hand:** 1 px outline (§3), remove single-pixel noise and orphan pixels, fix light direction to the top left, match the Lucifer shading density and proportions, align the feet/anchor across frames.
6. **Store every original** (full-size generated image and intermediate steps you used) in `asset_library/generated/originals/<task id>/` (e.g. `T-253/`) with that folder's own `PROMPTS.md` (table: file, prompt, tool/model, date, notes). One folder per task so parallel lanes never edit the same file. Don't edit the top-level `PROMPTS.md` except to add new "v2 templates".
7. Pack art goes through steps 4-5 too (pack originals use other colours: quantize, then fix collapsed ramps).

## 8. Licence ledger rules

- **CC0 and CC-BY only** (CC-BY credited in `CREDITS.md` and the Credits screen). **SIL OFL for fonts only.** No CC-BY-SA, NC, ND or custom/personal-use licences.
- Every asset task writes its **own** `game/assets/ledger/T-###.json` and never edits another task's fragment. Format (as in `T-246.json`):

```json
{"task": "T-253", "entries": [
  {"source": "Lucifer - Warrior", "author": "Foozle; Baldur (archive credit)",
   "url": "https://foozlecc.itch.io/lucifer-warrior", "licence": "CC0-1.0",
   "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
   "local_path": "asset_library/foozle_lucifer_warrior/",
   "files": ["game/assets/units/unit_bruiser_sheet.png"],
   "credit": "Lucifer - Warrior by Foozle; Baldur (archive credit) (CC0-1.0)", "kind": "pack"},
  {"source": "ChatGPT image generation", "author": "Grim Haven team (generated)",
   "url": "https://chatgpt.com/", "licence": "CC0-1.0",
   "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
   "local_path": "asset_library/generated/originals/T-253/",
   "files": ["game/assets/portraits/painted/bruiser.png"], "kind": "generated"}]}
```

  `kind` is `pack` or `generated`; `files` lists every game file the source contributed to (paths start with `game/assets/`); CC-BY entries need a `credit`.
- `python game/tools/build_asset_index.py --write` regenerates the ledger sections of `game/assets/ASSET_INDEX.md` and `CREDITS.md`. **Only lane-A tasks (reviews, milestone QA) run it.** Asset tasks never edit those two files directly.

## 9. Deliverables per asset task

- **Contact sheet at game scale:** `project/runs/<task>/a<n>/contact_sheet.png` — every new asset at **2x** (animation sheets as labelled rows of frames) on the new floor tile, next to a few existing units/tiles (legacy at 4x) for scale and style comparison. Portraits at 128 and 256 px.
- **Before/after screenshots** (1280x720) for any visible change, in the run folder, from the task's scenario.
- State the palette check you ran (every opaque pixel in `palette.json`, alpha 0/255) in `work.json`.
- **(v2.1) Readability evidence:** in the contact sheet, a **black-silhouette row** (every unit filled `void` on the floor) and a **greyscale row** (the units on the floor tile converted to greyscale: they must still stand out). In `work.json`, per unit: body height (px), idle-0 opaque count, faction-main %, light (L ≥ 0.58) %, `void` %, all excluding the contact shadow. `python project/art/check_v21_readability.py units <png>:<heroes|raiders|blighted|legion> ...` prints them (and `... tiles <png> ...` prints floor/cover values: `void`/`soot` %, largest darker-than-`ash` blob, mean L).

## 10. Region tile kits (M10)

Each region gets its own kit at `game/assets/tiles/<region_id>/` with the **same file names** as the shared set: `tile_floor_1..3.png`, `tile_wall_1..2.png`, `tile_half_cover_1..2.png`, `tile_full_cover_1..2.png`, `tile_hazard_1.png`, `tile_exit.png` (11 tiles, 32x32). The shared `game/assets/tiles/tile_*.png` (Scrapfields art from T-253) stay the fallback for any battle without a region kit. Haven raids and the Siege use `tiles/haven/`.

**Hazard:** v1 `~` tiles are fire, so every region's hazard reads as **burning** (`ember` + `gold` flames, `white` core pixels) on its region base. **Exit:** a gate, hatch, ladder or stairway with a `gold` or `ember` cue, the same idea in every region.

| Region (`region_id`) | Base pack | Floor 1-3 | Wall 1-2 | Half cover 1-2 | Full cover 1-2 | Hazard | Exit | Colour key (floor / wall / cover / accent) |
|---|---|---|---|---|---|---|---|---|
| Scrapfields (`scrapfields`) | Exterior + Desert | Packed dirt, dirt with scrap bits, oil-stained dirt | Stacked scrap sheet wall, crushed-car wall | Tyre stack, low crate | Car wreck, scrap-plate barricade | Burning oil slick | Chain-link gate | `earth ash stone` / `stone dust rust_dark` / `rust rust_light wood sand` / `ember` |
| Hollows (`hollows`) | Dungeon | Cracked metro tiles, rail track, puddled tiles | Tunnel brick, tiled wall with pipe | Fallen bench, sandbags | Derailed carriage end, concrete pillar | Burning gas vent over water | Maintenance ladder hatch | `ash stone moss` / `stone dust legion_dark` / `wood sand stone` / `water sky blight` |
| Glass Wastes (`glass_wastes`) | Desert | Sand-dusted ash, fused glass crust, cracked mall floor | Vitrified rock wall, ruined shop front | Glass shard ridge, toppled kiosk | Fused car hulk, mall pillar | Molten glass / burning slag | Escalator top / mall door | `earth ash sand` (specks) / `stone dust glass` / `glass stone sand` / `glass gold` |
| Rust Cathedral (`rust_cathedral`) | Dungeon | Rusted floor plates, cracked flagstones, grate | Gothic masonry, rusted iron wall with pipes | Pew, low iron railing | Iron altar, buttress pillar | Coal brazier spill | Iron double door | `ash earth rust_dark` / `stone dust rust` / `rust wood stone` / `ember blood` |
| Citadel (`citadel`) | Dungeon + Exterior | Steel deck plates, hazard-striped plates, concrete | Fortified steel wall, machinery bank | Ammo crates, low steel barrier | Bunker block, generator | Furnace grate | Blast door | `legion_dark ash stone` / `legion legion_dark` / `legion legion_light stone` / `gold blood` |
| Haven (`haven`) | Exterior + Desert | Trodden earth, plank walkway, patchy grass | Scrap palisade, patched shack wall | Barrel, sandbag row | Watchtower base, cart | Burning barricade debris | Settlement gate | `earth wood moss` / `wood sand stone rust` / `wood sand stone` / `ember gold` |

Colour keys are v2.1 (T-254): floor bases follow the §2/§3 value rules (L 0.33-0.46, no `soot`/`void` areas, no dark blobs); wall and cover keys list their lit colours, which must be brighter than the floor. Region kits use `tiles/` (Scrapfields, v2.1 revision) as the reference for value, noise level and outline.

## 11. What goes where

```
game/assets/
  units/      unit_<class>.png (+ _sheet.png/.json), enemy_<id>.png (+ _sheet.png/.json)
  tiles/      shared fallback kit; tiles/<region_id>/ region kits (§10)
  props/      decoration
  icons/      skill_<id>.png, status_<id>.png, item_<id>.png, trinket_<id>.png, ... (16 px legacy until M11)
  portraits/  legacy pixel layers (64 px); painted/<class>_<a|b>.png heroes and painted/<enemy_id>.png enemies (512 px;
              enemies shown by EnemyInspectPanel in combat, missing = sprite on the faction plate)
  art/        painted, opaque, linear filtering (M10; looked up by ArtLookup / HavenPanorama, missing = v1 look):
              regions/<region_id>.png (960x540, 16:9; mission-board banners crop it to ~3:1)
              rooms/<region_id>/<room_type>.png, else shared rooms/<room_type>.png (960x320, 3:1)
              haven/panorama.png (1920x1080, 16:9; buildings painted inside the rects of data/haven_hotspots.json)
  ledger/     T-###.json (one per asset task)
  ui/         theme.tres, 9-slices, fonts
  sfx/  music/
  palette.json  ASSET_INDEX.md
asset_library/   originals (outside the Godot project): packs and generated/originals/<task id>/
```

## 12. UI v2 (M11, owner R-3; full spec: `project/design/ui_v2.md`)

Ornate dark panels and frames over the v1 look: `soot` fill, `stone` 2 px
border, `bone` text, `dust` secondary. Ornament lives on borders/corners
only, never behind readable text: generated 12x12 `gold`/`brass_light`
corners on large panels only (title, haven frame, building/hero/embark/
results/overlays), drawn inside the existing outer rect so nothing overflows
at 1280x720; small panels, buttons, bars and the combat/expedition dense rows
keep the plain 2 px border. Buttons carry all five states (normal `ash`,
hover `ember` border, pressed `rust`, disabled same-rect `dust`, focus `bone`
ring with `draw_center = false`). Minimum hit areas: text buttons 96x32,
icon buttons 32x32; content margins 12 (buttons) / 24 (panels, +8 where a
corner sits). Spacing scale `4/8/12/16/24/32`.
Font: Departure Mono 1.500 retained (SIL OFL 1.1); sizes 44 title / 33
headings / 22 base / 14 micro (log lines, inspect details, tooltips only),
antialiasing off; required glyphs ASCII printable + `°×–—…→·é` with a
no-tofu probe at 22 px and 14 px. Icons stay 16x16 native at 2x,
palette-quantized: 42 `skill_*`, 11 affliction/virtue, 4 missing curios, 28
per-id trinkets (rarity frame: common `dust`, uncommon `sky`, rare `gold`,
legendary `ember`), 12 camp, 6 disease; statuses/buildings/rooms/provisions/
resources/actions keep their shipped art. Bars: HP = `rust` on `blood`;
stress = `bruise` segments with a `white` tick at 100. Hit% colours:
≥ 75 `bone`, 40-74 `dust`, < 40 `rust`.

## 13. Code feedback

Code still adds feedback on top of the sheets: lunge toward the target on attack, white flash on hit, blood flash on Death's Door, shake + fade on death, tile-to-tile move tweens (0.08 s per tile). Units without a sheet keep the v1 one-frame look.

## 14. Audio

Kenney impact/interface sounds for hits, misses, UI. Stingers for the resolve check and deaths (CC0). Ambient loops: CC0 preferred; CC-BY allowed with credit. Levels: about −14 LUFS for loops, −6 dBFS peak for SFX.
