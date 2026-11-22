const $ = (id) => document.getElementById(id);
let blenderReady = false;
let currentSpec = null;
const referenceFiles = { hero: null, side: null, front: null, spec: null };
const referenceLabels = { hero: 'Hero shot', side: 'Side view', front: 'Front view', spec: 'Spec sheet / extra view' };
let toastTimer;

function toast(message, error = false) {
  const el = $('toast');
  el.textContent = message;
  el.classList.toggle('error', error);
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 4400);
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { data = { detail: await response.text() }; }
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function parseSpec() {
  try {
    const spec = JSON.parse($('spec-json').value);
    if (!spec || typeof spec !== 'object' || Array.isArray(spec)) throw new Error('The spec root must be a JSON object.');
    currentSpec = spec;
    return spec;
  } catch (err) {
    throw new Error(`Invalid JSON: ${err.message}`);
  }
}

function syncBuildButton() {
  $('build-asset').disabled = !(blenderReady && $('approve-spec').checked);
}

function setBlenderState(state, message) {
  blenderReady = state === 'good';
  const node = $('blender-status');
  node.className = `status-card state-${state}`;
  node.innerHTML = '<span class="dot"></span><span></span>';
  node.querySelector('span:last-child').textContent = message;
  syncBuildButton();
}

function setupReferenceSlots() {
  document.querySelectorAll('.ref-card').forEach(card => {
    const slot = card.dataset.slot;
    const input = card.querySelector('.ref-input');
    const choose = card.querySelector('.ref-choose');
    const remove = card.querySelector('.ref-remove');
    const preview = card.querySelector('.ref-preview');
    const image = preview.querySelector('img');
    const placeholder = preview.querySelector('span');
    const filename = card.querySelector('.ref-file-name');

    choose.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      input.value = '';
      if (!file) return;
      if (file.size > 10 * 1024 * 1024) return toast('Each reference image must be 10 MB or smaller.', true);
      if (!file.type.startsWith('image/')) return toast('Choose an image file for this view.', true);
      if (card.dataset.objectUrl) URL.revokeObjectURL(card.dataset.objectUrl);
      const url = URL.createObjectURL(file);
      card.dataset.objectUrl = url;
      referenceFiles[slot] = file;
      image.src = url;
      image.hidden = false;
      placeholder.hidden = true;
      filename.textContent = file.name;
      filename.title = file.name;
      filename.hidden = false;
      remove.hidden = false;
      choose.textContent = 'Replace image';
    });
    remove.addEventListener('click', () => {
      if (card.dataset.objectUrl) URL.revokeObjectURL(card.dataset.objectUrl);
      delete card.dataset.objectUrl;
      referenceFiles[slot] = null;
      image.removeAttribute('src');
      image.hidden = true;
      placeholder.hidden = false;
      filename.textContent = '';
      filename.hidden = true;
      remove.hidden = true;
      choose.textContent = 'Choose image';
      input.value = '';
    });
  });
}

function orderedReferences() {
  return ['hero', 'side', 'front', 'spec']
    .filter(slot => referenceFiles[slot])
    .map(slot => ({ label: referenceLabels[slot], file: referenceFiles[slot] }));
}

function showResult(value, success = true) {
  $('result-panel').classList.remove('hidden');
  $('result-pill').textContent = success ? 'BUILD COMPLETE' : 'BUILD FAILED';
  $('result-text').textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const links = $('download-row');
  links.replaceChildren();
  if (value && value.spec_path) {
    for (const [title, ext] of [['Download GLB', 'glb'], ['Download approved spec', 'json']]) {
      const a = document.createElement('a');
      const filename = ext === 'glb' ? value.output_filename : `${value.output_filename.slice(0, -4)}.json`;
      a.href = `/api/output/${encodeURIComponent(filename)}`;
      a.textContent = title;
      a.download = filename;
      links.appendChild(a);
    }
  }
  $('result-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function loadStarter() {
  try {
    currentSpec = await request('/api/starter-spec');
    $('spec-json').value = JSON.stringify(currentSpec, null, 2);
    $('approve-spec').checked = false;
    syncBuildButton();
    toast('Starter spec loaded. Check the provisional values before build.');
  } catch (err) { toast(err.message, true); }
}

async function checkApp() {
  try {
    const data = await request('/api/health');
    $('app-status').innerHTML = `<span class="pulse"></span><span></span>`;
    $('app-status').querySelector('span:last-child').textContent = `Local app ready · output ${data.output_directory}`;
    $('vlm-note').textContent = data.vlm_configured
      ? `Local ${data.vlm_provider} VLM configured: ${data.vlm_model}. Draft requests and reference images go only to its local endpoint.`
      : 'No local VLM endpoint configured. Edit the included Gobble Rail JSON manually, or set POC_VLM_URL in PowerShell to enable local text + image drafting.';
  } catch (err) {
    $('app-status').textContent = `App health check failed: ${err.message}`;
  }
}

$('check-blender').addEventListener('click', async () => {
  setBlenderState('unknown', 'Testing MCP server and Blender add-on…');
  try {
    const data = await request('/api/blender/status');
    setBlenderState('good', `Connected · ${data.server} · ${data.tools.length} tools`);
    $('blender-status').title = data.addon_status;
    toast(`Confirmed: add-on status responded. ${data.addon_status.slice(0, 150)}`);
  } catch (err) {
    setBlenderState('bad', `Not connected · ${err.message}`);
    toast(err.message, true);
  }
});

setupReferenceSlots();
$('approve-spec').addEventListener('change', syncBuildButton);
$('load-starter').addEventListener('click', loadStarter);

$('draft-spec').addEventListener('click', async () => {
  const prompt = $('prompt').value.trim();
  if (!prompt) return toast('Add a short design brief first.', true);
  const references = orderedReferences();
  const form = new FormData();
  form.set('prompt', prompt);
  for (const reference of references) form.append('references', reference.file, reference.file.name);
  form.set('reference_labels', JSON.stringify(references.map(reference => reference.label)));
  const button = $('draft-spec');
  button.disabled = true;
  button.textContent = 'Drafting locally…';
  try {
    const data = await request('/api/draft-spec', { method: 'POST', body: form });
    currentSpec = data.spec;
    $('spec-json').value = JSON.stringify(data.spec, null, 2);
    $('approve-spec').checked = false;
    syncBuildButton();
    const unknownCount = (data.unknowns || []).length;
    toast(`Draft ready. Review ${unknownCount} unknown/provisional item(s) before building.`);
  } catch (err) { toast(err.message, true); }
  finally { button.disabled = false; button.textContent = 'Draft spec with local VLM'; }
});

$('build-asset').addEventListener('click', async () => {
  if (!blenderReady) return toast('Test Blender MCP and confirm the add-on status first.', true);
  if (!$('approve-spec').checked) return toast('Review and approve the spec first.', true);
  let spec;
  try { spec = parseSpec(); } catch (err) { return toast(err.message, true); }
  spec.approval = { ...(spec.approval || {}), reviewed_by_user: true };
  $('spec-json').value = JSON.stringify(spec, null, 2);
  const button = $('build-asset');
  button.disabled = true;
  button.querySelector('span:first-child').textContent = 'Building through Blender MCP…';
  try {
    const data = await request('/api/build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec, prompt: $('prompt').value.trim() })
    });
    showResult(data, true);
    toast('Blender MCP completed the build. The GLB and approved JSON are on this PC.');
  } catch (err) {
    showResult(err.message, false);
    toast(err.message, true);
  } finally {
    button.querySelector('span:first-child').textContent = 'Build in Blender';
    syncBuildButton();
  }
});

loadStarter();
checkApp();
