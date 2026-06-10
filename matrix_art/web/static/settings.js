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

async function postForm(url, formData) {
  const res = await fetch(url, {
    method: 'POST',
    body: formData,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.ok === false) throw new Error(body.error || res.statusText);
  return body;
}

function setStatus(text) {
  const box = qs('settingsStatus');
  if (box) box.textContent = text;
}

function fmtBytes(value) {
  if (value === null || value === undefined) return '--';
  const n = Number(value);
  if (!Number.isFinite(n)) return '--';
  const units = ['B', 'KB', 'MB', 'GB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function uiPayload() {
  return {
    title: qs('uiTitle').value,
    library_subtitle: qs('uiLibrarySubtitle').value,
    upload_subtitle: qs('uiUploadSubtitle').value,
    draw_subtitle: qs('uiDrawSubtitle').value,
    code_subtitle: qs('uiCodeSubtitle').value,
    settings_subtitle: qs('uiSettingsSubtitle').value,
  };
}

function renderSecurity(security) {
  if (!security) return;
  const pinState = qs('securityPinState');
  const unlockState = qs('securityUnlockState');
  const lockBtn = qs('lockSettingsNowBtn');
  const disableBtn = qs('disableSettingsPinBtn');
  const saveBtn = qs('saveSettingsPinBtn');
  if (pinState) pinState.textContent = security.pin_enabled ? 'ON' : 'OFF';
  if (unlockState) unlockState.textContent = security.unlocked ? 'YES' : 'NO';
  if (lockBtn) lockBtn.disabled = !security.pin_enabled;
  if (disableBtn) disableBtn.disabled = !security.pin_enabled;
  if (saveBtn) saveBtn.textContent = security.pin_enabled ? 'Change PIN' : 'Set PIN';
}

function clearPinFields() {
  for (const id of ['settingsCurrentPin', 'settingsNewPin', 'settingsConfirmPin']) {
    const el = qs(id);
    if (el) el.value = '';
  }
}

async function refreshSecurity() {
  try {
    const body = await getJson('/api/settings/security/status');
    renderSecurity(body.security || {});
  } catch (err) {
    setStatus(`Security status failed: ${err.message}`);
  }
}

async function saveSettingsPin() {
  const newPin = qs('settingsNewPin')?.value || '';
  const confirmPin = qs('settingsConfirmPin')?.value || '';
  const currentPin = qs('settingsCurrentPin')?.value || '';
  try {
    const body = await postJson('/api/settings/security/pin', {
      action: 'set',
      current_pin: currentPin,
      new_pin: newPin,
      confirm_pin: confirmPin,
    });
    renderSecurity(body.security || {});
    clearPinFields();
    setStatus('Settings PIN saved.');
  } catch (err) {
    setStatus(`PIN save failed: ${err.message}`);
  }
}

async function lockSettingsNow() {
  try {
    await postJson('/api/settings/security/pin', {action: 'lock'});
    window.location.href = '/settings';
  } catch (err) {
    setStatus(`Lock failed: ${err.message}`);
  }
}

async function disableSettingsPin() {
  const currentPin = qs('settingsCurrentPin')?.value || '';
  if (!confirm('Disable the Settings PIN? Settings will be accessible without a PIN.')) return;
  try {
    const body = await postJson('/api/settings/security/pin', {
      action: 'disable',
      current_pin: currentPin,
    });
    renderSecurity(body.security || {});
    clearPinFields();
    setStatus('Settings PIN disabled.');
  } catch (err) {
    setStatus(`Disable PIN failed: ${err.message}`);
  }
}

async function restoreDatabaseBackup() {
  const input = qs('databaseRestoreFile');
  const file = input?.files?.[0];
  if (!file) {
    setStatus('Choose a Matrix-Art backup file first.');
    return;
  }
  const msg = 'Restore this database backup? This replaces the current library, folders, settings, Code effects, demos, and saved database entries. The current Settings PIN is kept.';
  if (!confirm(msg)) return;
  const form = new FormData();
  form.append('backup', file);
  try {
    setStatus('Restoring database backup...');
    const body = await postForm('/api/settings/database/restore', form);
    const rows = body.result?.restored_rows ?? 0;
    setStatus(`Database restored. ${rows} row(s) imported. Settings PIN preserved. Reloading...`);
    setTimeout(() => window.location.reload(), 1200);
  } catch (err) {
    setStatus(`Database restore failed: ${err.message}`);
  }
}

async function saveUiText() {
  try {
    const body = await postJson('/api/settings/ui', uiPayload());
    setStatus(`Saved page text for ${body.ui.title}. Reload pages to see all changes.`);
  } catch (err) {
    setStatus(`Save failed: ${err.message}`);
  }
}

async function saveCodeSettings() {
  try {
    const body = await postJson('/api/settings/code', {
      default_fps: Number(qs('codeDefaultFps').value || 24),
      max_fps: Number(qs('codeMaxFps').value || 0),
      editor_enabled: !!qs('codeEditorEnabled')?.checked,
    });
    setStatus(`Saved code timing: default ${body.default_fps} FPS, max ${body.max_fps || 'uncapped'}, editor ${body.editor_enabled ? 'enabled' : 'disabled'}.`);
  } catch (err) {
    setStatus(`Code settings failed: ${err.message}`);
  }
}

async function saveAnimationSettings() {
  try {
    const body = await postJson('/api/settings/animation', {
      max_gif_frames: Number(qs('animMaxFrames').value || 240),
      default_frame_duration_ms: Number(qs('animDefaultMs').value || 100),
      min_frame_duration_ms: Number(qs('animMinMs').value || 20),
      max_frame_duration_ms: Number(qs('animMaxMs').value || 5000),
    });
    const a = body.animation;
    setStatus(`Saved animation defaults: ${a.max_gif_frames} frames, ${a.default_frame_duration_ms} ms default.`);
  } catch (err) {
    setStatus(`Animation settings failed: ${err.message}`);
  }
}

async function refreshDiagnostics() {
  try {
    const body = await getJson('/api/diagnostics');
    const d = body.diagnostics || {};
    const cpu = d.cpu || {};
    const freq = (cpu.frequency || {});
    const mem = d.memory || {};
    qs('diagCpuUsage').textContent = cpu.usage_percent == null ? '--' : `${cpu.usage_percent}%`;
    qs('diagTemp').textContent = cpu.temperature_c == null ? '--' : `${cpu.temperature_c}°C`;
    qs('diagClock').textContent = freq.current_mhz == null ? '--' : `${freq.current_mhz} MHz`;
    qs('diagRam').textContent = mem.used_percent == null ? '--' : `${mem.used_percent}%`;
    const net = d.network || {};
    const ipLines = (net.ip || []).map(x => `${x.interface}: ${x.address}`);
    const ifaceLines = Object.entries(net.interfaces || {}).map(([name, x]) => {
      const rx = x.rx_bps == null ? '--' : `${fmtBytes(x.rx_bps)}/s`;
      const tx = x.tx_bps == null ? '--' : `${fmtBytes(x.tx_bps)}/s`;
      return `${name}: RX ${rx} (${fmtBytes(x.rx_bytes)} total), TX ${tx} (${fmtBytes(x.tx_bytes)} total)`;
    });
    if (d.matrix_timing) renderMatrixTiming(d.matrix_timing);
    qs('diagDetails').textContent = [
      `Host: ${d.hostname || '--'}`,
      `Time: ${d.time || '--'}`,
      `Load average: ${(d.load_average || []).join(', ') || '--'}`,
      `CPU clock: current ${freq.current_mhz ?? '--'} MHz, min ${freq.min_mhz ?? '--'} MHz, max ${freq.max_mhz ?? '--'} MHz`,
      `RAM: ${fmtBytes(mem.used_bytes)} used / ${fmtBytes(mem.total_bytes)} total, ${fmtBytes(mem.available_bytes)} available`,
      '',
      'IP addresses:',
      ipLines.length ? ipLines.join('\n') : '  none reported',
      '',
      'Network:',
      ifaceLines.length ? ifaceLines.join('\n') : '  none reported',
    ].join('\n');
  } catch (err) {
    qs('diagDetails').textContent = `Diagnostics failed: ${err.message}`;
  }
}


function yn(value) { return value ? 'yes' : 'no'; }

function renderMatrixTiming(timing) {
  const pwm = timing.hardware_pwm || {};
  const affinity = timing.affinity || {};
  const isolation = timing.isolation || {};
  const checks = isolation.checks || {};

  if (qs('matrixPwmStatus')) qs('matrixPwmStatus').textContent = pwm.ok ? 'OK' : 'Check';
  if (qs('matrixAffinityStatus')) qs('matrixAffinityStatus').textContent = affinity.enabled ? `core ${affinity.matrix_cpu_core}` : 'off';
  if (qs('matrixIsolationStatus')) qs('matrixIsolationStatus').textContent = isolation.ok ? 'OK' : 'not reserved';
  if (qs('matrixAudioStatus')) qs('matrixAudioStatus').textContent = pwm.audio_module_loaded ? 'loaded' : 'clear';

  const driver = timing.driver || {};
  const lines = [
    `Hardware PWM expected: ${yn(pwm.ok)}`,
    `GPIO mapping: ${pwm.gpio_mapping || '--'}`,
    `Hardware pulse enabled: ${yn(pwm.hardware_pulse_enabled)}`,
    `snd_bcm2835 audio module loaded: ${yn(pwm.audio_module_loaded)}`,
    '',
    `Matrix affinity enabled: ${yn(affinity.enabled)}`,
    `Matrix CPU core: ${affinity.matrix_cpu_core ?? '--'}`,
    `Main/web CPU cores: ${affinity.app_cpu_cores || '--'}`,
    `Current process allowed CPUs: ${affinity.current_process_allowed_list || '--'}`,
    `Priority status: ${affinity.priority_status || '--'}`,
    '',
    `Boot core isolation OK: ${yn(isolation.ok)}`,
    `isolcpus: ${yn(checks.isolcpus)}`,
    `nohz_full: ${yn(checks.nohz_full)}`,
    `rcu_nocbs: ${yn(checks.rcu_nocbs)}`,
    `irqaffinity: ${yn(checks.irqaffinity)}`,
    '',
    `Driver rows/cols: ${driver.rows || '--'}x${driver.cols || '--'}`,
    `slowdown_gpio: ${driver.slowdown_gpio ?? '--'}`,
    `limit_refresh_rate_hz: ${driver.limit_refresh_rate_hz ?? '--'}`,
    `pwm_bits: ${driver.pwm_bits ?? '--'}`,
    `pwm_lsb_nanoseconds: ${driver.pwm_lsb_nanoseconds ?? '--'}`,
    '',
    'Threads:',
    timing.threads || '--',
  ];
  if (qs('matrixTimingDetails')) qs('matrixTimingDetails').textContent = lines.join('\n');
}

async function refreshMatrixTiming() {
  try {
    const body = await getJson('/api/matrix/timing');
    renderMatrixTiming(body.timing || {});
  } catch (err) {
    if (qs('matrixTimingDetails')) qs('matrixTimingDetails').textContent = `Matrix timing status failed: ${err.message}`;
  }
}

function wifiPayload() {
  return {
    ssid: qs('wifiSsid')?.value || '',
    password: qs('wifiPassword')?.value || '',
    interface: qs('wifiInterface')?.value || null,
    hidden: !!qs('wifiHidden')?.checked,
    autoconnect: !!qs('wifiAutoconnect')?.checked,
  };
}

function renderWifiStatus(body) {
  const select = qs('wifiInterface');
  const current = select.value;
  select.innerHTML = '';
  for (const iface of body.interfaces || []) {
    const opt = document.createElement('option');
    opt.value = iface.device;
    opt.textContent = `${iface.device} (${iface.state || 'unknown'}${iface.connection ? `: ${iface.connection}` : ''})`;
    select.appendChild(opt);
  }
  if (current) select.value = current;
  const active = (body.active || []).map(x => `${x.device || '--'}: ${x.name} (${x.type})`).join('\n');
  qs('wifiStatus').textContent = body.ok ? `Interfaces: ${(body.interfaces || []).length}\nActive connections:\n${active || 'none'}` : `Wi-Fi error: ${body.error}`;
  if (Array.isArray(body.saved)) renderSavedWifi(body.saved);
}

function chooseNetwork(net) {
  qs('wifiSsid').value = net.ssid === '<hidden>' ? '' : net.ssid;
  qs('wifiHidden').checked = net.ssid === '<hidden>' || !!net.hidden;
  if (net.interface) qs('wifiInterface').value = net.interface;
  if (Object.prototype.hasOwnProperty.call(net, 'password')) {
    qs('wifiPassword').value = net.password || '';
  }
  if (Object.prototype.hasOwnProperty.call(net, 'autoconnect')) {
    qs('wifiAutoconnect').checked = !!net.autoconnect;
  }
  qs('wifiPassword').focus();
}

function renderSavedWifi(saved) {
  const box = qs('wifiSavedNetworks');
  if (!box) return;
  box.innerHTML = '';
  if (!saved || !saved.length) {
    box.textContent = 'No saved networks yet.';
    return;
  }
  for (const entry of saved) {
    const row = document.createElement('div');
    row.className = 'wifi-saved-row';

    const info = document.createElement('button');
    info.type = 'button';
    info.className = 'wifi-saved-info';
    const title = document.createElement('strong');
    title.textContent = entry.ssid || '(no SSID)';
    const meta = document.createElement('span');
    meta.textContent = `${entry.interface || 'any interface'} · ${entry.hidden ? 'hidden' : 'visible'} · ${entry.autoconnect ? 'autoconnect' : 'manual'}`;
    info.append(title, meta);
    info.addEventListener('click', () => chooseNetwork(entry));

    const actions = document.createElement('div');
    actions.className = 'wifi-saved-actions';
    const connect = document.createElement('button');
    connect.type = 'button';
    connect.className = 'btn small';
    connect.textContent = 'Connect';
    connect.addEventListener('click', () => connectSavedWifi(entry));
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn small danger';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => removeSavedWifi(entry));
    actions.append(connect, remove);
    row.append(info, actions);
    box.appendChild(row);
  }
}

async function refreshSavedWifi() {
  try {
    const body = await getJson('/api/wifi/saved');
    renderSavedWifi(body.saved || []);
  } catch (err) {
    qs('wifiSavedNetworks').textContent = `Saved list failed: ${err.message}`;
  }
}

async function refreshWifi() {
  try {
    const body = await getJson('/api/wifi/status');
    renderWifiStatus(body);
  } catch (err) {
    qs('wifiStatus').textContent = `Wi-Fi status failed: ${err.message}`;
  }
}

async function scanWifi() {
  const box = qs('wifiNetworks');
  box.textContent = 'Scanning...';
  try {
    const body = await postJson('/api/wifi/scan', {interface: qs('wifiInterface').value || null});
    box.innerHTML = '';
    for (const net of body.networks || []) {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'wifi-network-row';
      row.innerHTML = `<strong></strong><span></span>`;
      row.querySelector('strong').textContent = net.ssid;
      row.querySelector('span').textContent = `${net.signal}% · ch ${net.channel || '--'} · ${net.security || 'open'}${net.in_use ? ' · connected' : ''}`;
      row.addEventListener('click', () => chooseNetwork(net));
      box.appendChild(row);
    }
    if (!box.children.length) box.textContent = 'No networks returned.';
  } catch (err) {
    box.textContent = `Scan failed: ${err.message}`;
  }
}

async function connectWifi() {
  try {
    qs('wifiStatus').textContent = 'Connecting...';
    const body = await postJson('/api/wifi/connect', wifiPayload());
    qs('wifiStatus').textContent = body.message || 'Connect command completed.';
    if (body.saved) renderSavedWifi(body.saved);
    setTimeout(refreshWifi, 1500);
  } catch (err) {
    qs('wifiStatus').textContent = `Connect failed: ${err.message}`;
  }
}

async function saveWifi() {
  try {
    qs('wifiStatus').textContent = 'Saving network profile...';
    const body = await postJson('/api/wifi/save', wifiPayload());
    qs('wifiStatus').textContent = body.message || 'Saved network profile.';
    renderSavedWifi(body.saved || []);
    setTimeout(refreshWifi, 1000);
  } catch (err) {
    qs('wifiStatus').textContent = `Save failed: ${err.message}`;
  }
}

async function connectSaveWifi() {
  try {
    qs('wifiStatus').textContent = 'Saving and connecting...';
    const body = await postJson('/api/wifi/connect-save', wifiPayload());
    qs('wifiStatus').textContent = body.message || 'Connect + Save command completed.';
    renderSavedWifi(body.saved || []);
    setTimeout(refreshWifi, 1500);
  } catch (err) {
    qs('wifiStatus').textContent = `Connect + Save failed: ${err.message}`;
  }
}

async function connectSavedWifi(entry) {
  try {
    qs('wifiStatus').textContent = `Connecting saved network ${entry.ssid}...`;
    const body = await postJson('/api/wifi/connect-saved', {
      ssid: entry.ssid,
      interface: entry.interface || null,
    });
    qs('wifiStatus').textContent = body.message || 'Saved network connect command completed.';
    if (body.saved) renderSavedWifi(body.saved);
    setTimeout(refreshWifi, 1500);
  } catch (err) {
    qs('wifiStatus').textContent = `Saved connect failed: ${err.message}`;
  }
}

async function removeSavedWifi(entry) {
  if (!confirm(`Remove saved network ${entry.ssid}? This also removes the Matrix-Art NetworkManager profile for it.`)) return;
  try {
    const body = await postJson('/api/wifi/remove-saved', {
      ssid: entry.ssid,
      interface: entry.interface || null,
      delete_profile: true,
    });
    renderSavedWifi(body.saved || []);
    qs('wifiStatus').textContent = `Removed saved network ${entry.ssid}.`;
    setTimeout(refreshWifi, 1000);
  } catch (err) {
    qs('wifiStatus').textContent = `Remove failed: ${err.message}`;
  }
}

async function startHotspot() {
  const ssid = qs('hotspotSsid')?.value || '';
  const password = qs('hotspotPassword')?.value || '';
  const iface = qs('wifiInterface')?.value || null;
  if (!ssid.trim()) {
    qs('wifiStatus').textContent = 'Hotspot SSID is required.';
    return;
  }
  if (password.length < 8 || password.length > 63) {
    qs('wifiStatus').textContent = 'Hotspot password must be 8 to 63 characters.';
    return;
  }
  const msg = `Start hotspot "${ssid}" on ${iface || 'any Wi-Fi adapter'}? Existing wireless connections on that adapter will be disconnected. Continue?`;
  if (!confirm(msg)) return;
  try {
    qs('wifiStatus').textContent = 'Starting hotspot...';
    const body = await postJson('/api/wifi/hotspot/start', {ssid, password, interface: iface});
    qs('wifiStatus').textContent = `${body.message || 'Hotspot started.'}\nIP: ${body.ip || 'waiting for IP'}\nThe panel is showing the IP countdown.`;
    setTimeout(refreshWifi, 1500);
  } catch (err) {
    qs('wifiStatus').textContent = `Hotspot failed: ${err.message}`;
  }
}

async function disconnectWifi() {
  try {
    const iface = qs('wifiInterface').value;
    if (!iface) return;
    if (!confirm(`Disconnect ${iface}? This can interrupt your browser session if you are using this Wi-Fi link.`)) return;
    const body = await postJson('/api/wifi/disconnect', {interface: iface});
    qs('wifiStatus').textContent = body.message || 'Disconnect command completed.';
    setTimeout(refreshWifi, 1500);
  } catch (err) {
    qs('wifiStatus').textContent = `Disconnect failed: ${err.message}`;
  }
}

function renderFolderSettings(folders) {
  const box = qs('folderSettingsList');
  if (!box) return;
  box.innerHTML = '';
  if (!folders || !folders.length) {
    box.textContent = 'No folders found.';
    return;
  }
  for (const folder of folders) {
    const row = document.createElement('div');
    row.className = 'folder-settings-row';
    row.dataset.path = folder.path;

    const info = document.createElement('div');
    info.className = 'folder-settings-info';
    const title = document.createElement('strong');
    title.textContent = `${folder.path}${folder.virtual ? ' (system)' : ''}`;
    const meta = document.createElement('span');
    meta.textContent = `${folder.count ?? 0} item(s)${folder.direct_count !== folder.count ? `, ${folder.direct_count ?? 0} direct` : ''}`;
    info.append(title, meta);

    const protectLabel = document.createElement('label');
    protectLabel.className = 'enabled-check';
    const protect = document.createElement('input');
    protect.type = 'checkbox';
    protect.checked = !!folder.protected;
    protect.disabled = !!folder.virtual;
    protect.addEventListener('change', () => setFolderProtected(folder.path, protect.checked));
    protectLabel.append(protect, document.createTextNode(' Protected'));

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn small danger';
    del.textContent = 'Delete';
    del.disabled = !!folder.protected || !!folder.virtual;
    del.addEventListener('click', () => deleteFolderFromSettings(folder.path));

    const actions = document.createElement('div');
    actions.className = 'folder-settings-actions';
    actions.append(protectLabel, del);

    row.append(info, actions);
    box.appendChild(row);
  }
}

async function refreshFolders() {
  const box = qs('folderSettingsList');
  if (box) box.textContent = 'Loading folders...';
  try {
    const body = await getJson('/api/folders/settings');
    renderFolderSettings(body.folders || []);
  } catch (err) {
    if (box) box.textContent = `Folder settings failed: ${err.message}`;
  }
}

async function setFolderProtected(folderPath, protected) {
  try {
    const body = await postJson('/api/folders/protect', {folder_path: folderPath, protected});
    renderFolderSettings(body.folders || []);
    setStatus(`${protected ? 'Protected' : 'Unprotected'} ${folderPath}.`);
  } catch (err) {
    setStatus(`Folder protection failed: ${err.message}`);
    refreshFolders();
  }
}

async function deleteFolderFromSettings(folderPath) {
  if (!confirm(`Delete folder "${folderPath}"? Its contents and subfolder contents will be moved to Unfiled.`)) return;
  try {
    const body = await postJson('/api/folders/delete', {folder_path: folderPath});
    const result = body.result || {};
    setStatus(`Deleted folder ${result.path || folderPath}; moved ${result.moved_count || 0} item(s) to Unfiled.`);
    refreshFolders();
  } catch (err) {
    setStatus(`Delete folder failed: ${err.message}`);
    refreshFolders();
  }
}

function init() {
  qs('saveSettingsPinBtn')?.addEventListener('click', saveSettingsPin);
  qs('lockSettingsNowBtn')?.addEventListener('click', lockSettingsNow);
  qs('disableSettingsPinBtn')?.addEventListener('click', disableSettingsPin);
  qs('saveUiTextBtn')?.addEventListener('click', saveUiText);
  qs('databaseRestoreBtn')?.addEventListener('click', restoreDatabaseBackup);
  qs('saveCodeSettingsBtn')?.addEventListener('click', saveCodeSettings);
  qs('saveAnimationSettingsBtn')?.addEventListener('click', saveAnimationSettings);
  qs('refreshFoldersBtn')?.addEventListener('click', refreshFolders);
  qs('refreshDiagBtn')?.addEventListener('click', refreshDiagnostics);
  qs('refreshMatrixTimingBtn')?.addEventListener('click', refreshMatrixTiming);
  qs('wifiRefreshBtn')?.addEventListener('click', refreshWifi);
  qs('wifiSavedRefreshBtn')?.addEventListener('click', refreshSavedWifi);
  qs('wifiScanBtn')?.addEventListener('click', scanWifi);
  qs('wifiConnectBtn')?.addEventListener('click', connectWifi);
  qs('wifiSaveBtn')?.addEventListener('click', saveWifi);
  qs('wifiConnectSaveBtn')?.addEventListener('click', connectSaveWifi);
  qs('wifiDisconnectBtn')?.addEventListener('click', disconnectWifi);
  qs('hotspotStartBtn')?.addEventListener('click', startHotspot);
  refreshSecurity();
  refreshDiagnostics();
  refreshMatrixTiming();
  refreshFolders();
  refreshWifi();
  setInterval(refreshDiagnostics, 3000);
}

init();
