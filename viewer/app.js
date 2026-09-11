// interval-analysis 3D viewer. Expects a global DATA (written by viewer.py into data.js):
//   DATA.pts  rows of [east_m, north_m, ele_m, t_s, dist_m, pace_min_km, cadence_spm, phase_idx]
//   DATA.reps detected work intervals, DATA.phases names, DATA.map optional ground texture.
// Vertical axis is speed (faster is higher); color is a heat ramp over pace.
const P = DATA.pts;                 // [east, north, ele, t, dist, pace, cad, phase]
const N = P.length;
const T_END = P[N - 1][3];
const BASE = 4;                     // scene meters the track floats above the ground at zero speed
const speedOf = i => 1000 / (P[i][5] * 60);   // m/s from pace; the vertical axis is speed, faster is higher

const fmtPace = m => (!isFinite(m) || m <= 0 || m >= 20) ? "-" : `${Math.floor(m)}:${String(Math.round((m % 1) * 60)).padStart(2, "0")}`;
const fmtClock = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Fast end of the ramp: fastest smoothed pace inside the reps (or the whole run if none were found).
const workPts = DATA.reps.length ? P.filter(p => p[7] > 0).map(p => p[5]) : P.map(p => p[5]);
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
// Logarithmic depth: the scene spans kilometers with surfaces a few cm apart (map, grid,
// curtain feet), which z-fights with a linear depth buffer.
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, logarithmicDepthBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
wrap.appendChild(renderer.domElement);

const scene = new THREE.Scene();
// Scene colors are read from style.css so the tokens there drive the 3D view too.
const cssTok = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
scene.background = new THREE.Color(cssTok("--ground"));
scene.fog = new THREE.Fog(cssTok("--ground"), 3500, 9000);

const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 5, 30000);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI / 2 - 0.02;

scene.add(new THREE.HemisphereLight("#e6e6e6", cssTok("--ground"), 0.9));
const sun = new THREE.DirectionalLight("#ffffff", 0.7); sun.position.set(-1500, 2200, 1200); scene.add(sun);

// Bounds and ground
const xs = P.map(p => p[0]), zs = P.map(p => -p[1]);
const bb = { x0: Math.min(...xs), x1: Math.max(...xs), z0: Math.min(...zs), z1: Math.max(...zs) };
const cx = (bb.x0 + bb.x1) / 2, cz = (bb.z0 + bb.z1) / 2;
const extent = Math.max(bb.x1 - bb.x0, bb.z1 - bb.z0);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(extent * 6, extent * 6), new THREE.MeshBasicMaterial({ color: cssTok("--plane") }));
ground.rotation.x = -Math.PI / 2; ground.position.set(cx, -0.5, cz); scene.add(ground);
const gridSize = Math.ceil(extent * 2.6 / 500) * 500;
const grid = new THREE.GridHelper(gridSize, gridSize / 100, cssTok("--grid-major"), cssTok("--grid-minor"));
grid.material.transparent = true; grid.material.opacity = 0.6; grid.position.set(cx, 0, cz); scene.add(grid);

// OpenStreetMap ground texture, placed with the same projection as the track (north = -z).
let mapMesh = null;
const mapBtn = document.getElementById("map-btn");
if (DATA.map) {
  const m = DATA.map;
  const tex = new THREE.TextureLoader().load(m.uri);
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  mapMesh = new THREE.Mesh(new THREE.PlaneGeometry(m.x1 - m.x0, m.n1 - m.n0), new THREE.MeshBasicMaterial({ map: tex }));
  mapMesh.rotation.x = -Math.PI / 2;                       // image top (north) ends up at -z
  mapMesh.position.set((m.x0 + m.x1) / 2, 0.05, -(m.n0 + m.n1) / 2);
  scene.add(mapMesh);
  grid.visible = false;
  mapBtn.hidden = false; document.getElementById("attrib").hidden = false;
}
function setMap(v) {
  if (!mapMesh) return;
  mapMesh.visible = v; grid.visible = !v;
  mapBtn.classList.toggle("on", v); mapBtn.setAttribute("aria-pressed", v);
}
mapBtn.addEventListener("click", () => setMap(!mapMesh.visible));

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
  // TubeGeometry samples the curve evenly by arc length, not by point index, and the
  // GPS points are denser when running slowly. Map each tube segment back to the track
  // point through cumulative path length so color and height agree at every location.
  const cum = new Float64Array(N);
  for (let i = 1; i < N; i++) cum[i] = cum[i - 1] + pts[i].distanceTo(pts[i - 1]);
  const total = cum[N - 1];
  const idxAtLength = d => {           // largest i with cum[i] <= d
    let lo = 0, hi = N - 1;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (cum[m] <= d) lo = m; else hi = m - 1; }
    return lo;
  };
  const curve = new THREE.CatmullRomCurve3(pts, false, "catmullrom", 0.1);
  curve.arcLengthDivisions = N * 2;  // accurate arc-length parameterization (default is 200)
  const radial = 6, segs = N - 1;
  const tube = new THREE.TubeGeometry(curve, segs, extent * 0.0016, radial, false);
  const colors = new Float32Array(tube.attributes.position.count * 3);
  for (let v = 0; v < tube.attributes.position.count; v++) {
    const seg = Math.floor(v / (radial + 1));
    const i = idxAtLength(seg / segs * total);
    const col = paceColor(P[i][5]);
    colors.set([col.r, col.g, col.b], v * 3);
  }
  tube.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  // Unlit material: the vertex color is the data, so no shading may alter it.
  const tubeMesh = new THREE.Mesh(tube, new THREE.MeshBasicMaterial({ vertexColors: true }));
  tubeMesh.name = "tube"; tubeMesh.userData.segs = segs; tubeMesh.userData.idxAtLength = idxAtLength; tubeMesh.userData.total = total;
  trackGroup.add(tubeMesh);

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
  const reps = DATA.reps;
  phaseEl.textContent = work ? DATA.phases[s.phase]
    : !reps.length ? "Easy" : (t < reps[0].start ? "Warm-up" : (t > reps[reps.length - 1].end ? "Cool-down" : "Recovery"));
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
  if (e.key.toLowerCase() === "m") setMap(!(mapMesh && mapMesh.visible));
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
  const i = tube.userData.idxAtLength(seg / tube.userData.segs * tube.userData.total);
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
