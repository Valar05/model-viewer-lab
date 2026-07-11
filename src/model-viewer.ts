import './model-viewer.css';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

type Mode = 'move' | 'rotate' | 'scale';
type Axis = 'screen' | 'all' | 'x' | 'y' | 'z';
type ViewPart = { id: string; label: string; object: THREE.Object3D; visible: boolean; initial: SnapshotPart; };
type SnapshotPart = { id: string; label: string; position: [number, number, number]; rotationDeg: [number, number, number]; scale: [number, number, number]; visible: boolean; };

const root = document.querySelector<HTMLDivElement>('#model-viewer-root');
if (!root) throw new Error('missing #model-viewer-root');
const query = new URLSearchParams(window.location.search);
const src = query.get('src') || '';
const manifestUrl = query.get('manifest') || '';
const title = query.get('title') || src.split('/').pop() || 'Model';

root.innerHTML = '<main class="viewer-shell">' +
  '<div class="viewer-stage"><canvas aria-label="Model Viewer Lab viewport"></canvas></div>' +
  '<section class="viewer-toolbar" aria-label="Viewer panels"><button type="button" data-toggle-panel="info">Info</button><button type="button" data-toggle-panel="objects">Objects</button><button type="button" data-toggle-panel="tools">Tools</button></section>' +
  '<section class="hud" data-info-panel hidden><p class="kicker">model viewer lab</p><p class="title"></p><p class="status" data-status>loading model</p></section>' +
  '<section class="camera-widget" aria-label="Camera views"><button data-view="front">Front</button><button data-view="left">Left</button><button data-view="top">Top</button><button data-view="right">Right</button><button data-view="back">Back</button><button data-view="fit">Fit</button></section>' +
  '<section class="tweak-dock" aria-label="Object tweak controls" data-tools-panel hidden><div class="tweak-title" data-selected-title>No object selected</div><div class="row lock"><button data-edit-lock>Editing locked</button></div><div class="row modes"><button data-mode="move">Move</button><button data-mode="rotate">Rotate</button><button data-mode="scale">Scale</button></div><div class="row axes"><button data-axis="screen">Screen</button><button data-axis="x">X</button><button data-axis="y">Y</button><button data-axis="z">Z</button></div><div class="row actions"><button data-undo>Undo</button><button data-redo>Redo</button><button data-reset>Reset</button><button data-export>Export</button></div><div class="row display"><button data-clay>Clay</button><button data-wire>Wire</button><button data-grid>Grid</button><button data-boxes>Boxes</button></div></section>' +
  '<section class="sheet" aria-label="Object list" data-objects-panel hidden><div class="sheet-head"><input class="search" data-search placeholder="Filter objects" /><button data-collapse>Panel</button><button data-show-all>All</button><button data-hide-all>Hide</button></div><div class="object-list" data-object-list></div></section>' +
  '<section class="export-panel" hidden><textarea data-export-output readonly></textarea><button data-close-export>Close</button></section>' +
'</main>';

root.querySelector<HTMLElement>('.title')!.textContent = title;
const canvas = root.querySelector<HTMLCanvasElement>('canvas')!;
const statusEl = root.querySelector<HTMLElement>('[data-status]')!;
const objectListEl = root.querySelector<HTMLElement>('[data-object-list]')!;
const selectedTitleEl = root.querySelector<HTMLElement>('[data-selected-title]')!;
const exportPanel = root.querySelector<HTMLElement>('.export-panel')!;
const exportOutput = root.querySelector<HTMLTextAreaElement>('[data-export-output]')!;
const searchInput = root.querySelector<HTMLInputElement>('[data-search]')!;
const infoPanel = root.querySelector<HTMLElement>('[data-info-panel]')!;
const objectsPanel = root.querySelector<HTMLElement>('[data-objects-panel]')!;
const toolsPanel = root.querySelector<HTMLElement>('[data-tools-panel]')!;
let toolsOpen = false;
let editUnlocked = false;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.02;
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x11130f);
const camera = new THREE.PerspectiveCamera(38, 1, 0.02, 500);
camera.position.set(0, 1.4, 5.0);
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
scene.add(new THREE.HemisphereLight(0xf4ead2, 0x252a20, 2.0));
const key = new THREE.DirectionalLight(0xffefd1, 3.0);
key.position.set(3.8, 5.0, 3.2);
scene.add(key);
const rim = new THREE.DirectionalLight(0x9bb4ff, 1.1);
rim.position.set(-4.2, 2.4, -4.4);
scene.add(rim);
const grid = new THREE.GridHelper(10, 20, 0x5a614b, 0x2c3126);
grid.position.y = -0.01;
scene.add(grid);
const modelRoot = new THREE.Group();
modelRoot.name = 'review_model_root';
scene.add(modelRoot);
const boxHelpers = new THREE.Group();
boxHelpers.name = 'object_bounds_helpers';
scene.add(boxHelpers);

const loader = new GLTFLoader();
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const pickMeshes: THREE.Mesh[] = [];
let modelObject: THREE.Object3D | null = null;
let parts: ViewPart[] = [];
let selected: ViewPart | null = null;
let currentMode: Mode = 'move';
let currentAxis: Axis = 'screen';
let gesture: { pointerId: number; part: ViewPart; lastX: number; lastY: number; moved: boolean; undoPushed: boolean } | null = null;
const pointerPositions = new Map<number, { x: number; y: number }>();
let lastPinch = 0;
let lastTwist = 0;
const undoStack: string[] = [];
const redoStack: string[] = [];
let originalMaterials = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
let clayEnabled = false;
let wireEnabled = false;
let boxesEnabled = false;
const clayMaterial = new THREE.MeshStandardMaterial({ color: 0xb4b9a6, roughness: 0.92, metalness: 0.0 });

bindUi();
loadManifest();
loadModel();
requestAnimationFrame(animate);

function loadManifest() {
  if (!manifestUrl) return;
  fetch(manifestUrl, { cache: 'no-store' }).then((response) => response.json()).then((manifest) => {
    const count = manifest?.kit_policy?.piece_count ?? manifest?.shape_count ?? manifest?.mesh_count ?? '?';
    statusEl.textContent = 'loading model; manifest ' + (manifest.asset_id || manifest.id || 'loaded') + ', count ' + count;
  }).catch(() => { statusEl.textContent = 'loading model; manifest unavailable'; });
}

function loadModel() {
  if (!src) {
    statusEl.textContent = 'missing ?src= model URL';
    return;
  }
  loader.load(src, (gltf) => {
    modelObject = gltf.scene;
    modelObject.name = title;
    modelRoot.add(modelObject);
    collectParts(modelObject);
    normalizeModel();
    buildBoxHelpers();
    renderObjectList();
    selectPart(null);
    fitCamera('front');
    statusEl.textContent = 'loaded ' + parts.length + ' objects from ' + src;
  }, undefined, (error) => {
    statusEl.textContent = 'load failed: ' + (error instanceof Error ? error.message : String(error));
  });
}

function collectParts(object: THREE.Object3D) {
  parts = [];
  pickMeshes.length = 0;
  originalMaterials.clear();
  let serial = 0;
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (!mesh.isMesh) return;
    const parent = mesh.parent && mesh.parent !== object ? mesh.parent : mesh;
    if (parts.some((part) => part.object === parent)) return;
    const id = parent.name || mesh.name || 'mesh_' + serial;
    const part: ViewPart = { id, label: id, object: parent, visible: parent.visible, initial: snapshotObject(id, id, parent, parent.visible) };
    parts.push(part);
    parent.traverse((node) => {
      const nested = node as THREE.Mesh;
      if (!nested.isMesh) return;
      nested.userData.viewerPartId = id;
      pickMeshes.push(nested);
      originalMaterials.set(nested, nested.material);
    });
    serial += 1;
  });
}

function normalizeModel() {
  const box = new THREE.Box3().setFromObject(modelRoot);
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  modelRoot.position.sub(center);
  const maxAxis = Math.max(size.x, size.y, size.z) || 1;
  const scale = 2.6 / maxAxis;
  modelRoot.scale.setScalar(scale);
  const normalized = new THREE.Box3().setFromObject(modelRoot);
  modelRoot.position.y -= normalized.min.y;
}

function buildBoxHelpers() {
  boxHelpers.clear();
  for (const part of parts) {
    const helper = new THREE.BoxHelper(part.object, 0xd5b46f);
    helper.name = 'bounds_' + part.id;
    helper.userData.viewerPartId = part.id;
    helper.visible = boxesEnabled && part.visible;
    boxHelpers.add(helper);
  }
}

function bindUi() {
  root.querySelectorAll<HTMLButtonElement>('[data-toggle-panel]').forEach((button) => button.addEventListener('click', () => togglePanel(button.dataset.togglePanel || '')));
  root.querySelectorAll<HTMLButtonElement>('[data-view]').forEach((button) => button.addEventListener('click', () => fitCamera(button.dataset.view || 'front')));
  root.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach((button) => button.addEventListener('click', () => { currentMode = button.dataset.mode as Mode; currentAxis = currentMode === 'scale' ? 'all' : 'screen'; renderControls(); }));
  root.querySelectorAll<HTMLButtonElement>('[data-axis]').forEach((button) => button.addEventListener('click', () => { currentAxis = button.dataset.axis as Axis; renderControls(); }));
  root.querySelector<HTMLButtonElement>('[data-collapse]')?.addEventListener('click', () => document.body.classList.toggle('sheet-collapsed'));
  root.querySelector<HTMLButtonElement>('[data-show-all]')?.addEventListener('click', () => { for (const part of parts) setVisible(part, true); renderObjectList(); });
  root.querySelector<HTMLButtonElement>('[data-hide-all]')?.addEventListener('click', () => { for (const part of parts) setVisible(part, false); renderObjectList(); });
  root.querySelector<HTMLButtonElement>('[data-edit-lock]')?.addEventListener('click', toggleEditLock);
  root.querySelector<HTMLButtonElement>('[data-reset]')?.addEventListener('click', resetSelected);
  root.querySelector<HTMLButtonElement>('[data-undo]')?.addEventListener('click', undo);
  root.querySelector<HTMLButtonElement>('[data-redo]')?.addEventListener('click', redo);
  root.querySelector<HTMLButtonElement>('[data-export]')?.addEventListener('click', showExport);
  root.querySelector<HTMLButtonElement>('[data-close-export]')?.addEventListener('click', () => { exportPanel.hidden = true; });
  root.querySelector<HTMLButtonElement>('[data-clay]')?.addEventListener('click', () => { clayEnabled = !clayEnabled; applyMaterialMode(); renderControls(); });
  root.querySelector<HTMLButtonElement>('[data-wire]')?.addEventListener('click', () => { wireEnabled = !wireEnabled; applyMaterialMode(); renderControls(); });
  root.querySelector<HTMLButtonElement>('[data-grid]')?.addEventListener('click', () => { grid.visible = !grid.visible; renderControls(); });
  root.querySelector<HTMLButtonElement>('[data-boxes]')?.addEventListener('click', () => { boxesEnabled = !boxesEnabled; updateBoxHelpers(); renderControls(); });
  searchInput.addEventListener('input', renderObjectList);
  canvas.addEventListener('pointerdown', pointerDown);
  canvas.addEventListener('pointermove', pointerMove);
  canvas.addEventListener('pointerup', pointerEnd);
  canvas.addEventListener('pointercancel', pointerEnd);
}

function togglePanel(panel: string) {
  if (panel === 'info') infoPanel.hidden = !infoPanel.hidden;
  if (panel === 'objects') objectsPanel.hidden = !objectsPanel.hidden;
  if (panel === 'tools') {
    toolsPanel.hidden = !toolsPanel.hidden;
    toolsOpen = !toolsPanel.hidden;
    controls.enabled = true;
  }
  root.querySelectorAll<HTMLButtonElement>('[data-toggle-panel]').forEach((button) => {
    const id = button.dataset.togglePanel;
    const open = (id === 'info' && !infoPanel.hidden) || (id === 'objects' && !objectsPanel.hidden) || (id === 'tools' && !toolsPanel.hidden);
    button.classList.toggle('is-active', open);
  });
}

function toggleEditLock() {
  editUnlocked = !editUnlocked;
  if (!editUnlocked) {
    gesture = null;
    pointerPositions.clear();
    controls.enabled = true;
  }
  renderControls();
}

function renderObjectList() {
  const filter = searchInput.value.trim().toLowerCase();
  objectListEl.innerHTML = '';
  for (const part of parts) {
    if (filter && !part.label.toLowerCase().includes(filter)) continue;
    const row = document.createElement('div');
    row.className = 'object-row' + (!part.visible ? ' is-hidden' : '');
    const pick = document.createElement('button');
    pick.className = 'object-name' + (part === selected ? ' is-active' : '');
    pick.textContent = part.label;
    pick.addEventListener('click', () => selectPart(part));
    const hide = document.createElement('button');
    hide.textContent = part.visible ? 'Hide' : 'Show';
    hide.addEventListener('click', () => { pushUndo(); setVisible(part, !part.visible); renderObjectList(); });
    const solo = document.createElement('button');
    solo.textContent = 'Solo';
    solo.addEventListener('click', () => { pushUndo(); for (const candidate of parts) setVisible(candidate, candidate === part); selectPart(part); renderObjectList(); });
    row.append(pick, hide, solo);
    objectListEl.append(row);
  }
  renderControls();
}

function renderControls() {
  selectedTitleEl.textContent = selected ? selected.label : 'No object selected';
  const lockButton = root.querySelector<HTMLButtonElement>('[data-edit-lock]');
  if (lockButton) {
    lockButton.textContent = editUnlocked ? 'Editing unlocked' : 'Editing locked';
    lockButton.classList.toggle('is-active', editUnlocked);
  }
  root.querySelectorAll<HTMLButtonElement>('[data-mode], [data-axis], [data-undo], [data-redo], [data-reset]').forEach((button) => {
    button.disabled = !editUnlocked;
  });
  root.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach((button) => button.classList.toggle('is-active', button.dataset.mode === currentMode));
  root.querySelectorAll<HTMLButtonElement>('[data-axis]').forEach((button) => {
    const axis = button.dataset.axis as Axis;
    button.classList.toggle('is-active', axis === currentAxis);
    button.hidden = currentMode !== 'scale' && axis === 'all';
  });
  root.querySelector<HTMLButtonElement>('[data-clay]')?.classList.toggle('is-active', clayEnabled);
  root.querySelector<HTMLButtonElement>('[data-wire]')?.classList.toggle('is-active', wireEnabled);
  root.querySelector<HTMLButtonElement>('[data-grid]')?.classList.toggle('is-active', grid.visible);
  root.querySelector<HTMLButtonElement>('[data-boxes]')?.classList.toggle('is-active', boxesEnabled);
}

function selectPart(part: ViewPart | null) {
  selected = part;
  if (part && !part.visible) setVisible(part, true);
  if (part) focusPart(part, false);
  renderObjectList();
}

function setVisible(part: ViewPart, visible: boolean) {
  part.visible = visible;
  part.object.visible = visible;
  updateBoxHelpers();
}

function focusPart(part: ViewPart, moveCamera = true) {
  const box = new THREE.Box3().setFromObject(part.object);
  const center = new THREE.Vector3();
  box.getCenter(center);
  controls.target.copy(center);
  if (moveCamera) fitCamera('fit');
  controls.update();
}

function fitCamera(view: string) {
  const targetObject = selected?.object || modelRoot;
  const box = new THREE.Box3().setFromObject(targetObject);
  if (!Number.isFinite(box.min.x)) return;
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  const radius = Math.max(size.x, size.y, size.z, 0.1);
  const distance = Math.max(1.2, radius * 2.1);
  const offsets: Record<string, THREE.Vector3> = {
    front: new THREE.Vector3(0, distance * 0.35, distance),
    back: new THREE.Vector3(0, distance * 0.35, -distance),
    left: new THREE.Vector3(-distance, distance * 0.35, 0),
    right: new THREE.Vector3(distance, distance * 0.35, 0),
    top: new THREE.Vector3(0.01, distance, 0.01),
    fit: camera.position.clone().sub(controls.target).normalize().multiplyScalar(distance)
  };
  controls.target.copy(center);
  camera.position.copy(center).add(offsets[view] || offsets.front);
  controls.minDistance = Math.max(0.08, distance * 0.12);
  controls.maxDistance = Math.max(10, distance * 6);
  camera.near = Math.max(0.001, distance / 200);
  camera.far = Math.max(500, distance * 80);
  camera.updateProjectionMatrix();
  controls.update();
}

function pointerDown(event: PointerEvent) {
  if (!toolsOpen || !editUnlocked) return;
  pointerPositions.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (pointerPositions.size === 2) {
    lastPinch = pointerDistance();
    lastTwist = pointerAngle();
    if (gesture) controls.enabled = false;
    return;
  }
  const part = pickPart(event.clientX, event.clientY);
  if (!part) return;
  selectPart(part);
  controls.enabled = false;
  gesture = { pointerId: event.pointerId, part, lastX: event.clientX, lastY: event.clientY, moved: false, undoPushed: false };
  canvas.setPointerCapture(event.pointerId);
}

function pointerMove(event: PointerEvent) {
  if (!toolsOpen || !editUnlocked) return;
  pointerPositions.set(event.pointerId, { x: event.clientX, y: event.clientY });
  if (gesture && pointerPositions.size >= 2) return twoFingerGesture();
  if (!gesture || event.pointerId !== gesture.pointerId) return;
  const dx = event.clientX - gesture.lastX;
  const dy = event.clientY - gesture.lastY;
  if (Math.abs(dx) + Math.abs(dy) < 0.5) return;
  pushUndoForGesture();
  transformPart(gesture.part, dx, dy);
  gesture.lastX = event.clientX;
  gesture.lastY = event.clientY;
  gesture.moved = true;
  updateBoxHelpers();
}

function pointerEnd(event: PointerEvent) {
  if (!toolsOpen || !editUnlocked) return;
  pointerPositions.delete(event.pointerId);
  if (gesture && event.pointerId === gesture.pointerId) {
    gesture = null;
    controls.enabled = true;
    renderObjectList();
  }
  if (pointerPositions.size < 2) {
    lastPinch = 0;
    lastTwist = 0;
  }
}

function twoFingerGesture() {
  if (!gesture) return;
  pushUndoForGesture();
  const distance = pointerDistance();
  const angle = pointerAngle();
  if (currentMode === 'scale' && lastPinch > 0) scalePart(gesture.part, (distance - lastPinch) * 0.006);
  if (currentMode === 'rotate' && Number.isFinite(lastTwist)) rotatePart(gesture.part, THREE.MathUtils.radToDeg(angle - lastTwist));
  lastPinch = distance;
  lastTwist = angle;
  updateBoxHelpers();
}

function pickPart(clientX: number, clientY: number) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -(((clientY - rect.top) / rect.height) * 2 - 1);
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(pickMeshes.filter((mesh) => mesh.visible), false);
  if (!hits.length) return selected;
  const id = hits[0].object.userData.viewerPartId;
  return parts.find((part) => part.id === id) || selected;
}

function transformPart(part: ViewPart, dx: number, dy: number) {
  if (currentMode === 'move') movePart(part, dx, dy);
  if (currentMode === 'rotate') rotatePart(part, (Math.abs(dx) > Math.abs(dy) ? dx : -dy) * 0.28);
  if (currentMode === 'scale') scalePart(part, (dx - dy) * 0.004);
}

function movePart(part: ViewPart, dx: number, dy: number) {
  const amount = 0.006;
  if (currentAxis === 'screen') {
    const right = new THREE.Vector3();
    const up = new THREE.Vector3();
    camera.matrixWorld.extractBasis(right, up, new THREE.Vector3());
    const delta = right.multiplyScalar(dx * amount).add(up.multiplyScalar(-dy * amount));
    part.object.position.add(delta);
    return;
  }
  const value = (Math.abs(dx) > Math.abs(dy) ? dx : -dy) * amount;
  if (currentAxis === 'x') part.object.position.x += value;
  if (currentAxis === 'y') part.object.position.y += value;
  if (currentAxis === 'z') part.object.position.z += value;
}

function rotatePart(part: ViewPart, degrees: number) {
  if (currentAxis === 'screen') part.object.rotation.y += THREE.MathUtils.degToRad(degrees);
  if (currentAxis === 'x') part.object.rotation.x += THREE.MathUtils.degToRad(degrees);
  if (currentAxis === 'y') part.object.rotation.y += THREE.MathUtils.degToRad(degrees);
  if (currentAxis === 'z') part.object.rotation.z += THREE.MathUtils.degToRad(degrees);
}

function scalePart(part: ViewPart, delta: number) {
  const apply = (axis: 'x' | 'y' | 'z') => { part.object.scale[axis] = Math.max(0.02, part.object.scale[axis] + delta); };
  if (currentAxis === 'all' || currentAxis === 'screen') { apply('x'); apply('y'); apply('z'); }
  if (currentAxis === 'x') apply('x');
  if (currentAxis === 'y') apply('y');
  if (currentAxis === 'z') apply('z');
}

function pointerDistance() {
  const values = [...pointerPositions.values()];
  if (values.length < 2) return 0;
  return Math.hypot(values[0].x - values[1].x, values[0].y - values[1].y);
}
function pointerAngle() {
  const values = [...pointerPositions.values()];
  if (values.length < 2) return 0;
  return Math.atan2(values[1].y - values[0].y, values[1].x - values[0].x);
}
function pushUndoForGesture() {
  if (!gesture || gesture.undoPushed) return;
  pushUndo();
  gesture.undoPushed = true;
}
function pushUndo() {
  undoStack.push(serializeState());
  redoStack.length = 0;
}
function undo() {
  if (!editUnlocked || !undoStack.length) return;
  redoStack.push(serializeState());
  restoreState(undoStack.pop()!);
}
function redo() {
  if (!editUnlocked || !redoStack.length) return;
  undoStack.push(serializeState());
  restoreState(redoStack.pop()!);
}
function resetSelected() {
  if (!editUnlocked || !selected) return;
  pushUndo();
  restorePart(selected, selected.initial);
  renderObjectList();
}
function snapshotObject(id: string, label: string, object: THREE.Object3D, visible: boolean): SnapshotPart {
  return { id, label, position: [object.position.x, object.position.y, object.position.z], rotationDeg: [THREE.MathUtils.radToDeg(object.rotation.x), THREE.MathUtils.radToDeg(object.rotation.y), THREE.MathUtils.radToDeg(object.rotation.z)], scale: [object.scale.x, object.scale.y, object.scale.z], visible };
}
function serializeState() {
  return JSON.stringify({ version: 1, src, manifest: manifestUrl, title, camera: { position: camera.position.toArray(), target: controls.target.toArray(), fov: camera.fov }, parts: parts.map((part) => snapshotObject(part.id, part.label, part.object, part.visible)) }, null, 2);
}
function restoreState(json: string) {
  const state = JSON.parse(json) as { parts: SnapshotPart[] };
  for (const saved of state.parts || []) {
    const part = parts.find((candidate) => candidate.id === saved.id);
    if (part) restorePart(part, saved);
  }
  renderObjectList();
}
function restorePart(part: ViewPart, saved: SnapshotPart) {
  part.object.position.set(saved.position[0], saved.position[1], saved.position[2]);
  part.object.rotation.set(THREE.MathUtils.degToRad(saved.rotationDeg[0]), THREE.MathUtils.degToRad(saved.rotationDeg[1]), THREE.MathUtils.degToRad(saved.rotationDeg[2]));
  part.object.scale.set(saved.scale[0], saved.scale[1], saved.scale[2]);
  setVisible(part, saved.visible);
}
function showExport() {
  exportOutput.value = serializeState();
  exportPanel.hidden = false;
}
function applyMaterialMode() {
  for (const [mesh, original] of originalMaterials) {
    mesh.material = clayEnabled ? clayMaterial : original;
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const material of materials) {
      material.wireframe = wireEnabled;
      material.needsUpdate = true;
    }
  }
}
function updateBoxHelpers() {
  for (const helper of boxHelpers.children) {
    const id = helper.userData.viewerPartId;
    const part = parts.find((candidate) => candidate.id === id);
    helper.visible = Boolean(boxesEnabled && part?.visible);
    (helper as THREE.BoxHelper).update();
  }
}
function resize() {
  const width = Math.max(1, canvas.clientWidth);
  const height = Math.max(1, canvas.clientHeight);
  const ratio = renderer.getPixelRatio();
  if (canvas.width !== Math.floor(width * ratio) || canvas.height !== Math.floor(height * ratio)) {
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
}
function animate() {
  resize();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
