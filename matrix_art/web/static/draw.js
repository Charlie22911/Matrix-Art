const small = document.getElementById('drawSmall');
const big = document.getElementById('drawCanvas');
const sctx = small.getContext('2d', {willReadFrequently: true});
const bctx = big.getContext('2d');
const statusBox = document.getElementById('drawStatus');
const colorInput = document.getElementById('drawColor');
const brushSizeInput = document.getElementById('brushSize');
const hotbar = document.getElementById('colorHotbar');
let currentTool = 'pencil';
let drawing = false;
let lastCell = null;
const history = [];
const maxHistory = 40;
const storageKey = 'matrix-art-draw-recent-colors';
let recentColors = [];
let liveInFlight = false;
let livePending = false;
let liveTimer = null;
let lastLiveAt = 0;
const liveMinIntervalMs = 110;

function setStatus(text) {
  if (statusBox) statusBox.textContent = text;
}

async function postForm(url, formData) {
  const res = await fetch(url, {method: 'POST', body: formData});
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

function canvasToBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => {
      if (blob) resolve(blob);
      else reject(new Error('could not encode 64x64 PNG'));
    }, 'image/png');
  });
}

function normalizeColor(color) {
  const value = String(color || '').trim().toLowerCase();
  return /^#[0-9a-f]{6}$/.test(value) ? value : '#000000';
}

function loadRecentColors() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (Array.isArray(raw)) {
      recentColors = [];
      raw.forEach(addRecentColorInternal);
    }
  } catch (_) {
    recentColors = [];
  }
  renderHotbar();
}

function saveRecentColors() {
  try { localStorage.setItem(storageKey, JSON.stringify(recentColors)); } catch (_) {}
}

function addRecentColorInternal(color) {
  const normalized = normalizeColor(color);
  recentColors = recentColors.filter(c => c !== normalized);
  recentColors.unshift(normalized);
  if (recentColors.length > 8) recentColors = recentColors.slice(0, 8);
}

function rememberCurrentColor() {
  if (currentTool === 'eraser') return;
  addRecentColorInternal(colorInput.value);
  saveRecentColors();
  renderHotbar();
}

function renderHotbar() {
  if (!hotbar) return;
  hotbar.innerHTML = '';
  if (!recentColors.length) {
    const empty = document.createElement('span');
    empty.className = 'subtle mini-note';
    empty.textContent = 'Colors appear here as you draw.';
    hotbar.appendChild(empty);
    return;
  }
  for (const color of recentColors) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'color-swatch';
    btn.style.backgroundColor = color;
    btn.title = color;
    btn.setAttribute('aria-label', `Use ${color}`);
    btn.addEventListener('click', () => {
      colorInput.value = color;
      if (currentTool === 'eraser') setTool('pencil');
      setStatus(`Selected ${color}.`);
    });
    hotbar.appendChild(btn);
  }
}

function pauseSlideshowForDrawing() {
  fetch('/api/slideshow', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled: false}),
  }).catch(() => {});
}

function initCanvas() {
  sctx.imageSmoothingEnabled = false;
  bctx.imageSmoothingEnabled = false;
  sctx.fillStyle = '#000000';
  sctx.fillRect(0, 0, 64, 64);
  resizeLargeCanvas();
  pushHistory();
  redrawLarge();
  pauseSlideshowForDrawing();
  requestLivePreview(true);
}

function pushHistory() {
  try {
    history.push(sctx.getImageData(0, 0, 64, 64));
    if (history.length > maxHistory) history.shift();
  } catch (_) {}
}

function undo() {
  if (history.length <= 1) {
    setStatus('Nothing to undo.');
    return;
  }
  history.pop();
  const prior = history[history.length - 1];
  sctx.putImageData(prior, 0, 0);
  redrawLarge();
  requestLivePreview();
  setStatus('Undo.');
}

function resizeLargeCanvas() {
  const area = big.closest('.draw-canvas-area') || big.parentElement || document.body;
  const available = Math.max(64, Math.floor((area.clientWidth || 512) - 4));
  const scale = Math.max(1, Math.min(8, Math.floor(available / 64)));
  const size = scale * 64;
  if (big.width !== size || big.height !== size) {
    big.width = size;
    big.height = size;
  }
  big.style.width = `${size}px`;
  big.style.height = `${size}px`;
  return scale;
}

function redrawLarge() {
  const scale = resizeLargeCanvas();
  bctx.imageSmoothingEnabled = false;
  bctx.clearRect(0, 0, big.width, big.height);
  bctx.drawImage(small, 0, 0, big.width, big.height);
  drawGrid(scale);
}

function drawGrid(scale) {
  const cell = scale || Math.max(1, Math.floor(big.width / 64));
  bctx.save();
  bctx.fillStyle = 'rgba(255,255,255,0.20)';
  for (let i = 1; i < 64; i++) {
    const p = i * cell;
    bctx.fillRect(p, 0, 1, big.height);
    bctx.fillRect(0, p, big.width, 1);
  }
  bctx.fillStyle = 'rgba(255,255,255,0.55)';
  bctx.fillRect(0, 0, big.width, 1);
  bctx.fillRect(0, big.height - 1, big.width, 1);
  bctx.fillRect(0, 0, 1, big.height);
  bctx.fillRect(big.width - 1, 0, 1, big.height);
  bctx.restore();
}

function setTool(tool) {
  currentTool = tool;
  document.querySelectorAll('[data-tool]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tool === tool);
  });
  setStatus(tool === 'eraser' ? 'Eraser selected.' : tool === 'fill' ? 'Fill selected.' : 'Pencil selected.');
}

function canvasCellFromEvent(ev) {
  const rect = big.getBoundingClientRect();
  const x = Math.floor(((ev.clientX - rect.left) / rect.width) * 64);
  const y = Math.floor(((ev.clientY - rect.top) / rect.height) * 64);
  return {
    x: Math.max(0, Math.min(63, x)),
    y: Math.max(0, Math.min(63, y)),
  };
}

function drawCell(x, y) {
  const size = Math.max(1, Math.min(4, Number(brushSizeInput.value || 1)));
  const half = Math.floor(size / 2);
  const color = currentTool === 'eraser' ? '#000000' : colorInput.value;
  sctx.fillStyle = color;
  const startX = Math.max(0, x - half);
  const startY = Math.max(0, y - half);
  const w = Math.min(size, 64 - startX);
  const h = Math.min(size, 64 - startY);
  sctx.fillRect(startX, startY, w, h);
}

function drawLine(a, b) {
  const dx = Math.abs(b.x - a.x);
  const dy = Math.abs(b.y - a.y);
  const steps = Math.max(dx, dy, 1);
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    drawCell(Math.round(a.x + (b.x - a.x) * t), Math.round(a.y + (b.y - a.y) * t));
  }
}

function colorAt(x, y) {
  const data = sctx.getImageData(x, y, 1, 1).data;
  return [data[0], data[1], data[2], data[3]];
}

function hexToRgba(hex) {
  const value = hex.replace('#', '');
  return [parseInt(value.slice(0, 2), 16), parseInt(value.slice(2, 4), 16), parseInt(value.slice(4, 6), 16), 255];
}

function sameColor(a, b) {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2] && a[3] === b[3];
}

function fillAt(x, y) {
  const target = colorAt(x, y);
  const replacement = currentTool === 'eraser' ? [0, 0, 0, 255] : hexToRgba(colorInput.value);
  if (sameColor(target, replacement)) return;
  const img = sctx.getImageData(0, 0, 64, 64);
  const data = img.data;
  const stack = [[x, y]];
  const visited = new Uint8Array(64 * 64);
  while (stack.length) {
    const [cx, cy] = stack.pop();
    if (cx < 0 || cy < 0 || cx >= 64 || cy >= 64) continue;
    const key = cy * 64 + cx;
    if (visited[key]) continue;
    visited[key] = 1;
    const idx = key * 4;
    const here = [data[idx], data[idx + 1], data[idx + 2], data[idx + 3]];
    if (!sameColor(here, target)) continue;
    data[idx] = replacement[0];
    data[idx + 1] = replacement[1];
    data[idx + 2] = replacement[2];
    data[idx + 3] = replacement[3];
    stack.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]);
  }
  sctx.putImageData(img, 0, 0);
}

function handleDraw(ev) {
  const cell = canvasCellFromEvent(ev);
  if (currentTool === 'fill') {
    fillAt(cell.x, cell.y);
  } else if (lastCell) {
    drawLine(lastCell, cell);
  } else {
    drawCell(cell.x, cell.y);
  }
  lastCell = cell;
  redrawLarge();
  requestLivePreview();
}

async function sendLivePreview() {
  if (liveInFlight) {
    livePending = true;
    return;
  }
  liveInFlight = true;
  livePending = false;
  try {
    const blob = await canvasToBlob(small);
    const form = new FormData();
    form.append('image', blob, 'live-drawing.png');
    form.append('title', 'Live drawing preview');
    await fetch('/api/display/live-preview', {method: 'POST', body: form});
  } catch (err) {
    setStatus(`Live panel update failed: ${err.message}`);
  } finally {
    liveInFlight = false;
    lastLiveAt = Date.now();
    if (livePending) requestLivePreview();
  }
}

function requestLivePreview(immediate = false) {
  if (liveTimer) {
    clearTimeout(liveTimer);
    liveTimer = null;
  }
  const now = Date.now();
  const delay = immediate ? 0 : Math.max(0, liveMinIntervalMs - (now - lastLiveAt));
  liveTimer = setTimeout(() => {
    liveTimer = null;
    sendLivePreview();
  }, delay);
}

big.addEventListener('pointerdown', ev => {
  ev.preventDefault();
  big.setPointerCapture?.(ev.pointerId);
  pushHistory();
  drawing = true;
  lastCell = null;
  rememberCurrentColor();
  handleDraw(ev);
  if (currentTool === 'fill') {
    drawing = false;
    lastCell = null;
    pushHistory();
  }
});

big.addEventListener('pointermove', ev => {
  if (!drawing || currentTool === 'fill') return;
  ev.preventDefault();
  handleDraw(ev);
});

function finishStroke() {
  if (!drawing) return;
  drawing = false;
  lastCell = null;
  pushHistory();
  requestLivePreview(true);
}

big.addEventListener('pointerup', finishStroke);
big.addEventListener('pointercancel', finishStroke);
big.addEventListener('pointerleave', finishStroke);

document.querySelectorAll('[data-tool]').forEach(btn => {
  btn.addEventListener('click', () => setTool(btn.dataset.tool));
});

document.getElementById('undoBtn')?.addEventListener('click', undo);

document.getElementById('clearDrawingBtn')?.addEventListener('click', () => {
  if (!confirm('Clear the drawing?')) return;
  pushHistory();
  sctx.fillStyle = '#000000';
  sctx.fillRect(0, 0, 64, 64);
  redrawLarge();
  pushHistory();
  requestLivePreview(true);
  setStatus('Drawing cleared.');
});

document.getElementById('saveDrawingBtn')?.addEventListener('click', async ev => {
  const button = ev.currentTarget;
  button.disabled = true;
  try {
    requestLivePreview(true);
    const blob = await canvasToBlob(small);
    const form = new FormData();
    form.append('image', blob, 'drawing.png');
    form.append('title', document.getElementById('drawTitle').value || 'Drawing');
    form.append('folder_path', document.getElementById('drawFolder').value || 'Drawings');
    form.append('enabled', document.getElementById('drawEnabled').checked ? '1' : '0');
    form.append('show_now', document.getElementById('drawShowNow').checked ? '1' : '0');
    const body = await postForm('/api/drawing', form);
    setStatus(`Saved drawing: ${body.title}`);
  } catch (err) {
    setStatus(`Save failed: ${err.message}`);
  } finally {
    button.disabled = false;
  }
});

window.addEventListener('resize', () => {
  redrawLarge();
});

loadRecentColors();
initCanvas();
