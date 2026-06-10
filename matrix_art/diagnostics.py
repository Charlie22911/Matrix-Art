from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_last_cpu: tuple[int, int] | None = None
_last_net: tuple[float, dict[str, tuple[int, int]]] | None = None


def _read_text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding='utf-8').strip()
    except Exception:
        return ''


def _read_int(path: str | Path) -> int | None:
    text = _read_text(path)
    try:
        return int(text)
    except Exception:
        return None


def _cpu_freqs() -> dict[str, Any]:
    cpus = sorted(Path('/sys/devices/system/cpu').glob('cpu[0-9]*'))
    cur_vals: list[int] = []
    min_vals: list[int] = []
    max_vals: list[int] = []
    per_cpu: list[dict[str, Any]] = []
    for cpu in cpus:
        cpufreq = cpu / 'cpufreq'
        cur = _read_int(cpufreq / 'scaling_cur_freq') or _read_int(cpufreq / 'cpuinfo_cur_freq')
        mn = _read_int(cpufreq / 'scaling_min_freq') or _read_int(cpufreq / 'cpuinfo_min_freq')
        mx = _read_int(cpufreq / 'scaling_max_freq') or _read_int(cpufreq / 'cpuinfo_max_freq')
        def mhz(v: int | None) -> float | None:
            return round(v / 1000.0, 1) if v is not None else None
        if cur is not None:
            cur_vals.append(cur)
        if mn is not None:
            min_vals.append(mn)
        if mx is not None:
            max_vals.append(mx)
        per_cpu.append({'cpu': cpu.name, 'current_mhz': mhz(cur), 'min_mhz': mhz(mn), 'max_mhz': mhz(mx)})
    return {
        'current_mhz': round((sum(cur_vals) / len(cur_vals)) / 1000.0, 1) if cur_vals else None,
        'min_mhz': round((min(min_vals)) / 1000.0, 1) if min_vals else None,
        'max_mhz': round((max(max_vals)) / 1000.0, 1) if max_vals else None,
        'per_cpu': per_cpu,
    }


def _cpu_usage() -> float | None:
    global _last_cpu
    first = _read_text('/proc/stat').splitlines()[0] if _read_text('/proc/stat') else ''
    parts = first.split()
    if len(parts) < 5 or parts[0] != 'cpu':
        return None
    values = [int(x) for x in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    with _lock:
        prev = _last_cpu
        _last_cpu = (total, idle)
    if not prev:
        return None
    prev_total, prev_idle = prev
    total_delta = total - prev_total
    idle_delta = idle - prev_idle
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0)), 1)


def _temperature_c() -> float | None:
    raw = _read_int('/sys/class/thermal/thermal_zone0/temp')
    if raw is None:
        return None
    return round(raw / 1000.0, 1)


def _memory() -> dict[str, Any]:
    data: dict[str, int] = {}
    for line in _read_text('/proc/meminfo').splitlines():
        if ':' not in line:
            continue
        key, rest = line.split(':', 1)
        try:
            data[key] = int(rest.strip().split()[0]) * 1024
        except Exception:
            pass
    total = data.get('MemTotal', 0)
    available = data.get('MemAvailable', 0)
    used = max(0, total - available)
    return {
        'total_bytes': total,
        'available_bytes': available,
        'used_bytes': used,
        'used_percent': round((used / total) * 100.0, 1) if total else None,
    }


def _net_raw() -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for line in _read_text('/proc/net/dev').splitlines()[2:]:
        if ':' not in line:
            continue
        iface, rest = line.split(':', 1)
        iface = iface.strip()
        if iface == 'lo':
            continue
        parts = rest.split()
        if len(parts) >= 16:
            try:
                result[iface] = (int(parts[0]), int(parts[8]))
            except Exception:
                pass
    return result


def _ip_info() -> list[dict[str, str]]:
    try:
        proc = subprocess.run(['ip', '-o', '-4', 'addr', 'show'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        lines = proc.stdout.splitlines()
    except Exception:
        lines = []
    result = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 4 and parts[2] == 'inet':
            result.append({'interface': parts[1], 'address': parts[3]})
    return result


def _network() -> dict[str, Any]:
    global _last_net
    now = time.time()
    raw = _net_raw()
    with _lock:
        prev = _last_net
        _last_net = (now, raw)
    rates: dict[str, dict[str, Any]] = {}
    for iface, (rx, tx) in raw.items():
        rx_rate = tx_rate = None
        if prev:
            prev_time, prev_raw = prev
            dt = max(0.001, now - prev_time)
            if iface in prev_raw:
                prx, ptx = prev_raw[iface]
                rx_rate = max(0.0, (rx - prx) / dt)
                tx_rate = max(0.0, (tx - ptx) / dt)
        rates[iface] = {
            'rx_bytes': rx,
            'tx_bytes': tx,
            'rx_bps': round(rx_rate, 1) if rx_rate is not None else None,
            'tx_bps': round(tx_rate, 1) if tx_rate is not None else None,
        }
    return {'interfaces': rates, 'ip': _ip_info()}


def diagnostics_snapshot() -> dict[str, Any]:
    loadavg = os.getloadavg() if hasattr(os, 'getloadavg') else (0.0, 0.0, 0.0)
    return {
        'hostname': socket.gethostname(),
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'uptime_seconds': float(_read_text('/proc/uptime').split()[0]) if _read_text('/proc/uptime') else None,
        'load_average': [round(x, 2) for x in loadavg],
        'cpu': {
            'usage_percent': _cpu_usage(),
            'temperature_c': _temperature_c(),
            'frequency': _cpu_freqs(),
        },
        'memory': _memory(),
        'network': _network(),
    }


def _self_cpu_allowed_list() -> str:
    for line in _read_text('/proc/self/status').splitlines():
        if line.startswith('Cpus_allowed_list:'):
            return line.split(':', 1)[1].strip()
    return ''


def _module_loaded(name: str) -> bool:
    return any(line.split()[0] == name for line in _read_text('/proc/modules').splitlines() if line.strip())


def _thread_table() -> str:
    try:
        proc = subprocess.run(
            ['ps', '-L', '-o', 'tid,cls,rtprio,psr,comm', '-p', str(os.getpid())],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
        )
        return proc.stdout.strip() or proc.stderr.strip()
    except Exception as exc:
        return f'thread table unavailable: {exc}'


def matrix_timing_snapshot(config: Any, display: Any | None = None, state: Any | None = None) -> dict[str, Any]:
    from .runtime_priority import cmdline_cpu_isolation_status

    panel = getattr(config, 'panel', None)
    runtime = getattr(config, 'runtime', None)
    driver_info: dict[str, Any] = {}
    if display is not None:
        driver = getattr(display, 'driver', None)
        timing_info = getattr(driver, 'timing_info', None)
        if callable(timing_info):
            try:
                driver_info = dict(timing_info())
            except Exception as exc:
                driver_info = {'error': str(exc)}

    gpio_mapping = str(getattr(panel, 'gpio_mapping', '') or '')
    hardware_pulse = bool(getattr(panel, 'hardware_pulse', False))
    hw_pwm_ok = bool(gpio_mapping == 'adafruit-hat-pwm' and hardware_pulse)
    matrix_core = int(getattr(runtime, 'matrix_cpu_core', 3) or 3)
    isolation = cmdline_cpu_isolation_status(matrix_core)
    audio_loaded = _module_loaded('snd_bcm2835')
    snap = state.snapshot() if state is not None and hasattr(state, 'snapshot') else {}

    return {
        'hardware_pwm': {
            'ok': hw_pwm_ok,
            'gpio_mapping': gpio_mapping,
            'hardware_pulse_enabled': hardware_pulse,
            'audio_module_loaded': audio_loaded,
            'note': 'adafruit-hat-pwm with hardware pulse enabled' if hw_pwm_ok else 'expected gpio_mapping=adafruit-hat-pwm and hardware_pulse=true',
        },
        'driver': driver_info,
        'affinity': {
            'enabled': bool(getattr(runtime, 'enable_matrix_core_affinity', False)),
            'matrix_cpu_core': matrix_core,
            'app_cpu_cores': str(getattr(runtime, 'app_cpu_cores', '') or ''),
            'current_process_allowed_list': _self_cpu_allowed_list(),
            'priority_status': snap.get('priority_status', ''),
        },
        'isolation': isolation,
        'threads': _thread_table(),
    }
