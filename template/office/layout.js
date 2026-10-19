// Office layout + routing: DOM-free. Sets window.OfficeLayout in the browser,
// module.exports under Node. office.js builds its scene from buildLayout().
// Wrapped in a function scope: classic <script>s share one global scope, and office.js declares some of the
// same names (W, DOOR, CAT_SPOTS...), so a top-level const here was a SyntaxError that blanked the page.
(function () {
"use strict";

const W = 320;
const FLOOR_Y = 46;
const WB = { x: 26, y: 7, w: 46, h: 28 };
const PLAN_SPOT = { x: 49, y: 58 };
const DOOR = { x: 168, y: 50 };

// All idle spots sit inside the break room (x 192-319, y 46-H), clear of props.
const IDLE_SPOTS = [
  [206, 62, "vending"],
  [225, 62, "cooler"],
  [204, 190, "coffee"],
  [218, 190, "coffee"],
  [304, 62, "fridge"],
  [210, 140, "lounge"],
  [230, 140, "lounge"],
  [290, 140, "lounge"],
  [250, 110, "lounge"],
  [260, 100, "lounge"],
  [280, 155, "lounge"],
  [244, 70, "window"],
  [214, 100, "lounge"],
  [236, 152, "lounge"],
];
// Orange couch (2) + blue couch (2) + green couch (2), all in the break room.
const NAP_SEATS = [[244, 46], [260, 46], [221, 114], [237, 114], [275, 114], [291, 114]];
const NAP_FLOOR = [[210, 160], [300, 100], [196, 140], [226, 150]];
// Work floor or break room only; never the planning office.
const CAT_SPOTS = [[240, 52], [300, 60], [230, 132], [290, 140], [196, 64], [120, 58], [50, 126]];

const PROP_SIZE = {
  tableL: [40, 16], tableS: [26, 16], vending: [24, 34], cooler: [9, 17],
  plant: [14, 19], couchOrg: [33, 16], couchBlu: [33, 16], couchGrn: [33, 16],
  fridge: [24, 31], binG: [9, 14], chair: [11, 22],
};

function inPlanning(p) { return p.x >= 0 && p.x <= 97 && p.y >= 46 && p.y <= 85; }
function inBreak(p, H) { return p.x >= 192 && p.x <= 319 && p.y >= 46 && p.y <= H; }

function buildLayout(nLanes) {
  const rows = Math.max(2, Math.ceil(nLanes / 4));
  const H = Math.max(202, 90 + rows * 42 + 34);
  const pairs = [];
  const desks = [];
  const aisles = [56];
  for (let r = 0; r < rows; r++) {
    for (const x of [8, 98]) pairs.push({ x, y: 90 + r * 42, w: 79, h: 31 });
    aisles.push(90 + r * 42 + 36);
  }
  aisles.push(H - 6);
  for (const p of pairs) {
    desks.push({ pair: p, cx: p.x + 15, by: p.y + 27, screen: [p.x + 26, p.y + 8, 7, 7], plate: [p.x + 21, p.y + 31] });
    desks.push({ pair: p, cx: p.x + 64, by: p.y + 27, screen: [p.x + 46, p.y + 8, 7, 7], plate: [p.x + 58, p.y + 31] });
  }
  const boss = { x: 24, y: H - 10, tableX: 34, tableY: H - 24 };
  const bed = { x: 88, y: H - 12 };
  // Wall segments exclude door gaps, so a route crossing a segment is always wrong.
  const walls = [
    { x1: 97, y1: 46, x2: 97, y2: 50 },   // planning right glass, above door
    { x1: 97, y1: 63, x2: 97, y2: 85 },   // planning right glass, below door
    { x1: 0, y1: 85, x2: 97, y2: 85 },    // planning front glass (no door)
    { x1: 189.5, y1: 46, x2: 189.5, y2: 50 },
    { x1: 189.5, y1: 63, x2: 189.5, y2: 118 },
    { x1: 189.5, y1: 135, x2: 189.5, y2: H },
  ];
  const gaps = [
    { x: 97, y0: 50, y1: 63, kind: "plan" },
    { x: 189.5, y0: 50, y1: 63, kind: "partition" },
    { x: 189.5, y0: 118, y1: 135, kind: "partition" },
  ];
  const zones = {
    planning: { x0: 0, x1: 97, y0: 46, y1: 85 },
    work: [{ x0: 0, x1: 187, y0: 86, y1: H }, { x0: 98, x1: 187, y0: 46, y1: 85 }],
    brk: { x0: 192, x1: 319, y0: 46, y1: H },
  };
  const P = (kind, x, y) => ({ kind, x, y, w: PROP_SIZE[kind][0], h: PROP_SIZE[kind][1] });
  const coffeeY = H - 40, binY = H - 18;
  const props = [
    P("tableL", 34, 64), P("chair", 20, 58),               // planning meeting table + chair
    P("vending", 194, 16), P("cooler", 221, 33), P("couchOrg", 236, 34),
    P("plant", 272, 31), P("fridge", 292, 19),             // break-room back wall
    P("couchBlu", 212, 104), P("couchGrn", 266, 104),
    P("tableS", 252, 126), P("plant", 302, 128),           // lounge, unchanged
    P("tableS", 198, coffeeY), P("binG", 306, binY),       // coffee station + bin
    P("tableL", 34, H - 24), P("chair", 18, H - 26),       // supervisor corner
  ];
  const graph = buildGraph(aisles, H);
  // Coffee idle spots track the coffee table so they stay in front of it for any H.
  const idle = IDLE_SPOTS.map(s => (s[2] === "coffee" ? [s[0], H - 18, s[2]] : s));
  return { W, FLOOR_Y, H, rows, pairs, desks, aisles, boss, bed, WB, PLAN_SPOT, DOOR,
    IDLE_SPOTS: idle, NAP_SEATS, NAP_FLOOR, CAT_SPOTS, zones, walls, gaps, props, graph };
}

function buildGraph(aisles, H) {
  const nodes = [];
  const key = (x, y) => x + "," + y;
  const seen = new Map();
  const add = (x, y) => {
    const k = key(x, y);
    if (!seen.has(k)) { const n = { x, y }; seen.set(k, n); nodes.push(n); }
    return seen.get(k);
  };
  for (const y of aisles) {
    if (y === 56) { add(100, 56); add(184, 56); }
    else if (y >= 90) { add(3, y); add(100, y); add(184, y); }
  }
  const pdL = add(92, 56), pdR = add(102, 56);
  add(196, 56); add(196, 126);
  const adj = new Map(nodes.map(n => [n, []]));
  const link = (a, b) => { adj.get(a).push(b); adj.get(b).push(a); };
  const byY = new Map();
  for (const n of nodes) {
    if (!byY.has(n.y)) byY.set(n.y, []);
    byY.get(n.y).push(n);
  }
  for (const arr of byY.values()) {
    arr.sort((a, b) => a.x - b.x);
    for (let i = 0; i + 1 < arr.length; i++) link(arr[i], arr[i + 1]);
  }
  const byX = new Map();
  for (const n of nodes) {
    if (!byX.has(n.x)) byX.set(n.x, []);
    byX.get(n.x).push(n);
  }
  for (const arr of byX.values()) {
    arr.sort((a, b) => a.y - b.y);
    for (let i = 0; i + 1 < arr.length; i++) {
      // x=3 only runs for y>=90; every stored x=3 node already satisfies that.
      link(arr[i], arr[i + 1]);
    }
  }
  // Break-room interior: the two break doorway nodes connect freely.
  const n56 = seen.get("196,56"), n126 = seen.get("196,126");
  if (n56 && n126 && !adj.get(n56).includes(n126)) link(n56, n126);
  void pdL; void pdR; void H;
  return { nodes, adj };
}

function nearestAisle(aisles, y, x) {
  let best = aisles[0], bd = 1e9;
  for (const a of aisles) {
    if (a === 56 && x < 100) continue; // top aisle only exists for x>=100
    const d = Math.abs(a - y);
    if (d < bd) { bd = d; best = a; }
  }
  return best;
}

function nearestNodeOnAisle(layout, y, x) {
  let best = null, bd = 1e9;
  for (const n of layout.graph.nodes) {
    if (n.y !== y) continue;
    const d = Math.abs(n.x - x);
    if (d < bd) { bd = d; best = n; }
  }
  return best;
}

function bfs(layout, fromN, toN) {
  if (fromN === toN) return [fromN];
  const prev = new Map([[fromN, null]]);
  const q = [fromN];
  while (q.length) {
    const cur = q.shift();
    for (const nb of layout.graph.adj.get(cur) || []) {
      if (!prev.has(nb)) { prev.set(nb, cur); if (nb === toN) { q.length = 0; break; } q.push(nb); }
    }
  }
  if (!prev.has(toN)) return null;
  const path = [];
  let c = toN;
  while (c) { path.unshift(c); c = prev.get(c); }
  return path;
}

function samePt(a, b) { return a && b && a.x === b.x && a.y === b.y; }

function route(layout, from, to) {
  const H = layout.H;
  const f = { x: from.x, y: from.y }, t = { x: to.x, y: to.y };
  const fPlan = inPlanning(f), tPlan = inPlanning(t);
  const fBrk = inBreak(f, H), tBrk = inBreak(t, H);
  if ((fPlan && tPlan) || (fBrk && tBrk)) return [{ x: t.x, y: t.y }];
  const door56 = { x: 196, y: 56 }, door126 = { x: 196, y: 126 };
  const nearBreakDoor = (p) => {
    const d56 = Math.hypot(p.x - door56.x, p.y - door56.y);
    const d126 = Math.hypot(p.x - door126.x, p.y - door126.y);
    return d56 <= d126 ? door56 : door126;
  };
  // Entry nodes plus the free straight prefix inside a room.
  let fromEntry, toEntry;
  const pre = [], post = [];
  if (fPlan) fromEntry = { x: 92, y: 56 };
  else if (fBrk) { const d = nearBreakDoor(f); fromEntry = d; pre.push({ x: d.x, y: d.y }); }
  else {
    const ay = nearestAisle(layout.aisles, f.y, f.x);
    const en = nearestNodeOnAisle(layout, ay, f.x);
    pre.push({ x: f.x, y: ay });
    fromEntry = en;
    if (!samePt(pre[0], en)) pre.push({ x: en.x, y: en.y });
  }
  if (tPlan) toEntry = { x: 92, y: 56 };
  else if (tBrk) { const d = nearBreakDoor(t); toEntry = d; post.push({ x: d.x, y: d.y }); }
  else {
    const by = nearestAisle(layout.aisles, t.y, t.x);
    const en = nearestNodeOnAisle(layout, by, t.x);
    toEntry = en;
    post.push({ x: en.x, y: en.y }, { x: t.x, y: by });
  }
  // Resolve entries to real graph nodes.
  const findNode = (p) => layout.graph.nodes.find(n => n.x === p.x && n.y === p.y);
  const fn = findNode(fromEntry), tn = findNode(toEntry);
  let mid = [];
  if (fn && tn) {
    const path = bfs(layout, fn, tn);
    if (path) mid = path.map(n => ({ x: n.x, y: n.y }));
  }
  // Stitch: pre + mid + post + target, dropping the start and dupes.
  let pts = [];
  if (fPlan || fBrk) {
    // pre already holds the doorway (break) or nothing (planning: start at door)
    if (fPlan) pts.push({ x: 92, y: 56 });
    else pts.push(...pre);
    pts.push(...mid.filter(p => !samePt(p, pts[pts.length - 1])));
  } else {
    pts.push(...pre);
    pts.push(...mid.filter(p => !samePt(p, pts[pts.length - 1])));
  }
  if (tPlan) {
    if (!samePt(pts[pts.length - 1], { x: 92, y: 56 })) pts.push({ x: 92, y: 56 });
  } else if (tBrk) {
    for (const p of post) if (!samePt(p, pts[pts.length - 1])) pts.push(p);
  } else {
    for (const p of post) if (!samePt(p, pts[pts.length - 1])) pts.push(p);
  }
  pts.push({ x: t.x, y: t.y });
  // Drop any leading dupes and collapse consecutive dupes.
  const out = [];
  for (const p of pts) if (!samePt(p, out[out.length - 1])) out.push(p);
  return out;
}

const OfficeLayout = { W, FLOOR_Y, WB, PLAN_SPOT, DOOR, IDLE_SPOTS, NAP_SEATS, NAP_FLOOR,
  CAT_SPOTS, buildLayout, route, inPlanning, inBreak };
if (typeof window !== "undefined") window.OfficeLayout = OfficeLayout;
if (typeof module !== "undefined" && module.exports) module.exports = OfficeLayout;
})();
