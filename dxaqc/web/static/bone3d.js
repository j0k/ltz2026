// Модель таза и тазобедренных суставов (главная): белый фон, белая кость с запечённым затенением, студийный свет,
// медленное вращение. Сетка — static/bone/pelvis.bin.gz (scripts/make_bone_mesh.py), сжатие снимает браузер.
import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/three/OrbitControls.js';

const box = document.getElementById('bone3d');
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

async function loadMesh(url) {
  const res = await fetch(url);
  let buf;
  if ('DecompressionStream' in window) buf = await new Response(res.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  else throw new Error('браузер не умеет распаковывать gzip');
  const dv = new DataView(buf);
  const nv = dv.getUint32(4, true), nf = dv.getUint32(8, true);
  const lo = [0, 1, 2].map(i => dv.getFloat32(12 + i * 4, true)), hi = [0, 1, 2].map(i => dv.getFloat32(24 + i * 4, true));
  let off = 36;
  const q = new Uint16Array(buf, off, nv * 3); off += nv * 6;
  const n = new Int8Array(buf, off, nv * 3); off += nv * 3;
  const ao = new Uint8Array(buf, off, nv); off += nv;
  off = Math.ceil(off / 4) * 4 === off ? off : off;               // индексы идут сразу за затенением
  const idx = new Uint32Array(buf.slice(off, off + nf * 12));
  const pos = new Float32Array(nv * 3), col = new Float32Array(nv * 3);
  const base = new THREE.Color(0xf3efe7);
  for (let i = 0; i < nv; i++) {
    for (let k = 0; k < 3; k++) pos[i * 3 + k] = lo[k] + q[i * 3 + k] / 65535 * (hi[k] - lo[k]);
    const a = 0.30 + 0.70 * Math.pow(ao[i] / 255, 1.1);                            // складки и поры — мягко-серые
    col[i * 3] = base.r * a; col[i * 3 + 1] = base.g * a; col[i * 3 + 2] = base.b * a;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(n).map(v => v / 127), 3));
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  return g;
}

(async () => {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.08;
  box.appendChild(renderer.domElement);
  renderer.domElement.className = 'k-bone-canvas';
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(28, 1, 10, 4000);
  // мягкий студийный свет: верхний рассеянный, ключевой, заполняющий, контровой
  scene.add(new THREE.HemisphereLight(0xffffff, 0xcfd0d4, 0.85));
  const key = new THREE.DirectionalLight(0xffffff, 2.3); key.position.set(-320, 520, 460); scene.add(key);
  const fill = new THREE.DirectionalLight(0xfff4ea, 0.45); fill.position.set(460, 80, 260); scene.add(fill);
  const rim = new THREE.DirectionalLight(0xffffff, 0.7); rim.position.set(0, 260, -520); scene.add(rim);
  const geo = await loadMesh('/static/bone/pelvis.bin.gz?v=' + (box.dataset.v || '1'));
  geo.computeBoundingBox();
  const c = geo.boundingBox.getCenter(new THREE.Vector3()), size = geo.boundingBox.getSize(new THREE.Vector3());
  geo.translate(-c.x, -c.y, -c.z);
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.62, metalness: 0.0 });
  const mesh = new THREE.Mesh(geo, mat);
  scene.add(mesh);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.enablePan = false;
  controls.autoRotate = !reduce; controls.autoRotateSpeed = 0.7;
  controls.minDistance = size.length() * 0.6; controls.maxDistance = size.length() * 3;
  let idle;
  controls.addEventListener('start', () => { controls.autoRotate = false; clearTimeout(idle); });
  controls.addEventListener('end', () => { if (!reduce) idle = setTimeout(() => controls.autoRotate = true, 5000); });
  function resize() {
    const w = box.clientWidth, h = box.clientHeight; if (!w || !h) return;
    renderer.setSize(w, h, false); camera.aspect = w / h;
    const fit = Math.max(size.y, size.x / camera.aspect) / 2 / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    camera.position.set(0, size.y * 0.06, fit * 1.18); controls.target.set(0, 0, 0);
    if (box.dataset.focus) {                       // крупный план для проверки: data-focus="x,y,z,расстояние" в мм модели
      const [fx, fy, fz, fd] = box.dataset.focus.split(',').map(Number);
      controls.target.set(fx - c.x, fy - c.y, fz - c.z); camera.position.set(fx - c.x + fd * 0.35, fy - c.y + fd * 0.2, fz - c.z + fd);
    }
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(box); resize();
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
  box.dataset.ready = '1';
  box.classList.add('ready');                         // заставка уходит, живая модель остаётся
})().catch(e => { box.dataset.error = String(e); console.error(e); });
