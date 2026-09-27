// 3D-вид исследования: схематичный скелет (Th12–L5, крестец, таз, проксимальные бёдра) на подиуме.
// Области окрашены по вердикту проверки; выноски — HTML-элементы шаблона, линии к ним пересчитываются каждый кадр.
// Единицы — сантиметры, y вверх, пациент смотрит на камеру (+z), его левая сторона — +x (справа на экране).
import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/three/OrbitControls.js';

const root = document.getElementById('b3d');
const holder = document.getElementById('b3dCanvas');
const svg = document.getElementById('b3dLines');
const data = JSON.parse(document.getElementById('b3dData').textContent);
const R = data.regions;

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
} catch (e) {
  document.getElementById('b3dNoGL').hidden = false;
  document.getElementById('b3dHint').hidden = true;
  throw e;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
holder.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 1, 600);
const TARGET = new THREE.Vector3(0, 2, 0);
const VIEW = new THREE.Vector3(0, 0.06, 1).normalize();   // чуть сверху, спереди
camera.position.copy(TARGET).addScaledVector(VIEW, 165);

scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x1b2130, 1.25));
const key = new THREE.DirectionalLight(0xffffff, 2.4); key.position.set(30, 50, 60); scene.add(key);
const rim = new THREE.DirectionalLight(0x7fb3ff, 1.6); rim.position.set(-40, 20, -50); scene.add(rim);
const fill = new THREE.DirectionalLight(0xffe2c8, 0.5); fill.position.set(-30, -20, 40); scene.add(fill);

// ---------------------------------------------------------------- материалы
const COLORS = { bad: 0xff3a3a, spot: 0xffb020, ok: 0x6be39a };
function boneMat(status) {
  const m = new THREE.MeshPhysicalMaterial({ color: 0xe9edf2, roughness: 0.38, metalness: 0.02, clearcoat: 0.55, clearcoatRoughness: 0.35 });
  if (status === 'bad') {
    m.color.set(0xff4a4a); m.emissive.set(0x7a0000); m.emissiveIntensity = 0.55; m.transparent = true; m.opacity = 0.92;
  } else if (status === 'absent' || status === 'na') {
    m.transparent = true; m.opacity = 0.2; m.depthWrite = false;
  }
  return m;
}
const neutral = boneMat('ok');
const pulsing = [];                                   // материалы, которые мягко пульсируют: нарушения и предметы
const regionMeshes = { lumbar_spine: [], hip_left: [], hip_right: [] };
const matFor = {};
for (const reg of Object.keys(regionMeshes)) {
  matFor[reg] = boneMat(R[reg].status);
  if (R[reg].status === 'bad') pulsing.push(matFor[reg]);
}

function add(parent, geo, mat, reg, pos, rot, scale) {
  const m = new THREE.Mesh(geo, mat);
  if (pos) m.position.set(...pos);
  if (rot) m.rotation.set(...rot);
  if (scale) m.scale.set(...scale);
  if (reg) { m.userData.region = reg; regionMeshes[reg].push(m); }
  parent.add(m);
  return m;
}

const body = new THREE.Group();
scene.add(body);

// ---------------------------------------------------------------- позвоночник Th12–L5
const LEVELS = ['L5', 'L4', 'L3', 'L2', 'L1', 'Th12'];
const H = 2.6, GAP = 0.75, Y0 = 1.7;
const levelY = (i) => Y0 + i * (H + GAP);
const spine = new THREE.Group();
body.add(spine);
const sMat = matFor.lumbar_spine;
const discMat = new THREE.MeshPhysicalMaterial({ color: 0x9fc4ff, roughness: 0.2, transmission: 0.3, transparent: true, opacity: 0.55 });
LEVELS.forEach((name, i) => {
  const y = levelY(i);
  const w = name === 'Th12' ? 0.86 : 1 + 0.05 * (4 - Math.abs(i - 2));   // поясничные шире грудного
  const v = new THREE.Group(); v.position.y = y; spine.add(v);
  add(v, new THREE.CylinderGeometry(2.05, 2.15, H, 36), sMat, 'lumbar_spine', [0, 0, 0], null, [1.35 * w, 1, 1]);
  add(v, new THREE.BoxGeometry(0.9, 1.2, 3.6), sMat, 'lumbar_spine', [0, -0.35, -3.9], [0.35, 0, 0]);           // остистый
  for (const s of [-1, 1]) {
    add(v, new THREE.BoxGeometry(4.2 * w, 0.75, 0.9), sMat, 'lumbar_spine', [s * 3.9 * w, 0.1, -1.7], [0, 0, s * 0.08]); // поперечный
    add(v, new THREE.CylinderGeometry(0.55, 0.55, 2.2, 12), sMat, 'lumbar_spine', [s * 1.35, 0.2, -2.2], [Math.PI / 2, 0, 0]); // ножка дуги
  }
  if (i < LEVELS.length - 1) add(spine, new THREE.CylinderGeometry(2.0, 2.0, GAP * 0.9, 32), discMat, null, [0, y + H / 2 + GAP / 2, 0], null, [1.35 * w, 1, 1]);
});
const spineTop = levelY(LEVELS.length - 1) + H / 2;

// ось столба: измеренный угол, серой пунктирной линией — вертикаль
const sp = R.lumbar_spine;
const hasSpine = sp.status !== 'absent';
const angle = hasSpine ? (sp.angle || 0) : 0;
spine.rotation.z = -THREE.MathUtils.degToRad(angle);
if (hasSpine) {
  const axisMat = new THREE.LineBasicMaterial({ color: sp.axis_bad ? COLORS.bad : COLORS.ok });
  const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, -1.5, 3), new THREE.Vector3(0, spineTop + 3, 3)]);
  spine.add(new THREE.Line(g, axisMat));
  const vg = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, -1.5, 3.05), new THREE.Vector3(0, spineTop + 3, 3.05)]);
  const vl = new THREE.Line(vg, new THREE.LineDashedMaterial({ color: 0x8190a8, dashSize: 0.8, gapSize: 0.6 }));
  vl.computeLineDistances(); body.add(vl);
}

// ---------------------------------------------------------------- крестец и таз
add(body, new THREE.CylinderGeometry(3.9, 1.1, 10, 28), neutral, null, [0, -5.2, -0.6], [-0.28, 0, 0], [1, 1, 0.55]);
const crestMat = hasSpine && sp.coverage_bad ? boneMat('bad') : neutral;
if (crestMat !== neutral) pulsing.push(crestMat);
for (const s of [-1, 1]) {
  // крыло подвздошной кости и его гребень (граница охвата снимка позвоночника)
  add(body, new THREE.SphereGeometry(1, 40, 28), neutral, null, [s * 8.4, -2.4, -1.4], [0.12, s * 0.95, s * -0.2], [6.4, 7.2, 1.6]);
  add(body, new THREE.TorusGeometry(6.4, 0.55, 12, 40, Math.PI * 0.95), crestMat, null, [s * 8.4, -2.8, -1.4], [0.12, s * 0.95, s * -0.2 + 0.08]);
  // вертлужная впадина, седалищная и лобковая кости — кольцо запирательного отверстия
  add(body, new THREE.SphereGeometry(3.0, 28, 20, 0, Math.PI * 2, 0, Math.PI / 2), neutral, null, [s * 9.6, -9.6, 1.2], [0, 0, s * -1.3]);
  add(body, new THREE.TorusGeometry(3.6, 1.05, 14, 36), neutral, null, [s * 5.4, -13.4, 2.4], [-0.35, s * 0.35, 0]);
}
add(body, new THREE.CapsuleGeometry(0.9, 2.6, 6, 12), neutral, null, [0, -13.4, 4.2]);   // лобковый симфиз

// ---------------------------------------------------------------- бёдра
const femurs = {};
for (const [reg, s] of [['hip_left', 1], ['hip_right', -1]]) {
  const d = R[reg];
  const mat = matFor[reg];
  const f = new THREE.Group(); f.position.set(s * 9.6, -9.6, 1.2); body.add(f); femurs[reg] = f;
  add(f, new THREE.SphereGeometry(2.45, 32, 24), mat, reg);                                                   // головка
  add(f, new THREE.CylinderGeometry(1.45, 1.75, 5.6, 24), mat, reg, [s * 2.6, -1.9, 0], [0, 0, s * 0.95]);    // шейка
  add(f, new THREE.SphereGeometry(1, 28, 20), mat, reg, [s * 5.6, -2.0, -0.6], null, [2.5, 3.4, 2.5]);           // большой вертел
  add(f, new THREE.SphereGeometry(1.05, 20, 14), mat, reg, [s * 3.2, -6.0, -1.2]);                              // малый вертел
  add(f, new THREE.CylinderGeometry(1.55, 1.35, 25, 28), mat, reg, [s * 3.7, -16.8, 0], [0, 0, s * -0.1]);     // диафиз
  add(f, new THREE.SphereGeometry(1.35, 20, 14), mat, reg, [s * 2.45, -29.2, 0]);                               // срез диафиза
  if (d.status !== 'absent' && d.positioning) f.rotation.y = s * 0.35;          // нарушение укладки: бедро развёрнуто
  if (d.status !== 'absent' && d.roi) {                                           // поля зоны интереса: рамка вокруг проксимального бедра
    const box = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(12, 14, 8)),
      new THREE.LineBasicMaterial({ color: COLORS.bad }));
    box.position.set(s * 3.2, -4.5, 0); f.add(box);
  }
}

// ---------------------------------------------------------------- найденные предметы: из долей кадра в сантиметры
if (hasSpine && sp.spots && sp.spots.length && sp.levels) {
  const lv = sp.levels;
  const known = LEVELS.map((n, i) => lv[n] ? { i, u: lv[n][0], v: lv[n][1] } : null).filter(Boolean);
  if (known.length >= 2) {
    const a = known[0], b = known[known.length - 1];
    const cmPerV = (levelY(b.i) - levelY(a.i)) / (a.v - b.v);   // v растёт вниз, y — вверх
    const uc = known.reduce((t, k) => t + k.u, 0) / known.length;
    const spotMat = new THREE.MeshStandardMaterial({ color: COLORS.spot, emissive: 0xff7a00, emissiveIntensity: 0.8 });
    pulsing.push(spotMat);
    for (const [u, v] of sp.spots) {
      const x = THREE.MathUtils.clamp((u - uc) * (sp.aspect || 1) * cmPerV, -16, 16);
      const y = THREE.MathUtils.clamp(levelY(a.i) + (a.v - v) * cmPerV, -14, spineTop + 6);
      const m = add(spine, new THREE.OctahedronGeometry(0.9, 1), spotMat, null, [x, y, 3.6]);
      m.userData.spot = true;
    }
  }
}

// ---------------------------------------------------------------- подиум
const floorY = -42;
const disc = new THREE.Mesh(new THREE.CircleGeometry(30, 72), new THREE.MeshStandardMaterial({ color: 0x1a2233, roughness: 0.9, transparent: true, opacity: 0.9 }));
disc.rotation.x = -Math.PI / 2; disc.position.y = floorY; scene.add(disc);
const ring = new THREE.Mesh(new THREE.TorusGeometry(30, 0.22, 8, 120), new THREE.MeshBasicMaterial({ color: 0x9cc4ff }));
ring.rotation.x = -Math.PI / 2; ring.position.y = floorY; scene.add(ring);
const glow = new THREE.Mesh(new THREE.RingGeometry(30.4, 34, 96), new THREE.MeshBasicMaterial({ color: 0x4f7fd0, transparent: true, opacity: 0.18, side: THREE.DoubleSide }));
glow.rotation.x = -Math.PI / 2; glow.position.y = floorY - 0.05; scene.add(glow);
function sideLabel(text, x) {                        // «П» и «Л» пациента на подиуме
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'); g.fillStyle = '#9cc4ff'; g.font = '600 84px system-ui, sans-serif';
  g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, 64, 70);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(5, 5), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true }));
  m.rotation.x = -Math.PI / 2; m.position.set(x, floorY + 0.1, 18); body.add(m);
}
sideLabel('П', -22); sideLabel('Л', 22);
body.position.y = 8;                                  // скелет по центру кадра над подиумом
disc.position.y = ring.position.y = floorY + 8; glow.position.y = floorY + 7.95;

// ---------------------------------------------------------------- управление
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.copy(TARGET);
controls.enableDamping = true; controls.enablePan = false;
controls.minDistance = 60; controls.maxDistance = 240;
controls.minPolarAngle = 0.35; controls.maxPolarAngle = 1.75;
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
controls.autoRotate = !reduce; controls.autoRotateSpeed = 1.1;
let idleTimer;
controls.addEventListener('start', () => { controls.autoRotate = false; clearTimeout(idleTimer); });
controls.addEventListener('end', () => { clearTimeout(idleTimer); if (!reduce) idleTimer = setTimeout(() => { controls.autoRotate = true; }, 7000); });

// нажатие на область — карточка её снимка
const ray = new THREE.Raycaster(); const ptr = new THREE.Vector2(); let down = null;
renderer.domElement.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', (e) => {
  if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return;
  const r = renderer.domElement.getBoundingClientRect();
  ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ptr, camera);
  const hit = ray.intersectObjects(Object.values(regionMeshes).flat(), false)[0];
  const reg = hit && hit.object.userData.region;
  if (reg && R[reg].card) window.location.href = R[reg].card;
});

// ---------------------------------------------------------------- выноски
const tags = [...root.querySelectorAll('.b3d-tag')];
const anchors = {
  lumbar_spine: () => spine.localToWorld(new THREE.Vector3(2.8, levelY(3), 1.5)),
  hip_left: () => femurs.hip_left.localToWorld(new THREE.Vector3(5.8, -2.4, 1.6)),
  hip_right: () => femurs.hip_right.localToWorld(new THREE.Vector3(-5.8, -2.4, 1.6)),
};
const lineColor = { bad: '#ff5a5a', ok: '#dfe6f0', na: '#7d8799', absent: '#5d6677' };
svg.innerHTML = tags.map(() => '<polyline/><circle r="3.2"/>').join('');
function drawLines() {
  if (getComputedStyle(svg).display === 'none') return;
  const box = root.getBoundingClientRect();
  tags.forEach((tag, i) => {
    const reg = tag.dataset.region;
    const p = anchors[reg]().project(camera);
    const ax = (p.x + 1) / 2 * box.width, ay = (1 - p.y) / 2 * box.height;
    const t = tag.getBoundingClientRect();
    const y = t.bottom - box.top;
    let sx, kx;
    if (tag.classList.contains('left') || tag.classList.contains('tl')) { sx = t.right - box.left; kx = sx + 18; }
    else if (tag.classList.contains('right')) { sx = t.left - box.left; kx = sx - 18; }
    else { sx = kx = t.left - box.left + t.width / 2; }
    const pl = svg.children[i * 2], c = svg.children[i * 2 + 1];
    const col = lineColor[R[reg].status] || '#ccc';
    pl.setAttribute('points', tag.classList.contains('top') ? `${sx},${y} ${sx},${y + 14} ${ax},${ay}` : `${sx},${y} ${kx},${y} ${ax},${ay}`);
    pl.setAttribute('stroke', col); pl.setAttribute('opacity', R[reg].status === 'absent' ? 0.5 : 0.9);
    c.setAttribute('cx', ax); c.setAttribute('cy', ay); c.setAttribute('fill', col);
  });
}

function resize() {
  const w = holder.clientWidth, h = holder.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  const dist = w < 560 ? 150 : h < 560 ? 185 : 165;   // выноски сверху не должны закрывать позвоночник
  const dir = camera.position.clone().sub(controls.target).normalize();
  camera.position.copy(controls.target).addScaledVector(dir, dist);
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(holder);
resize();

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const t = clock.getElapsedTime();
  const k = 0.5 + 0.5 * Math.sin(t * 2.6);
  for (const m of pulsing) m.emissiveIntensity = 0.35 + 0.5 * k;
  controls.update();
  renderer.render(scene, camera);
  drawLines();
});
root.dataset.ready = '1';                             // для e2e-проверки: сцена построена
