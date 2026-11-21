import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

/* =========================================================================
   Application State
   ========================================================================= */
const state = {
  presets: {},
  samples: [],
  selectedSampleId: 'dragon_helm',
  uploadedFiles: { front: null, left: null, back: null, right: null },
  currentJob: null,
  shadingMode: 'pbr',
  wireframe: false,
  turntable: true,
  showR15Dummy: false,
  optSelectedFile: null,
};

/* =========================================================================
   Three.js Roblox Studio Viewport Setup
   ========================================================================= */
const container = document.getElementById('three-container');
const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 200);
camera.position.set(4.2, 3.0, 5.2);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.outputColorSpace = THREE.SRGBColorSpace;
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.target.set(0, 1.1, 0);

// Procedural Studio PMREM Environment so MetalnessMap & RoughnessMap reflect crisply offline!
function buildStudioEnvironment() {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  envScene.background = new THREE.Color(0x162032);

  const skyPanel = new THREE.Mesh(
    new THREE.PlaneGeometry(20, 20),
    new THREE.MeshBasicMaterial({ color: 0xdbeafe, side: THREE.DoubleSide })
  );
  skyPanel.position.set(0, 9, 0);
  skyPanel.rotation.x = Math.PI / 2;
  envScene.add(skyPanel);

  const warmSide = new THREE.Mesh(
    new THREE.PlaneGeometry(14, 10),
    new THREE.MeshBasicMaterial({ color: 0xfde68a, side: THREE.DoubleSide })
  );
  warmSide.position.set(9, 3, 5);
  warmSide.lookAt(0, 0, 0);
  envScene.add(warmSide);

  const coolRim = new THREE.Mesh(
    new THREE.PlaneGeometry(14, 10),
    new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide })
  );
  coolRim.position.set(-9, 4, -6);
  coolRim.lookAt(0, 0, 0);
  envScene.add(coolRim);

  const rt = pmrem.fromScene(envScene, 0.04);
  scene.environment = rt.texture;
  pmrem.dispose();
}
buildStudioEnvironment();

// Studio 3-Point Lights
const hemiLight = new THREE.HemisphereLight(0xe0f2fe, 0x1e293b, 0.9);
scene.add(hemiLight);

const keyLight = new THREE.DirectionalLight(0xffffff, 2.1);
keyLight.position.set(5, 8, 6);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight(0x38bdf8, 1.1);
rimLight.position.set(-6, 4, -5);
scene.add(rimLight);

// 1-Stud Roblox Baseplate Grid (24 x 24 studs)
const studGridMinor = new THREE.GridHelper(24, 24, 0x2a3954, 0x1a2436);
studGridMinor.position.y = -0.002;
scene.add(studGridMinor);

const studGridMajor = new THREE.GridHelper(24, 6, 0x38bdf8, 0x2c3e5e);
studGridMajor.material.opacity = 0.35;
studGridMajor.material.transparent = true;
scene.add(studGridMajor);

// 5-Stud Roblox R15 Blocky Avatar Scale Reference Dummy
function createR15ScaleDummy() {
  const group = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({
    color: 0x38bdf8,
    roughness: 0.4,
    metalness: 0.1,
    transparent: true,
    opacity: 0.28,
  });
  const edgeMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.55 });

  function addBlock(w, h, d, x, y, z) {
    const geo = new THREE.BoxGeometry(w, h, d);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, y, z);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat);
    mesh.add(edges);
    group.add(mesh);
  }

  // Standard 5.0-stud R15 proportions: Legs 2.0, Torso 2.0, Head 1.0 (Total Y = 5.0 studs)
  addBlock(0.95, 2.0, 0.95, -0.52, 1.0, 0); // Left Leg
  addBlock(0.95, 2.0, 0.95,  0.52, 1.0, 0); // Right Leg
  addBlock(2.0,  2.0, 1.0,   0.0,  3.0, 0); // Torso
  addBlock(0.95, 2.0, 0.95, -1.52, 3.0, 0); // Left Arm
  addBlock(0.95, 2.0, 0.95,  1.52, 3.0, 0); // Right Arm
  addBlock(1.15, 1.0, 1.15,  0.0,  4.55, 0); // Head

  group.position.set(-3.2, 0, 0);
  group.visible = false;
  return group;
}
const r15Dummy = createR15ScaleDummy();
scene.add(r15Dummy);

let assetRoot = new THREE.Group();
scene.add(assetRoot);
let originalMaterials = new Map();
let wireOverlayGroup = new THREE.Group();
scene.add(wireOverlayGroup);

const gltfLoader = new GLTFLoader();
const texLoader = new THREE.TextureLoader();

function resizeViewport() {
  const w = container.clientWidth || 640;
  const h = container.clientHeight || 480;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}
window.addEventListener('resize', resizeViewport);
new ResizeObserver(resizeViewport).observe(container);

function frameCurrentAsset() {
  const box = new THREE.Box3().setFromObject(assetRoot);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 1.0);

  controls.target.copy(center);
  camera.position.set(center.x + maxDim * 1.45, center.y + maxDim * 0.95, center.z + maxDim * 1.65);
  controls.update();

  // Position R15 dummy neatly beside the asset without overlapping
  r15Dummy.position.set(-(size.x * 0.5 + 2.2), 0, 0);
}

function rebuildWireframeOverlay() {
  scene.remove(wireOverlayGroup);
  wireOverlayGroup = new THREE.Group();
  if (state.wireframe) {
    assetRoot.traverse((child) => {
      if (child.isMesh && child.geometry) {
        const wfGeo = new THREE.WireframeGeometry(child.geometry);
        const wfMat = new THREE.LineBasicMaterial({
          color: 0x38bdf8,
          transparent: true,
          opacity: 0.42,
        });
        const lines = new THREE.LineSegments(wfGeo, wfMat);
        lines.position.copy(child.position);
        lines.rotation.copy(child.rotation);
        lines.scale.copy(child.scale);
        child.updateWorldMatrix(true, false);
        lines.applyMatrix4(child.matrixWorld);
        wireOverlayGroup.add(lines);
      }
    });
  }
  scene.add(wireOverlayGroup);
}

function applyShadingMode() {
  assetRoot.traverse((child) => {
    if (!child.isMesh) return;
    const orig = originalMaterials.get(child.uuid);
    if (!orig) return;

    if (state.shadingMode === 'pbr') {
      child.material = orig;
    } else if (state.shadingMode === 'albedo') {
      child.material = new THREE.MeshBasicMaterial({
        map: orig.map || null,
        color: orig.map ? 0xffffff : orig.color,
      });
    } else if (state.shadingMode === 'normal') {
      if (orig.normalMap) {
        child.material = new THREE.MeshBasicMaterial({ map: orig.normalMap });
      } else {
        child.material = new THREE.MeshNormalMaterial();
      }
    } else if (state.shadingMode === 'roughmetal') {
      child.material = new THREE.MeshBasicMaterial({
        map: orig.metalnessMap || orig.roughnessMap || null,
        color: 0xffffff,
      });
    } else if (state.shadingMode === 'clay') {
      child.material = new THREE.MeshStandardMaterial({
        color: 0x94a3b8,
        roughness: 0.58,
        metalness: 0.08,
      });
    }
  });
}

function loadGlbIntoViewport(glbUrl) {
  return new Promise((resolve, reject) => {
    gltfLoader.load(
      glbUrl,
      (gltf) => {
        scene.remove(assetRoot);
        originalMaterials.clear();

        assetRoot = gltf.scene;
        assetRoot.traverse((child) => {
          if (child.isMesh && child.material) {
            originalMaterials.set(child.uuid, child.material);
          }
        });
        scene.add(assetRoot);
        applyShadingMode();
        rebuildWireframeOverlay();
        frameCurrentAsset();
        resolve();
      },
      undefined,
      (err) => reject(err)
    );
  });
}

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  if (state.turntable && assetRoot) {
    assetRoot.rotation.y += dt * 0.55;
    if (state.wireframe && wireOverlayGroup) {
      wireOverlayGroup.rotation.y = assetRoot.rotation.y;
    }
  }
  controls.update();
  renderer.render(scene, camera);
}
resizeViewport();
animate();

/* =========================================================================
   UI Wiring & Relative API Calls
   ========================================================================= */
function switchTab(tabId) {
  document.querySelectorAll('.nav-tab').forEach((b) => {
    b.classList.toggle('active', b.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-view').forEach((v) => {
    v.classList.toggle('active', v.id === `tab-${tabId}`);
  });
  if (tabId === 'creator') {
    setTimeout(resizeViewport, 40);
  }
}

document.querySelectorAll('.nav-tab').forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// Shading & Viewport Toolbar Buttons
document.querySelectorAll('#shading-group .vp-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#shading-group .vp-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    state.shadingMode = btn.dataset.shade;
    applyShadingMode();
  });
});

document.getElementById('btn-wireframe').addEventListener('click', (e) => {
  state.wireframe = !state.wireframe;
  e.currentTarget.classList.toggle('active', state.wireframe);
  assetRoot.rotation.y = 0;
  rebuildWireframeOverlay();
});

document.getElementById('btn-turntable').addEventListener('click', (e) => {
  state.turntable = !state.turntable;
  e.currentTarget.classList.toggle('active', state.turntable);
});

document.getElementById('btn-r15-dummy').addEventListener('click', (e) => {
  state.showR15Dummy = !state.showR15Dummy;
  r15Dummy.visible = state.showR15Dummy;
  e.currentTarget.classList.toggle('active', state.showR15Dummy);
});

document.getElementById('btn-reset-cam').addEventListener('click', () => {
  assetRoot.rotation.y = 0;
  if (wireOverlayGroup) wireOverlayGroup.rotation.y = 0;
  frameCurrentAsset();
});

// Sliders & Preset Selector
const selEngine = document.getElementById('sel-engine');
const comfyUrlWrap = document.getElementById('comfy-url-wrap');
function updateEngineInputMode() {
  const singleImage = ['budget3d_turbo', 'comfy_idol'].includes(selEngine.value);
  const comfyEngine = ['comfy_pixal3d', 'comfy_idol'].includes(selEngine.value);
  const comfyIdol = selEngine.value === 'comfy_idol';
  comfyUrlWrap.style.display = comfyEngine ? 'flex' : 'none';
  document.getElementById('idol-mode-wrap').style.display = comfyIdol ? 'flex' : 'none';
  document.querySelectorAll('.view-slot[data-view="left"], .view-slot[data-view="back"], .view-slot[data-view="right"]')
    .forEach((slot) => { slot.style.display = singleImage ? 'none' : 'flex'; });
  document.getElementById('view-input-title').textContent = singleImage
    ? 'Single Image Input (Idol)'
    : 'Multi-View Inputs (2–4 Angles)';
  document.getElementById('idol-input-note').hidden = !singleImage;
  document.getElementById('btn-generate-label').textContent = singleImage
    ? (comfyIdol ? 'Generate Idol Splat + Best-Effort Roblox Mesh' : 'Generate Single-Image Idol Splats')
    : 'Generate Roblox 3D Asset';
  document.getElementById('vp-loading-text').textContent = comfyIdol
    ? 'Running ComfyUI-Idol, splat preview and experimental mesh extraction...'
    : (singleImage
      ? 'Running experimental Budget3D-Idol Turbo single-image generation...'
      : 'Reconstructing 3D Mesh & Baking SurfaceAppearance PBR...');
  if (state.currentJob) {
    const isSplatOnly = state.currentJob.output_type === 'gaussian_splat';
    document.getElementById('roblox-export-panel').hidden = isSplatOnly;
    document.getElementById('gaussian-splat-panel').hidden = !isSplatOnly;
    document.getElementById('pbr-maps-panel').hidden = isSplatOnly;
    document.getElementById('lua-export-panel').hidden = isSplatOnly;
    document.getElementById('idol-artifacts-panel').hidden = !(state.currentJob.splat_url && !isSplatOnly);
  }
}
selEngine.addEventListener('change', updateEngineInputMode);
updateEngineInputMode();

const rngTris = document.getElementById('rng-tris');
const lblTris = document.getElementById('lbl-tris');
rngTris.addEventListener('input', () => {
  lblTris.textContent = `${Number(rngTris.value).toLocaleString()} tris`;
});

const rngStuds = document.getElementById('rng-studs');
const lblStuds = document.getElementById('lbl-studs');
rngStuds.addEventListener('input', () => {
  lblStuds.textContent = `${Number(rngStuds.value).toFixed(1)} st`;
});

const rngMetal = document.getElementById('rng-metal');
const lblMetal = document.getElementById('lbl-metal');
rngMetal.addEventListener('input', () => {
  lblMetal.textContent = Number(rngMetal.value).toFixed(2);
});

const rngRough = document.getElementById('rng-rough');
const lblRough = document.getElementById('lbl-rough');
rngRough.addEventListener('input', () => {
  lblRough.textContent = Number(rngRough.value).toFixed(2);
});

const selPreset = document.getElementById('sel-preset');
function applyPresetValues(presetId) {
  const p = state.presets[presetId];
  if (!p) return;
  selPreset.value = presetId;
  rngTris.value = p.target_tris;
  lblTris.textContent = `${Number(p.target_tris).toLocaleString()} tris`;
  rngStuds.value = p.target_studs;
  lblStuds.textContent = `${Number(p.target_studs).toFixed(1)} st`;
  document.getElementById('sel-texsize').value = String(p.texture_size);
  document.getElementById('preset-hint').textContent = p.description;
}
selPreset.addEventListener('change', () => applyPresetValues(selPreset.value));

// 4-View Uploader Slots
function setSlotPreview(viewName, imgSrc) {
  const slot = document.querySelector(`.view-slot[data-view="${viewName}"]`);
  if (!slot) return;
  let img = slot.querySelector('img');
  const ph = slot.querySelector('.view-placeholder');
  if (imgSrc) {
    if (!img) {
      img = document.createElement('img');
      slot.appendChild(img);
    }
    img.src = imgSrc;
    if (ph) ph.style.display = 'none';
    slot.classList.add('filled');
  } else {
    if (img) img.remove();
    if (ph) ph.style.display = 'block';
    slot.classList.remove('filled');
  }
}

document.querySelectorAll('.view-slot').forEach((slot) => {
  const viewName = slot.dataset.view;
  const fileInp = slot.querySelector('input[type="file"]');
  const clearBtn = slot.querySelector('.view-clear');

  slot.addEventListener('click', (e) => {
    if (e.target === clearBtn) return;
    fileInp.click();
  });

  clearBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    state.uploadedFiles[viewName] = null;
    state.selectedSampleId = null;
    document.querySelectorAll('.sample-card').forEach((c) => c.classList.remove('selected'));
    setSlotPreview(viewName, null);
  });

  fileInp.addEventListener('change', () => {
    const f = fileInp.files[0];
    if (!f) return;
    handleUserViewFile(viewName, f);
    fileInp.value = '';
  });

  slot.addEventListener('dragover', (e) => {
    e.preventDefault();
    slot.classList.add('dragover');
  });
  slot.addEventListener('dragleave', () => slot.classList.remove('dragover'));
  slot.addEventListener('drop', (e) => {
    e.preventDefault();
    slot.classList.remove('dragover');
    const f = e.dataTransfer.files[0];
    if (f) handleUserViewFile(viewName, f);
  });
});

function handleUserViewFile(viewName, file) {
  // If user was viewing a sample, clear sample previews on other slots first
  if (state.selectedSampleId) {
    state.selectedSampleId = null;
    document.querySelectorAll('.sample-card').forEach((c) => c.classList.remove('selected'));
    ['front', 'left', 'back', 'right'].forEach((v) => {
      if (!state.uploadedFiles[v]) setSlotPreview(v, null);
    });
  }
  state.uploadedFiles[viewName] = file;
  const url = URL.createObjectURL(file);
  setSlotPreview(viewName, url);
}

document.getElementById('btn-clear-views').addEventListener('click', () => {
  state.selectedSampleId = null;
  state.uploadedFiles = { front: null, left: null, back: null, right: null };
  document.querySelectorAll('.sample-card').forEach((c) => c.classList.remove('selected'));
  ['front', 'left', 'back', 'right'].forEach((v) => setSlotPreview(v, null));
});

// Sample Cards Rendering & Selection
function renderSampleCards(samples) {
  const grid = document.getElementById('sample-grid');
  grid.innerHTML = '';
  samples.forEach((s) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `sample-card ${s.id === state.selectedSampleId ? 'selected' : ''}`;
    btn.dataset.sampleId = s.id;
    btn.innerHTML = `
      <img class="sample-thumb" src="${s.views.front}" alt="${s.name}" />
      <div class="sample-meta">
        <div class="sample-name" title="${s.name}">${s.name}</div>
        <div class="sample-badge">${s.badge}</div>
      </div>
    `;
    btn.addEventListener('click', () => selectSample(s, true));
    grid.appendChild(btn);
  });
}

function selectSample(sampleObj, triggerGenerate = false) {
  state.selectedSampleId = sampleObj.id;
  state.uploadedFiles = { front: null, left: null, back: null, right: null };
  document.querySelectorAll('.sample-card').forEach((c) => {
    c.classList.toggle('selected', c.dataset.sampleId === sampleObj.id);
  });

  ['front', 'left', 'back', 'right'].forEach((v) => {
    setSlotPreview(v, sampleObj.views[v]);
  });

  document.getElementById('inp-asset-name').value = sampleObj.name.replace(/\s+/g, '_');
  applyPresetValues(sampleObj.preset_id);
  rngMetal.value = sampleObj.metallic_bias;
  lblMetal.textContent = Number(sampleObj.metallic_bias).toFixed(2);
  rngRough.value = sampleObj.roughness_bias;
  lblRough.textContent = Number(sampleObj.roughness_bias).toFixed(2);

  if (triggerGenerate) {
    runGeneration();
  }
}

// Update UI with a completed Job Response
async function applyJobResult(job) {
  state.currentJob = job;
  const isSplatOutput = job.output_type === 'gaussian_splat';
  document.getElementById('roblox-export-panel').hidden = isSplatOutput;
  document.getElementById('gaussian-splat-panel').hidden = !isSplatOutput;
  document.getElementById('pbr-maps-panel').hidden = isSplatOutput;
  document.getElementById('lua-export-panel').hidden = isSplatOutput;
  document.getElementById('idol-artifacts-panel').hidden = !(job.splat_url && !isSplatOutput);

  if (job.splat_url) {
    document.getElementById('dl-idol-ply').href = job.splat_url;
    const previewImg = document.getElementById('idol-preview-img');
    previewImg.hidden = !job.idol_preview_url;
    if (job.idol_preview_url) previewImg.src = job.idol_preview_url;
    const turntable = document.getElementById('dl-idol-turntable');
    turntable.hidden = !job.idol_turntable_url;
    if (job.idol_turntable_url) turntable.href = job.idol_turntable_url;
  }

  if (isSplatOutput) {
    document.getElementById('dl-splat-ply').href = job.splat_url;
    document.getElementById('splat-output-title').textContent = job.engine_note.includes('ComfyUI-Idol')
      ? 'ComfyUI-Idol Gaussian Splat Output'
      : 'Budget3D Gaussian Splat Output';
    document.getElementById('splat-output-note').textContent = job.engine_note;
    const splatPreview = document.getElementById('splat-preview-img');
    splatPreview.hidden = !job.idol_preview_url;
    if (job.idol_preview_url) splatPreview.src = job.idol_preview_url;
    const splatTurntable = document.getElementById('dl-splat-turntable');
    splatTurntable.hidden = !job.idol_turntable_url;
    if (job.idol_turntable_url) splatTurntable.href = job.idol_turntable_url;
    const timeTag = job.elapsed_sec > 0 ? ` (${job.elapsed_sec}s)` : '';
    document.getElementById('engine-banner').textContent =
      `${job.engine_note}${timeTag} The viewport is still showing the previous mesh.`;
    document.getElementById('hud-tris').textContent = 'N/A — Gaussian PLY';
    document.getElementById('hud-tri-bar').style.width = '0%';
    document.getElementById('hud-pass-badge').textContent = 'PLY ONLY';
    document.getElementById('hud-pass-badge').classList.add('warn');
    document.getElementById('hud-dims').textContent = 'Not measured';
    document.getElementById('hud-topo').textContent = 'Gaussian splat; not a Roblox mesh';
    return;
  }

  document.getElementById('hud-pass-badge').classList.remove('warn');
  const st = job.stats;

  // Update Export Links
  document.getElementById('dl-zip').href = job.zip_url;
  document.getElementById('dl-glb').href = job.glb_url;
  document.getElementById('dl-obj').href = job.obj_url;

  // Update 4 SurfaceAppearance PBR Map Cards
  ['ColorMap', 'NormalMap', 'MetalnessMap', 'RoughnessMap'].forEach((m) => {
    const imgEl = document.getElementById(`img-${m}`);
    if (imgEl && job.maps[m]) imgEl.src = job.maps[m];
  });
  document.getElementById('lbl-map-res').textContent = `${st.texture_size}×${st.texture_size}`;

  // Update Luau Script
  document.getElementById('lua-code-box').textContent = job.lua_script;

  // Update Compliance HUD
  const cap = st.hard_cap || 21000;
  document.getElementById('hud-tris').textContent = `${st.final_triangles.toLocaleString()} / ${cap.toLocaleString()}`;
  const pct = Math.min(100, Math.round((st.final_triangles / cap) * 100));
  document.getElementById('hud-tri-bar').style.width = `${pct}%`;

  const badge = document.getElementById('hud-pass-badge');
  if (st.passes_preset_cap) {
    badge.textContent = 'STUDIO PASS';
    badge.classList.remove('warn');
  } else {
    badge.textContent = 'OVER PRESET';
    badge.classList.add('warn');
  }

  const d = st.dimensions_studs;
  document.getElementById('hud-dims').textContent = `${d.x} × ${d.y} × ${d.z} studs`;
  document.getElementById('hud-topo').textContent =
    `${st.is_watertight ? 'Watertight' : 'Manifold'} • 4× ${st.texture_size}px PNG`;

  if (job.engine_note) {
    const timeTag = job.elapsed_sec > 0 ? ` (${job.elapsed_sec}s)` : '';
    document.getElementById('engine-banner').textContent = `${job.engine_note}${timeTag}`;
  }

  await loadGlbIntoViewport(job.glb_url);
}

// Generate Roblox 3D Asset Action
async function runGeneration() {
  const btn = document.getElementById('btn-generate');
  const lbl = document.getElementById('btn-generate-label');
  const overlay = document.getElementById('vp-loading');

  const idolSingleImage = ['budget3d_turbo', 'comfy_idol'].includes(selEngine.value);
  const comfyIdol = selEngine.value === 'comfy_idol';
  const hasUploads = idolSingleImage
    ? Boolean(state.uploadedFiles.front)
    : Object.values(state.uploadedFiles).some(Boolean);
  if (!hasUploads && !state.selectedSampleId) {
    alert(idolSingleImage
      ? `Upload one image in the Front slot for ${comfyIdol ? 'ComfyUI-Idol' : 'Budget3D-Idol Turbo'}.`
      : 'Upload 1–4 turnaround images (Front/Left/Back/Right) or click a Sample Sheet first!');
    return;
  }

  btn.disabled = true;
  lbl.textContent = comfyIdol
    ? 'Generating Idol splat, mesh and turntable...'
    : (idolSingleImage ? 'Generating Idol Gaussian PLY...' : 'Generating 3D + PBR...');
  overlay.classList.add('visible');

  try {
    const fd = new FormData();
    fd.append('engine', selEngine.value);
    fd.append('comfy_url', document.getElementById('inp-comfy-url').value.trim());
    fd.append('asset_name', document.getElementById('inp-asset-name').value.trim() || 'Roblox_Asset');
    fd.append('preset_id', selPreset.value);
    fd.append('target_tris', rngTris.value);
    fd.append('texture_size', document.getElementById('sel-texsize').value);
    fd.append('target_studs', rngStuds.value);
    fd.append('metallic_bias', rngMetal.value);
    fd.append('roughness_bias', rngRough.value);
    fd.append('idol_mode', document.getElementById('sel-idol-mode').value);

    if (hasUploads) {
      const viewsToSend = idolSingleImage ? ['front'] : ['front', 'left', 'back', 'right'];
      viewsToSend.forEach((v) => {
        if (state.uploadedFiles[v]) fd.append(v, state.uploadedFiles[v]);
      });
    } else if (state.selectedSampleId) {
      fd.append('sample_id', state.selectedSampleId);
    }

    const resp = await fetch('/api/generate', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || 'Generation failed.');
    }
    await applyJobResult(data);
  } catch (err) {
    alert(`Generation Notice:\n${err.message}`);
  } finally {
    btn.disabled = false;
    lbl.textContent = selEngine.value === 'budget3d_turbo'
      ? 'Generate Single-Image Idol Splats'
      : (selEngine.value === 'comfy_idol'
        ? 'Generate Idol Splat + Best-Effort Roblox Mesh'
        : 'Generate Roblox 3D Asset');
    overlay.classList.remove('visible');
  }
}
document.getElementById('btn-generate').addEventListener('click', runGeneration);

// Copy Luau Script
document.getElementById('btn-copy-lua').addEventListener('click', async (e) => {
  const btn = e.currentTarget;
  const txt = document.getElementById('lua-code-box').textContent;
  await navigator.clipboard.writeText(txt);
  const prev = btn.textContent;
  btn.textContent = 'Copied!';
  setTimeout(() => { btn.textContent = prev; }, 1400);
});

// PBR Map Lightbox Modal
const modal = document.getElementById('map-modal');
document.querySelectorAll('.pbr-card').forEach((card) => {
  card.addEventListener('click', () => {
    const mName = card.dataset.map;
    if (!state.currentJob || !state.currentJob.maps[mName]) return;
    const url = state.currentJob.maps[mName];
    document.getElementById('modal-map-title').textContent =
      `Roblox SurfaceAppearance — ${mName}.png (${state.currentJob.stats.texture_size}×${state.currentJob.stats.texture_size})`;
    document.getElementById('modal-map-img').src = url;
    const dl = document.getElementById('modal-map-dl');
    dl.href = url;
    dl.download = `${mName}.png`;
    modal.classList.add('open');
  });
});
document.getElementById('modal-close').addEventListener('click', () => modal.classList.remove('open'));
modal.addEventListener('click', (e) => {
  if (e.target === modal) modal.classList.remove('open');
});

/* =========================================================================
   Tab 2: Existing .GLB / .OBJ Decimator & SurfaceAppearance Unpacker
   ========================================================================= */
const optDrop = document.getElementById('opt-dropzone');
const optInput = document.getElementById('opt-file-input');
const optLabel = document.getElementById('opt-file-label');
const optPreset = document.getElementById('opt-preset');

optDrop.addEventListener('click', () => optInput.click());
optDrop.addEventListener('dragover', (e) => { e.preventDefault(); });
optDrop.addEventListener('drop', (e) => {
  e.preventDefault();
  if (e.dataTransfer.files[0]) {
    state.optSelectedFile = e.dataTransfer.files[0];
    optLabel.textContent = `Selected: ${state.optSelectedFile.name}`;
  }
});
optInput.addEventListener('change', () => {
  if (optInput.files[0]) {
    state.optSelectedFile = optInput.files[0];
    optLabel.textContent = `Selected: ${state.optSelectedFile.name}`;
  }
});
optPreset.addEventListener('change', () => {
  const p = state.presets[optPreset.value];
  if (p) {
    document.getElementById('opt-tris').value = p.target_tris;
    document.getElementById('opt-studs').value = p.target_studs;
  }
});

document.getElementById('btn-run-optimize').addEventListener('click', async (e) => {
  const btn = e.currentTarget;
  if (!state.optSelectedFile) {
    alert('Select a .glb, .obj, or .ply file first!');
    return;
  }
  btn.disabled = true;
  btn.textContent = 'Decimating & Splitting PBR...';
  try {
    const fd = new FormData();
    fd.append('mesh_file', state.optSelectedFile);
    fd.append('asset_name', document.getElementById('opt-name').value.trim() || 'Optimized_MeshPart');
    fd.append('preset_id', optPreset.value);
    fd.append('target_tris', document.getElementById('opt-tris').value);
    fd.append('target_studs', document.getElementById('opt-studs').value);

    const resp = await fetch('/api/optimize-mesh', { method: 'POST', body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || 'Mesh optimization failed.');

    await applyJobResult(data);
    document.getElementById('opt-status-msg').innerHTML =
      `Success! Decimated from <strong>${data.stats.raw_triangles.toLocaleString()}</strong> to <strong>${data.stats.final_triangles.toLocaleString()}</strong> triangles and unpacked 4 SurfaceAppearance PNGs. Switching to 3D Viewport...`;
    setTimeout(() => switchTab('creator'), 650);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Decimate & Split SurfaceAppearance PBR';
  }
});

/* =========================================================================
   Tab 3: Render Verified Hugging Face 6 GB Multi-View Model Catalog
   ========================================================================= */
function populateNonRunnableModelOptions(models) {
  const group = document.getElementById('catalog-only-engines');
  if (!group) return;
  const runnableCatalogIds = new Set(['pixal3d_mv', 'hunyuan3d_2mv']);
  const catalogOnly = models.filter((model) => !runnableCatalogIds.has(model.id));
  group.replaceChildren();
  group.hidden = catalogOnly.length === 0;
  catalogOnly.forEach((model) => {
    const option = document.createElement('option');
    option.value = `catalog_only:${model.id}`;
    option.disabled = true;
    option.textContent = `${model.name} — catalog only, not runnable yet`;
    option.title = model.verdict || 'This catalog model does not have a generation backend in this app yet.';
    group.appendChild(option);
  });
}

function renderHfModelCatalog(models) {
  const tbody = document.getElementById('hf-models-tbody');
  tbody.innerHTML = '';
  models.forEach((m) => {
    const tr = document.createElement('tr');
    if (m.recommended) tr.className = 'rec-row';
    const reposHtml = m.hf_repos.map((r) => `<code>${r}</code>`).join('<br/>');
    tr.innerHTML = `
      <td>
        <strong>#${m.rank} ${m.name}</strong>
        ${m.recommended ? '<div style="margin-top:4px;"><span class="tag-6gb">Best for 6GB + Roblox</span></div>' : ''}
        <div style="color:var(--text-muted);font-size:11px;margin-top:4px;">${m.verdict}</div>
      </td>
      <td style="font-size:11px;">${reposHtml}</td>
      <td>${m.release_date}</td>
      <td style="font-family:var(--font-mono);font-size:11px;">
        ${m.downloads_30d.toLocaleString()} / mo<br/>
        <span style="color:var(--text-dim);">${m.downloads_all_time.toLocaleString()} total</span>
      </td>
      <td>
        <div><strong>VRAM:</strong> ${m.vram_gb}</div>
        <div style="color:var(--text-muted);font-size:11px;"><strong>RAM:</strong> ${m.ram_gb}</div>
      </td>
      <td>
        <div><strong>PBR:</strong> ${m.pbr ? 'Native 4-Map PBR' : 'Shape Only (+Cam Bake)'}</div>
        <div style="color:var(--text-muted);font-size:11px;">${m.license}</div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

/* =========================================================================
   Initial Boot
   ========================================================================= */
async function initApp() {
  try {
    const [statusResp, samplesResp] = await Promise.all([
      fetch('/api/status'),
      fetch('/api/samples'),
    ]);
    const statusData = await statusResp.json();
    const samplesData = await samplesResp.json();

    state.presets = statusData.presets || {};
    state.samples = samplesData.samples || [];

    // Populate Hardware Pill
    const hw = statusData.hardware;
    const hwTxt = document.getElementById('hw-status-text');
    if (hw.comfy_pixal3d && hw.comfy_pixal3d.online) {
      hwTxt.textContent = `ComfyUI Pixal3D Online (${hw.gpu_name || 'GPU'}) • ${hw.system_ram_gb} GB RAM`;
    } else if (hw.hunyuan_2mv_ready) {
      hwTxt.textContent = `Hunyuan3D-2mv CUDA Ready • ${hw.system_ram_gb} GB RAM`;
    } else {
      hwTxt.textContent = `Local Studio Ready (${hw.system_ram_gb} GB RAM • CPU Sculpt Active, ComfyUI 6GB Ready)`;
    }

    renderSampleCards(state.samples);
    populateNonRunnableModelOptions(statusData.hf_models || []);
    renderHfModelCatalog(statusData.hf_models || []);

    // Pre-populate Dragon Helm 4-view previews & load starter 3D asset into viewport
    const helm = state.samples.find((s) => s.id === 'dragon_helm') || state.samples[0];
    if (helm) {
      selectSample(helm, false);
    }
    if (statusData.starter_asset) {
      await applyJobResult(statusData.starter_asset);
    }
  } catch (err) {
    console.error('Initialization error:', err);
    document.getElementById('hw-status-text').textContent = 'Backend connection error';
  }
}

initApp();
