let demos = [];
let currentDemo = null;
let dirty = false;

const STARTER_CODE = `import math\n\nNAME = "New Code"\nDEFAULT_FPS = 24\nPARAMS = {\n    "speed": {"type": "float", "default": 1.0},\n}\n\ndef render(ctx, t, dt, frame, params):\n    frame.fill(0, 0, 0)\n    cx = ctx.width // 2\n    cy = ctx.height // 2\n    radius = 18\n    a = t * float(params.get("speed", 1.0))\n    x = int(cx + math.cos(a) * radius)\n    y = int(cy + math.sin(a) * radius)\n    frame.circle(cx, cy, 12, 0, 40, 90)\n    frame.circle(x, y, 5, 255, 80, 20, fill=True)\n`;

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
    flag.textContent = dirty ? 'New unsaved code.' : 'New code.';
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
    title: qs('demoTitle')?.value || 'New Code',
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
  const canSave = enabled;
  const canDelete = enabled && currentDemo;
  const canSetThumb = enabled && currentDemo;
  if (qs('saveBtn')) qs('saveBtn').disabled = !canSave;
  if (qs('currentThumbBtn')) qs('currentThumbBtn').disabled = !canSetThumb;
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
  const body = await getJson('/api/code');
  demos = body.demos || [];
  renderDemoList();
  if (selectedId) await loadDemo(selectedId);
}

async function maybeLoadDemo(id) {
  if (dirty && !confirm('Discard unsaved changes and load another code effect?')) return;
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
  const body = await getJson(`/api/code/${id}`);
  currentDemo = body.demo;
  qs('demoTitle').value = currentDemo.title || '';
  qs('demoDescription').value = currentDemo.description || '';
  qs('demoFpsInput').value = currentDemo.default_fps || 24;
  qs('demoCode').value = currentDemo.code || '';
  setEnabledButton(!!currentDemo.enabled);
  qs('editorHeading').textContent = currentDemo.title || 'Code editor';
  qs('editorMeta').textContent = currentDemo.builtin
    ? `${currentDemo.slug} · built-in example · editable in place`
    : `${currentDemo.slug} · editable code effect`;
  showVersions(body.versions || []);
  setDirty(false);
  updateStats();
  setEditorEnabled(true);
  renderDemoList();
  setStatus(`Loaded ${currentDemo.title}.`);
}

function newDemo() {
  if (dirty && !confirm('Discard unsaved changes and create a new code effect?')) return;
  currentDemo = null;
  qs('demoTitle').value = 'New Code';
  qs('demoDescription').value = 'A browser-created Python visual effect.';
  qs('demoFpsInput').value = 24;
  qs('demoCode').value = STARTER_CODE;
  qs('editorHeading').textContent = 'New code';
  qs('editorMeta').textContent = 'Unsaved custom code effect';
  setEnabledButton(true);
  showVersions([]);
  setDirty(true);
  updateStats();
  setEditorEnabled(true);
  renderDemoList();
  setStatus('New code ready. Run the editor version or save it to the library.');
}

async function checkCode() {
  setError('');
  try {
    const body = await postJson('/api/code/check', {code: qs('demoCode').value || ''});
    setStatus(body.message || 'Syntax check passed.');
  } catch (err) {
    setStatus(`Check failed: ${err.message}`);
    setError(err.message);
  }
}

async function runDraft() {
  setError('');
  try {
    const body = await postJson('/api/code/run-editor', payloadFromEditor());
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
    const body = await postJson(`/api/code/${currentDemo.id}/run`);
    setStatus(`Running code ${body.title} at ${body.fps} FPS.`);
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
      body = await postJson('/api/code/new', payloadFromEditor());
    } else {
      body = await postJson(`/api/code/${currentDemo.id}/save`, payloadFromEditor());
    }
    currentDemo = body.demo;
    await refreshDemoList(currentDemo.id);
    if (body.artwork && body.artwork.thumbnail_url) {
      setStatus(`Saved ${currentDemo.title}. Library thumbnail updated.`);
    } else {
      setStatus(`Saved ${currentDemo.title}.`);
    }
    setDirty(false);
  } catch (err) {
    setStatus(`Save failed: ${err.message}`);
    setError(err.message);
  }
}


async function saveCurrentDisplayAsThumbnail() {
  setError('');
  if (!currentDemo) {
    setStatus('Save the code item first, then save the current display as its thumbnail.');
    return;
  }
  if (dirty && !confirm('This will update the thumbnail for the currently saved code item. Save code changes first if needed. Continue?')) return;
  try {
    const body = await postJson(`/api/code/${currentDemo.id}/thumbnail-current`);
    if (body.demo) currentDemo = body.demo;
    await refreshDemoList(currentDemo.id);
    setStatus(`Saved current display as thumbnail for ${currentDemo.title}.`);
  } catch (err) {
    setStatus(`Thumbnail save failed: ${err.message}`);
    setError(err.message);
  }
}
async function saveAsCopy() {
  setError('');
  try {
    let body;
    if (currentDemo) {
      body = await postJson(`/api/code/${currentDemo.id}/copy`, payloadFromEditor());
    } else {
      const payload = payloadFromEditor();
      payload.title = `${payload.title || 'New Code'} copy`;
      body = await postJson('/api/code/new', payload);
    }
    currentDemo = body.demo;
    await refreshDemoList(currentDemo.id);
    if (body.artwork && body.artwork.thumbnail_url) {
      setStatus(`Saved copy as ${currentDemo.title}. Library thumbnail updated.`);
    } else {
      setStatus(`Saved copy as ${currentDemo.title}.`);
    }
    setDirty(false);
  } catch (err) {
    setStatus(`Save copy failed: ${err.message}`);
    setError(err.message);
  }
}

async function deleteDemo() {
  if (!currentDemo) return;
  if (!confirm(`Move code effect "${currentDemo.title}" to Trash?`)) return;
  try {
    await postJson(`/api/code/${currentDemo.id}/delete`);
    const deletedId = currentDemo.id;
    currentDemo = null;
    await refreshDemoList();
    const next = demos.find(d => d.id !== deletedId);
    if (next) await loadDemo(next.id);
    else newDemo();
    setStatus('Moved code to Trash.');
  } catch (err) {
    setStatus(`Delete failed: ${err.message}`);
    setError(err.message);
  }
}

async function refreshDemoStatus() {
  try {
    const body = await fetch('/api/code/status').then(r => r.json());
    if (!body.ok) return;
    qs('demoRunning').textContent = body.running ? 'YES' : 'NO';
    qs('demoFps').textContent = body.fps || 0;
    qs('demoFrames').textContent = body.frames_rendered || 0;
    const line = qs('demoStatusLine');
    if (line) line.textContent = body.running ? `Code: ${body.title}` : 'Code: stopped';
    const toggle = qs('runStopCodeBtn');
    if (toggle) {
      toggle.dataset.running = body.running ? '1' : '0';
      toggle.textContent = body.running ? 'Stop Code' : 'Run Code';
      toggle.classList.toggle('danger', !!body.running);
      toggle.classList.toggle('run-toggle', !body.running);
    }
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
  qs('saveBtn')?.addEventListener('click', saveDemo);
  qs('currentThumbBtn')?.addEventListener('click', saveCurrentDisplayAsThumbnail);
  qs('copyBtn')?.addEventListener('click', saveAsCopy);
  qs('deleteDemoBtn')?.addEventListener('click', deleteDemo);
  qs('runStopCodeBtn')?.addEventListener('click', async () => {
    const btn = qs('runStopCodeBtn');
    const running = btn?.dataset.running === '1';
    try {
      if (running) {
        const body = await postJson('/api/code/stop');
        setStatus(`Stopped code. Rendered ${body.frames_rendered || 0} frames.`);
      } else {
        await runDraft();
      }
      await refreshDemoStatus();
    } catch (err) {
      setStatus(`${running ? 'Stop' : 'Run'} failed: ${err.message}`);
      setError(err.message);
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
