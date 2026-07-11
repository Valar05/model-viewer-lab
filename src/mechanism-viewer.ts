import './mechanism-viewer.css';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

type Vec3 = [number, number, number];
type MechanismConfig = {
  schemaVersion: number;
  id: string;
  title: string;
  description?: string;
  forwardAxis: '+z';
  dimensions: {
    trackGauge: number;
    trackWidth: number;
    trackLength: number;
    bottomY: number;
    topY: number;
    hullWidth: number;
    hullLength: number;
    hullHeight: number;
  };
  tread: {
    linksPerSide: number;
    shoeWidth: number;
    shoeLength: number;
    shoeThickness: number;
    grouserHeight: number;
  };
  simulation: {
    driveSpeed: number;
    yawSpeed: number;
    trackVisualSpeed: number;
    joystickDeadzone: number;
    joystickResponse: number;
  };
  display: {
    showPathDefault: boolean;
    showStatsDefault: boolean;
    showGhostDefault: boolean;
    colors: Record<string, string>;
  };
};

type BeltSample = { position: THREE.Vector3; tangent: THREE.Vector3; };
type MechanismPart = { id: string; label: string; object: THREE.Object3D; visible: boolean; };

const root = document.querySelector<HTMLDivElement>('#mechanism-viewer-root');
if (!root) throw new Error('missing #mechanism-viewer-root');

const query = new URLSearchParams(window.location.search);
const defaultMechanism = './labs/hard-surface-factory/mechanisms/tread-system-v1/mechanism.json';
let mechanismUrl = query.get('mechanism') || defaultMechanism;
let title = query.get('title') || 'tread-system-v1';

root.innerHTML = '<main class="mechanism-shell">' +
  '<div class="stage"><canvas aria-label="Mechanism Viewer Lab viewport"></canvas></div>' +
  '<section class="toolbar" aria-label="Mechanism panels"><button type="button" data-toggle-panel="info">Info</button><button type="button" data-toggle-panel="parts">Parts</button><button type="button" data-toggle-panel="sim">Sim</button></section>' +
  '<section class="panel info" data-info-panel hidden><p class="kicker">mechanism viewer lab</p><p class="title"></p><p class="status" data-status>loading mechanism</p><p class="small" data-description></p></section>' +
  '<section class="camera-widget" aria-label="Camera views"><button data-view="front">Front</button><button data-view="left">Left</button><button data-view="top">Top</button><button data-view="right">Right</button><button data-view="back">Back</button><button data-view="fit">Fit</button></section>' +
  '<section class="joystick-card" aria-label="Tank-relative movement joystick"><div class="joystick-base" data-joystick><div class="joystick-thumb" data-joystick-thumb></div></div></section>' +
  '<section class="panel parts" data-parts-panel hidden><p class="kicker">instanced pieces</p><div class="part-list" data-part-list></div></section>' +
  '<section class="panel sim" data-sim-panel hidden><p class="kicker">simulation</p><div class="sim-grid"><button data-pause>Pause</button><button data-reset>Reset</button><button data-show-path>Path</button><button data-show-ghost>Ghost</button><button data-show-stats>Stats</button><button data-fit>Fit</button></div><div class="stat-grid" data-stats hidden></div></section>' +
'</main>';

const canvas = root.querySelector<HTMLCanvasElement>('canvas')!;
const statusEl = root.querySelector<HTMLElement>('[data-status]')!;
const titleEl = root.querySelector<HTMLElement>('.title')!;
const descriptionEl = root.querySelector<HTMLElement>('[data-description]')!;
const infoPanel = root.querySelector<HTMLElement>('[data-info-panel]')!;
const partsPanel = root.querySelector<HTMLElement>('[data-parts-panel]')!;
const simPanel = root.querySelector<HTMLElement>('[data-sim-panel]')!;
const partListEl = root.querySelector<HTMLElement>('[data-part-list]')!;
const statsEl = root.querySelector<HTMLElement>('[data-stats]')!;
const joystickBase = root.querySelector<HTMLElement>('[data-joystick]')!;
const joystickThumb = root.querySelector<HTMLElement>('[data-joystick-thumb]')!;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.04;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x10120f);
const camera = new THREE.PerspectiveCamera(38, 1, 0.02, 500);
camera.position.set(2.8, 1.6, 4.0);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.enablePan = true;
controls.screenSpacePanning = true;
controls.rotateSpeed = 0.78;
controls.panSpeed = 0.7;
controls.zoomSpeed = 0.82;
controls.touches.ONE = THREE.TOUCH.ROTATE;
controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;

scene.add(new THREE.HemisphereLight(0xf5ecd8, 0x262b22, 2.1));
const key = new THREE.DirectionalLight(0xffefd1, 3.0);
key.position.set(4.0, 5.2, 3.3);
scene.add(key);
const rim = new THREE.DirectionalLight(0x9bb4ff, 1.15);
rim.position.set(-4.3, 2.6, -4.5);
scene.add(rim);
const grid = new THREE.GridHelper(9, 18, 0x5d664e, 0x2b3126);
scene.add(grid);

const vehicle = new THREE.Group();
vehicle.name = 'tank_relative_mechanism_root';
scene.add(vehicle);
const trackRoot = new THREE.Group();
trackRoot.name = 'instanced_tread_system';
vehicle.add(trackRoot);
const pathRoot = new THREE.Group();
pathRoot.name = 'belt_path_guides';
vehicle.add(pathRoot);
const ghostRoot = new THREE.Group();
ghostRoot.name = 'reference_ghost';
vehicle.add(ghostRoot);

let config: MechanismConfig | null = null;
let leftTreads: THREE.InstancedMesh | null = null;
let rightTreads: THREE.InstancedMesh | null = null;
let leftGrousers: THREE.InstancedMesh | null = null;
let rightGrousers: THREE.InstancedMesh | null = null;
let parts: MechanismPart[] = [];
let beltLength = 1;
let leftOffset = 0;
let rightOffset = 0;
let joyForward = 0;
let joyTurn = 0;
let leftSpeed = 0;
let rightSpeed = 0;
let paused = false;
let showStats = false;
let activeJoystickId: number | null = null;
let lastTime = performance.now();
const tempMatrix = new THREE.Matrix4();
const tempQuat = new THREE.Quaternion();
const tempScale = new THREE.Vector3(1, 1, 1);
const zAxis = new THREE.Vector3(0, 0, 1);

bindUi();
loadMechanism();
requestAnimationFrame(animate);

async function loadMechanism() {
  try {
    const response = await fetch(mechanismUrl, { cache: 'no-store' });
    if (!response.ok) throw new Error('HTTP ' + response.status + ' for ' + mechanismUrl);
    config = await response.json();
    title = query.get('title') || config.title || config.id;
    document.title = title + ' - Mechanism Viewer Lab';
    titleEl.textContent = title;
    descriptionEl.textContent = config.description || '';
    buildMechanism(config);
    statusEl.textContent = 'loaded ' + config.id + '; joystick controls tank-local motion';
    fitCamera('front');
  } catch (error) {
    titleEl.textContent = title;
    statusEl.textContent = 'mechanism load failed: ' + (error instanceof Error ? error.message : String(error));
  }
}

function buildMechanism(cfg: MechanismConfig) {
  clearGroup(trackRoot);
  clearGroup(pathRoot);
  clearGroup(ghostRoot);
  parts = [];
  beltLength = computeBeltLength(cfg);

  const trackMaterial = new THREE.MeshStandardMaterial({ color: new THREE.Color(cfg.display.colors.track), roughness: 0.88, metalness: 0.08 });
  const grouserMaterial = new THREE.MeshStandardMaterial({ color: new THREE.Color(cfg.display.colors.grouser), roughness: 0.9, metalness: 0.1 });
  const hullMaterial = new THREE.MeshStandardMaterial({ color: new THREE.Color(cfg.display.colors.hull), roughness: 0.85, metalness: 0.02 });
  const pathMaterial = new THREE.LineBasicMaterial({ color: new THREE.Color(cfg.display.colors.path), transparent: true, opacity: 0.78 });
  const ghostMaterial = new THREE.MeshStandardMaterial({ color: new THREE.Color(cfg.display.colors.ghost), roughness: 0.9, metalness: 0, transparent: true, opacity: 0.16, depthWrite: false });

  const shoeGeometry = new THREE.BoxGeometry(cfg.tread.shoeWidth, cfg.tread.shoeThickness, cfg.tread.shoeLength);
  const grouserGeometry = new THREE.BoxGeometry(cfg.tread.shoeWidth * 0.92, cfg.tread.grouserHeight, cfg.tread.shoeLength * 0.24);
  leftTreads = new THREE.InstancedMesh(shoeGeometry, trackMaterial, cfg.tread.linksPerSide);
  rightTreads = new THREE.InstancedMesh(shoeGeometry, trackMaterial, cfg.tread.linksPerSide);
  leftGrousers = new THREE.InstancedMesh(grouserGeometry, grouserMaterial, cfg.tread.linksPerSide);
  rightGrousers = new THREE.InstancedMesh(grouserGeometry, grouserMaterial, cfg.tread.linksPerSide);
  leftTreads.name = 'left_instanced_tread_links';
  rightTreads.name = 'right_instanced_tread_links';
  leftGrousers.name = 'left_instanced_grousers';
  rightGrousers.name = 'right_instanced_grousers';
  trackRoot.add(leftTreads, rightTreads, leftGrousers, rightGrousers);

  const hull = new THREE.Mesh(new THREE.BoxGeometry(cfg.dimensions.hullWidth, cfg.dimensions.hullHeight, cfg.dimensions.hullLength), hullMaterial);
  hull.name = 'simple_hull_reference_mass';
  hull.position.y = cfg.dimensions.topY + cfg.dimensions.hullHeight * 0.45;
  vehicle.add(hull);

  const capGeo = new THREE.CylinderGeometry(0.22, 0.22, cfg.dimensions.trackWidth * 1.05, 24);
  capGeo.rotateZ(Math.PI / 2);
  for (const side of [-1, 1]) {
    for (const z of [-cfg.dimensions.trackLength / 2, cfg.dimensions.trackLength / 2]) {
      const wheel = new THREE.Mesh(capGeo, hullMaterial);
      wheel.name = (side < 0 ? 'left' : 'right') + '_guide_disc_' + (z < 0 ? 'rear' : 'front');
      wheel.position.set(side * cfg.dimensions.trackGauge / 2, (cfg.dimensions.topY + cfg.dimensions.bottomY) / 2, z);
      trackRoot.add(wheel);
    }
  }

  const ghost = new THREE.Mesh(new THREE.BoxGeometry(cfg.dimensions.trackGauge + cfg.dimensions.trackWidth, cfg.dimensions.topY + 0.24, cfg.dimensions.trackLength + 0.18), ghostMaterial);
  ghost.name = 'mechanism_extent_ghost';
  ghost.position.y = (cfg.dimensions.topY + 0.24) / 2;
  ghost.visible = cfg.display.showGhostDefault;
  ghostRoot.add(ghost);

  pathRoot.visible = cfg.display.showPathDefault;
  ghostRoot.visible = cfg.display.showGhostDefault;

  for (const side of [-1, 1]) {
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(buildPathPoints(cfg, side, 96)), pathMaterial);
    line.name = (side < 0 ? 'left' : 'right') + '_belt_path';
    line.visible = cfg.display.showPathDefault;
    pathRoot.add(line);
  }

  parts = [
    { id: 'left_track_links', label: 'left instanced tread links', object: leftTreads, visible: true },
    { id: 'right_track_links', label: 'right instanced tread links', object: rightTreads, visible: true },
    { id: 'left_grousers', label: 'left instanced grouser bars', object: leftGrousers, visible: true },
    { id: 'right_grousers', label: 'right instanced grouser bars', object: rightGrousers, visible: true },
    { id: 'belt_paths', label: 'belt path guides', object: pathRoot, visible: cfg.display.showPathDefault },
    { id: 'reference_ghost', label: 'reference extent ghost', object: ghostRoot, visible: cfg.display.showGhostDefault },
    { id: 'hull_reference', label: 'simple hull reference mass', object: hull, visible: true },
  ];

  renderPartList();
  updateButtons();
  updateTreadInstances();
}

function clearGroup(group: THREE.Group) {
  while (group.children.length) group.remove(group.children[0]);
}

function computeBeltLength(cfg: MechanismConfig) {
  const r = (cfg.dimensions.topY - cfg.dimensions.bottomY) / 2;
  const straight = Math.max(0.1, cfg.dimensions.trackLength - 2 * r);
  return 2 * straight + 2 * Math.PI * r;
}

function buildPathPoints(cfg: MechanismConfig, side: number, count: number) {
  const points: THREE.Vector3[] = [];
  for (let i = 0; i <= count; i += 1) points.push(sampleBelt(cfg, side, (i / count) * beltLength).position);
  return points;
}

function sampleBelt(cfg: MechanismConfig, side: number, distance: number): BeltSample {
  const topY = cfg.dimensions.topY;
  const bottomY = cfg.dimensions.bottomY;
  const midY = (topY + bottomY) / 2;
  const r = (topY - bottomY) / 2;
  const frontZ = cfg.dimensions.trackLength / 2 - r;
  const rearZ = -cfg.dimensions.trackLength / 2 + r;
  const straight = frontZ - rearZ;
  const arc = Math.PI * r;
  const total = 2 * straight + 2 * arc;
  let d = ((distance % total) + total) % total;
  const x = side * cfg.dimensions.trackGauge / 2;

  if (d < straight) {
    return { position: new THREE.Vector3(x, topY, rearZ + d), tangent: new THREE.Vector3(0, 0, 1) };
  }
  d -= straight;
  if (d < arc) {
    const a = Math.PI / 2 - d / r;
    return { position: new THREE.Vector3(x, midY + Math.sin(a) * r, frontZ + Math.cos(a) * r), tangent: new THREE.Vector3(0, -Math.cos(a), Math.sin(a)).normalize() };
  }
  d -= arc;
  if (d < straight) {
    return { position: new THREE.Vector3(x, bottomY, frontZ - d), tangent: new THREE.Vector3(0, 0, -1) };
  }
  d -= straight;
  const a = -Math.PI / 2 - d / r;
  return { position: new THREE.Vector3(x, midY + Math.sin(a) * r, rearZ + Math.cos(a) * r), tangent: new THREE.Vector3(0, -Math.cos(a), Math.sin(a)).normalize() };
}

function updateTreadInstances() {
  if (!config || !leftTreads || !rightTreads || !leftGrousers || !rightGrousers) return;
  updateSideInstances(config, -1, leftOffset, leftTreads, leftGrousers);
  updateSideInstances(config, 1, rightOffset, rightTreads, rightGrousers);
}

function updateSideInstances(cfg: MechanismConfig, side: number, offset: number, shoes: THREE.InstancedMesh, grousers: THREE.InstancedMesh) {
  const count = cfg.tread.linksPerSide;
  const spacing = beltLength / count;
  for (let i = 0; i < count; i += 1) {
    const sample = sampleBelt(cfg, side, i * spacing + offset);
    tempQuat.setFromUnitVectors(zAxis, sample.tangent);
    tempMatrix.compose(sample.position, tempQuat, tempScale);
    shoes.setMatrixAt(i, tempMatrix);
    const normal = new THREE.Vector3(0, sample.tangent.z, -sample.tangent.y).normalize();
    const grouserPosition = sample.position.clone().add(normal.multiplyScalar(cfg.tread.shoeThickness * 0.62));
    tempMatrix.compose(grouserPosition, tempQuat, tempScale);
    grousers.setMatrixAt(i, tempMatrix);
  }
  shoes.instanceMatrix.needsUpdate = true;
  grousers.instanceMatrix.needsUpdate = true;
}

function bindUi() {
  root.querySelectorAll<HTMLButtonElement>('[data-toggle-panel]').forEach((button) => button.addEventListener('click', () => togglePanel(button.dataset.togglePanel || '')));
  root.querySelectorAll<HTMLButtonElement>('[data-view]').forEach((button) => button.addEventListener('click', () => fitCamera(button.dataset.view || 'front')));
  root.querySelector<HTMLButtonElement>('[data-pause]')?.addEventListener('click', () => { paused = !paused; updateButtons(); });
  root.querySelector<HTMLButtonElement>('[data-reset]')?.addEventListener('click', resetSimulation);
  root.querySelector<HTMLButtonElement>('[data-show-path]')?.addEventListener('click', () => { pathRoot.visible = !pathRoot.visible; for (const p of parts) if (p.id === 'belt_paths') p.visible = pathRoot.visible; renderPartList(); updateButtons(); });
  root.querySelector<HTMLButtonElement>('[data-show-ghost]')?.addEventListener('click', () => { ghostRoot.visible = !ghostRoot.visible; for (const p of parts) if (p.id === 'reference_ghost') p.visible = ghostRoot.visible; renderPartList(); updateButtons(); });
  root.querySelector<HTMLButtonElement>('[data-show-stats]')?.addEventListener('click', () => { showStats = !showStats; statsEl.hidden = !showStats; updateButtons(); });
  root.querySelector<HTMLButtonElement>('[data-fit]')?.addEventListener('click', () => fitCamera('fit'));
  joystickBase.addEventListener('pointerdown', joystickDown);
  joystickBase.addEventListener('pointermove', joystickMove);
  joystickBase.addEventListener('pointerup', joystickEnd);
  joystickBase.addEventListener('pointercancel', joystickEnd);
  window.addEventListener('resize', resize);
}

function togglePanel(panel: string) {
  if (panel === 'info') infoPanel.hidden = !infoPanel.hidden;
  if (panel === 'parts') partsPanel.hidden = !partsPanel.hidden;
  if (panel === 'sim') simPanel.hidden = !simPanel.hidden;
  updateButtons();
}

function updateButtons() {
  root.querySelectorAll<HTMLButtonElement>('[data-toggle-panel]').forEach((button) => {
    const id = button.dataset.togglePanel;
    button.classList.toggle('is-active', (id === 'info' && !infoPanel.hidden) || (id === 'parts' && !partsPanel.hidden) || (id === 'sim' && !simPanel.hidden));
  });
  root.querySelector<HTMLButtonElement>('[data-pause]')!.textContent = paused ? 'Resume' : 'Pause';
  root.querySelector<HTMLButtonElement>('[data-pause]')!.classList.toggle('is-active', paused);
  root.querySelector<HTMLButtonElement>('[data-show-path]')!.classList.toggle('is-active', pathRoot.visible);
  root.querySelector<HTMLButtonElement>('[data-show-ghost]')!.classList.toggle('is-active', ghostRoot.visible);
  root.querySelector<HTMLButtonElement>('[data-show-stats]')!.classList.toggle('is-active', showStats);
}

function renderPartList() {
  partListEl.innerHTML = '';
  for (const part of parts) {
    const row = document.createElement('div');
    row.className = 'part-row';
    const label = document.createElement('span');
    label.textContent = part.label;
    const toggle = document.createElement('button');
    toggle.textContent = part.visible ? 'Hide' : 'Show';
    toggle.addEventListener('click', () => {
      part.visible = !part.visible;
      part.object.visible = part.visible;
      renderPartList();
      updateButtons();
    });
    row.append(label, toggle);
    partListEl.append(row);
  }
}

function joystickDown(event: PointerEvent) {
  activeJoystickId = event.pointerId;
  joystickBase.setPointerCapture(event.pointerId);
  updateJoystick(event);
}
function joystickMove(event: PointerEvent) {
  if (activeJoystickId !== event.pointerId) return;
  updateJoystick(event);
}
function joystickEnd(event: PointerEvent) {
  if (activeJoystickId !== event.pointerId) return;
  activeJoystickId = null;
  joyForward = 0;
  joyTurn = 0;
  joystickThumb.style.transform = 'translate(0px, 0px)';
}
function updateJoystick(event: PointerEvent) {
  if (!config) return;
  const rect = joystickBase.getBoundingClientRect();
  const radius = Math.min(rect.width, rect.height) * 0.5;
  const max = radius - 27;
  const cx = rect.left + rect.width * 0.5;
  const cy = rect.top + rect.height * 0.5;
  let x = event.clientX - cx;
  let y = event.clientY - cy;
  const length = Math.hypot(x, y);
  if (length > max) {
    x = (x / length) * max;
    y = (y / length) * max;
  }
  joystickThumb.style.transform = `translate(${x}px, ${y}px)`;
  const nx = x / max;
  const ny = y / max;
  joyTurn = shapeAxis(nx, config.simulation.joystickDeadzone, config.simulation.joystickResponse);
  joyForward = shapeAxis(-ny, config.simulation.joystickDeadzone, config.simulation.joystickResponse);
}
function shapeAxis(value: number, deadzone: number, response: number) {
  const sign = Math.sign(value);
  const magnitude = Math.abs(value);
  if (magnitude < deadzone) return 0;
  const normalized = (magnitude - deadzone) / (1 - deadzone);
  return sign * Math.min(1, Math.pow(normalized, response));
}

function resetSimulation() {
  vehicle.position.set(0, 0, 0);
  vehicle.rotation.set(0, 0, 0);
  leftOffset = 0;
  rightOffset = 0;
  joyForward = 0;
  joyTurn = 0;
  joystickThumb.style.transform = 'translate(0px, 0px)';
  updateTreadInstances();
}

function stepSimulation(dt: number) {
  if (!config || paused) {
    leftSpeed = 0;
    rightSpeed = 0;
    return;
  }
  leftSpeed = THREE.MathUtils.clamp(joyForward + joyTurn, -1, 1);
  rightSpeed = THREE.MathUtils.clamp(joyForward - joyTurn, -1, 1);
  const average = (leftSpeed + rightSpeed) * 0.5;
  const turn = (leftSpeed - rightSpeed) * 0.5;
  vehicle.rotation.y += turn * config.simulation.yawSpeed * dt;
  const forward = new THREE.Vector3(Math.sin(vehicle.rotation.y), 0, Math.cos(vehicle.rotation.y));
  vehicle.position.addScaledVector(forward, average * config.simulation.driveSpeed * dt);
  leftOffset += leftSpeed * config.simulation.trackVisualSpeed * dt;
  rightOffset += rightSpeed * config.simulation.trackVisualSpeed * dt;
  updateTreadInstances();
}

function fitCamera(view: string) {
  const box = new THREE.Box3().setFromObject(vehicle);
  if (!Number.isFinite(box.min.x)) return;
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  const radius = Math.max(size.x, size.y, size.z, 0.1);
  const distance = Math.max(2.2, radius * 1.8);
  const offsets: Record<string, THREE.Vector3> = {
    front: new THREE.Vector3(0, distance * 0.42, distance),
    back: new THREE.Vector3(0, distance * 0.42, -distance),
    left: new THREE.Vector3(-distance, distance * 0.42, 0),
    right: new THREE.Vector3(distance, distance * 0.42, 0),
    top: new THREE.Vector3(0.01, distance, 0.01),
    fit: camera.position.clone().sub(controls.target).normalize().multiplyScalar(distance),
  };
  controls.target.copy(center);
  camera.position.copy(center).add(offsets[view] || offsets.front);
  controls.minDistance = Math.max(0.1, distance * 0.12);
  controls.maxDistance = Math.max(10, distance * 6);
  camera.near = Math.max(0.001, distance / 200);
  camera.far = Math.max(500, distance * 80);
  camera.updateProjectionMatrix();
  controls.update();
}

function resize() {
  const width = Math.max(1, canvas.clientWidth);
  const height = Math.max(1, canvas.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function updateStats() {
  if (!showStats || !config) return;
  statsEl.innerHTML = '';
  const values: [string, string][] = [
    ['forward', joyForward.toFixed(2)],
    ['turn', joyTurn.toFixed(2)],
    ['left track', leftSpeed.toFixed(2)],
    ['right track', rightSpeed.toFixed(2)],
    ['yaw deg', THREE.MathUtils.radToDeg(vehicle.rotation.y).toFixed(1)],
    ['links/side', String(config.tread.linksPerSide)],
  ];
  for (const [key, value] of values) {
    const k = document.createElement('div');
    const v = document.createElement('div');
    k.textContent = key;
    v.textContent = value;
    statsEl.append(k, v);
  }
}

function animate(now: number) {
  const dt = Math.min(0.05, Math.max(0, (now - lastTime) / 1000));
  lastTime = now;
  resize();
  stepSimulation(dt);
  updateStats();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
