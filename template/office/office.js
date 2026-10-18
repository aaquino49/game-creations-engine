// The Office: draws the AI team as little people. Reads /api/state (served by server.py) every few seconds.
// Art: "Pixel Office" by 2dPig (CC0). Font: Departure Mono (OFL).
"use strict";

const W = 320;
let H = 176;
const FLOOR_Y = 46;
const cvs = document.getElementById("office");
const ctx = cvs.getContext("2d");
const stage = document.getElementById("stage");
const stageWrap = document.getElementById("stageWrap");
const overlay = document.getElementById("overlay");
const bannerEl = document.getElementById("banner");

// ------------------------------------------------------------------ art

const R = { // sprite rectangles in assets/office.png
  chairs: [6, 19, 32, 45, 58, 71].map(x => [x, 41, 11, 22]),
  tableS: [85, 47, 26, 16], tableL: [115, 47, 40, 16], plant: [170, 65, 14, 19],
  couchBlu: [120, 83, 33, 16], couchGrn: [120, 102, 33, 16], couchOrg: [120, 121, 33, 16],
  calendar: [234, 81, 17, 11], coffee: [159, 91, 7, 11], mug: [169, 95, 8, 7], picture: [239, 94, 11, 8],
  window: [59, 96, 26, 21], window2: [88, 96, 26, 21], computer: [233, 106, 15, 19], printer: [200, 107, 9, 9],
  clock: [159, 108, 19, 6], door: [98, 120, 16, 31], vending: [159, 123, 24, 34], fridge: [184, 126, 24, 31],
  binG: [116, 143, 9, 14], binR: [126, 143, 9, 14], cooler: [147, 140, 9, 17], cat: [65, 129, 15, 13], corgi: [59, 146, 24, 11],
  paper: [183, 107, 6, 8], flagless: [222, 94, 6, 8],
};
// Five base characters; shirt/hair colours are swapped so every agent looks different.
const BASES = {
  boy:       { r: [2, 105, 15, 23], shirt: [13, 19], hair: [0, 9], shirtCols: ["#94b0c2", "#566c86"], hairCols: ["#333c57"] },
  ponytail:  { r: [19, 104, 19, 24], shirt: [14, 20], hair: [0, 13], shirtCols: ["#f4f4f4", "#94b0c2"], hairCols: ["#b13e53", "#5d275d"] },
  glasses:   { r: [40, 107, 13, 21], shirt: [11, 17], hair: [0, 4], shirtCols: ["#f4f4f4"], hairCols: ["#94b0c2"] },
  redgirl:   { r: [3, 132, 17, 23], shirt: [13, 20], hair: [0, 14], shirtCols: ["#41a6f6", "#3b5dc9"], hairCols: ["#b13e53", "#5d275d"] },
  blackgirl: { r: [22, 132, 17, 23], shirt: [13, 20], hair: [0, 14], shirtCols: ["#b13e53", "#5d275d"], hairCols: ["#333c57"] },
};
const LOOKS = { // known agents get a fixed look; others are assigned in order
  quarterback: { base: "glasses", shirt: "#d97757" },
  qa_lead: { base: "boy", shirt: "#10a37f" },
  coder_1: { base: "ponytail", shirt: "#3b82f6" },
  coder_2: { base: "blackgirl", shirt: "#7b5cd6" },
  coder_3: { base: "redgirl", shirt: "#facc15", hair: "#8b5a2b" },
  coder_4: { base: "boy", shirt: "#f97316", hair: "#6b4423" },
  coder_5: { base: "blackgirl", shirt: "#2563eb" },
  claude: { base: "glasses", shirt: "#d97757" },
  codex: { base: "boy", shirt: "#10a37f" },
  codex_luna: { base: "blackgirl", shirt: "#7b5cd6" },
  muse_paid: { base: "ponytail", shirt: "#3b82f6" },
  muse: { base: "redgirl", shirt: "#60a5fa" },
  beam: { base: "redgirl", shirt: "#facc15", hair: "#8b5a2b" },
  longcat: { base: "boy", shirt: "#f97316", hair: "#6b4423" },
  deepseek: { base: "blackgirl", shirt: "#2563eb" },
};
const BASE_ORDER = ["boy", "ponytail", "redgirl", "blackgirl", "glasses"];
const PALETTE = ["#e11d48", "#0ea5e9", "#22c55e", "#a855f7", "#f59e0b", "#14b8a6", "#ec4899", "#84cc16"];
const NAMES = { quarterback: "Quarterback", qa_lead: "QA Lead",
  coder_1: "Coder 1", coder_2: "Coder 2", coder_3: "Coder 3", coder_4: "Coder 4", coder_5: "Coder 5",
  claude: "Claude", codex: "Codex", codex_luna: "Codex Luna", muse_paid: "Muse (paid)", muse: "Muse",
  deepseek: "DeepSeek", longcat: "LongCat", beam: "Beam" };
const shortName = id => NAMES[id] || id.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());

const sheet = new Image();
const deskImg = new Image();
const loaded = Promise.all([[sheet, "assets/office.png"], [deskImg, "assets/desk.png"]].map(([im, src]) =>
  new Promise((res, reject) => { im.onload = res; im.onerror = () => reject(new Error(`Couldn't load ${src}`)); im.src = src; })));
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let connectionError = false, polling = false, pollTimer;

function hex(c) { const n = parseInt(c.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function shade(c, f) { return "#" + hex(c).map(v => Math.max(0, Math.min(255, Math.round(v * f))).toString(16).padStart(2, "0")).join(""); }

const spriteCache = {};
function makeSprite(id, idx) {
  if (spriteCache[id]) return spriteCache[id];
  const look = LOOKS[id] || { base: BASE_ORDER[idx % 5], shirt: PALETTE[idx % PALETTE.length],
    hair: idx >= 5 ? ["#6b4423", "#e0b04a", "#3a2a1a"][idx % 3] : null };
  const b = BASES[look.base];
  const [sx, sy, w, h] = b.r;
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  g.drawImage(sheet, sx, sy, w, h, 0, 0, w, h);
  const img = g.getImageData(0, 0, w, h);
  const swap = (rows, from, to) => {
    const pairs = from.map((f, i) => [hex(f), hex(to[Math.min(i, to.length - 1)])]);
    for (let y = rows[0]; y < Math.min(rows[1], h); y++) for (let x = 0; x < w; x++) {
      const k = (y * w + x) * 4;
      if (!img.data[k + 3]) continue;
      for (const [f, t] of pairs) if (img.data[k] === f[0] && img.data[k + 1] === f[1] && img.data[k + 2] === f[2]) {
        img.data[k] = t[0]; img.data[k + 1] = t[1]; img.data[k + 2] = t[2]; break;
      }
    }
  };
  if (look.shirt) swap(b.shirt, b.shirtCols, [look.shirt, shade(look.shirt, 0.72)]);
  if (look.hair) swap(b.hair, b.hairCols, [look.hair, shade(look.hair, 0.7)]);
  g.putImageData(img, 0, 0);
  return (spriteCache[id] = c);
}

function blit(r, x, y, flip = false) {
  const [sx, sy, w, h] = r;
  if (!flip) return ctx.drawImage(sheet, sx, sy, w, h, Math.round(x), Math.round(y), w, h);
  ctx.save(); ctx.translate(Math.round(x) + w, Math.round(y)); ctx.scale(-1, 1);
  ctx.drawImage(sheet, sx, sy, w, h, 0, 0, w, h); ctx.restore();
}

// ------------------------------------------------------------------ layout

let L = null; // built once we know how many lanes there are
const IDLE_SPOTS = [[16, 57, "vending"], [36, 57, "cooler"], [52, 58, "coffee"], [64, 57, "coffee"], [90, 57, "window"],
  [178, 58, "plant"], [214, 74, "lounge"], [230, 78, "lounge"], [262, 72, "lounge"], [278, 76, "lounge"], [302, 66, "fridge"],
  [196, 100, "lounge"], [304, 152, "lounge"], [252, 96, "lounge"]];
const NAP_SEATS = [[241, 50], [257, 50], [221, 120], [237, 120], [275, 120], [291, 120]];
const NAP_FLOOR = [[210, 160], [300, 100], [196, 140], [226, 150]];
const DOOR = { x: 168, y: 50 };
const PLAN_SPOT = { x: 96, y: 57 };
const COLS = [3, 92, 187];

function buildLayout(nLanes) {
  const rows = Math.max(2, Math.ceil(nLanes / 4));
  H = Math.max(182, 70 + rows * 42 + 34);
  cvs.height = H;
  const pairs = [], desks = [], aisles = [56];
  for (let r = 0; r < rows; r++) {
    for (const x of [8, 98]) pairs.push({ x, y: 70 + r * 42 });
    aisles.push(70 + r * 42 + 36);
  }
  aisles.push(H - 6);
  for (const p of pairs) {
    desks.push({ pair: p, cx: p.x + 15, by: p.y + 27, screen: [p.x + 26, p.y + 8, 7, 7], plate: [p.x + 21, p.y + 31] });
    desks.push({ pair: p, cx: p.x + 64, by: p.y + 27, screen: [p.x + 46, p.y + 8, 7, 7], plate: [p.x + 58, p.y + 31] });
  }
  const bossY = H - 22;
  L = { rows, pairs, desks, aisles, boss: { x: 246, y: bossY + 16, tableY: bossY }, bed: { x: 214, y: H - 14 } };
  // scenery that sorts with the characters (x, y = top-left; sort by bottom edge)
  L.props = [
    [R.vending, 4, 16], [R.cooler, 31, 33], [R.tableS, 42, 34], [R.coffee, 47, 27, 0.2], [R.mug, 58, 31, 0.2],
    [R.plant, 184, 31], [R.couchOrg, 232, 34], [R.plant, 268, 31], [R.fridge, 290, 19],
    [R.couchBlu, 212, 104], [R.couchGrn, 266, 104], [R.tableS, 252, 126], [R.mug, 262, 123, 0.2], [R.plant, 302, 128],
    [R.binG, 182, 142], [R.tableL, 252, bossY], [R.computer, 264, bossY - 12, 0.2], [R.paper, 284, bossY - 4, 0.2],
    [R.chairs[5], 236, bossY - 6, -0.5],
  ].map(([r, x, y, bias = 0]) => ({ r, x, y, sort: y + r[3] + bias }));
  L.bg = paintBackground();
}

function paintBackground() {
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d");
  // wall
  g.fillStyle = "#f4f4f4"; g.fillRect(0, 0, W, FLOOR_Y);
  g.fillStyle = "#566c86"; g.fillRect(0, 0, W, 4);
  g.fillStyle = "#94b0c2"; for (const y of [14, 24, 34]) g.fillRect(0, y, W, 1);
  g.fillStyle = "#566c86"; g.fillRect(0, FLOOR_Y - 2, W, 1);
  g.fillStyle = "#ffcd75"; g.fillRect(0, FLOOR_Y - 1, W, 1);
  // floor planks (same pattern as the pack's floor)
  for (let y = FLOOR_Y, row = 0; y < H; y += 8, row++) {
    g.fillStyle = "#41a6f6"; g.fillRect(0, y, W, 8);
    g.fillStyle = "#73eff7"; g.fillRect(0, y, W, 1);
    g.fillStyle = "#29366f"; g.fillRect(0, y + 7, W, 1);
    for (let x = (row % 2) * 36 - 36; x < W; x += 73) {
      g.fillStyle = "#29366f"; g.fillRect(x, y, 1, 8);
      g.fillStyle = "#73eff7"; g.fillRect(x + 1, y + 1, 1, 6);
    }
  }
  const put = (r, x, y) => g.drawImage(sheet, r[0], r[1], r[2], r[3], x, y, r[2], r[3]);
  put(R.window2, 76, 10); put(R.window, 200, 10); put(R.calendar, 62, 18); put(R.picture, 300, 8);
  put(R.door, 160, 15); put(R.clock, 158, 7);
  g.fillStyle = "#1a1c2c"; g.fillRect(159, 8, 17, 4); // blank the sprite's 12:00; the real time is drawn on top
  // whiteboard (planning)
  g.fillStyle = "#566c86"; g.fillRect(105, 7, 46, 28);
  g.fillStyle = "#f4f4f4"; g.fillRect(107, 9, 42, 24);
  g.fillStyle = "#94b0c2"; g.fillRect(106, 35, 44, 2);
  // lounge rug and the supervisor's dog bed
  g.fillStyle = "#c15b82"; g.fillRect(203, 96, 114, 52);
  g.fillStyle = "#e58fb0"; g.fillRect(205, 98, 110, 48);
  g.fillStyle = "#5d275d"; g.beginPath(); g.ellipse(L.bed.x, L.bed.y, 14, 6, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = "#b13e53"; g.beginPath(); g.ellipse(L.bed.x, L.bed.y - 1, 12, 4.5, 0, 0, Math.PI * 2); g.fill();
  return c;
}

// ------------------------------------------------------------------ characters

const chars = new Map(); // id -> character
const pets = {};
let STATE = null, firstState = true, lastEventId = -1;
let deskInfo = []; // per desk: lane state from the server
const deskFx = {};  // desk index -> {alert, until, cloudUntil}
const now = () => performance.now() / 1000;

function nearest(list, v) { return list.reduce((a, b) => Math.abs(b - v) < Math.abs(a - v) ? b : a); }
function route(a, b) {
  if (a.x > 192 && b.x > 192) return [{ x: b.x, y: b.y }];
  const pts = [];
  const ay = nearest(L.aisles, a.y), by = nearest(L.aisles, b.y);
  if (Math.abs(a.y - ay) > 1) pts.push({ x: a.x, y: ay });
  if (ay !== by) {
    const cx = nearest(COLS, (a.x + b.x) / 2);
    pts.push({ x: cx, y: ay }, { x: cx, y: by });
  }
  pts.push({ x: b.x, y: by }, { x: b.x, y: b.y });
  return pts;
}

function makeChar(id, agent, idx, x, y) {
  return { id, agent, sprite: makeSprite(agent, idx), x, y, path: [], mode: "stand", targetKey: "", targetMode: "stand",
    facing: 1, leaving: false, idleUntil: 0, say: null, bubble: null, seed: Math.random() * 10 };
}
function goTo(ch, spot, mode, key) {
  if (ch.targetKey === key && !ch.leaving) return;
  ch.targetKey = key; ch.targetMode = mode; ch.leaving = false;
  ch.path = route(ch, spot); ch.mode = "walk";
}

function updateChar(ch, dt) {
  if (!ch.path.length) return;
  if (reducedMotion.matches) {
    const end = ch.path[ch.path.length - 1]; ch.x = end.x; ch.y = end.y;
    ch.path = []; ch.mode = ch.targetMode;
    if (ch.leaving) chars.delete(ch.id);
    return;
  }
  const p = ch.path[0], dx = p.x - ch.x, dy = p.y - ch.y, d = Math.hypot(dx, dy), step = 34 * dt;
  if (Math.abs(dx) > 0.3) ch.facing = dx < 0 ? -1 : 1;
  if (d <= step) { ch.x = p.x; ch.y = p.y; ch.path.shift(); }
  else { ch.x += dx / d * step; ch.y += dy / d * step; }
  if (!ch.path.length) {
    ch.mode = ch.targetMode;
    if (ch.leaving) chars.delete(ch.id);
  }
}

function drawChar(ch, t) {
  const s = ch.sprite, w = s.width, h = s.height;
  let x = ch.x - w / 2, y = ch.y - h;
  if (!reducedMotion.matches) {
    if (ch.mode === "walk") y -= Math.floor(t * 8 + ch.seed) % 2;
    else if (ch.mode === "sit") y -= (Math.floor(t * 3 + ch.seed) % 2) * (ch.typing ? 1 : 0);
    else if (ch.mode === "stand") y -= Math.floor(t * 0.8 + ch.seed) % 2;
  }
  if (ch.mode === "couch") { // sitting: hide the legs in the cushions
    const keep = h - 7;
    ctx.drawImage(s, 0, 0, w, keep, Math.round(x), Math.round(ch.y - keep), w, keep);
    return;
  }
  if (ch.mode === "floor") { // napping on the floor
    ctx.save(); ctx.translate(Math.round(ch.x), Math.round(ch.y - 4)); ctx.rotate(-Math.PI / 2);
    ctx.drawImage(s, -w / 2, -h / 2); ctx.restore();
    return;
  }
  ctx.save();
  if (ch.facing < 0) { ctx.translate(Math.round(x) + w, Math.round(y)); ctx.scale(-1, 1); ctx.drawImage(s, 0, 0); }
  else ctx.drawImage(s, Math.round(x), Math.round(y));
  ctx.restore();
  if (ch.holding && ch.mode !== "walk") blit(R.mug, ch.x + (ch.facing < 0 ? -w / 2 - 4 : w / 2 - 4), ch.y - 11, ch.facing < 0);
}

// pets: the supervisor's corgi and the office cat
function makePet(kind, x, y) { return { kind, x, y, path: [], facing: 1, mode: "stand", targetMode: "stand", nextAt: 0, say: null, leaving: false, id: kind }; }

function updatePets(t, dt) {
  const dog = pets.corgi, cat = pets.cat;
  const supOn = STATE && STATE.supervisor === true;
  if (dog) {
    if (!supOn) {
      if (dog.targetKey !== "bed") { dog.targetKey = "bed"; dog.path = route(dog, { x: L.bed.x, y: L.bed.y + 2 }); dog.targetMode = "sleep"; dog.mode = "walk"; }
    } else if (!dog.path.length && t > dog.nextAt) { // patrol the desks, then back to bed (supervisor checks every 2 min)
      const stops = L.desks.slice(0, Math.max(2, deskInfo.length)).map(d => ({ x: d.cx + 6, y: d.by + 6 }));
      dog.path = [];
      let from = dog;
      for (const s of [...stops, { x: L.bed.x, y: L.bed.y + 2 }]) { dog.path.push(...route(from, s)); from = s; }
      dog.targetMode = "sleep"; dog.mode = "walk"; dog.targetKey = "patrol"; dog.nextAt = t + 120;
    }
    updateChar(dog, dt * 0.9);
  }
  if (cat) {
    if (!cat.path.length && t > cat.nextAt) {
      const spots = [[240, 52], [300, 60], [230, 132], [290, 140], [196, 64], [120, 58], [60, 62]];
      const [x, y] = spots[Math.floor(Math.random() * spots.length)];
      cat.path = route(cat, { x, y }); cat.mode = "walk"; cat.targetMode = Math.random() < 0.5 ? "sleep" : "stand";
      cat.nextAt = t + 20 + Math.random() * 30;
    }
    updateChar(cat, dt * 0.7);
  }
}
function drawPet(p, t) {
  const r = R[p.kind], w = r[2], h = r[3];
  let y = p.y - h;
  if (p.mode === "walk" && !reducedMotion.matches) y -= Math.floor(t * 8) % 2;
  blit(r, p.x - w / 2, y, p.facing < 0);
}

// ------------------------------------------------------------------ state -> office

const STEP_VERB = (step, type) => step === "work" ? (type === "asset" ? "painting" : type === "design" ? "designing" : type === "qa" ? "playtesting" : "coding")
  : ({ qa: "testing", review: "reviewing", plan: "planning", fix: "fixing a stall" }[step] || step);
const ICON = { coding: "💻", painting: "🎨", designing: "📐", playtesting: "🎮", testing: "🔍", reviewing: "✅", planning: "📝", "fixing a stall": "🛠️" };

function laneDesk(name) {
  const i = STATE.lanes.findIndex(l => l.lane === name);
  return i >= 0 ? i : 0;
}
function spotFor(job) {
  if (job.station === "plan") return { x: PLAN_SPOT.x, y: PLAN_SPOT.y, mode: "stand", key: "plan" };
  if (job.station === "boss") return { x: L.boss.x - 8, y: L.boss.y - 1, mode: "sit", key: "boss" };
  const i = laneDesk(job.station.split(":")[1]), d = L.desks[i];
  return { x: d.cx, y: d.by, mode: "sit", key: "desk" + i, desk: i };
}

function applyState(st) {
  const firstLayout = !L;
  STATE = st;
  if (firstLayout || deskInfo.length !== st.lanes.length) {
    buildLayout(st.lanes.length);
    for (const ch of chars.values()) { ch.targetKey = ""; ch.idleKey = ch.napKey = null; }
  }
  if (firstLayout) {
    pets.corgi = makePet("corgi", L.bed.x, L.bed.y + 2); pets.corgi.mode = "sleep";
    pets.cat = makePet("cat", 248, 52); pets.cat.mode = "sleep";
  }
  deskInfo = st.lanes;
  const open = st.orchestrator !== false;
  const want = new Map(); // character id -> plan
  st.agents.forEach((a, idx) => {
    if (!open) return;
    const jobs = st.jobs.filter(j => j.agent === a.id);
    jobs.forEach((j, k) => {
      const v = STEP_VERB(j.step, j.type);
      want.set(k ? `${a.id}#${k + 1}` : a.id, { agent: a.id, idx, job: j, spot: spotFor(j),
        bubble: { text: `${ICON[v] || "•"} ${j.task ? j.task + " " : ""}${v}`, cls: j.step === "work" ? "work" : j.step,
                  title: `${shortName(a.id)}: ${j.task ? j.task + " " : ""}${j.title || ""}` } });
    });
    if (jobs.length) return;
    if (a.limit && a.limit.state === "gone") return; // on leave
    if (a.limit) { want.set(a.id, { agent: a.id, idx, nap: a.limit }); return; }
    want.set(a.id, { agent: a.id, idx, idle: true });
  });

  // people who should leave walk out of the door
  for (const ch of chars.values()) if (!want.has(ch.id) && !ch.leaving) {
    ch.leaving = true; ch.targetKey = "door"; ch.targetMode = "stand";
    ch.path = route(ch, DOOR); ch.mode = "walk"; ch.bubble = null; ch.say = null;
  }
  const napTaken = new Set([...chars.values()].filter(c => want.get(c.id)?.nap && c.napKey).map(c => c.napKey));
  const idleTaken = new Set([...chars.values()].filter(c => want.get(c.id)?.idle && c.idleKey).map(c => c.idleKey));
  for (const [id, plan] of want) {
    let ch = chars.get(id);
    if (!ch) {
      const start = firstState ? null : DOOR;
      ch = makeChar(id, plan.agent, plan.idx, start ? start.x : DOOR.x, start ? start.y : DOOR.y);
      chars.set(id, ch);
      if (firstState) ch.spawnDirect = true;
    }
    if (ch.leaving) { ch.targetKey = ""; ch.idleKey = ch.napKey = null; }
    ch.leaving = false;
    ch.label = shortName(plan.agent) + (id.includes("#") ? " ×" + id.split("#")[1] : "");
    ch.holding = false; ch.typing = false;
    if (plan.job) {
      ch.bubble = plan.bubble; ch.say = null; ch.typing = true; ch.napKey = ch.idleKey = null;
      place(ch, plan.spot, plan.spot.mode, plan.spot.key);
    } else if (plan.nap) {
      ch.say = null;
      ch.bubble = { text: plan.nap.state === "limited" ? `💤 back ~${plan.nap.until}` : `🔌 down ~${plan.nap.until}`, cls: "nap",
                    title: `${shortName(plan.agent)} is ${plan.nap.state === "limited" ? "rate-limited" : "unavailable (provider down)"} until about ${plan.nap.until}` };
      ch.idleKey = null;
      if (!ch.napKey) {
        const seat = NAP_SEATS.map((s, i) => ["seat" + i, s]).find(([k]) => !napTaken.has(k))
                  || NAP_FLOOR.map((s, i) => ["floor" + i, s]).find(([k]) => !napTaken.has(k)) || ["floor0", NAP_FLOOR[0]];
        ch.napKey = seat[0]; napTaken.add(seat[0]);
      }
      const seat = ch.napKey.startsWith("seat") ? NAP_SEATS[+ch.napKey.slice(4)] : NAP_FLOOR[+ch.napKey.slice(5)];
      place(ch, { x: seat[0], y: seat[1] }, ch.napKey.startsWith("seat") ? "couch" : "floor", "nap:" + ch.napKey);
    } else {
      ch.bubble = null; ch.napKey = null;
      if (!ch.idleKey || ch.targetKey.startsWith("desk") || ch.targetKey === "plan" || ch.targetKey === "boss" || ch.targetKey.startsWith("nap")) {
        pickIdle(ch, idleTaken);
      }
      ch.holding = ch.idleSpot === "coffee";
    }
  }
  if (firstState) for (const ch of chars.values()) if (ch.spawnDirect) { ch.path = []; ch.mode = ch.targetMode; ch.spawnDirect = false; }

  // events: effects for new ones (not on first load)
  for (const ev of st.events) {
    if (ev.id <= lastEventId) continue;
    if (!firstState) effect(ev);
  }
  if (st.events.length) lastEventId = Math.max(lastEventId, ...st.events.map(e => e.id));
  firstState = false;
  renderSide(st);
  renderBanner();
}

function place(ch, spot, mode, key) {
  if (ch.spawnDirect) { ch.x = spot.x; ch.y = spot.y; ch.targetKey = key; ch.targetMode = mode; ch.mode = mode; ch.path = []; return; }
  goTo(ch, spot, mode, key);
}
function pickIdle(ch, taken) {
  const free = IDLE_SPOTS.map((s, i) => ["idle" + i, s]).filter(([k]) => !taken.has(k));
  const [key, s] = free.length ? free[Math.floor(Math.random() * free.length)] : ["idle0", IDLE_SPOTS[0]];
  if (ch.idleKey) taken.delete(ch.idleKey);
  taken.add(key);
  ch.idleKey = key; ch.idleSpot = s[2];
  ch.idleUntil = now() + 12 + Math.random() * 20;
  place(ch, { x: s[0], y: s[1] }, "stand", key);
}

const CHAT = ["☕?", "nice merge!", "who broke the build?", "lgtm 👍", "brb", "🍩", "tabs or spaces?", "ship it!", "did you see M-progress?",
  "😂", "same", "one more coffee", "tests are green!", "the planner is cooking", "I ❤️ small diffs", "Friday deploy? 😬", "pixel art ftw", "need a nap"];
let nextChatAt = 0;
function idleLife(t) {
  if (reducedMotion.matches || connectionError) return;
  const idle = [...chars.values()].filter(c => c.idleKey && !c.path.length && !c.leaving);
  const taken = new Set(idle.map(c => c.idleKey));
  for (const c of idle) if (t > c.idleUntil) { pickIdle(c, taken); c.holding = c.idleSpot === "coffee"; }
  if (t > nextChatAt && idle.length) {
    nextChatAt = t + 2.5 + Math.random() * 3;
    const a = idle[Math.floor(Math.random() * idle.length)];
    const b = idle.find(c => c !== a && Math.hypot(c.x - a.x, c.y - a.y) < 34);
    if (b || Math.random() < 0.25) a.say = { text: b ? CHAT[Math.floor(Math.random() * CHAT.length)] : (a.idleSpot === "coffee" ? "☕" : "📱"), until: t + 2.6 };
  }
}

// ------------------------------------------------------------------ effects

const particles = [];
function confetti(x, y, n = 40, spread = 1) {
  if (reducedMotion.matches) return;
  const cols = ["#ffcd75", "#38b764", "#41a6f6", "#ef7d57", "#b13e53", "#f4f4f4", "#a855f7"];
  for (let i = 0; i < n; i++) particles.push({ x, y, vx: (Math.random() - 0.5) * 70 * spread, vy: -30 - Math.random() * 60,
    c: cols[i % cols.length], life: 1.6 + Math.random() });
}
function floatText(text, x, y, cls = "float") {
  const el = document.createElement("div");
  el.className = "ov " + cls; el.textContent = text;
  el.dataset.x = x; el.dataset.y = y;
  overlay.appendChild(el); positionEl(el, x, y);
  setTimeout(() => el.remove(), 3000);
}
let bannerFlash = null;
function effect(ev) {
  const t = now();
  const deskOf = lane => (lane && L) ? L.desks[laneDesk(lane)] : null;
  const laneOfTask = task => (STATE.lanes.find(l => l.task === task) || {}).lane || ev.lane;
  if (ev.kind === "done") {
    const d = deskOf(ev.lane); if (d) { confetti(d.cx, d.by - 14); floatText(`✓ ${ev.task} done!`, d.cx, d.by - 26); }
  } else if (ev.kind === "milestone" || ev.kind === "complete") {
    bannerFlash = { text: ev.kind === "complete" ? "🎉 Project complete!" : "🏆 " + ev.text.replace(/^MILESTONE\s*/, ""), until: t + 9 };
    for (let i = 0; i < 6; i++) setTimeout(() => confetti(30 + Math.random() * 260, 40 + Math.random() * 60, 50, 1.5), i * 300);
    renderBanner();
  } else if (ev.kind === "blocked") {
    const i = laneDesk(laneOfTask(ev.task)); (deskFx[i] = deskFx[i] || {}).cloudUntil = t + 40;
  } else if (/^(qa_fail|review_revise|review_block|checks_fail|work_blocked)/.test(ev.kind)) {
    const lane = laneOfTask(ev.task), i = laneDesk(lane);
    const msg = ev.kind.startsWith("qa") ? "QA found issues" : ev.kind.startsWith("checks") ? "checks failed" : ev.kind === "work_blocked" ? "stuck, asking for help" : "changes requested";
    deskFx[i] = { ...(deskFx[i] || {}), alert: `❗ ${msg}`, until: t + 8 };
  } else if (ev.kind === "supervisor" && pets.corgi) {
    pets.corgi.say = { text: "Woof! " + ev.text.replace(/^SUPERVISOR(-AI)?:?\s*/, "").slice(0, 46), until: t + 7 };
  } else if (ev.kind === "merged") {
    const d = deskOf(ev.lane); if (d) confetti(d.cx, d.by - 14, 14, 0.6);
  }
}

// ------------------------------------------------------------------ drawing

function drawScene(t) {
  ctx.clearRect(0, 0, W, H);
  ctx.drawImage(L.bg, 0, 0);
  // whiteboard: current milestone progress, scribbles while planning
  const cur = STATE && STATE.milestones.find(m => m.done < m.total);
  if (cur) {
    ctx.fillStyle = "#94b0c2"; ctx.fillRect(110, 27, 36, 4);
    ctx.fillStyle = "#38b764"; ctx.fillRect(110, 27, Math.round(36 * cur.done / cur.total), 4);
  }
  if (STATE && STATE.planner && STATE.planner.busy) {
    ctx.fillStyle = "#3b5dc9";
    const n = Math.floor(t * 2) % 7 + 2;
    for (let i = 0; i < n; i++) { const r = (i * 9301 + 49297) % 233280 / 233280; ctx.fillRect(110 + (i % 2) * 18, 19 + Math.floor(i / 2) * 2, 6 + Math.round(r * 10), 1); }
  }
  // sorted drawables
  const items = [];
  for (const p of L.props) items.push({ s: p.sort, f: () => blit(p.r, p.x, p.y) });
  L.pairs.forEach(p => items.push({ s: p.y + 31, f: () => drawDeskPair(p, t) }));
  for (const ch of chars.values()) {
    const s = ch.mode === "sit" && !ch.path.length ? ch.y + 4.5 : ch.mode === "couch" ? ch.y + 1 : ch.y;
    items.push({ s, f: () => drawChar(ch, t) });
  }
  for (const p of Object.values(pets)) items.push({ s: p.y, f: () => drawPet(p, t) });
  items.sort((a, b) => a.s - b.s).forEach(i => i.f());
  // particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i]; ctx.fillStyle = p.c; ctx.fillRect(Math.round(p.x), Math.round(p.y), 2, 2);
  }
  if (STATE && STATE.orchestrator === false) { ctx.fillStyle = "rgba(20,22,40,.5)"; ctx.fillRect(0, 0, W, H); }
}

function drawDeskPair(p, t) {
  ctx.drawImage(deskImg, p.x, p.y);
  for (const i of [L.desks.findIndex(d => d.pair === p && d.cx < p.x + 40), L.desks.findIndex(d => d.pair === p && d.cx > p.x + 40)]) {
    const d = L.desks[i], info = deskInfo[i], [sx, sy, sw, sh] = d.screen;
    if (!info) { ctx.fillStyle = "#566c86"; ctx.fillRect(sx + 1, sy + 1, sw - 2, sh - 2); continue; } // unused desk: screen off
    if (info.state !== "busy") { ctx.fillStyle = "#333c57"; ctx.fillRect(sx + 1, sy + 1, sw - 2, sh - 2); continue; }
    const col = { work: "#38b764", qa: "#41a6f6", review: "#ef7d57", checks: "#ffcd75", merge: "#a855f7" }[info.step] || "#73eff7";
    ctx.fillStyle = "#1a1c2c"; ctx.fillRect(sx + 1, sy + 1, sw - 2, sh - 2);
    ctx.fillStyle = col;
    const k = Math.floor(t * 4 + i);
    for (let r = 0; r < 3; r++) ctx.fillRect(sx + 2, sy + 2 + r * 2, 1 + ((k + r * 3) % (sw - 3)), 1);
  }
}

// ------------------------------------------------------------------ overlay (bubbles, tags, plates)

let scale = 3;
function positionEl(el, x, y) {
  const half = el.offsetWidth / 2;
  el.style.left = Math.max(half + 3, Math.min(stage.clientWidth - half - 3, x * scale)) + "px";
  el.style.top = (y * scale) + "px";
}
const ovEls = new Map();
let hoverCh = null, pinnedCh = null; // task bubbles stay collapsed unless hovered/focused, or pinned with a click
let hoverDesk = -1, pinnedDesk = -1; // same for lane-desk states (tests running, waiting to merge, sleeping)
function bindTag(el, id, label) {
  if (!el) return;
  if (!el._bound) {
    el._bound = true; el.tabIndex = 0;
    el.addEventListener("mouseenter", () => { hoverCh = el._chid; });
    el.addEventListener("mouseleave", () => { if (hoverCh === el._chid) hoverCh = null; });
    el.addEventListener("focus", () => { hoverCh = el._chid; });
    el.addEventListener("blur", () => { if (hoverCh === el._chid) hoverCh = null; });
    el.addEventListener("click", () => { pinnedCh = pinnedCh === el._chid ? null : el._chid; });
  }
  el._chid = id;
  el.setAttribute("aria-label", label);
}
function bindPlate(el, i, label) {
  if (!el) return;
  if (!el._bound) {
    el._bound = true; el.tabIndex = 0;
    el.addEventListener("mouseenter", () => { hoverDesk = el._deski; });
    el.addEventListener("mouseleave", () => { if (hoverDesk === el._deski) hoverDesk = -1; });
    el.addEventListener("focus", () => { hoverDesk = el._deski; });
    el.addEventListener("blur", () => { if (hoverDesk === el._deski) hoverDesk = -1; });
    el.addEventListener("click", () => { pinnedDesk = pinnedDesk === el._deski ? -1 : el._deski; });
  }
  el._deski = i;
  el.setAttribute("aria-label", label);
}
function ov(key, cls, text, x, y, title) {
  let el = ovEls.get(key);
  if (!el) { el = document.createElement("div"); overlay.appendChild(el); ovEls.set(key, el); }
  if (el.className !== "ov " + cls) el.className = "ov " + cls;
  if (el.textContent !== text) el.textContent = text;
  if (title !== undefined && el.title !== title) el.title = title;
  if (cls.startsWith("bubble") && title) { el.tabIndex = 0; el.setAttribute("aria-label", title); }
  positionEl(el, x, y);
  el._seen = true;
}

function drawOverlay(t) {
  for (const el of ovEls.values()) el._seen = false;
  if (!STATE) return;
  if (pinnedCh && !chars.has(pinnedCh)) pinnedCh = null;
  if (pinnedDesk >= deskInfo.length) pinnedDesk = -1;
  // desk name plates and desk-only states (tests running, waiting to merge, alerts)
  deskInfo.forEach((info, i) => {
    const d = L.desks[i];
    ov("plate" + i, "plate" + (i === pinnedDesk ? " pinned" : ""), "Lane " + info.lane, d.plate[0], d.plate[1]);
    bindPlate(ovEls.get("plate" + i), i, "Lane " + info.lane + (info.state === "busy" ? ": " + info.task + " " + (info.title || "") : ": idle"));
    const someoneHere = [...chars.values()].some(c => c.targetKey === "desk" + i && !c.leaving);
    const fx = deskFx[i] || {};
    const stagger = i % 2 ? 0 : -Math.max(8, 44 / scale);
    if (fx.alert && fx.until > t) ov("dalert" + i, "bubble alert", fx.alert, d.cx, d.by - 30 + stagger);
    else if (info.state === "busy" && !someoneHere && (i === hoverDesk || i === pinnedDesk)) {
      const txt = info.step === "checks" ? `🧪 ${info.task} tests running` : info.step === "merge" ? `📦 ${info.task} waiting to merge`
        : `⏳ ${info.task} ${info.step === "other" ? "" : info.step}`.trim();
      ov("desk" + i, "bubble desk", txt, d.cx, d.by - 26 + stagger, `${info.task} ${info.title || ""}\n${info.activity || ""}`);
    }
    if (fx.cloudUntil > t) ov("cloud" + i, "emoji", "🌧️", d.cx, d.by - 34);
  });
  for (const ch of chars.values()) {
    if (ch.leaving && ch.path.length === 0) continue;
    const h = ch.sprite.height;
    const top = ch.mode === "couch" ? ch.y - (h - 7) : ch.mode === "floor" ? ch.y - 14 : ch.y - h;
    const deskIdx = ch.targetKey.startsWith("desk") ? +ch.targetKey.slice(4) : -1;
    const stagger = deskIdx >= 0 && deskIdx % 2 === 0 ? -Math.max(8, 44 / scale) : 0;
    ov("tag" + ch.id, "tag" + (ch.id === pinnedCh ? " pinned" : ""), ch.label || ch.id, ch.x, ch.y + 1);
    bindTag(ovEls.get("tag" + ch.id), ch.id, (ch.label || ch.id) + (ch.bubble ? ": " + (ch.bubble.title || ch.bubble.text) : ""));
    if (ch.say && ch.say.until > t) ov("say" + ch.id, "bubble chat", ch.say.text, ch.x, top - 3);
    else if (ch.bubble && !ch.path.length && (ch.id === hoverCh || ch.id === pinnedCh)) ov("b" + ch.id, "bubble " + ch.bubble.cls, ch.bubble.text, ch.x, top - 3 + stagger, ch.bubble.title);
    if (ch.mode === "couch" || ch.mode === "floor") ov("z" + ch.id, "emoji", Math.floor(t * 1.5) % 2 ? "💤" : "💭", ch.x + 9, top + 2);
  }
  for (const p of Object.values(pets)) {
    if (p.say && p.say.until > t) ov("say" + p.id, "bubble woof", p.say.text, p.x, p.y - R[p.kind][3] - 3);
    else if (p.mode === "sleep" && !p.path.length) ov("z" + p.id, "emoji", "💤", p.x + 8, p.y - 8);
  }
  ov("clock", "clocktext", STATE.time || "", 167.5, 10);
  ovEls.get("clock").style.fontSize = Math.max(7, Math.round(4.6 * scale)) + "px";
  const cur = STATE.milestones.find(m => m.done < m.total);
  ov("board", "boardtext", cur ? `${cur.id} ${cur.done}/${cur.total}` : (STATE.complete ? "done!" : ""), 128, 10);
  if (scale) { const el = ovEls.get("board"); el.style.fontSize = Math.max(8, Math.round(6.5 * scale)) + "px"; }
  for (const [k, el] of ovEls) if (!el._seen) { el.remove(); ovEls.delete(k); }
}

// ------------------------------------------------------------------ banner, sidebar

function renderBanner() {
  const t = now();
  let text = "", dim = false;
  if (connectionError) { text = STATE ? "Connection lost · showing last reported activity" : "Office server offline · reconnecting…"; dim = true; }
  else if (STATE && !STATE.configured) { text = "No team configured yet"; dim = true; }
  else if (bannerFlash && bannerFlash.until > t) text = bannerFlash.text;
  else if (STATE) {
    if (STATE.orchestrator === false) { text = STATE.flags.includes("STOP") ? "Office closed (stopped by the owner)" : "Office closed: the team is offline"; dim = true; }
    else if (STATE.complete) text = "🎉 Project complete!";
    else if (STATE.flags.includes("STOP")) text = "Closing up after the current step";
    else if (STATE.flags.includes("RESTART")) text = "Reloading between tasks…";
    else if (STATE.flags.includes("PLAN_NOW")) text = "📝 The owner asked for a plan";
  }
  bannerEl.hidden = !text;
  bannerEl.textContent = text;
  bannerEl.classList.toggle("dim", dim);
}

const TICK = {
  start: e => `🚀 ${e.task} started on lane ${e.lane}`, done: e => `✅ ${e.task} done`, merged: e => `📦 lane ${e.lane} merged ${e.task}`,
  blocked: e => `⛔ ${e.task} blocked`, work_done: e => `💻 ${e.task} work handed in`, checks_pass: e => `🧪 ${e.task} checks pass`,
  checks_fail: e => `🧪 ${e.task} checks failed`, qa_pass: e => `🔍 ${e.task} QA pass`, qa_fail: e => `🔍 ${e.task} QA: changes needed`,
  review_approve: e => `👍 ${e.task} approved`, review_revise: e => `↩️ ${e.task} sent back for changes`, review_block: e => `⛔ ${e.task} review blocked it`,
  work_blocked: e => `🧱 ${e.task} coder got stuck`,
  plan_start: () => "📝 planning started", plan_done: e => "📝 " + e.text.replace(/^PLAN done:\s*/, "plan ready: "),
  milestone: e => "🏆 " + e.text, complete: () => "🎉 project complete", limit: e => "😴 " + e.text, restored: e => "☀️ " + e.text,
  fallback: e => "🔁 " + e.text.replace(/^FALLBACK\s*/, ""), supervisor: e => "🐶 " + e.text, gone: e => "👋 " + e.text,
  restart: () => "🔄 reloading", boot: () => "🌅 office opened",
};
let tickerSeen = -1;
function renderSide(st) {
  document.getElementById("game").textContent = (st.game || "The Office") + " · The Office";
  document.title = (st.game || "Game") + " · The Office";
  const pill = document.getElementById("pill");
  document.getElementById("subtitle").textContent = st.demo ? "demo · simulated activity" : "the AI team, live";
  document.getElementById("demoControl").hidden = !st.demo;
  document.getElementById("hint").textContent = st.demo
    ? "Demo only · no agents are running. Choose a scene or watch the auto tour."
    : !st.configured ? "Launch office.bat --demo to preview, or use --project with a scaffolded game folder."
    : st.orchestrator == null ? "Process status is unverified. Showing the project's last reported activity."
    : "Hover or tap a worker or lane plate for details; click to pin it. Closing this window never affects the team.";
  const working = st.jobs.length;
  if (!st.configured) { pill.textContent = "awaiting a team"; pill.className = "pill off"; }
  else if (st.orchestrator === false) { pill.textContent = "office closed"; pill.className = "pill off"; }
  else if (st.complete) { pill.textContent = "project complete"; pill.className = "pill ok"; }
  else if (st.orchestrator == null) { pill.textContent = "status unverified"; pill.className = "pill warn"; }
  else if (st.flags.includes("STOP") || st.flags.includes("RESTART")) { pill.textContent = st.flags.includes("STOP") ? "closing up" : "reloading"; pill.className = "pill warn"; }
  else { pill.textContent = `${working} at work`; pill.className = "pill ok"; }
  const c = st.counts || {};
  document.getElementById("counts").textContent = `${c.done || 0} done · ${c.in_progress || 0} in progress · ${(c.ready || 0) + (c.backlog || 0)} to go`;

  // milestones
  const ol = document.getElementById("milestones");
  const cur = st.milestones.find(m => m.done < m.total);
  ol.replaceChildren(...st.milestones.map(m => {
    const li = document.createElement("li");
    li.className = "ms" + (m === cur ? " current" : m.done >= m.total ? " done" : "");
    const pct = m.total ? Math.round(100 * m.done / m.total) : 0;
    li.innerHTML = `<span class="id"></span><span class="bar"><span class="fill"></span></span><span class="num"></span>`;
    li.querySelector(".id").textContent = m.id;
    li.querySelector(".fill").style.width = pct + "%";
    li.querySelector(".num").textContent = `${m.done}/${m.total}` + (m.done >= m.total ? " ✓" : "");
    li.title = `${m.id}${m.title ? ": " + m.title : ""} · ${pct}%${m.active ? ` · ${m.active} in progress` : ""}${m.blocked ? ` · ${m.blocked} blocked` : ""}`;
    if (m.title && m === cur) { const s = document.createElement("span"); s.className = "mtitle"; s.textContent = m.title; li.appendChild(s); }
    return li;
  }));
  if (!st.milestones.length) emptyItem(ol, "Milestones will appear when tasks are planned.");

  // team
  const ul = document.getElementById("team");
  ul.replaceChildren(...st.agents.map((a, idx) => {
    const li = document.createElement("li");
    const jobs = st.jobs.filter(j => j.agent === a.id);
    let what, away = false;
    if (st.orchestrator === false) { what = "off for the day"; away = true; }
    else if (jobs.length) what = jobs.map(j => {
      const v = STEP_VERB(j.step, j.type);
      return j.station === "plan" ? (j.title && j.title !== "planning the next tasks" ? `planning: ${j.title}` : "planning the next tasks") : j.station === "boss" ? "fixing a stall for the supervisor"
        : `${v} ${j.task} on lane ${j.station.split(":")[1]}`;
    }).join(" + ");
    else if (a.limit && a.limit.state === "gone") { what = "on leave (model withdrawn)"; away = true; }
    else if (a.limit) { what = a.limit.state === "limited" ? `asleep: usage limit, back ~${a.limit.until}` : `provider down, back ~${a.limit.until}`; away = true; }
    else { const ch = chars.get(a.id); what = ({ coffee: "on a coffee break", cooler: "at the water cooler", vending: "at the vending machine", lounge: "hanging out in the lounge",
      window: "looking out the window", fridge: "raiding the fridge", plant: "watering the plant" })[ch && ch.idleSpot] || "taking a break"; }
    li.className = "member" + (away ? " away" : "");
    const av = document.createElement("canvas");
    const sp = makeSprite(a.id, idx);
    av.width = 15; av.height = 23;
    av.getContext("2d").drawImage(sp, Math.floor((15 - sp.width) / 2), 23 - sp.height);
    const info = document.createElement("div");
    const name = document.createElement("div"); name.className = "name"; name.textContent = shortName(a.id);
    if (a.coder) { const b = document.createElement("span"); b.className = "badge"; b.textContent = "coder"; name.appendChild(b); }
    if (a.paid) { const b = document.createElement("span"); b.className = "badge paid"; b.textContent = "paid"; name.appendChild(b); }
    const w = document.createElement("div"); w.className = "what"; w.textContent = what;
    w.title = `${a.label}${a.model ? " · " + a.model : ""}\n${what}`;
    info.append(name, w);
    li.append(av, info);
    return li;
  }));
  if (!st.agents.length) emptyItem(ul, "Your configured agents will appear here.");

  // subscriptions (usage-limit buckets shared by every position on the account)
  const sub = document.getElementById("subs");
  const accts = st.accounts || [];
  sub.replaceChildren(...accts.map(a => {
    const li = document.createElement("li");
    const state = a.state || "ok";
    li.className = "sub" + (state === "limited" ? " warn" : state === "down" ? " bad" : state === "ok" ? "" : " mute");
    const dot = document.createElement("span"); dot.className = "sdot";
    const nm = document.createElement("span"); nm.textContent = a.label || a.id;
    const when = document.createElement("span"); when.className = "when";
    when.textContent = state === "ok" ? "ok" : `${state} ~${a.until || "?"}`;
    li.append(dot, nm, when);
    li.title = `${a.label || a.id}: ${(a.agents || []).map(m => shortName(m)).join(", ") || "no positions"}`;
    return li;
  }));
  if (!accts.length) emptyItem(sub, "No subscriptions configured.");

  // ticker
  const tk = document.getElementById("ticker");
  const evs = st.events.filter(e => e.kind !== "other" && e.kind !== "fallback").slice(-16).reverse();
  tk.replaceChildren(...evs.map(e => {
    const li = document.createElement("li");
    if (tickerSeen >= 0 && e.id > tickerSeen) li.className = "new";
    const tt = document.createElement("span"); tt.className = "t"; tt.textContent = e.t;
    const x = document.createElement("span"); x.className = "x"; x.textContent = (TICK[e.kind] || (ev => ev.text))(e); x.title = e.text;
    li.append(tt, x);
    return li;
  }));
  if (!evs.length) emptyItem(tk, "Waiting for the team's first event.");
  if (st.events.length) tickerSeen = Math.max(...st.events.map(e => e.id));
}

function emptyItem(list, text) {
  const li = document.createElement("li"); li.className = "empty"; li.textContent = text; list.appendChild(li);
}

// ------------------------------------------------------------------ loop, sizing, polling

function fit() {
  if (!L) return;
  const wrapW = stageWrap.clientWidth;
  const availH = Math.max(240, window.innerHeight - 140);
  let s = Math.min(wrapW / W, availH / H);
  if (s >= 2) s = Math.floor(s);
  stage.style.width = Math.floor(W * s) + "px";
  scale = Math.floor(W * s) / W;
}
window.addEventListener("resize", fit);

let lastT = now();
function frame() {
  const t = now(), dt = Math.min(0.1, t - lastT);
  lastT = t;
  if (L && STATE) {
    for (const ch of [...chars.values()]) updateChar(ch, dt);
    updatePets(t, dt);
    idleLife(t);
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i]; p.vy += 90 * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.life -= dt;
      if (p.life <= 0 || p.y > H) particles.splice(i, 1);
    }
    drawScene(t);
    drawOverlay(t);
    if (bannerFlash && bannerFlash.until < t) { bannerFlash = null; renderBanner(); }
  }
  requestAnimationFrame(frame);
}

async function poll() {
  if (polling) return;
  clearTimeout(pollTimer);
  polling = true;
  try {
    const scene = document.getElementById("scene").value;
    const r = await fetch("api/state?scene=" + encodeURIComponent(scene), { cache: "no-store", signal: AbortSignal.timeout(6000) });
    if (!r.ok) throw new Error(`Office returned ${r.status}`);
    const st = await r.json();
    if (!st || !Array.isArray(st.lanes) || st.error) throw new Error("Project state unavailable");
    connectionError = false;
    applyState(st); fit();
  } catch (e) {
    connectionError = true;
    const pill = document.getElementById("pill");
    pill.textContent = "office server offline"; pill.className = "pill off";
    renderBanner();
  } finally {
    polling = false;
  }
  pollTimer = setTimeout(poll, 3000);
}
document.getElementById("scene").addEventListener("change", () => { bannerFlash = null; poll(); });

function tickClock() { document.getElementById("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
setInterval(tickClock, 10000); tickClock();

loaded.then(() => { poll(); requestAnimationFrame(frame); }).catch(error => {
  document.getElementById("pill").textContent = "art could not load";
  bannerEl.hidden = false; bannerEl.textContent = error.message + ". Refresh to retry.";
});
