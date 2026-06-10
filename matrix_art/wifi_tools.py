from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import Any


class WifiError(RuntimeError):
    pass


WIFI_PROFILE_PREFIX = "matrix-art-wifi-"
MIN_WPA_PASSWORD_LEN = 8
MAX_WPA_PASSWORD_LEN = 63


def _require_nmcli() -> None:
    if not shutil.which('nmcli'):
        raise WifiError('nmcli was not found. Install or enable NetworkManager first.')


def _run(args: list[str], *, timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise WifiError(f'Command not found: {args[0]}') from exc
    except subprocess.TimeoutExpired as exc:
        raise WifiError(f'Command timed out: {" ".join(args)}') from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or 'unknown error').strip()
        raise WifiError(detail)
    return proc


def _nmcli(args: list[str], *, timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess[str]:
    _require_nmcli()
    return _run(['nmcli'] + args, timeout=timeout, check=check)


def split_nmcli_terse(line: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    escape = False
    for ch in line.rstrip('\n'):
        if escape:
            buf.append(ch)
            escape = False
        elif ch == '\\':
            escape = True
        elif ch == ':':
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append(''.join(buf))
    return parts


def sanitize_name(value: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    cleaned = cleaned.strip("_") or "unnamed"
    return cleaned[:max_len]


def profile_name_wifi(ssid: str, interface: str | None = None) -> str:
    iface_part = sanitize_name(interface or "any", 12)
    ssid_part = sanitize_name(ssid, 36)
    return f"{WIFI_PROFILE_PREFIX}{iface_part}-{ssid_part}"


def validate_wpa_passphrase(passphrase: str) -> None:
    if not passphrase:
        return
    if not (MIN_WPA_PASSWORD_LEN <= len(passphrase) <= MAX_WPA_PASSWORD_LEN):
        raise WifiError("Passphrase must be 8 to 63 characters for WPA/WPA2.")


def normalize_wifi_entry(entry: dict[str, Any]) -> dict[str, Any]:
    ssid = str(entry.get('ssid') or entry.get('name') or '').strip()
    password = str(entry.get('password') or entry.get('passphrase') or entry.get('psk') or '')
    interface = entry.get('interface') or entry.get('ifname') or None
    if interface == '':
        interface = None
    autoconnect = entry.get('autoconnect', True)
    if isinstance(autoconnect, str):
        autoconnect = autoconnect.strip().lower() not in {'0', 'false', 'no', 'off'}
    hidden = entry.get('hidden', False)
    if isinstance(hidden, str):
        hidden = hidden.strip().lower() in {'1', 'true', 'yes', 'on'}
    try:
        priority = int(entry.get('priority', 0) or 0)
    except Exception:
        priority = 0
    profile_name = str(entry.get('profile_name') or profile_name_wifi(ssid, interface))
    return {
        'ssid': ssid,
        'password': password,
        'passphrase': password,
        'interface': interface,
        'hidden': bool(hidden),
        'autoconnect': bool(autoconnect),
        'priority': priority,
        'profile_name': profile_name,
        'notes': str(entry.get('notes') or ''),
    }


def wifi_interfaces() -> list[dict[str, str]]:
    proc = _nmcli(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device'], check=True)
    result: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = split_nmcli_terse(line)
        while len(parts) < 4:
            parts.append('')
        device, typ, state, connection = parts[:4]
        if typ == 'wifi':
            result.append({'device': device, 'state': state, 'connection': connection})
    return result


def active_connections() -> list[dict[str, str]]:
    proc = _nmcli(['-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'], check=False)
    result: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = split_nmcli_terse(line)
        while len(parts) < 3:
            parts.append('')
        result.append({'name': parts[0], 'type': parts[1], 'device': parts[2]})
    return result


def scan_wifi_networks(interface: str | None = None) -> list[dict[str, Any]]:
    iface = interface
    if not iface:
        interfaces = wifi_interfaces()
        iface = interfaces[0]['device'] if interfaces else None
    if not iface:
        raise WifiError('No Wi-Fi interface found.')
    _nmcli(['device', 'wifi', 'rescan', 'ifname', iface], timeout=20, check=False)
    time.sleep(1.0)
    proc = _nmcli(['-t', '-f', 'SSID,BSSID,CHAN,SIGNAL,SECURITY,IN-USE', 'device', 'wifi', 'list', 'ifname', iface], timeout=30, check=True)
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = split_nmcli_terse(line)
        while len(parts) < 6:
            parts.append('')
        ssid, bssid, channel, signal, security, in_use = parts[:6]
        ssid = ssid or '<hidden>'
        try:
            sig_int = int(signal or 0)
        except Exception:
            sig_int = 0
        row = {
            'ssid': ssid,
            'bssid': bssid,
            'channel': channel,
            'signal': sig_int,
            'security': security,
            'in_use': in_use == '*',
            'interface': iface,
        }
        key = (ssid, security)
        if key not in best_by_key or sig_int > int(best_by_key[key].get('signal') or 0):
            best_by_key[key] = row
    return sorted(best_by_key.values(), key=lambda item: int(item.get('signal') or 0), reverse=True)


def connection_exists(name: str) -> bool:
    proc = _nmcli(['-t', '-f', 'NAME', 'connection', 'show'], check=False)
    return name in proc.stdout.splitlines()


def delete_wifi_profile(profile_name: str) -> None:
    if profile_name and connection_exists(profile_name):
        _nmcli(['connection', 'delete', profile_name], timeout=30, check=False)


def create_or_update_wifi_profile(entry: dict[str, Any]) -> dict[str, Any]:
    entry = normalize_wifi_entry(entry)
    ssid = entry['ssid']
    if not ssid:
        raise WifiError('SSID is required.')
    validate_wpa_passphrase(entry.get('password', ''))

    con_name = entry.get('profile_name') or profile_name_wifi(ssid, entry.get('interface'))
    entry['profile_name'] = con_name
    delete_wifi_profile(con_name)

    add_args = ['connection', 'add', 'type', 'wifi', 'con-name', con_name, 'ssid', ssid]
    add_args += ['ifname', entry['interface'] if entry.get('interface') else '*']
    _nmcli(add_args, timeout=30, check=True)

    _nmcli([
        'connection', 'modify', con_name,
        'connection.autoconnect', 'yes' if entry.get('autoconnect', True) else 'no',
        'connection.autoconnect-priority', str(int(entry.get('priority', 0) or 0)),
    ], timeout=30, check=True)

    if entry.get('hidden'):
        _nmcli(['connection', 'modify', con_name, '802-11-wireless.hidden', 'yes'], timeout=30, check=False)

    password = entry.get('password') or ''
    if password:
        _nmcli([
            'connection', 'modify', con_name,
            'wifi-sec.key-mgmt', 'wpa-psk',
            'wifi-sec.psk', password,
        ], timeout=30, check=True)
    else:
        _nmcli(['connection', 'modify', con_name, 'wifi-sec.key-mgmt', ''], timeout=30, check=False)

    return entry


def connect_wifi_entry(entry: dict[str, Any]) -> str:
    entry = create_or_update_wifi_profile(entry)
    con_name = entry['profile_name']
    args = ['connection', 'up', con_name]
    if entry.get('interface'):
        args += ['ifname', entry['interface']]
    proc = _nmcli(args, timeout=60, check=True)
    return (proc.stdout or proc.stderr or f'connected using saved profile {con_name}').strip()


def connect_wifi(ssid: str, password: str = '', interface: str | None = None, hidden: bool = False) -> str:
    """One-shot connect without adding it to Matrix-Art's saved network list."""
    ssid = (ssid or '').strip()
    if not ssid:
        raise WifiError('SSID is required.')
    validate_wpa_passphrase(password)
    args = ['device', 'wifi', 'connect', ssid]
    if password:
        args += ['password', password]
    if interface:
        args += ['ifname', interface]
    if hidden:
        args += ['hidden', 'yes']
    proc = _nmcli(args, timeout=60, check=True)
    return (proc.stdout or proc.stderr or 'connection command completed').strip()


def disconnect_wifi(interface: str) -> str:
    if not interface:
        raise WifiError('Interface is required.')
    proc = _nmcli(['device', 'disconnect', interface], timeout=30, check=True)
    return (proc.stdout or proc.stderr or 'disconnect command completed').strip()


def wifi_status() -> dict[str, Any]:
    try:
        interfaces = wifi_interfaces()
        active = active_connections()
        return {'ok': True, 'interfaces': interfaces, 'active': active}
    except Exception as exc:
        return {'ok': False, 'error': str(exc), 'interfaces': [], 'active': []}

# -----------------------------
# Hotspot and startup helpers
# -----------------------------

HOTSPOT_PROFILE_PREFIX = "matrix-art-hotspot-"
DEFAULT_HOTSPOT_IPV4 = "10.42.0.1/24"


def profile_name_hotspot(ssid: str, interface: str | None = None) -> str:
    iface_part = sanitize_name(interface or "any", 12)
    ssid_part = sanitize_name(ssid or "Matrix-Art", 36)
    return f"{HOTSPOT_PROFILE_PREFIX}{iface_part}-{ssid_part}"


def _list_connection_names(prefix: str) -> list[str]:
    proc = _nmcli(['-t', '-f', 'NAME', 'connection', 'show'], check=False)
    return [line for line in proc.stdout.splitlines() if line.startswith(prefix)]


def set_matrix_art_hotspots_autoconnect(enabled: bool) -> None:
    for name in _list_connection_names(HOTSPOT_PROFILE_PREFIX):
        _nmcli(['connection', 'modify', name, 'connection.autoconnect', 'yes' if enabled else 'no'], timeout=20, check=False)


def stop_matrix_art_hotspots() -> list[str]:
    stopped: list[str] = []
    for active in active_connections():
        name = active.get('name') or ''
        if name.startswith(HOTSPOT_PROFILE_PREFIX):
            _nmcli(['connection', 'down', name], timeout=20, check=False)
            stopped.append(name)
    return stopped


def create_or_update_hotspot_profile(
    ssid: str,
    password: str,
    interface: str | None = None,
    *,
    ipv4_address: str = DEFAULT_HOTSPOT_IPV4,
    autoconnect: bool = True,
) -> dict[str, Any]:
    ssid = (ssid or '').strip()
    if not ssid:
        raise WifiError('Hotspot SSID is required.')
    validate_wpa_passphrase(password)
    if not password:
        raise WifiError('Hotspot password is required.')
    con_name = profile_name_hotspot(ssid, interface)
    delete_wifi_profile(con_name)

    add_args = ['connection', 'add', 'type', 'wifi', 'con-name', con_name, 'ssid', ssid]
    add_args += ['ifname', interface if interface else '*']
    _nmcli(add_args, timeout=30, check=True)

    _nmcli([
        'connection', 'modify', con_name,
        'connection.autoconnect', 'yes' if autoconnect else 'no',
        'connection.autoconnect-priority', '100',
        '802-11-wireless.mode', 'ap',
        'ipv4.method', 'shared',
        'ipv4.addresses', ipv4_address,
        'ipv6.method', 'ignore',
        'wifi-sec.key-mgmt', 'wpa-psk',
        'wifi-sec.psk', password,
    ], timeout=30, check=True)

    return {
        'ssid': ssid,
        'password': password,
        'interface': interface,
        'profile_name': con_name,
        'ipv4_address': ipv4_address,
        'autoconnect': bool(autoconnect),
    }


def start_hotspot(
    ssid: str,
    password: str,
    interface: str | None = None,
    *,
    persist: bool = True,
    ipv4_address: str = DEFAULT_HOTSPOT_IPV4,
) -> str:
    entry = create_or_update_hotspot_profile(
        ssid,
        password,
        interface,
        ipv4_address=ipv4_address,
        autoconnect=bool(persist),
    )
    con_name = str(entry['profile_name'])
    # A single Wi-Fi radio normally cannot be a normal client and AP at the same time.
    if interface:
        _nmcli(['device', 'disconnect', interface], timeout=20, check=False)
        time.sleep(0.8)
        proc = _nmcli(['connection', 'up', con_name, 'ifname', interface], timeout=60, check=True)
    else:
        proc = _nmcli(['connection', 'up', con_name], timeout=60, check=True)
    return (proc.stdout or proc.stderr or f'started hotspot {ssid}').strip()


def ip_addresses() -> list[dict[str, str]]:
    proc = _run(['ip', '-o', '-4', 'addr', 'show'], timeout=10, check=False)
    out: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[1] == 'lo':
            continue
        if 'inet' not in parts:
            continue
        try:
            addr = parts[parts.index('inet') + 1].split('/')[0]
        except Exception:
            continue
        if addr and not addr.startswith('127.'):
            out.append({'interface': parts[1], 'address': addr})
    return out


def first_ipv4() -> str | None:
    addrs = ip_addresses()
    return addrs[0]['address'] if addrs else None


def wait_for_ipv4(timeout: float = 30.0, interval: float = 1.0) -> str | None:
    deadline = time.time() + max(0.0, float(timeout))
    while time.time() <= deadline:
        ip = first_ipv4()
        if ip:
            return ip
        time.sleep(max(0.1, float(interval)))
    return first_ipv4()


def visible_saved_networks(saved_entries: list[dict[str, Any]], interface: str | None = None) -> list[dict[str, Any]]:
    """Return saved entries whose SSIDs currently appear in a scan.

    Hidden networks are returned because a scan cannot reliably prove absence.
    """
    if not saved_entries:
        return []
    hidden = [normalize_wifi_entry(e) for e in saved_entries if normalize_wifi_entry(e).get('hidden')]
    try:
        scanned = scan_wifi_networks(interface)
    except Exception:
        scanned = []
    ssids = {str(net.get('ssid') or '') for net in scanned}
    visible = [normalize_wifi_entry(e) for e in saved_entries if str(normalize_wifi_entry(e).get('ssid') or '') in ssids]
    return hidden + [e for e in visible if e not in hidden]
