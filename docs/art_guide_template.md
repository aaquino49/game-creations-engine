# ART_GUIDE skeleton (write project/ART_GUIDE.md from this)

One consistent style beats pretty-but-mixed. The approach that worked for Grim Haven with no image generation:

- **Source**: one big CC0 pack as the backbone. Kenney's **1-Bit Pack** (16×16, ~1,000 sprites: characters, weapons, walls, props, icons, UI glyphs) recolors cleanly; other Kenney packs (UI Pack, Game Icons, Tiny Dungeon/Town, Roguelike) for gaps. Download into `asset_library/<pack>/` with the license file. Direct zip links are on each kenney.nl asset page ("Continue without donating").
- **Palette**: 12–16 named colors in `game/assets/palette.json`; faction/class colors assigned from it.
- **Pipeline**: `game/tools/recolor.py` (PIL) slices tiles from the packed sheet by (col, row), maps opaque pixels to a palette ink, writes 16×16 PNGs; `game/assets/sprite_manifest.json` records every sprite's source so the whole set regenerates byte-identically.
- **Scale**: integer only (e.g. 3× for the play area, 2× for UI), nearest filtering, never pre-upscale PNGs, never rotate pixel sprites.
- **Portraits / big art**: composed layers (plate, bust, tint, overlays) at 64×64 shown at 2×.
- **Animation**: if the pack has no frames, animate in code (bob, squash, lunge, flash, fade).
- **UI**: a shared `theme.tres` (dark panels, 1–2 px borders, palette text colors), one pixel font with unambiguous digits (OFL/CC0), used at integer sizes with antialiasing off.
- **Audio**: Kenney impact/interface sounds (CC0); CC-BY music only with credit.
- **Every asset task** produces a contact sheet at game scale for review, updates `game/assets/ASSET_INDEX.md` and `CREDITS.md`.

```markdown
# Art and Audio Guide
## Sources (table: pack | path | use)
## 1. Style (view, pixel size, inks, what's forbidden)
## 2. Palette (table: name | hex | use) + faction/class colors
## 3. Pipeline (slice → recolor → manifest → regenerate)
## 4. Where files go (folder tree + naming)
## 5. Portraits / large art
## 6. UI (theme, font, bars, colors for numbers)
## 7. Animation and feedback
## 8. Audio
```
