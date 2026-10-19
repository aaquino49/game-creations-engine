// Office zones layout tests: plain Node, assert only, no packages.
"use strict";
const assert = require("assert");
const OL = require("../template/office/layout.js");

const inBreak = (p, H) => p.x >= 192 && p.x <= 319 && p.y >= 46 && p.y <= H;
const inPlan = (p) => p.x >= 0 && p.x <= 97 && p.y >= 46 && p.y <= 85;
const onWork = (p, H) => (p.x >= 0 && p.x <= 187 && p.y >= 86 && p.y <= H) ||
  (p.x >= 98 && p.x <= 187 && p.y >= 46 && p.y <= 85);

// Segment intersection (proper crossing or touching counts; walls exclude gaps).
function segInt(a, b, c, d) {
  const d1 = (d.x - c.x) * (a.y - c.y) - (d.y - c.y) * (a.x - c.x);
  const d2 = (d.x - c.x) * (b.y - c.y) - (d.y - c.y) * (b.x - c.x);
  const d3 = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const d4 = (b.x - a.x) * (d.y - a.y) - (b.y - a.y) * (d.x - a.x);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true;
  const on = (p, q, r) => Math.min(p.x, r.x) <= q.x && q.x <= Math.max(p.x, r.x) &&
    Math.min(p.y, r.y) <= q.y && q.y <= Math.max(p.y, r.y);
  const col = (p, q, r) => (q.y - p.y) * (r.x - q.x) === (q.x - p.x) * (r.y - q.y);
  if (d1 === 0 && col(c, a, d) && on(c, a, d)) return true;
  if (d2 === 0 && col(c, b, d) && on(c, b, d)) return true;
  if (d3 === 0 && col(a, c, b) && on(a, c, b)) return true;
  if (d4 === 0 && col(a, d, b) && on(a, d, b)) return true;
  return false;
}

function crossesX(p1, p2, x, y0, y1) {
  if ((p1.x - x) * (p2.x - x) >= 0) return false;
  const t = (x - p1.x) / (p2.x - p1.x);
  const y = p1.y + t * (p2.y - p1.y);
  return y >= y0 && y <= y1;
}

function wallRects(H) {
  return [
    { x: 96, y: 46, w: 2, h: 4 }, { x: 96, y: 63, w: 2, h: 22 },
    { x: 0, y: 84, w: 97, h: 2 },
    { x: 188, y: 46, w: 4, h: 4 }, { x: 188, y: 63, w: 4, h: 55 }, { x: 188, y: 135, w: 4, h: H - 135 },
  ];
}
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

// Seeded RNG (mulberry32).
function rng32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

for (const nLanes of [1, 3, 6]) {
  const L = OL.buildLayout(nLanes);
  const H = L.H;
  // 1. Zones.
  for (const s of L.IDLE_SPOTS) assert.ok(inBreak({ x: s[0], y: s[1] }, H), `n=${nLanes} idle ${s} not in break room`);
  assert.ok(L.IDLE_SPOTS.length >= 12, "need >=12 idle spots");
  for (const s of [...L.NAP_SEATS, ...L.NAP_FLOOR]) assert.ok(inBreak({ x: s[0], y: s[1] }, H), `n=${nLanes} nap ${s} not in break`);
  assert.ok(inPlan(L.PLAN_SPOT), "PLAN_SPOT not in planning office");
  for (const d of L.desks) assert.ok(onWork({ x: d.cx, y: d.by }, H), `desk ${d.cx},${d.by} not on work floor`);
  assert.ok(onWork({ x: L.boss.x, y: L.boss.y }, H), "boss seat not on work floor");
  for (const s of L.CAT_SPOTS) assert.ok(!inPlan({ x: s[0], y: s[1] }), `cat spot ${s} in planning office`);
  // 2. Overlaps.
  const props = L.props;
  for (let i = 0; i < props.length; i++) for (let j = i + 1; j < props.length; j++) {
    assert.ok(!overlap(props[i], props[j]), `props overlap ${props[i].kind}@${props[i].x},${props[i].y} vs ${props[j].kind}@${props[j].x},${props[j].y}`);
  }
  for (const p of props) for (const d of L.pairs) {
    assert.ok(!overlap(p, d), `prop ${p.kind}@${p.x},${p.y} overlaps desk @${d.x},${d.y}`);
  }
  for (const p of props) for (const w of wallRects(H)) {
    assert.ok(!overlap(p, w), `prop ${p.kind}@${p.x},${p.y} overlaps wall ${JSON.stringify(w)}`);
  }
  // Idle spots not on props.
  for (const s of L.IDLE_SPOTS) for (const p of props) {
    assert.ok(!(s[0] >= p.x && s[0] < p.x + p.w && s[1] >= p.y && s[1] < p.y + p.h), `idle ${s} on prop ${p.kind}@${p.x},${p.y}`);
  }
  // 3. 300 seeded routes: no wall crossing, ends at target.
  const pool = [
    ...L.IDLE_SPOTS.map(s => ({ x: s[0], y: s[1] })),
    ...L.NAP_SEATS.map(s => ({ x: s[0], y: s[1] })),
    ...L.NAP_FLOOR.map(s => ({ x: s[0], y: s[1] })),
    ...L.desks.map(d => ({ x: d.cx, y: d.by })),
    { x: L.PLAN_SPOT.x, y: L.PLAN_SPOT.y },
    { x: L.boss.x, y: L.boss.y },
    { x: L.DOOR.x, y: L.DOOR.y },
    { x: L.bed.x, y: L.bed.y },
  ];
  const rnd = rng32(1000 + nLanes);
  for (let k = 0; k < 300; k++) {
    const from = pool[Math.floor(rnd() * pool.length)];
    const to = pool[Math.floor(rnd() * pool.length)];
    const pts = OL.route(L, from, to);
    assert.ok(pts.length > 0, "empty route");
    const last = pts[pts.length - 1];
    assert.strictEqual(last.x, to.x, `route ends x ${JSON.stringify(last)} vs ${JSON.stringify(to)}`);
    assert.strictEqual(last.y, to.y, `route ends y ${JSON.stringify(last)} vs ${JSON.stringify(to)}`);
    const full = [from, ...pts];
    for (let i = 0; i + 1 < full.length; i++) {
      for (const w of L.walls) {
        const c = { x: w.x1, y: w.y1 }, d = { x: w.x2, y: w.y2 };
        assert.ok(!segInt(full[i], full[i + 1], c, d),
          `n=${nLanes} route ${JSON.stringify(from)}->${JSON.stringify(to)} seg ${JSON.stringify(full[i])}->${JSON.stringify(full[i + 1])} hits wall ${JSON.stringify(w)}`);
      }
    }
  }
  // 4. Doorways.
  for (const d of L.desks) {
    const from = { x: d.cx, y: d.by };
    for (const s of L.IDLE_SPOTS) {
      const pts = OL.route(L, from, { x: s[0], y: s[1] });
      const full = [from, ...pts];
      const via = full.some((_, i) => i + 1 < full.length &&
        (crossesX(full[i], full[i + 1], 189.5, 50, 63) || crossesX(full[i], full[i + 1], 189.5, 118, 135)));
      assert.ok(via, `desk->idle misses partition doorway ${JSON.stringify(d)} -> ${s}`);
    }
    const pts = OL.route(L, from, L.PLAN_SPOT);
    const full = [from, ...pts];
    const via = full.some((_, i) => i + 1 < full.length && crossesX(full[i], full[i + 1], 97, 50, 63));
    assert.ok(via, `desk->plan misses planning door ${JSON.stringify(d)}`);
  }
}

console.log("office zones layout: all checks passed");

// Browser-like loading: layout.js and office.js run as classic scripts in ONE global scope, so layout.js must not
// leak top-level declarations (it once declared CAT_SPOTS etc. at top level and the page died with a SyntaxError).
{
  const vm = require("vm");
  const fs = require("fs");
  const path = require("path");
  const src = fs.readFileSync(path.join(__dirname, "..", "template", "office", "layout.js"), "utf8");
  const ctx = vm.createContext({ window: {} });
  vm.runInContext(src, ctx);
  assert.ok(ctx.window.OfficeLayout, "layout.js must set window.OfficeLayout");
  const officeSrc = fs.readFileSync(path.join(__dirname, "..", "template", "office", "office.js"), "utf8");
  const names = [...officeSrc.matchAll(/^(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)/gm)].map(m => m[1]);
  for (const n of new Set(names)) {
    assert.doesNotThrow(() => vm.runInContext(`let ${n} = 0;`, vm.createContext(ctx)), `layout.js leaks a global that office.js redeclares: ${n}`);
  }
  console.log("layout.js global-scope isolation OK");
}
