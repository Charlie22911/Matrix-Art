let demos = [];
let currentDemo = null;
let dirty = false;

const STARTER_CODE = `import math\n\nNAME = "New Demo"\nDEFAULT_FPS = 24\nPARAMS = {\n    "speed": {"type": "float", "default": 1.0},\n}\n\ndef render(ctx, t, dt, frame, params):\n    frame.fill(0, 0, 0)\n    cx = ctx.width // 2\n    cy = ctx.height // 2\n    radius = 18\n    a = t * float(params.get("speed", 1.0))\n    x = int(cx + math.cos(a) * radius)\n    y = int(cy + math.sin(a) * radius)\n    frame.circle(cx, cy, 12, 0, 40, 90)\n    frame.circle(x, y, 5, 255, 80, 20, fill=True)\n`;

function qs(id) { return document.getElementById(id); }

async function postJson(url, data = {}) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

async function getJson(url) {
  const res = await fetch(url);
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

function setStatus(text) {
  const box = qs('demoStatus');
  if (box) box.textContent = text;
}

function setError(text) {
  const box = qs('demoError');
  if (!box) return;
  box.textContent = text || '';
  box.hidden = !text;
}

function setDirty(value) {
  dirty = !!value;
  const flag = qs('dirtyFlag');
  if (!flag) return;
  if (!currentDemo) {
    flag.textContent = dirty ? 'New unsaved demo.' : 'New demo.';
    return;
  }
  flag.textContent = dirty ? 'Unsaved changes.' : `Saved: ${currentDemo.updated_at || ''}`;
}

function updateStats() {
  const code = qs('demoCode')?.value || '';
  const lines = code ? code.split('\n').length : 0;
  const bytes = new Blob([code]).size;
  const stats = qs('codeStats');
  if (stats) stats.textContent = `${lines} lines · ${bytes} bytes`;
}

function payloadFromEditor() {
  return {
    title: qs('demoTitle')?.value || 'New Demo',
    description: qs('demoDescription')?.value || '',
    default_fps: Number(qs('demoFpsInput')?.value || 24),
    enabled: qs('demoEnabledBtn')?.dataset.enabled === '1',
    code: qs('demoCode')?.value || '',
  };
}

function setEnabledButton(enabled) {
  const btn = qs('demoEnabledBtn');
  if (!btn) return;
  btn.dataset.enabled = enabled ? '1' : '0';
  btn.textContent = enabled ? 'Enabled' : 'Disabled';
  btn.classList.toggle('enabled', enabled);
  btn.classList.toggle('disabled', !enabled);
}

function setEditorEnabled(enabled) {
  for (const id of ['demoTitle', 'demoDescription', 'demoFpsInput', 'demoCode', 'demoEnabledBtn', 'checkBtn', 'runDraftBtn', 'copyBtn']) {
    const el = qs(id);
    if (el) el.disabled = !enabled;
  }
  const canSave = enabled && (!currentDemo || !currentDemo.builtin);
  const canRunSaved = enabled && currentDemo && currentDemo.enabled;
  const canDelete = enabled && currentDemo && !currentDemo.builtin;
  if (qs('saveBtn')) qs('saveBtn').disabled = !canSave;
  if (qs('runSavedBtn')) qs('runSavedBtn').disabled = !canRunSaved;
  if (qs('deleteDemoBtn')) qs('deleteDemoBtn').disabled = !canDelete;
}

function renderDemoList() {
  const list = qs('demoList');
  if (!list) return;
  list.innerHTML = '';
  for (const demo of demos) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'demo-list-item';
    btn.dataset.id = demo.id;
    btn.classList.toggle('active', currentDemo && Number(currentDemo.id) === Number(demo.id));
    btn.classList.toggle('disabled', !demo.enabled);
    btn.innerHTML = `
      <span class="demo-list-title"></span>
      <span class="demo-list-meta"></span>
    `;
    btn.querySelector('.demo-list-title').textContent = demo.title;
    btn.querySelector('.demo-list-meta').textContent = `${demo.default_fps} FPS${demo.builtin ? ' · built-in' : ''}${demo.enabled ? '' : ' · disabled'}`;
    btn.addEventListener('click', () => maybeLoadDemo(demo.id));
    list.appendChild(btn);
  }
  const count = qs('demoCount');
  if (count) count.textContent = demos.length;
}

async function refreshDemoList(selectedId = null) {
  const body = await getJson('/api/demos');
  demos = body.demos || [];
  renderDemoList();
  if (selectedId) await loadDemo(selectedId);
}

async function maybeLoadDemo(id) {
  if (dirty && !confirm('Discard unsaved changes and load another demo?')) return;
  await loadDemo(id);
}

function showVersions(versions) {
  const box = qs('versionList');
  if (!box) return;
  if (!versions || !versions.length) {
    box.textContent = 'No saved versions yet.';
    return;
  }
  box.innerHTML = '';
  for (const version of versions) {
    const div = document.createElement('div');
    div.className = 'version-row';
    div.textContent = `${version.created_at} · ${version.note || 'version'} · ${version.bytes || 0} bytes`;
    box.appendChild(div);
  }
}

async function loadDemo(id) {
  setError('');
  const body = await getJson(`/api/demos/${id}`);
  currentDemo = body.demo;
  qs('demoTitle').value = currentDemo.title || '';
  qs('demoDescription').value = currentDemo.description || '';
  qs('demoFpsInput').value = currentDemo.default_fps || 24;
  qs('demoCode').value = currentDemo.code || '';
  setEnabledButton(!!currentDemo.enabled);
  qs('editorHeading').textContent = currentDemo.title || 'Demo editor';
  qs('editorMeta').textContent = currentDemo.builtin
    ? `${currentDemo.slug} · built-in example · read-only until saved as copy`
    : `${currentDemo.slug} · editable demo`;
  showVersions(body.versions || []);
  setDirty(false);
  updateStats();
  setEditorEnabled(true);
  renderDemoList();
  setStatus(`Loaded ${currentDemo.title}.`);
}

function newDemo() {
  if (dirty && !confirm('Discard unsaved changes and create a new demo?')) return;
  currentDemo = null;
  qs('demoTitle').value = 'New Demo';
  qs('demoDescription').value = 'A browser-created Python visual effect.';
  qs('demoFpsInput').value = 24;
  qs('demoCode').value = STARTER_CODE;
  qs('editorHeading').textContent = 'New demo';
  qs('editorMeta').textContent = 'Unsaved custom demo';
  setEnabledButton(true);
  showVersions([]);
  setDirty(true);
  updateStats();
  setEditorEnabled(true);
  renderDemoList();
  setStatus('New demo ready. Run the draft or save it to the library.');
}

async function checkCode() {
  setError('');
  try {
    const body = await postJson('/api/demos/check', {code: qs('demoCode').value || ''});
    setStatus(body.message || 'Syntax check passed.');
  } catch (err) {
    setStatus(`Check failed: ${err.message}`);
    setError(err.message);
  }
}

async function runDraft() {
  setError('');
  try {
    const body = await postJson('/api/demos/run-draft', payloadFromEditor());
    setStatus(`Running ${body.title} at ${body.fps} FPS.`);
    await refreshDemoStatus();
  } catch (err) {
    setStatus(`Run failed: ${err.message}`);
    setError(err.message);
  }
}

async function runSaved() {
  if (!currentDemo) return;
  setError('');
  try {
    const body = await postJson(`/api/demos/${currentDemo.id}/run`);
    setStatus(`Running saved demo ${body.title} at ${body.fps} FPS.`);
    await refreshDemoStatus();
  } catch (err) {
    setStatus(`Run failed: ${err.message}`);
    setError(err.message);
  }
}

async function saveDemo() {
  setError('');
  try {
    let body;
    if (!currentDemo) {
      body = await postJson('/api/demos/new', payloadFromEditor());
    } else if (currentDemo.builtin) {
      body = await postJson(`/api/demos/${currentDemo.id}/copy`, payloadFromEditor());
    } else {
      body = await postJson(`/api/demos/${currentDemo.id}/save`, payloadFromEditor());
    }
    currentDemo = body.demo;
    await refreshDemoList(currentDemo.id);
    setStatus(`Saved ${currentDemo.title}.`);
    setDirty(false);
  } catch (err) {
    setStatus(`Save failed: ${err.message}`);
    setError(err.message);
  }
}

async function saveAsCopy() {
  setError('');
  try {
    let body;
    if (currentDemo) {
      body = await postJson(`/api/demos/${currentDemo.id}/copy`, payloadFromEditor());
    } else {
      const payload = payloadFromEditor();
      payload.title = `${payload.title || 'New Demo'} copy`;
      body = await postJson('/api/demos/new', payload);
    }
    currentDemo = body.demo;
    await refreshDemoList(currentDemo.id);
    setStatus(`Saved copy as ${currentDemo.title}.`);
    setDirty(false);
  } catch (err) {
    setStatus(`Save copy failed: ${err.message}`);
    setError(err.message);
  }
}

async function deleteDemo() {
  if (!currentDemo || currentDemo.builtin) return;
  if (!confirm(`Delete demo "${currentDemo.title}"?`)) return;
  try {
    await postJson(`/api/demos/${currentDemo.id}/delete`);
    const deletedId = currentDemo.id;
    currentDemo = null;
    await refreshDemoList();
    const next = demos.find(d => d.id !== deletedId);
    if (next) await loadDemo(next.id);
    else newDemo();
    setStatus('Deleted demo.');
  } catch (err) {
    setStatus(`Delete failed: ${err.message}`);
    setError(err.message);
  }
}

async function refreshDemoStatus() {
  try {
    const body = await fetch('/api/demos/status').then(r => r.json());
    if (!body.ok) return;
    qs('demoRunning').textContent = body.running ? 'YES' : 'NO';
    qs('demoFps').textContent = body.fps || 0;
    qs('demoFrames').textContent = body.frames_rendered || 0;
    const line = qs('demoStatusLine');
    if (line) line.textContent = body.running ? `Demo: ${body.title}` : 'Demo: stopped';
    if (body.last_error) setError(body.last_error);
    const img = qs('currentPreview');
    if (img && body.running) img.src = `/current.png?t=${Date.now()}`;
  } catch (_) {}
}

function hookEditor() {
  for (const id of ['demoTitle', 'demoDescription', 'demoFpsInput', 'demoCode']) {
    const el = qs(id);
    el?.addEventListener('input', () => { setDirty(true); updateStats(); });
  }
  qs('demoEnabledBtn')?.addEventListener('click', () => {
    const enabled = qs('demoEnabledBtn').dataset.enabled !== '1';
    setEnabledButton(enabled);
    setDirty(true);
  });

  qs('demoCode')?.addEventListener('keydown', (ev) => {
    if (ev.key === 'Tab') {
      ev.preventDefault();
      const target = ev.currentTarget;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const spaces = '    ';
      target.value = target.value.slice(0, start) + spaces + target.value.slice(end);
      target.selectionStart = target.selectionEnd = start + spaces.length;
      setDirty(true);
      updateStats();
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') {
      ev.preventDefault();
      saveDemo();
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {
      ev.preventDefault();
      runDraft();
    }
  });

  qs('newDemoBtn')?.addEventListener('click', newDemo);
  qs('checkBtn')?.addEventListener('click', checkCode);
  qs('runDraftBtn')?.addEventListener('click', runDraft);
  qs('runSavedBtn')?.addEventListener('click', runSaved);
  qs('saveBtn')?.addEventListener('click', saveDemo);
  qs('copyBtn')?.addEventListener('click', saveAsCopy);
  qs('deleteDemoBtn')?.addEventListener('click', deleteDemo);
  qs('stopDemoBtn')?.addEventListener('click', async () => {
    try {
      const body = await postJson('/api/demos/stop');
      setStatus(`Stopped demo. Rendered ${body.frames_rendered || 0} frames.`);
      await refreshDemoStatus();
    } catch (err) {
      setStatus(`Stop failed: ${err.message}`);
    }
  });
}

async function init() {
  hookEditor();
  try {
    await refreshDemoList();
    if (demos.length) await loadDemo(demos[0].id);
    else newDemo();
  } catch (err) {
    setError(err.message);
    newDemo();
  }
  setInterval(refreshDemoStatus, 1000);
  refreshDemoStatus();
}

init();
