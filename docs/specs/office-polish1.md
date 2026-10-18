# Office polish 1: three cosmetic fixes

Follow the shared conventions C1-C9 in `docs/specs/office-phase1.md`. Change only `template/office/office.js`,
`office.css` and `demo.py`, plus tests if needed. Check each fix in `--demo`, at 1400 px and 500 px wide.

1. **Graph fit-to-width scales too small.** With ~30 demo tasks, the Graph view draws the whole DAG in about the
   top-left third of its box, with tiny unreadable labels. On load and on window resize, scale the drawing to fill
   the box's width, then cap the height at 70vh, keeping the aspect ratio. Never scale above 1.5× or below the
   point where node text is 9 px. When the result is taller than the box, the box scrolls vertically. The −/+ zoom
   buttons keep working relative to the fitted scale. Add a "Fit" button between them that resets to the fitted
   scale.
2. **Burndown x-axis labels overlap the edges.** In Stats → Throughput and burndown, the first tick label collides
   with the y-axis labels ("10-10-17 17") and the last is cut off at the right edge. Inset the plot area so the
   y-axis labels have their own gutter. Anchor the first label `start`, the last `end`, and the middle ones
   `middle`. Use a short tick format: `HH:00` for windows of 24 h or less, `Mon 14h` for longer ones. Apply the
   same rules to the throughput bar chart's x-axis.
3. **Demo roster is inconsistent.** In `--demo`, the Settings → Team section shows 4 positions, but the Team panel
   (from the demo state) shows 7 (quarterback, qa_lead, coder_1..coder_5). Make `demo_config()` cover the same 7
   agents with the same accounts, coders and paid flags the demo state uses (coder_3 benched, coder_1 paid), and
   fallback chains for each coder. Add a test that the agent ids in the demo config equal the agent ids in the
   demo state, for every scene.

Acceptance: all existing tests pass, plus the new demo-consistency test.
