const fileInput = document.getElementById('uploadFile');
const titleInput = document.getElementById('uploadTitle');
const folderInput = document.getElementById('uploadFolder');
const enabledBox = document.getElementById('uploadEnabled');
const showNowBox = document.getElementById('showNow');
const saveBtn = document.getElementById('saveUploadBtn');
const previewPanelBtn = document.getElementById('previewPanelBtn');
const statusBox = document.getElementById('uploadStatus');
const kindBadge = document.getElementById('fileKindBadge');

const transformControls = document.getElementById('transformControls') || document.getElementById('stillControls');
const gifControls = document.getElementById('gifControls');
const sourceArea = document.getElementById('sourceArea');
const sourceLabel = document.getElementById('sourceLabel');
const sourceHelp = document.getElementById('sourceHelp');
const previewHelp = document.getElementById('previewHelp');

const scaleMode = document.getElementById('scaleMode');
const resampleMode = document.getElementById('resampleMode');
const bgInput = document.getElementById('backgroundColor');
const zoomInput = document.getElementById('cropZoom');
const fitCropBtn = document.getElementById('fitCropBtn');
const centerCropBtn = document.getElementById('centerCropBtn');

const gifMaxFrames = document.getElementById('gifMaxFrames');
const gifDefaultDuration = document.getElementById('gifDefaultDuration');
const gifMinDuration = document.getElementById('gifMinDuration');
const gifMaxDuration = document.getElementById('gifMaxDuration');

const sourceCanvas = document.getElementById('sourceCanvas');
const sourceCtx = sourceCanvas.getContext('2d', {willReadFrequently: true});
const previewCanvas = document.getElementById('previewCanvas');
const previewCtx = previewCanvas.getContext('2d', {willReadFrequently: true});
const previewLarge = document.getElementById('previewLarge');
const previewLargeCtx = previewLarge.getContext('2d', {willReadFrequently: true});

let sourceFile = null;
let sourceImage = null;
let fileKind = 'none'; // none, still, gif
let currentObjectUrl = null;
let imageRect = {x: 0, y: 0, w: 1, h: 1, scale: 1};
let crop = {x: 0, y: 0, size: 1};
let dragging = false;
let dragOffset = {x: 0, y: 0};

let gifPreviewFrames = []; // {image: HTMLImageElement, duration_ms: number}
let gifAnimationFrame = 0;
let gifPreviewIndex = 0;
let gifFrameStartedAt = 0;
let gifRenderTimer = 0;
let gifRenderToken = 0;
let gifRenderPendingText = '';

function setStatus(text) {
  if (statusBox) statusBox.textContent = text;
}

function setKindLabel(text) {
  if (kindBadge) kindBadge.textContent = text;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function fileBaseName(name) {
  return (name || 'upload').replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim();
}

function isGifFile(file) {
  return !!file && (file.type === 'image/gif' || /\.gif$/i.test(file.name || ''));
}

function activeScaleMode() {
  return scaleMode?.value || 'crop';
}

function activeBackground() {
  return bgInput?.value || '#000000';
}

function imageSmoothingEnabled() {
  const mode = resampleMode?.value || 'nearest';
  return !(mode === 'nearest' || mode === 'pixel');
}

function updateModeVisibility() {
  const hasFile = fileKind !== 'none';
  const isGif = fileKind === 'gif';
  transformControls?.classList.toggle('hidden-panel', !hasFile);
  gifControls?.classList.toggle('hidden-panel', !isGif);
  sourceArea?.classList.toggle('hidden-panel', !hasFile);
  document.querySelectorAll('.crop-only').forEach(el => {
    el.classList.toggle('hidden-panel', !(hasFile && activeScaleMode() === 'crop'));
  });
  if (saveBtn) {
    saveBtn.disabled = !sourceFile || !sourceImage || fileKind === 'none';
    saveBtn.textContent = isGif ? 'Save GIF to library' : 'Save preview to library';
  }
  if (previewPanelBtn) previewPanelBtn.disabled = !sourceFile || !sourceImage || fileKind === 'none';
  if (sourceLabel) sourceLabel.textContent = isGif ? 'Source GIF crop' : 'Source crop';
  if (sourceHelp) {
    sourceHelp.textContent = isGif
      ? 'Drag the crop square or adjust zoom. The animated 64×64 preview is generated from these exact settings.'
      : 'Drag the crop square. Use the zoom slider to change how much of the source image becomes the 64×64 result.';
  }
  if (previewHelp) {
    previewHelp.textContent = isGif
      ? 'This is the processed animated GIF preview. Panel preview and save use the same crop, scaling, and timing settings.'
      : 'Grid lines show the 64×64 RGB matrix cells. The saved image is the exact 64×64 preview shown here.';
  }
}

function updatePreviewBackingSize() {
  if (!previewLarge) return false;
  const wrap = previewLarge.parentElement;
  const container = previewLarge.closest('.preview-area') || wrap?.parentElement || document.body;
  const available = Math.max(64, Math.floor((container?.clientWidth || 512) - 12));
  const scale = Math.max(1, Math.min(8, Math.floor(available / 64)));
  const size = scale * 64;
  const changed = previewLarge.width !== size || previewLarge.height !== size;
  if (changed) {
    previewLarge.width = size;
    previewLarge.height = size;
  }
  previewLarge.style.width = `${size}px`;
  previewLarge.style.height = `${size}px`;
  if (wrap) {
    wrap.style.width = `${size}px`;
    wrap.style.height = `${size}px`;
  }
  return changed;
}

function computeImageRect() {
  if (!sourceImage) return;
  const cw = sourceCanvas.width;
  const ch = sourceCanvas.height;
  const scale = Math.min(cw / sourceImage.naturalWidth, ch / sourceImage.naturalHeight);
  const w = sourceImage.naturalWidth * scale;
  const h = sourceImage.naturalHeight * scale;
  imageRect = {x: (cw - w) / 2, y: (ch - h) / 2, w, h, scale};
}

function setCropFromZoom(centerExisting = true) {
  if (!sourceImage) return;
  const minDim = Math.min(sourceImage.naturalWidth, sourceImage.naturalHeight);
  const zoom = clamp(Number(zoomInput.value || 1), 1, 8);
  const size = Math.max(1, minDim / zoom);
  const oldCenterX = crop.x + crop.size / 2;
  const oldCenterY = crop.y + crop.size / 2;
  crop.size = size;
  if (centerExisting) {
    crop.x = oldCenterX - size / 2;
    crop.y = oldCenterY - size / 2;
  } else {
    crop.x = (sourceImage.naturalWidth - size) / 2;
    crop.y = (sourceImage.naturalHeight - size) / 2;
  }
  clampCrop();
}

function clampCrop() {
  if (!sourceImage) return;
  crop.size = clamp(crop.size, 1, Math.min(sourceImage.naturalWidth, sourceImage.naturalHeight));
  crop.x = clamp(crop.x, 0, sourceImage.naturalWidth - crop.size);
  crop.y = clamp(crop.y, 0, sourceImage.naturalHeight - crop.size);
}

function canvasToSource(clientX, clientY) {
  const rect = sourceCanvas.getBoundingClientRect();
  const cx = (clientX - rect.left) * (sourceCanvas.width / rect.width);
  const cy = (clientY - rect.top) * (sourceCanvas.height / rect.height);
  return {
    x: (cx - imageRect.x) / imageRect.scale,
    y: (cy - imageRect.y) / imageRect.scale,
  };
}

function drawSource() {
  sourceCtx.clearRect(0, 0, sourceCanvas.width, sourceCanvas.height);
  sourceCtx.fillStyle = '#000';
  sourceCtx.fillRect(0, 0, sourceCanvas.width, sourceCanvas.height);
  if (!sourceImage) return;

  sourceCtx.imageSmoothingEnabled = imageSmoothingEnabled();
  sourceCtx.drawImage(sourceImage, imageRect.x, imageRect.y, imageRect.w, imageRect.h);

  if (activeScaleMode() === 'crop') {
    const x = imageRect.x + crop.x * imageRect.scale;
    const y = imageRect.y + crop.y * imageRect.scale;
    const size = crop.size * imageRect.scale;

    sourceCtx.save();
    sourceCtx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    sourceCtx.fillRect(imageRect.x, imageRect.y, imageRect.w, imageRect.h);
    sourceCtx.clearRect(x, y, size, size);
    sourceCtx.drawImage(sourceImage, crop.x, crop.y, crop.size, crop.size, x, y, size, size);
    sourceCtx.strokeStyle = '#ffffff';
    sourceCtx.lineWidth = 2;
    sourceCtx.strokeRect(x + 1, y + 1, size - 2, size - 2);
    sourceCtx.strokeStyle = '#69a7ff';
    sourceCtx.lineWidth = 1;
    sourceCtx.strokeRect(x + 5, y + 5, size - 10, size - 10);
    sourceCtx.restore();
  }
}

function drawFitLike(mode) {
  previewCtx.fillStyle = activeBackground();
  previewCtx.fillRect(0, 0, 64, 64);
  previewCtx.imageSmoothingEnabled = imageSmoothingEnabled();

  const iw = sourceImage.naturalWidth;
  const ih = sourceImage.naturalHeight;
  if (mode === 'stretch') {
    previewCtx.drawImage(sourceImage, 0, 0, 64, 64);
    return;
  }

  const scale = mode === 'fill' ? Math.max(64 / iw, 64 / ih) : Math.min(64 / iw, 64 / ih);
  const w = Math.max(1, Math.round(iw * scale));
  const h = Math.max(1, Math.round(ih * scale));
  const x = Math.round((64 - w) / 2);
  const y = Math.round((64 - h) / 2);
  previewCtx.drawImage(sourceImage, x, y, w, h);
}

function drawSourcePreviewFrame() {
  previewCtx.clearRect(0, 0, 64, 64);
  previewCtx.fillStyle = activeBackground();
  previewCtx.fillRect(0, 0, 64, 64);

  if (!sourceImage) return;

  previewCtx.imageSmoothingEnabled = imageSmoothingEnabled();
  const mode = activeScaleMode();
  if (mode === 'crop') {
    previewCtx.drawImage(sourceImage, crop.x, crop.y, crop.size, crop.size, 0, 0, 64, 64);
  } else {
    drawFitLike(mode);
  }
}

function drawLargeFromPreview() {
  updatePreviewBackingSize();
  const scale = Math.max(1, Math.floor(previewLarge.width / 64));
  const data = previewCtx.getImageData(0, 0, 64, 64).data;
  previewLargeCtx.clearRect(0, 0, previewLarge.width, previewLarge.height);
  for (let y = 0; y < 64; y++) {
    for (let x = 0; x < 64; x++) {
      const i = (y * 64 + x) * 4;
      previewLargeCtx.fillStyle = `rgb(${data[i]}, ${data[i + 1]}, ${data[i + 2]})`;
      previewLargeCtx.fillRect(x * scale, y * scale, scale, scale);
    }
  }
}

function drawMatrixGrid() {
  const cell = Math.max(1, Math.floor(previewLarge.width / 64));
  const size = cell * 64;
  previewLargeCtx.save();
  previewLargeCtx.fillStyle = 'rgba(255, 255, 255, 0.22)';
  for (let i = 1; i < 64; i++) {
    const p = i * cell;
    previewLargeCtx.fillRect(p, 0, 1, size);
    previewLargeCtx.fillRect(0, p, size, 1);
  }
  previewLargeCtx.strokeStyle = 'rgba(255, 255, 255, 0.58)';
  previewLargeCtx.lineWidth = 1;
  previewLargeCtx.strokeRect(0.5, 0.5, size - 1, size - 1);
  previewLargeCtx.restore();
}

function drawPreview() {
  updatePreviewBackingSize();
  if (fileKind === 'gif' && gifPreviewFrames.length) {
    const frame = gifPreviewFrames[gifPreviewIndex % gifPreviewFrames.length];
    previewCtx.clearRect(0, 0, 64, 64);
    previewCtx.imageSmoothingEnabled = false;
    previewCtx.drawImage(frame.image, 0, 0, 64, 64);
  } else {
    drawSourcePreviewFrame();
  }
  drawLargeFromPreview();
  drawMatrixGrid();
}

function redrawAll() {
  if (sourceImage) computeImageRect();
  updateModeVisibility();
  drawSource();
  drawPreview();
}

function stopGifLoop() {
  if (gifAnimationFrame) {
    cancelAnimationFrame(gifAnimationFrame);
    gifAnimationFrame = 0;
  }
}

function startGifLoop() {
  stopGifLoop();
  const loop = timestamp => {
    if (fileKind !== 'gif' || !sourceImage) {
      gifAnimationFrame = 0;
      return;
    }
    drawSource();
    if (gifPreviewFrames.length) {
      const frame = gifPreviewFrames[gifPreviewIndex % gifPreviewFrames.length];
      if (!gifFrameStartedAt) gifFrameStartedAt = timestamp;
      if (timestamp - gifFrameStartedAt >= Math.max(10, frame.duration_ms || 100)) {
        gifPreviewIndex = (gifPreviewIndex + 1) % gifPreviewFrames.length;
        gifFrameStartedAt = timestamp;
      }
    }
    drawPreview();
    gifAnimationFrame = requestAnimationFrame(loop);
  };
  gifFrameStartedAt = 0;
  gifAnimationFrame = requestAnimationFrame(loop);
}

function cleanupObjectUrl() {
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl);
    currentObjectUrl = null;
  }
}

function clearGifPreviewFrames() {
  gifPreviewFrames = [];
  gifPreviewIndex = 0;
  gifFrameStartedAt = 0;
}

function appendTransformOptions(form) {
  form.append('scale_mode', activeScaleMode());
  form.append('resample', resampleMode?.value || 'nearest');
  form.append('background_color', activeBackground());
  form.append('crop_x', String(Math.round(crop.x * 1000) / 1000));
  form.append('crop_y', String(Math.round(crop.y * 1000) / 1000));
  form.append('crop_size', String(Math.round(crop.size * 1000) / 1000));
}

function appendGifOptions(form) {
  appendTransformOptions(form);
  form.append('max_frames', gifMaxFrames?.value || '240');
  form.append('default_duration_ms', gifDefaultDuration?.value || '100');
  form.append('min_duration_ms', gifMinDuration?.value || '20');
  form.append('max_duration_ms', gifMaxDuration?.value || '5000');
}

function scheduleGifPreviewRender(message = 'Updating animated preview...') {
  if (fileKind !== 'gif' || !sourceFile || !sourceImage) return;
  gifRenderPendingText = message;
  clearTimeout(gifRenderTimer);
  gifRenderTimer = setTimeout(() => renderGifBrowserPreview(), 450);
}

function loadFrameImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('could not load processed GIF preview frame'));
    img.src = dataUrl;
  });
}

async function renderGifBrowserPreview() {
  if (fileKind !== 'gif' || !sourceFile || !sourceImage) return;
  const token = ++gifRenderToken;
  setStatus(gifRenderPendingText || 'Updating animated preview...');
  const form = new FormData();
  form.append('gif', sourceFile, sourceFile.name || 'animation.gif');
  appendGifOptions(form);
  try {
    const res = await fetch('/api/gif/browser-preview', {method: 'POST', body: form});
    const body = await res.json().catch(() => ({}));
    if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
    const loaded = await Promise.all((body.frames || []).map(async frame => ({
      image: await loadFrameImage(frame.data_url),
      duration_ms: Number(frame.duration_ms || 100),
    })));
    if (token !== gifRenderToken) return;
    gifPreviewFrames = loaded;
    gifPreviewIndex = 0;
    gifFrameStartedAt = 0;
    startGifLoop();
    setStatus(`Animated preview ready: ${body.frame_count} frame(s), ${(Number(body.total_ms || 0) / 1000).toFixed(1)}s loop.`);
    drawPreview();
  } catch (err) {
    if (token !== gifRenderToken) return;
    clearGifPreviewFrames();
    setStatus(`Animated preview failed: ${err.message}`);
    drawPreview();
  }
}

fileInput?.addEventListener('change', () => {
  const file = fileInput.files && fileInput.files[0];
  stopGifLoop();
  clearTimeout(gifRenderTimer);
  cleanupObjectUrl();
  clearGifPreviewFrames();
  sourceFile = null;
  sourceImage = null;
  fileKind = 'none';
  saveBtn.disabled = true;
  previewPanelBtn.disabled = true;

  if (!file) {
    setKindLabel('No file selected');
    setStatus('Choose an image or GIF to begin.');
    redrawAll();
    return;
  }

  sourceFile = file;
  fileKind = isGifFile(file) ? 'gif' : 'still';
  if (!titleInput.value.trim()) titleInput.value = fileBaseName(file.name);
  if (fileKind === 'gif' && (!folderInput.value.trim() || folderInput.value.trim() === 'Uploads')) folderInput.value = 'Animations';
  if (fileKind === 'still' && !folderInput.value.trim()) folderInput.value = 'Uploads';

  currentObjectUrl = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    sourceImage = img;
    computeImageRect();
    zoomInput.value = '1';
    const size = Math.min(img.naturalWidth, img.naturalHeight);
    crop = {
      x: (img.naturalWidth - size) / 2,
      y: (img.naturalHeight - size) / 2,
      size,
    };
    setKindLabel(fileKind === 'gif' ? 'Animated GIF' : 'Still image');
    setStatus(`Loaded ${file.name} (${img.naturalWidth}×${img.naturalHeight}).`);
    redrawAll();
    if (fileKind === 'gif') {
      startGifLoop();
      scheduleGifPreviewRender('Processing animated browser preview...');
    }
  };
  img.onerror = () => {
    sourceImage = null;
    saveBtn.disabled = true;
    previewPanelBtn.disabled = true;
    setKindLabel('Could not load file');
    setStatus('Could not load that file in the browser.');
    redrawAll();
  };
  img.src = currentObjectUrl;
});

sourceCanvas?.addEventListener('pointerdown', ev => {
  if (!sourceImage || activeScaleMode() !== 'crop') return;
  sourceCanvas.setPointerCapture(ev.pointerId);
  const p = canvasToSource(ev.clientX, ev.clientY);
  dragging = true;
  dragOffset = {x: p.x - crop.x, y: p.y - crop.y};
  ev.preventDefault();
});

sourceCanvas?.addEventListener('pointermove', ev => {
  if (!dragging || !sourceImage) return;
  const p = canvasToSource(ev.clientX, ev.clientY);
  crop.x = p.x - dragOffset.x;
  crop.y = p.y - dragOffset.y;
  clampCrop();
  if (fileKind === 'gif') clearGifPreviewFrames();
  redrawAll();
  if (fileKind === 'gif') scheduleGifPreviewRender('Updating animated crop preview...');
  ev.preventDefault();
});

function endDrag(ev) {
  if (!dragging) return;
  dragging = false;
  try { sourceCanvas.releasePointerCapture(ev.pointerId); } catch (_) {}
  if (fileKind === 'gif') scheduleGifPreviewRender('Updating animated crop preview...');
}
sourceCanvas?.addEventListener('pointerup', endDrag);
sourceCanvas?.addEventListener('pointercancel', endDrag);
sourceCanvas?.addEventListener('pointerleave', endDrag);

function transformChanged({clearGif = true} = {}) {
  if (fileKind === 'gif' && clearGif) clearGifPreviewFrames();
  redrawAll();
  if (fileKind === 'gif') scheduleGifPreviewRender('Updating animated preview...');
}

zoomInput?.addEventListener('input', () => {
  setCropFromZoom(true);
  transformChanged();
});
fitCropBtn?.addEventListener('click', () => {
  zoomInput.value = '1';
  setCropFromZoom(false);
  transformChanged();
});
centerCropBtn?.addEventListener('click', () => {
  setCropFromZoom(false);
  transformChanged();
});
[scaleMode, resampleMode, bgInput].forEach(el => {
  el?.addEventListener('input', () => transformChanged());
  el?.addEventListener('change', () => transformChanged());
});
[gifMaxFrames, gifDefaultDuration, gifMinDuration, gifMaxDuration].forEach(el => {
  el?.addEventListener('input', () => {
    if (fileKind === 'gif') {
      clearGifPreviewFrames();
      redrawAll();
      scheduleGifPreviewRender('Updating animated timing preview...');
    }
  });
});

function canvasToPngBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => {
      if (blob) resolve(blob);
      else reject(new Error('could not encode 64x64 preview as PNG'));
    }, 'image/png');
  });
}

function safeUploadName() {
  const base = (titleInput.value.trim() || (sourceFile ? fileBaseName(sourceFile.name) : 'upload'))
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'upload';
  return `${base}-64x64.png`;
}

function appendCommonFormFields(form, fallbackTitle) {
  form.append('title', titleInput.value.trim() || fallbackTitle);
  form.append('folder_path', (folderInput?.value || (fileKind === 'gif' ? 'Animations' : 'Uploads')).trim() || (fileKind === 'gif' ? 'Animations' : 'Uploads'));
  form.append('enabled', enabledBox.checked ? '1' : '0');
  form.append('show_now', showNowBox.checked ? '1' : '0');
}

async function saveStill() {
  drawPreview();
  const blob = await canvasToPngBlob(previewCanvas);
  const form = new FormData();
  form.append('image', blob, safeUploadName());
  appendCommonFormFields(form, sourceFile ? fileBaseName(sourceFile.name) : 'Uploaded image');
  const res = await fetch('/api/upload', {method: 'POST', body: form});
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

async function saveGif() {
  const form = new FormData();
  form.append('gif', sourceFile, sourceFile.name || 'animation.gif');
  appendCommonFormFields(form, sourceFile ? fileBaseName(sourceFile.name) : 'Animated GIF');
  appendGifOptions(form);
  const res = await fetch('/api/gif', {method: 'POST', body: form});
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

saveBtn?.addEventListener('click', async () => {
  if (!sourceImage || !sourceFile || fileKind === 'none') return;
  saveBtn.disabled = true;
  const wasGif = fileKind === 'gif';
  setStatus(wasGif ? 'Saving processed GIF frames...' : 'Saving the approved 64×64 preview...');

  try {
    const body = wasGif ? await saveGif() : await saveStill();
    if (wasGif) {
      setStatus(`Saved “${body.title}” with ${body.frame_count} frame(s).`);
    } else {
      setStatus(`Saved the displayed 64×64 preview as “${body.title}” (artwork ${body.artwork_id}).`);
    }
  } catch (err) {
    setStatus(`Save failed: ${err.message}`);
  } finally {
    saveBtn.disabled = false;
  }
});

async function previewStillOnPanel() {
  drawPreview();
  const blob = await canvasToPngBlob(previewCanvas);
  const form = new FormData();
  form.append('image', blob, 'preview-64x64.png');
  form.append('title', titleInput.value.trim() || 'Upload preview');
  const res = await fetch('/api/display/live-preview', {method: 'POST', body: form});
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

async function previewGifOnPanel() {
  const form = new FormData();
  form.append('gif', sourceFile, sourceFile.name || 'animation.gif');
  form.append('title', titleInput.value.trim() || fileBaseName(sourceFile.name) || 'GIF preview');
  appendGifOptions(form);
  const res = await fetch('/api/gif/preview', {method: 'POST', body: form});
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

previewPanelBtn?.addEventListener('click', async () => {
  if (!sourceImage || !sourceFile || fileKind === 'none') return;
  previewPanelBtn.disabled = true;
  setStatus(fileKind === 'gif' ? 'Preparing GIF panel preview...' : 'Sending still preview to panel...');
  try {
    const body = fileKind === 'gif' ? await previewGifOnPanel() : await previewStillOnPanel();
    if (fileKind === 'gif') {
      setStatus(`Panel preview running: ${body.frame_count} frame(s), ${(body.total_ms / 1000).toFixed(1)}s loop.`);
    } else {
      setStatus('Panel preview updated.');
    }
  } catch (err) {
    setStatus(`Panel preview failed: ${err.message}`);
  } finally {
    previewPanelBtn.disabled = false;
  }
});

window.addEventListener('resize', () => {
  redrawAll();
});

updateModeVisibility();
updatePreviewBackingSize();
drawPreview();
