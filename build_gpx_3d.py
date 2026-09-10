"""Build a self-contained 3D viewer (three.js) for the interval session.

Reads the CSVs written by interval_analysis.ipynb and writes index.html
with the track data embedded. The vertical axis is running speed (faster is
higher), not elevation: the route is flat and pace is what the session is about.
The data is embedded, so the page works from a plain file:// open
(only the three.js scripts and fonts are loaded from a CDN).

Usage:  python build_gpx_3d.py [--fragment]
  --fragment  also write gpx_3d_fragment.html without the <html>/<head>/<body>
              wrapper, for hosts that supply their own document skeleton.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
POINTS = pd.read_csv(HERE / "data" / "3_x_5min_processed.csv")
INTERVALS = pd.read_csv(HERE / "data" / "3_x_5min_intervals.csv", index_col=0)
GPX_NAME = "3 x 5min"

# --- project to local meters (east = x, north = y) ---------------------------
lat0 = POINTS.lat.mean()
east = (POINTS.lon - POINTS.lon.iloc[0]).values * 111_320 * np.cos(np.radians(lat0))
north = (POINTS.lat - POINTS.lat.iloc[0]).values * 110_540
phase_names = ["easy"] + list(INTERVALS.index)
phase_idx = POINTS.phase.map({p: i for i, p in enumerate(phase_names)}).fillna(0).astype(int)

pace = POINTS.pace_min_km.replace([np.inf, -np.inf], np.nan).fillna(20).clip(upper=20)

data = {
    "name": GPX_NAME,
    "start": str(POINTS.time.iloc[0]),
    "phases": phase_names,
    "reps": [
        {"name": n, "start": float(r.start_s), "end": float(r.end_s), "startIdx": int(r.start_idx),
         "endIdx": int(r.end_idx), "dist": float(r.distance_m), "pace": float(r.avg_pace_min_km),
         "cad": float(r.avg_cadence_spm)}
        for n, r in INTERVALS.iterrows()
    ],
    # columns: east, north, ele, t, dist, pace, cadence, phase
    "pts": [
        [round(float(e), 1), round(float(n), 1), round(float(z), 1), float(t), round(float(d), 1),
         round(float(p), 2), int(c), int(ph)]
        for e, n, z, t, d, p, c, ph in zip(east, north, POINTS.ele, POINTS.t, POINTS.dist_m, pace,
                                            POINTS.cadence_spm.fillna(0), phase_idx)
    ],
}

HEAD = """<title>3 x 5min in 3D</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap">
<style>
  :root {
    --ground: #1a1a1a;
    --panel: rgba(17, 17, 17, 0.9);
    --panel-edge: #333;
    --text: #ddd;
    --muted: #888;
    --faint: #555;
    --work: #dc143c;
    --easy: #444;
    --pace-slow: #551100;
    --pace-mid: #cc3300;
    --pace-fast: #ffee55;
    --focus: #dc143c;
    --display: "Space Mono", Consolas, "Courier New", monospace;
    --ui: "Space Mono", Consolas, "Courier New", monospace;
  }
  html, body { margin: 0; height: 100%; }
  body {
    background: var(--ground); color: var(--text); font-family: var(--ui); font-size: 12px;
    overflow: hidden; -webkit-font-smoothing: antialiased;
  }
  #scene { position: fixed; inset: 0; display: block; }
  #scene canvas { display: block; }
  .panel {
    position: fixed; background: var(--panel); border: 1px solid var(--panel-edge);
    border-radius: 6px; backdrop-filter: blur(6px); pointer-events: auto;
  }
  #session { top: 16px; left: 16px; padding: 14px 18px 12px; min-width: 250px; }
  #session h1 {
    margin: 0; font-family: var(--display); font-weight: 700; font-size: 22px; line-height: 1.1;
    letter-spacing: -0.01em; text-wrap: balance;
  }
  #session .sub { margin: 6px 0 14px; color: var(--muted); font-size: 11px; }
  .stats { display: grid; grid-template-columns: repeat(3, auto); gap: 10px 22px; }
  .stat .k { color: var(--muted); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; }
  .stat .v {
    font-family: var(--display); font-weight: 700; font-size: 20px; line-height: 1.05;
    font-variant-numeric: tabular-nums; margin-top: 2px;
  }
  .stat .v small { font-size: 11px; color: var(--muted); font-family: var(--ui); margin-left: 3px; font-weight: 500; }
  #phase {
    display: inline-flex; align-items: center; gap: 7px; margin-top: 12px; padding: 3px 10px 3px 7px;
    border-radius: 999px; font-size: 11.5px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
    background: #2a2a2a; color: var(--text);
  }
  #phase::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
  #phase.work { background: rgba(220, 20, 60, 0.18); }
  #phase.work::before { background: var(--work); }

  #reps { top: 16px; right: 16px; padding: 12px 14px; width: 232px; }
  #reps h2, #legend h2 {
    margin: 0 0 8px; font-size: 10.5px; color: var(--muted); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.08em;
  }
  #reps table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  #reps td { padding: 4px 0; border-top: 1px solid var(--panel-edge); font-size: 12.5px; }
  #reps tr:first-child td { border-top: 0; }
  #reps td:first-child { font-weight: 600; }
  #reps td:first-child::before {
    content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 2px;
    background: var(--work); margin-right: 7px; vertical-align: 1px;
  }
  #reps td.n { text-align: right; color: var(--muted); }
  #reps td.n b { color: var(--text); font-weight: 600; }
  #reps tr { cursor: pointer; }
  #reps tr:hover td { color: var(--pace-fast); }

  #legend { right: 16px; top: 158px; padding: 12px 14px; width: 232px; }
  #legend .note { margin: 0 0 10px; color: var(--muted); font-size: 11.5px; line-height: 1.4; }
  .ramp { height: 8px; border-radius: 4px; background: linear-gradient(90deg, var(--pace-slow), var(--pace-mid), var(--pace-fast)); }
  .ramp-l { display: flex; justify-content: space-between; color: var(--muted); font-size: 11px; margin-top: 4px; font-variant-numeric: tabular-nums; }
  .sw { display: flex; gap: 14px; margin-top: 10px; font-size: 11.5px; color: var(--muted); }
  .sw span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; opacity: 0.8; }
  .sw .w::before { background: var(--work); }
  .sw .e::before { background: #666; }

  #bar {
    left: 16px; right: 16px; bottom: 16px; padding: 10px 14px;
    display: grid; grid-template-columns: auto auto 1fr auto auto auto; gap: 14px; align-items: center;
  }
  button, select {
    font: inherit; font-weight: 600; color: var(--text); background: #222; border: 1px solid var(--panel-edge);
    border-radius: 4px; padding: 6px 12px; cursor: pointer;
  }
  button:hover, select:hover { border-color: var(--faint); }
  button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
  button.on { background: var(--work); border-color: var(--work); color: #fff; }
  #play { width: 74px; }
  .clock { font-family: var(--display); font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; min-width: 64px; line-height: 1; }
  .clock small { font-family: var(--ui); font-size: 11px; color: var(--muted); font-weight: 500; }
  #time { width: 100%; }
  input[type=range] { accent-color: var(--work); height: 24px; margin: 0; }
  label.ctl { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 11.5px; white-space: nowrap; }
  label.ctl input[type=range] { width: 90px; }
  label.ctl output { color: var(--text); font-variant-numeric: tabular-nums; min-width: 28px; }
  .seg { display: inline-flex; border: 1px solid var(--panel-edge); border-radius: 4px; overflow: hidden; }
  .seg button { border: 0; border-radius: 0; padding: 6px 10px; }
  .seg button + button { border-left: 1px solid var(--panel-edge); }

  #tip {
    position: fixed; pointer-events: none; display: none; padding: 6px 9px; border-radius: 4px;
    background: var(--panel); border: 1px solid var(--panel-edge); font-size: 11.5px; line-height: 1.5;
    font-variant-numeric: tabular-nums; transform: translate(12px, -50%);
  }
  #tip b { font-family: var(--display); font-size: 14px; font-weight: 700; }
  #hint { position: fixed; left: 50%; bottom: 74px; transform: translateX(-50%); color: var(--faint); font-size: 11px; pointer-events: none; }

  @media (max-width: 860px) {
    #legend, #reps { display: none; }
    #bar { grid-template-columns: auto auto 1fr; }
    #bar .hide-sm { display: none; }
  }
  @media (prefers-reduced-motion: reduce) { .panel { backdrop-filter: none; } }
</style>"""

BODY = """<div id="scene"></div>

<section id="session" class="panel" aria-live="polite">
  <h1 id="title"></h1>
  <div class="sub" id="sub"></div>
  <div class="stats">
    <div class="stat"><div class="k">Distance</div><div class="v"><span id="s-dist">0.00</span><small>km</small></div></div>
    <div class="stat"><div class="k">Pace</div><div class="v"><span id="s-pace">-</span><small>/km</small></div></div>
    <div class="stat"><div class="k">Cadence</div><div class="v"><span id="s-cad">-</span><small>spm</small></div></div>
  </div>
  <div id="phase">Warm-up</div>
</section>

<section id="reps" class="panel">
  <h2>Work intervals</h2>
  <table><tbody id="rep-rows"></tbody></table>
</section>

<section id="legend" class="panel">
  <h2>Height and color: pace</h2>
  <p class="note">Faster is higher. Walking sits near the ground, the 5 min reps rise above it.</p>
  <div class="ramp"></div>
  <div class="ramp-l"><span id="l-slow"></span><span id="l-fast"></span></div>
  <div class="sw"><span class="w">Work curtain</span><span class="e">Easy curtain</span></div>
</section>

<div id="hint">Drag to orbit, wheel to zoom, right-drag to pan. Hover the track for details.</div>

<footer id="bar" class="panel">
  <button id="play" aria-label="Play">Play</button>
  <div class="clock"><span id="clock">0:00</span> <small>/ <span id="total"></span></small></div>
  <input id="time" type="range" min="0" max="1" step="1" value="0" aria-label="Elapsed time">
  <label class="ctl hide-sm">Speed
    <select id="speed" aria-label="Playback speed">
      <option value="1">1x</option><option value="5">5x</option><option value="10" selected>10x</option><option value="30">30x</option>
    </select>
  </label>
  <label class="ctl hide-sm">Height scale <input id="exag" type="range" min="10" max="150" step="5" value="60"><output id="exag-o">60</output></label>
  <div class="seg hide-sm" role="group" aria-label="Camera">
    <button id="cam-orbit" class="on">Overview</button><button id="cam-follow">Follow</button>
  </div>
</footer>
<div id="tip" role="tooltip"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
const DATA = __DATA__;
const P = DATA.pts;                 // [east, north, ele, t, dist, pace, cad, phase]
const N = P.length;
const T_END = P[N - 1][3];
const BASE = 4;                     // scene meters the track floats above the ground at zero speed
const speedOf = i => 1000 / (P[i][5] * 60);   // m/s from pace; the vertical axis is speed, faster is higher

const fmtPace = m => (!isFinite(m) || m <= 0 || m >= 20) ? "-" : `${Math.floor(m)}:${String(Math.round((m % 1) * 60)).padStart(2, "0")}`;
const fmtClock = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Pace color ramp: slow = deep blue, fast = pale blue (light means more on the dark ground).
const workPts = P.filter(p => p[7] > 0).map(p => p[5]);
const PACE_FAST = Math.min(...workPts), PACE_SLOW = 9.0;
// Heat ramp: ember for slow, crimson-orange in the middle, hot yellow for the fastest running.
const RAMP = ["#551100", "#882200", "#cc3300", "#ff8800", "#ffee55"].map(c => new THREE.Color(c));
const cWork = new THREE.Color("#dc143c"), cEasy = new THREE.Color("#3c3c3c");
function paceColor(p) {
  const u = THREE.MathUtils.clamp((PACE_SLOW - p) / (PACE_SLOW - PACE_FAST), 0, 0.9999) * (RAMP.length - 1);
  const k = Math.floor(u);
  return RAMP[k].clone().lerp(RAMP[k + 1], u - k);
}

// --- HUD text ---------------------------------------------------------------
document.getElementById("title").textContent = DATA.name;
const startDate = new Date(DATA.start);
document.getElementById("sub").textContent =
  `${startDate.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })} · ${startDate.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })} · ${(P[N - 1][4] / 1000).toFixed(2)} km in ${fmtClock(T_END)}`;
document.getElementById("total").textContent = fmtClock(T_END);
document.getElementById("l-slow").textContent = fmtPace(PACE_SLOW) + " or slower";
document.getElementById("l-fast").textContent = fmtPace(PACE_FAST) + " /km";
const repRows = document.getElementById("rep-rows");
DATA.reps.forEach(r => {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td>${r.name}</td><td class="n">${(r.dist / 1000).toFixed(2)} km</td><td class="n"><b>${fmtPace(r.pace)}</b> /km</td>`;
  tr.title = "Jump to " + r.name;
  tr.addEventListener("click", () => { setTime(r.start); });
  repRows.appendChild(tr);
});

// --- Scene ------------------------------------------------------------------
const wrap = document.getElementById("scene");
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputEncoding = THREE.sRGBEncoding;
wrap.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color("#1a1a1a");
scene.fog = new THREE.Fog("#1a1a1a", 3500, 9000);

const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 1, 30000);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI / 2 - 0.02;

scene.add(new THREE.HemisphereLight("#e6e6e6", "#1a1a1a", 0.9));
const sun = new THREE.DirectionalLight("#ffffff", 0.7); sun.position.set(-1500, 2200, 1200); scene.add(sun);

// Bounds and ground
const xs = P.map(p => p[0]), zs = P.map(p => -p[1]);
const bb = { x0: Math.min(...xs), x1: Math.max(...xs), z0: Math.min(...zs), z1: Math.max(...zs) };
const cx = (bb.x0 + bb.x1) / 2, cz = (bb.z0 + bb.z1) / 2;
const extent = Math.max(bb.x1 - bb.x0, bb.z1 - bb.z0);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(extent * 6, extent * 6), new THREE.MeshBasicMaterial({ color: "#1e1e1e" }));
ground.rotation.x = -Math.PI / 2; ground.position.set(cx, -0.5, cz); scene.add(ground);
const gridSize = Math.ceil(extent * 2.6 / 500) * 500;
const grid = new THREE.GridHelper(gridSize, gridSize / 100, "#333333", "#262626");
grid.material.transparent = true; grid.material.opacity = 0.6; grid.position.set(cx, 0, cz); scene.add(grid);

// Scale bar: 500 m on the ground, south-west corner
(function scaleBar() {
  const y = 0.6, x0 = bb.x0, z = bb.z1 + extent * 0.08;
  const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x0, y, z), new THREE.Vector3(x0 + 500, y, z),
    new THREE.Vector3(x0, y, z - 20), new THREE.Vector3(x0, y, z + 20), new THREE.Vector3(x0 + 500, y, z - 20), new THREE.Vector3(x0 + 500, y, z + 20)]);
  scene.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: "#888888" })));
  scene.add(label("500 m", new THREE.Vector3(x0 + 250, 18, z + 40), 0.6, "#888888"));
})();

// Text label sprite
function label(text, pos, scale = 1, color = "#dddddd") {
  const c = document.createElement("canvas"); c.width = 512; c.height = 128;
  const ctx = c.getContext("2d");
  ctx.font = "700 52px 'Space Mono', Consolas, monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillStyle = color; ctx.fillText(text, 256, 64);
  const tex = new THREE.CanvasTexture(c); tex.minFilter = THREE.LinearFilter;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  s.scale.set(320 * scale, 80 * scale, 1); s.position.copy(pos); return s;
}

// Track geometry, rebuilt when the relief slider moves
let exag = 60;
const trackGroup = new THREE.Group(); scene.add(trackGroup);
const heightOf = i => BASE + speedOf(i) * exag;
const posOf = i => new THREE.Vector3(P[i][0], heightOf(i), -P[i][1]);

function buildTrack() {
  trackGroup.clear();
  const pts = P.map((_, i) => posOf(i));

  // Curtain: wall from ground to the track, colored by phase
  const cv = new Float32Array((N - 1) * 6 * 3), cc = new Float32Array((N - 1) * 6 * 3);
  for (let i = 0; i < N - 1; i++) {
    const a = pts[i], b = pts[i + 1];
    const quad = [a.x, 0, a.z, a.x, a.y, a.z, b.x, b.y, b.z, a.x, 0, a.z, b.x, b.y, b.z, b.x, 0, b.z];
    cv.set(quad, i * 18);
    const col = P[i][7] > 0 ? cWork : cEasy;
    for (let k = 0; k < 6; k++) cc.set([col.r, col.g, col.b], i * 18 + k * 3);
  }
  const cg = new THREE.BufferGeometry();
  cg.setAttribute("position", new THREE.BufferAttribute(cv, 3));
  cg.setAttribute("color", new THREE.BufferAttribute(cc, 3));
  trackGroup.add(new THREE.Mesh(cg, new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.28, side: THREE.DoubleSide, depthWrite: false })));

  // Ground shadow of the route
  const shadow = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(p => new THREE.Vector3(p.x, 0.3, p.z))),
    new THREE.LineBasicMaterial({ color: "#3a3a3a" }));
  trackGroup.add(shadow);

  // Tube, colored by pace
  const curve = new THREE.CatmullRomCurve3(pts, false, "catmullrom", 0.1);
  const radial = 6, segs = N - 1;
  const tube = new THREE.TubeGeometry(curve, segs, extent * 0.0016, radial, false);
  const colors = new Float32Array(tube.attributes.position.count * 3);
  for (let v = 0; v < tube.attributes.position.count; v++) {
    const seg = Math.floor(v / (radial + 1));
    const i = Math.min(N - 1, Math.round(seg / segs * (N - 1)));
    const col = paceColor(P[i][5]);
    colors.set([col.r, col.g, col.b], v * 3);
  }
  tube.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const tubeMesh = new THREE.Mesh(tube, new THREE.MeshLambertMaterial({ vertexColors: true, emissive: "#000000" }));
  tubeMesh.name = "tube"; tubeMesh.userData.segs = segs; trackGroup.add(tubeMesh);

  // Rep labels above the midpoint of each rep
  DATA.reps.forEach((r, k) => {
    const mid = Math.round((r.startIdx + r.endIdx) / 2);
    const p = posOf(mid); p.y += extent * (0.04 + 0.03 * k);   // stagger so parallel reps do not collide
    trackGroup.add(label(`${r.name}  ${fmtPace(r.pace)}`, p, 0.9));
    const stem = new THREE.Line(new THREE.BufferGeometry().setFromPoints([posOf(mid), new THREE.Vector3(p.x, p.y - extent * 0.015, p.z)]),
      new THREE.LineBasicMaterial({ color: "#555555" }));
    trackGroup.add(stem);
  });

  // Start and finish markers
  trackGroup.add(label("Start", posOf(0).add(new THREE.Vector3(0, extent * 0.02, 0)), 0.55, "#888888"));
  trackGroup.add(label("Finish", posOf(N - 1).add(new THREE.Vector3(0, extent * 0.02, 0)), 0.55, "#888888"));
}
buildTrack();

// Runner marker
const runner = new THREE.Group();
const rBall = new THREE.Mesh(new THREE.SphereGeometry(extent * 0.004, 20, 14), new THREE.MeshLambertMaterial({ color: "#ffffff", emissive: "#dc143c", emissiveIntensity: 0.7 }));
const rRing = new THREE.Mesh(new THREE.RingGeometry(extent * 0.006, extent * 0.0085, 40), new THREE.MeshBasicMaterial({ color: "#dc143c", side: THREE.DoubleSide, transparent: true, opacity: 0.85 }));
rRing.rotation.x = -Math.PI / 2;
const rStem = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3(0, 1, 0)]), new THREE.LineBasicMaterial({ color: "#dc143c" }));
runner.add(rBall, rRing, rStem); scene.add(runner);

// Camera fit
function fitCamera() {
  controls.target.set(cx, 0, cz);
  camera.position.set(cx + extent * 0.55, extent * 0.5, cz + extent * 0.75);
  controls.update();
}
fitCamera();

// --- Playback ---------------------------------------------------------------
let t = 0, playing = false, speed = 10, follow = false, idx = 0;
const playBtn = document.getElementById("play"), timeEl = document.getElementById("time");
timeEl.max = T_END;

function indexAt(time) {           // largest i with P[i].t <= time
  let lo = 0, hi = N - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (P[m][3] <= time) lo = m; else hi = m - 1; }
  return lo;
}
function stateAt(time) {
  const i = indexAt(time), j = Math.min(N - 1, i + 1);
  const span = P[j][3] - P[i][3] || 1, f = THREE.MathUtils.clamp((time - P[i][3]) / span, 0, 1);
  const a = posOf(i), b = posOf(j);
  return { i, pos: a.lerp(b, f), dist: P[i][4] + (P[j][4] - P[i][4]) * f, pace: P[i][5], cad: P[i][6], phase: P[i][7] };
}
const phaseEl = document.getElementById("phase");
function setTime(newT, fromSlider = false) {
  t = THREE.MathUtils.clamp(newT, 0, T_END);
  const s = stateAt(t); idx = s.i;
  runner.position.copy(s.pos);
  rRing.position.y = -s.pos.y + 0.4;
  rStem.scale.y = -s.pos.y;
  document.getElementById("clock").textContent = fmtClock(t);
  document.getElementById("s-dist").textContent = (s.dist / 1000).toFixed(2);
  document.getElementById("s-pace").textContent = fmtPace(s.pace);
  document.getElementById("s-cad").textContent = s.cad > 0 ? Math.round(s.cad) : "-";
  const work = s.phase > 0;
  phaseEl.textContent = work ? DATA.phases[s.phase] : (t < DATA.reps[0].start ? "Warm-up" : (t > DATA.reps[DATA.reps.length - 1].end ? "Cool-down" : "Recovery"));
  phaseEl.classList.toggle("work", work);
  if (!fromSlider) timeEl.value = t;
}
function setPlaying(v) {
  playing = v; playBtn.textContent = v ? "Pause" : "Play";
  playBtn.setAttribute("aria-label", v ? "Pause" : "Play");
}
playBtn.addEventListener("click", () => { if (t >= T_END) setTime(0); setPlaying(!playing); });
timeEl.addEventListener("input", e => setTime(+e.target.value, true));
document.getElementById("speed").addEventListener("change", e => speed = +e.target.value);
document.getElementById("exag").addEventListener("input", e => {
  exag = +e.target.value; document.getElementById("exag-o").textContent = exag; buildTrack(); setTime(t);
});
const camO = document.getElementById("cam-orbit"), camF = document.getElementById("cam-follow");
function setFollow(v) { follow = v; camO.classList.toggle("on", !v); camF.classList.toggle("on", v); if (!v) fitCamera(); else { controls.target.copy(runner.position); const dir = camera.position.clone().sub(controls.target).setLength(extent * 0.16); camera.position.copy(controls.target).add(dir); } }
camO.addEventListener("click", () => setFollow(false));
camF.addEventListener("click", () => setFollow(true));
addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.code === "Space") { e.preventDefault(); playBtn.click(); }
  if (e.key === "ArrowRight") setTime(t + 10);
  if (e.key === "ArrowLeft") setTime(t - 10);
  if (e.key.toLowerCase() === "f") setFollow(!follow);
});

// Hover tooltip on the tube
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(); const tip = document.getElementById("tip");
let hoverPending = null;
renderer.domElement.addEventListener("pointermove", e => { hoverPending = e; });
renderer.domElement.addEventListener("pointerleave", () => { tip.style.display = "none"; hoverPending = null; });
function doHover(e) {
  mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const tube = trackGroup.getObjectByName("tube");
  const hit = ray.intersectObject(tube, false)[0];
  if (!hit) { tip.style.display = "none"; return; }
  const seg = Math.floor(hit.faceIndex / (2 * 6));
  const i = Math.min(N - 1, Math.round(seg / tube.userData.segs * (N - 1)));
  const p = P[i];
  tip.innerHTML = `<b>${fmtPace(p[5])}</b> /km<br>${fmtClock(p[3])} · ${(p[4] / 1000).toFixed(2)} km · ${p[6] || "-"} spm<br>${p[2].toFixed(1)} m elevation · ${p[7] > 0 ? DATA.phases[p[7]] : "easy"}`;
  tip.style.left = e.clientX + "px"; tip.style.top = e.clientY + "px"; tip.style.display = "block";
}

// --- Loop -------------------------------------------------------------------
let last = performance.now();
function frame(now) {
  const dt = (now - last) / 1000; last = now;
  if (playing) { setTime(t + dt * speed); if (t >= T_END) setPlaying(false); }
  if (follow) {
    const prev = controls.target.clone(); controls.target.lerp(runner.position, 0.15);
    camera.position.add(controls.target.clone().sub(prev));
  }
  if (hoverPending) { doHover(hoverPending); hoverPending = null; }
  rRing.rotation.z += dt * 0.8;
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
addEventListener("resize", () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
setTime(0);
if (!reduceMotion) setPlaying(true);
requestAnimationFrame(frame);
</script>"""

fragment = HEAD + "\n" + BODY.replace("__DATA__", json.dumps(data, separators=(",", ":")))
full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + HEAD + "\n</head>\n<body>\n" + BODY.replace("__DATA__", json.dumps(data, separators=(",", ":")))
        + "\n</body>\n</html>\n")

(HERE / "index.html").write_text(full, encoding="utf-8")
print(f"wrote index.html ({len(full)/1024:.0f} KB, {len(data['pts'])} points)")
if "--fragment" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--fragment") + 1]) if len(sys.argv) > sys.argv.index("--fragment") + 1 else HERE / "gpx_3d_fragment.html"
    out.write_text(fragment, encoding="utf-8")
    print("wrote", out)
