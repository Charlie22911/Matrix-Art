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

function setStatus(text) {
  const box = document.getElementById('statusBox');
  if (box) box.textContent = text;
}

let lastPreviewFrameVersion = null;

async function createFolderFromPrompt(defaultValue = '') {
  const folderPath = prompt('New folder path, for example Drawings or Uploads/Favorites:', defaultValue || 'New Folder');
  if (folderPath === null) return null;
  const cleaned = folderPath.trim();
  if (!cleaned) {
    setStatus('Folder name was empty.');
    return null;
  }
  const body = await postJson('/api/folders', {folder_path: cleaned});
  return body.folder;
}

let selectionMode = null;
const selectedIds = new Set();
const trashView = document.body?.dataset.trashView === '1';

const filterForm = document.querySelector('.filters form');
filterForm?.querySelectorAll('select').forEach(select => {
  select.addEventListener('change', () => {
    cancelSelection();
    if (filterForm.requestSubmit) filterForm.requestSubmit();
    else filterForm.submit();
  });
});

document.getElementById('newFolderBtn')?.addEventListener('click', async () => {
  try {
    const folder = await createFolderFromPrompt('New Folder');
    if (!folder) return;
    setStatus(`Created folder ${folder.path}`);
    const folderSelect = filterForm?.querySelector('select[name="folder"]');
    if (folderSelect) {
      const existing = Array.from(folderSelect.options).find(opt => opt.value === folder.path);
      if (!existing) {
        const opt = document.createElement('option');
        opt.value = folder.path;
        opt.textContent = `${folder.path} (0)`;
        folderSelect.insertBefore(opt, Array.from(folderSelect.options).find(opt => opt.value === 'Trash') || null);
      }
      folderSelect.value = folder.path;
      if (filterForm.requestSubmit) filterForm.requestSubmit();
      else filterForm.submit();
    } else {
      location.reload();
    }
  } catch (err) {
    setStatus(`Create folder failed: ${err.message}`);
  }
});




function updateTransitionUi(s) {
  const enabled = document.getElementById('transitionEnabledBox');
  if (enabled && document.activeElement !== enabled) enabled.checked = !!s.transition_enabled;
  const effect = document.getElementById('transitionEffectSelect');
  if (effect && document.activeElement !== effect && s.transition_effect) effect.value = s.transition_effect;
  const duration = document.getElementById('transitionDurationInput');
  if (duration && document.activeElement !== duration) duration.value = Math.round(Number(s.transition_duration_ms || 600));
  const fps = document.getElementById('transitionFpsInput');
  if (fps && document.activeElement !== fps) fps.value = Math.round(Number(s.transition_fps || 30));
  const smoothing = document.getElementById('transitionSmoothingBox');
  if (smoothing && document.activeElement !== smoothing) smoothing.checked = !!s.transition_smoothing;
  const smoothingStrength = document.getElementById('transitionSmoothingStrengthInput');
  if (smoothingStrength && document.activeElement !== smoothingStrength) smoothingStrength.value = Math.round(Number(s.transition_smoothing_strength || 35));
}

async function sendTransitionSettings(partial = {}) {
  const enabled = document.getElementById('transitionEnabledBox');
  const effect = document.getElementById('transitionEffectSelect');
  const duration = document.getElementById('transitionDurationInput');
  const fps = document.getElementById('transitionFpsInput');
  const smoothing = document.getElementById('transitionSmoothingBox');
  const smoothingStrength = document.getElementById('transitionSmoothingStrengthInput');
  const payload = {
    enabled: enabled ? enabled.checked : true,
    effect: effect ? effect.value : 'fade',
    duration_ms: duration ? Number(duration.value || 0) : 600,
    fps: fps ? Number(fps.value || 30) : 30,
    smoothing: smoothing ? smoothing.checked : true,
    smoothing_strength: smoothingStrength ? Number(smoothingStrength.value || 0) : 35,
    ...partial,
  };
  const body = await postJson('/api/transitions', payload);
  updateTransitionUi(body);
  setStatus(`Transition ${body.transition_effect} ${body.transition_enabled ? 'enabled' : 'disabled'} (${body.transition_duration_ms}ms @ ${body.transition_fps}fps, smoothing ${body.transition_smoothing ? body.transition_smoothing_strength + '%' : 'off'})`);
  return body;
}

function updateSlideshowUi(s) {
  const ssState = document.getElementById('slideshowState');
  if (ssState) ssState.textContent = s.slideshow_enabled ? 'ON' : 'OFF';
  const ssBtn = document.getElementById('slideshowToggleBtn');
  if (ssBtn) {
    ssBtn.dataset.enabled = s.slideshow_enabled ? '1' : '0';
    ssBtn.textContent = s.slideshow_enabled ? 'Pause slideshow' : 'Start slideshow';
  }
  const shuffle = document.getElementById('shuffleBox');
  if (shuffle && document.activeElement !== shuffle) shuffle.checked = !!s.shuffle_enabled;
  const interval = document.getElementById('intervalInput');
  if (interval && document.activeElement !== interval) interval.value = Math.round(Number(s.interval_seconds || 10));
}

async function refreshStatus(forcePreview = false) {
  try {
    const res = await fetch('/api/status');
    const s = await res.json();
    document.getElementById('currentTitle').textContent = s.current_title || 'None';
    document.getElementById('driverLine').textContent = `Driver: ${s.display_driver}`;
    document.getElementById('brightnessValue').textContent = s.brightness;
    const slider = document.getElementById('brightnessSlider');
    if (slider && document.activeElement !== slider) slider.value = s.brightness;
    document.getElementById('displayState').textContent = s.display_enabled ? 'ON' : 'OFF';
    const toggleBtn = document.getElementById('displayToggleBtn');
    if (toggleBtn) toggleBtn.dataset.enabled = s.display_enabled ? '1' : '0';
    updateSlideshowUi(s);
    updateTransitionUi(s);
    const priority = document.getElementById('priorityLine');
    if (priority && s.priority_status) priority.textContent = s.priority_status;

    if (forcePreview || s.frame_version !== lastPreviewFrameVersion) {
      const preview = document.getElementById('currentPreview');
      if (preview) preview.src = `/current.png?v=${s.frame_version}&t=${Date.now()}`;
      lastPreviewFrameVersion = s.frame_version;
    }
    setStatus(s.last_action || 'ready');
  } catch (err) {
    setStatus(`Status error: ${err.message}`);
  }
}

async function showArtwork(id) {
  try {
    const body = await postJson(`/api/artwork/${id}/show`);
    setStatus(`Queued: ${body.title}`);
    setTimeout(() => refreshStatus(true), 120);
  } catch (err) {
    setStatus(`Show failed: ${err.message}`);
  }
}

function actionLabel(action) {
  if (action === 'move') return 'Move Items';
  if (action === 'trash') return 'Delete';
  if (action === 'recover') return 'Recover';
  if (action === 'destroy') return 'Destroy';
  return action;
}

function updateSelectionUi() {
  const count = selectedIds.size;
  document.body.classList.toggle('selecting', !!selectionMode);
  document.querySelectorAll('.art-card').forEach(card => {
    card.classList.toggle('selected', selectedIds.has(card.dataset.id));
  });

  const moveFolderSelect = document.getElementById('bulkMoveFolderSelect');
  if (moveFolderSelect) moveFolderSelect.hidden = selectionMode !== 'move';

  const countEl = document.getElementById('selectionCount');
  if (countEl) {
    countEl.hidden = !selectionMode;
    countEl.textContent = `${count} selected`;
  }
  const cancel = document.getElementById('cancelSelectBtn');
  if (cancel) cancel.hidden = !selectionMode;
  const hint = document.getElementById('selectHint');
  if (hint) {
    if (!selectionMode) {
      hint.textContent = trashView
        ? 'Trash mode: choose Recover or Destroy, then tap images.'
        : 'Press Move Image to select images for a folder move, or Delete to select images to move to Trash.';
    } else if (selectionMode === 'move') {
      hint.textContent = count ? 'Choose a folder, then tap Move Items again.' : 'Choose a folder, tap images to select them, then tap Move Items again.';
    } else if (selectionMode === 'trash') {
      hint.textContent = count ? 'Tap Delete again to move selected images to Trash.' : 'Tap images to select them, then tap Delete again.';
    } else if (selectionMode === 'recover') {
      hint.textContent = count ? 'Tap Recover again to restore selected images.' : 'Tap images to select them, then tap Recover again.';
    } else if (selectionMode === 'destroy') {
      hint.textContent = count ? 'Tap Destroy again to permanently delete selected images.' : 'Tap images to select them, then tap Destroy again.';
    }
  }
  document.querySelectorAll('[data-bulk-action]').forEach(btn => {
    const action = btn.dataset.bulkAction;
    btn.classList.toggle('active', selectionMode === action);
    if (!selectionMode) {
      btn.textContent = action === 'move' ? 'Move Image' : actionLabel(action);
    } else if (selectionMode === action) {
      btn.textContent = count ? `${actionLabel(action)} ${count}` : `Select images`;
    } else {
      btn.textContent = action === 'move' ? 'Move Image' : actionLabel(action);
    }
  });
}


function cancelSelection() {
  selectionMode = null;
  selectedIds.clear();
  updateSelectionUi();
}

function toggleCardSelected(card) {
  const id = card.dataset.id;
  if (!id) return;
  if (selectedIds.has(id)) selectedIds.delete(id);
  else selectedIds.add(id);
  updateSelectionUi();
}

async function runBulkAction(action) {
  const ids = Array.from(selectedIds).map(id => Number(id));
  if (!ids.length) {
    setStatus('No images selected.');
    return;
  }

  let endpoint = '/api/artworks/trash';
  let payload = {ids};
  let verb = 'move to Trash';

  if (action === 'move') {
    const folderSelect = document.getElementById('bulkMoveFolderSelect');
    const folderPath = folderSelect ? folderSelect.value : '';
    endpoint = '/api/artworks/move';
    payload = {ids, folder_path: folderPath};
    verb = `move to ${folderPath || 'Unfiled'}`;
  } else if (action === 'recover') {
    endpoint = '/api/artworks/recover';
    verb = 'recover';
  } else if (action === 'destroy') {
    endpoint = '/api/artworks/destroy';
    verb = 'destroy';
    if (!confirm(`Permanently destroy ${ids.length} image(s)? This cannot be undone.`)) return;
  }

  try {
    const body = await postJson(endpoint, payload);
    if (action === 'move') {
      const folderPath = body.folder_path || '';
      ids.forEach(id => {
        const card = document.querySelector(`.art-card[data-id="${id}"]`);
        if (!card) return;
        card.dataset.folder = folderPath;
        const pathLine = card.querySelector('.art-path');
        if (pathLine) pathLine.textContent = folderPath || 'Unfiled';
        card.querySelectorAll('.folder-select').forEach(select => { select.value = folderPath; });
      });
    } else {
      ids.forEach(id => document.querySelector(`.art-card[data-id="${id}"]`)?.remove());
    }
    cancelSelection();
    setStatus(`${verb} complete: ${body.count} image(s).`);
    setTimeout(() => location.reload(), 220);
  } catch (err) {
    setStatus(`Bulk action failed: ${err.message}`);
  }
}


document.querySelectorAll('[data-bulk-action]').forEach(btn => {
  btn.addEventListener('click', async () => {
    const action = btn.dataset.bulkAction;
    if (selectionMode !== action) {
      selectionMode = action;
      selectedIds.clear();
      updateSelectionUi();
      return;
    }
    await runBulkAction(action);
  });
});


document.getElementById('folderEnableToggleBtn')?.addEventListener('click', async ev => {
  const button = ev.currentTarget;
  const folder = button.dataset.folder || 'all';
  const enabled = button.dataset.enableTarget !== '0';
  const folderLabel = folder === 'all' ? 'all visible folders' : folder === 'unfiled' ? 'Unfiled' : folder;
  const verb = enabled ? 'enable' : 'disable';
  if (!confirm(`${verb[0].toUpperCase() + verb.slice(1)} all items in ${folderLabel}?`)) return;
  button.disabled = true;
  try {
    const body = await postJson('/api/artworks/folder-enabled', {folder, enabled});
    setStatus(`${enabled ? 'Enabled' : 'Disabled'} ${body.count} item(s).`);
    setTimeout(() => location.reload(), 220);
  } catch (err) {
    setStatus(`Enable all failed: ${err.message}`);
  } finally {
    button.disabled = false;
  }
});

document.getElementById('cancelSelectBtn')?.addEventListener('click', cancelSelection);

function cardClickShouldSelect(ev) {
  if (!selectionMode) return false;
  const interactive = ev.target.closest('button, a, input, select, label');
  return !interactive;
}

document.querySelectorAll('.art-card').forEach(card => {
  const id = card.dataset.id;

  card.addEventListener('click', ev => {
    if (cardClickShouldSelect(ev)) {
      toggleCardSelected(card);
      ev.preventDefault();
      ev.stopPropagation();
    }
  });

  card.querySelector('.show-btn')?.addEventListener('click', () => showArtwork(id));
  card.querySelector('.thumb')?.addEventListener('click', ev => {
    if (selectionMode) return;
    if (!trashView) showArtwork(id);
  });

  card.querySelector('.enable-toggle')?.addEventListener('click', async ev => {
    const button = ev.currentTarget;
    const enabled = !(button.dataset.enabled === '1');
    button.disabled = true;
    try {
      const body = await postJson(`/api/artwork/${id}/enabled`, {enabled});
      button.dataset.enabled = body.enabled ? '1' : '0';
      button.textContent = body.enabled ? 'Enabled' : 'Disabled';
      button.classList.toggle('enabled', body.enabled);
      button.classList.toggle('disabled', !body.enabled);
      card.classList.toggle('disabled', !body.enabled);
      setStatus(`${body.enabled ? 'Enabled' : 'Disabled'} artwork ${id}`);
    } catch (err) {
      setStatus(`Enable update failed: ${err.message}`);
    } finally {
      button.disabled = false;
    }
  });

  card.querySelector('.rename-btn')?.addEventListener('click', async ev => {
    ev.preventDefault();
    ev.stopPropagation();
    const button = ev.currentTarget;
    const oldTitle = card.dataset.title || card.querySelector('.art-title')?.textContent || '';
    const title = prompt('Rename item:', oldTitle);
    if (title === null) return;
    const cleaned = title.trim();
    if (!cleaned) {
      setStatus('Rename cancelled: title cannot be empty.');
      return;
    }
    button.disabled = true;
    try {
      const body = await postJson(`/api/artwork/${id}/rename`, {title: cleaned});
      card.dataset.title = body.title;
      const titleEl = card.querySelector('.art-title');
      if (titleEl) {
        titleEl.textContent = body.title;
        titleEl.title = body.title;
      }
      const img = card.querySelector('.thumb');
      if (img) img.alt = body.title;
      button.setAttribute('aria-label', `Rename ${body.title}`);
      setStatus(`Renamed to ${body.title}`);
      refreshStatus(false);
    } catch (err) {
      setStatus(`Rename failed: ${err.message}`);
    } finally {
      button.disabled = false;
    }
  });

  card.querySelector('.folder-select')?.addEventListener('change', async ev => {
    const select = ev.target;
    const oldFolder = card.dataset.folder || '';
    let folder = select.value;
    if (folder === '__new__') {
      const typed = prompt('Folder path, for example Uploads or Uploads/Favorites:', oldFolder || 'Uploads');
      if (typed === null) {
        select.value = oldFolder;
        return;
      }
      folder = typed.trim();
    }
    try {
      const body = await postJson(`/api/artwork/${id}/folder`, {folder_path: folder});
      card.dataset.folder = body.folder_path || '';
      const pathLine = card.querySelector('.art-path');
      if (pathLine) pathLine.textContent = body.folder_path || 'Unfiled';
      setStatus(`Moved artwork ${id} to ${body.folder_path || 'Unfiled'}`);
      if (folder === '__new__' || !Array.from(select.options).some(opt => opt.value === body.folder_path)) {
        const opt = document.createElement('option');
        opt.value = body.folder_path;
        opt.textContent = body.folder_path || 'Unfiled';
        select.insertBefore(opt, select.querySelector('option[value="__new__"]'));
      }
      select.value = body.folder_path || '';
    } catch (err) {
      select.value = oldFolder;
      setStatus(`Folder update failed: ${err.message}`);
    }
  });
});


