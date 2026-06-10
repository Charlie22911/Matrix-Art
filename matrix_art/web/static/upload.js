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
const zoomValue = document.getElementById('zoomValue');
const fitCropBtn = document.getElementById('fitCropBtn');
const centerCropBtn = document.getElementById('centerCropBtn');
const integerZoomBtn = document.getElementById('integerZoomBtn');

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
let transform = {scale: 1, x: 0, y: 0}; // destination transform in 64x64 panel coordinates
let pixelSnapActive = false;
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
  return scaleMode?.value || 'scale';
}

function activeBackground() {
  return bgInput?.value || '#000000';
}

function imageSmoothingEnabled() {
  const mode = resampleMode?.value || 'nearest';
  return !(mode === 'nearest' || mode === 'pixel');
}

function fitScale() {
  if (!sourceImage) return 1;
  return Math.min(64 / sourceImage.naturalWidth, 64 / sourceImage.naturalHeight);
}

function fillScale() {
  if (!sourceImage) return 1;
  return Math.max(64 / sourceImage.naturalWidth, 64 / sourceImage.naturalHeight);
}

function maxScale() {
  if (!sourceImage) return 8;
  return Math.max(fillScale() * 8, fitScale() * 8, fillScale() + 0.0001);
}

function minScale() {
  if (!sourceImage) return 1;
  if (!pixelSnapActive) return fitScale();
  return pixelSnapMinScale();
}

function pixelSnapMinScale() {
  if (!sourceImage) return 1;
  const fit = fitScale();
  const largestSide = Math.max(sourceImage.naturalWidth, sourceImage.naturalHeight, 1);
  // Pixel snap may zoom out below Fit so oversized pixel art can land on a
  // clean source-pixel grid with background padding. Keep that within a
  // practical range by requiring the largest side to stay about half-panel
  // size or larger.
  const halfPanelScale = 32 / largestSide;
  return Math.max(0.0001, Math.min(fit, halfPanelScale));
}

function setZoomRange() {
  if (!zoomInput || !sourceImage) return;
  const min = minScale();
  const max = maxScale();
  zoomInput.min = String(min);
  zoomInput.max = String(max);
  zoomInput.step = String(Math.max(0.0001, (max - min) / 800));
  zoomInput.value = String(clamp(transform.scale, min, max));
  updateZoomLabel();
}

function zoomMultiple() {
  if (!sourceImage) return 1;
  return transform.scale / fitScale();
}

function scalePixelRatioLabel(scale) {
  const safeScale = Math.max(0.0001, Number(scale || 0.0001));
  if (safeScale >= 1) {
    return `${safeScale.toFixed(safeScale >= 10 ? 1 : 2)} LED/src`;
  }
  return `${(1 / safeScale).toFixed(2)} src/LED`;
}

function updateZoomLabel() {
  if (!zoomValue || !sourceImage) return;
  const multiple = zoomMultiple();
  const pct = Math.round(multiple * 100);
  const snapText = pixelSnapActive ? ' · snapped' : '';
  zoomValue.textContent = `${pct}% fit · ${scalePixelRatioLabel(transform.scale)}${snapText}`;
}

function panelOffsetStepForScale(scale) {
  const safeScale = Math.max(0.0001, Number(scale || 0.0001));
  if (safeScale >= 1) return Math.max(1, Math.round(safeScale));
  return 1;
}

function sourceOriginStepForScale(scale) {
  const safeScale = Math.max(0.0001, Number(scale || 0.0001));
  if (safeScale >= 1) return 1;
  return Math.max(1, Math.round(1 / safeScale));
}

function snapPanelOffset(value, min, max, step) {
  const safeStep = Math.max(1, Number(step || 1));
  const lo = Math.ceil(min / safeStep) * safeStep;
  const hi = Math.floor(max / safeStep) * safeStep;
  if (lo > hi) return clamp(Math.round(value), min, max);
  return clamp(Math.round(value / safeStep) * safeStep, lo, hi);
}

function snapSourceOrigin(value, max, step) {
  const safeStep = Math.max(1, Number(step || 1));
  const hi = Math.floor(Math.max(0, max) / safeStep) * safeStep;
  return clamp(Math.round(value / safeStep) * safeStep, 0, hi);
}

function clampTransform() {
  if (!sourceImage) return;
  const min = minScale();
  const max = maxScale();
  transform.scale = clamp(Number(transform.scale || min), min, max);

  const w = sourceImage.naturalWidth * transform.scale;
  const h = sourceImage.naturalHeight * transform.scale;
  const offsetStep = pixelSnapActive ? panelOffsetStepForScale(transform.scale) : 1;

  if (w <= 64) {
    const centered = (64 - w) / 2;
    transform.x = pixelSnapActive ? snapPanelOffset(centered, 0, 64 - w, offsetStep) : centered;
  } else {
    const x = clamp(Number(transform.x || 0), 64 - w, 0);
    transform.x = pixelSnapActive ? snapPanelOffset(x, 64 - w, 0, offsetStep) : x;
  }

  if (h <= 64) {
    const centered = (64 - h) / 2;
    transform.y = pixelSnapActive ? snapPanelOffset(centered, 0, 64 - h, offsetStep) : centered;
  } else {
    const y = clamp(Number(transform.y || 0), 64 - h, 0);
    transform.y = pixelSnapActive ? snapPanelOffset(y, 64 - h, 0, offsetStep) : y;
  }

  setZoomRange();
}

function setScaleCentered(scale) {
  if (!sourceImage) return;
  transform.scale = scale;
  const w = sourceImage.naturalWidth * transform.scale;
  const h = sourceImage.naturalHeight * transform.scale;
  transform.x = (64 - w) / 2;
  transform.y = (64 - h) / 2;
  clampTransform();
}

function setScaleKeepingPanelCenter(scale) {
  if (!sourceImage) return;
  const oldScale = Math.max(0.0001, Number(transform.scale || fitScale()));
  const centerSourceX = (32 - Number(transform.x || 0)) / oldScale;
  const centerSourceY = (32 - Number(transform.y || 0)) / oldScale;
  transform.scale = scale;
  transform.x = 32 - centerSourceX * transform.scale;
  transform.y = 32 - centerSourceY * transform.scale;
  clampTransform();
}

function pixelAlignedScaleCandidates() {
  if (!sourceImage) return [1];
  const min = pixelSnapMinScale();
  const max = maxScale();
  const candidates = [];
  const seen = new Set();
  const addCandidate = scale => {
    const value = Number(scale);
    if (!Number.isFinite(value)) return;
    if (value < min - 1e-9 || value > max + 1e-9) return;
    const key = value.toFixed(9);
    if (!seen.has(key)) {
      seen.add(key);
      candidates.push(value);
    }
  };

  const reciprocalLimit = Math.min(1024, Math.max(2, Math.ceil(1 / Math.max(min, 0.0001)) + 4));
  for (let denominator = reciprocalLimit; denominator >= 2; denominator--) {
    addCandidate(1 / denominator);
  }
  const integerLimit = Math.min(256, Math.max(1, Math.ceil(max) + 1));
  for (let scale = 1; scale <= integerLimit; scale++) {
    addCandidate(scale);
  }

  if (!candidates.length) addCandidate(clamp(transform.scale || min, min, max));
  return candidates.sort((a, b) => a - b);
}

function fullSourceVisible() {
  if (!sourceImage) return false;
  const rect = visibleSourceRect();
  if (!rect) return false;
  const eps = 0.01;
  return rect.x <= eps
    && rect.y <= eps
    && rect.x + rect.w >= sourceImage.naturalWidth - eps
    && rect.y + rect.h >= sourceImage.naturalHeight - eps;
}

function nearestPixelAlignedScale(currentScale, {preferZoomOut = false} = {}) {
  const current = Math.max(0.0001, Number(currentScale || fitScale()));
  const candidates = pixelAlignedScaleCandidates();

  if (preferZoomOut) {
    const lower = candidates.filter(candidate => candidate <= current + 1e-9);
    if (lower.length) return lower[lower.length - 1];
  }

  let best = candidates[0] || current;
  let bestDistance = Infinity;
  candidates.forEach(candidate => {
    const distance = Math.abs(Math.log(candidate / current));
    if (distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  });
  return best;
}

function snapToPixelGrid() {
  if (!sourceImage) return;
  const oldScale = Math.max(0.0001, Number(transform.scale || fitScale()));
  const centerSourceX = (32 - Number(transform.x || 0)) / oldScale;
  const centerSourceY = (32 - Number(transform.y || 0)) / oldScale;
  const targetScale = nearestPixelAlignedScale(oldScale, {preferZoomOut: fullSourceVisible()});

  pixelSnapActive = true;
  transform.scale = targetScale;

  const viewW = 64 / targetScale;
  const viewH = 64 / targetScale;
  const sourceStep = sourceOriginStepForScale(targetScale);

  if (sourceImage.naturalWidth * targetScale <= 64) {
    transform.x = snapPanelOffset((64 - sourceImage.naturalWidth * targetScale) / 2, 0, 64 - sourceImage.naturalWidth * targetScale, panelOffsetStepForScale(targetScale));
  } else {
    const maxX = Math.max(0, sourceImage.naturalWidth - viewW);
    const x = snapSourceOrigin(centerSourceX - viewW / 2, maxX, sourceStep);
    transform.x = -x * targetScale;
  }

  if (sourceImage.naturalHeight * targetScale <= 64) {
    transform.y = snapPanelOffset((64 - sourceImage.naturalHeight * targetScale) / 2, 0, 64 - sourceImage.naturalHeight * targetScale, panelOffsetStepForScale(targetScale));
  } else {
    const maxY = Math.max(0, sourceImage.naturalHeight - viewH);
    const y = snapSourceOrigin(centerSourceY - viewH / 2, maxY, sourceStep);
    transform.y = -y * targetScale;
  }

  clampTransform();
}

function setInitialTransform() {
  if (!sourceImage) return;
  pixelSnapActive = false;
  const defaultMode = (scaleMode?.dataset?.defaultScaleMode || '').toLowerCase();
  if (defaultMode === 'fill' || defaultMode === 'crop') {
    setScaleCentered(fillScale());
  } else {
    setScaleCentered(fitScale());
  }
}

function updateModeVisibility() {
  const hasFile = fileKind !== 'none';
  const isGif = fileKind === 'gif';
  const mode = activeScaleMode();
  transformControls?.classList.toggle('hidden-panel', !hasFile);
  gifControls?.classList.toggle('hidden-panel', !isGif);
  sourceArea?.classList.toggle('hidden-panel', !hasFile);
  document.querySelectorAll('.scale-only').forEach(el => {
    el.classList.toggle('hidden-panel', !(hasFile && mode === 'scale'));
  });
  if (saveBtn) {
    saveBtn.disabled = !sourceFile || !sourceImage || fileKind === 'none';
    saveBtn.textContent = isGif ? 'Save GIF to library' : 'Save preview to library';
  }
  if (previewPanelBtn) previewPanelBtn.disabled = !sourceFile || !sourceImage || fileKind === 'none';

  if (sourceLabel) {
    sourceLabel.textContent = mode === 'stretch'
      ? (isGif ? 'Source GIF' : 'Source image')
      : (isGif ? 'Source GIF scale' : 'Source scale');
  }

  if (sourceHelp) {
    if (mode === 'scale') {
      sourceHelp.textContent = isGif
        ? 'Scale mode keeps aspect ratio. Use Fit or Fill, adjust zoom, then use Pixel snap to align source pixels to matrix pixels. If the whole image is visible, Pixel snap may zoom out and add padding.'
        : 'Scale mode keeps aspect ratio. Use Fit or Fill, adjust zoom, then use Pixel snap to align source pixels to matrix pixels. If the whole image is visible, Pixel snap may zoom out and add padding.';
    } else {
      sourceHelp.textContent = 'Stretch scales the source directly to 64×64 and may distort non-square images.';
    }
  }

  if (previewHelp) {
    if (isGif) {
      previewHelp.textContent = 'This is the processed animated GIF preview. Panel preview and save use the same scale, timing, and background settings.';
    } else if (mode === 'scale') {
      previewHelp.textContent = 'Grid lines show the 64×64 RGB matrix cells. Scale mode can fit, fill, zoom further, or snap zoom and position to the source-pixel grid. Snap can zoom out from Fit when that better preserves the full source image.';
    } else {
      previewHelp.textContent = 'Grid lines show the 64×64 RGB matrix cells. Stretch mode saves the full image reshaped to a square.';
    }
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

function canvasToSource(clientX, clientY) {
  const rect = sourceCanvas.getBoundingClientRect();
  const cx = (clientX - rect.left) * (sourceCanvas.width / rect.width);
  const cy = (clientY - rect.top) * (sourceCanvas.height / rect.height);
  return {
    x: (cx - imageRect.x) / imageRect.scale,
    y: (cy - imageRect.y) / imageRect.scale,
  };
}

function visibleSourceRect() {
  if (!sourceImage || transform.scale <= 0) return null;
  const sx0 = clamp((0 - transform.x) / transform.scale, 0, sourceImage.naturalWidth);
  const sy0 = clamp((0 - transform.y) / transform.scale, 0, sourceImage.naturalHeight);
  const sx1 = clamp((64 - transform.x) / transform.scale, 0, sourceImage.naturalWidth);
  const sy1 = clamp((64 - transform.y) / transform.scale, 0, sourceImage.naturalHeight);
  if (sx1 <= sx0 || sy1 <= sy0) return null;
  return {x: sx0, y: sy0, w: sx1 - sx0, h: sy1 - sy0};
}

function drawSource() {
  sourceCtx.clearRect(0, 0, sourceCanvas.width, sourceCanvas.height);
  sourceCtx.fillStyle = '#000';
  sourceCtx.fillRect(0, 0, sourceCanvas.width, sourceCanvas.height);
  if (!sourceImage) return;

  sourceCtx.imageSmoothingEnabled = imageSmoothingEnabled();
  sourceCtx.drawImage(sourceImage, imageRect.x, imageRect.y, imageRect.w, imageRect.h);

  if (activeScaleMode() === 'scale') {
    const rect = visibleSourceRect();
    if (!rect) return;
    const x = imageRect.x + rect.x * imageRect.scale;
    const y = imageRect.y + rect.y * imageRect.scale;
    const w = rect.w * imageRect.scale;
    const h = rect.h * imageRect.scale;

    sourceCtx.save();
    sourceCtx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    sourceCtx.fillRect(imageRect.x, imageRect.y, imageRect.w, imageRect.h);
    sourceCtx.clearRect(x, y, w, h);
    sourceCtx.drawImage(sourceImage, rect.x, rect.y, rect.w, rect.h, x, y, w, h);
    sourceCtx.strokeStyle = '#ffffff';
    sourceCtx.lineWidth = 2;
    sourceCtx.strokeRect(x + 1, y + 1, Math.max(0, w - 2), Math.max(0, h - 2));
    sourceCtx.strokeStyle = '#69a7ff';
    sourceCtx.lineWidth = 1;
    sourceCtx.strokeRect(x + 5, y + 5, Math.max(0, w - 10), Math.max(0, h - 10));
    sourceCtx.restore();
  }
}

function drawScaledPreview() {
  previewCtx.fillStyle = activeBackground();
  previewCtx.fillRect(0, 0, 64, 64);
  previewCtx.imageSmoothingEnabled = imageSmoothingEnabled();
  if (!sourceImage) return;
  clampTransform();
  const w = Math.max(1, Math.round(sourceImage.naturalWidth * transform.scale));
  const h = Math.max(1, Math.round(sourceImage.naturalHeight * transform.scale));
  const x = Math.round(transform.x);
  const y = Math.round(transform.y);
  previewCtx.drawImage(sourceImage, x, y, w, h);
}

function drawSourcePreviewFrame() {
  previewCtx.clearRect(0, 0, 64, 64);
  previewCtx.fillStyle = activeBackground();
  previewCtx.fillRect(0, 0, 64, 64);

  if (!sourceImage) return;

  previewCtx.imageSmoothingEnabled = imageSmoothingEnabled();
  if (activeScaleMode() === 'stretch') {
    previewCtx.drawImage(sourceImage, 0, 0, 64, 64);
  } else {
    drawScaledPreview();
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
  if (sourceImage) {
    computeImageRect();
    clampTransform();
  }
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
  clampTransform();
  form.append('scale_mode', activeScaleMode());
  form.append('resample', resampleMode?.value || 'nearest');
  form.append('background_color', activeBackground());
  form.append('transform_scale', String(Math.round(transform.scale * 1000000) / 1000000));
  form.append('offset_x', String(Math.round(transform.x * 1000) / 1000));
  form.append('offset_y', String(Math.round(transform.y * 1000) / 1000));

  const rect = visibleSourceRect() || {x: 0, y: 0, w: sourceImage?.naturalWidth || 1, h: sourceImage?.naturalHeight || 1};
  form.append('crop_x', String(Math.round(rect.x * 1000) / 1000));
  form.append('crop_y', String(Math.round(rect.y * 1000) / 1000));
  form.append('crop_size', String(Math.round(Math.min(rect.w, rect.h) * 1000) / 1000));
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
    setInitialTransform();
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
  if (!sourceImage || activeScaleMode() !== 'scale') return;
  const rect = visibleSourceRect();
  if (!rect) return;
  sourceCanvas.setPointerCapture(ev.pointerId);
  const p = canvasToSource(ev.clientX, ev.clientY);
  dragging = true;
  dragOffset = {x: p.x - rect.x, y: p.y - rect.y};
  ev.preventDefault();
});

sourceCanvas?.addEventListener('pointermove', ev => {
  if (!dragging || !sourceImage) return;
  const p = canvasToSource(ev.clientX, ev.clientY);
  const rect = visibleSourceRect();
  if (!rect) return;

  const maxX = Math.max(0, sourceImage.naturalWidth - rect.w);
  const maxY = Math.max(0, sourceImage.naturalHeight - rect.h);
  let targetX = clamp(p.x - dragOffset.x, 0, maxX);
  let targetY = clamp(p.y - dragOffset.y, 0, maxY);
  if (pixelSnapActive) {
    const step = sourceOriginStepForScale(transform.scale);
    targetX = snapSourceOrigin(targetX, maxX, step);
    targetY = snapSourceOrigin(targetY, maxY, step);
  }

  transform.x = -targetX * transform.scale;
  transform.y = -targetY * transform.scale;
  clampTransform();
  if (fileKind === 'gif') clearGifPreviewFrames();
  redrawAll();
  if (fileKind === 'gif') scheduleGifPreviewRender('Updating animated scale preview...');
  ev.preventDefault();
});

function endDrag(ev) {
  if (!dragging) return;
  dragging = false;
  try { sourceCanvas.releasePointerCapture(ev.pointerId); } catch (_) {}
  if (fileKind === 'gif') scheduleGifPreviewRender('Updating animated scale preview...');
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
  pixelSnapActive = false;
  setScaleKeepingPanelCenter(Number(zoomInput.value || fitScale()));
  transformChanged();
});
fitCropBtn?.addEventListener('click', () => {
  pixelSnapActive = false;
  setScaleCentered(fitScale());
  transformChanged();
});
centerCropBtn?.addEventListener('click', () => {
  pixelSnapActive = false;
  setScaleCentered(fillScale());
  transformChanged();
});
integerZoomBtn?.addEventListener('click', () => {
  snapToPixelGrid();
  transformChanged();
});
[scaleMode, resampleMode, bgInput].forEach(el => {
  el?.addEventListener('input', () => { pixelSnapActive = false; transformChanged(); });
  el?.addEventListener('change', () => { pixelSnapActive = false; transformChanged(); });
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
