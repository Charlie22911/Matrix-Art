from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass


@dataclass(slots=True)
class PriorityResult:
    requested: str
    ok: bool
    message: str


def set_process_nice(target_nice: int | None) -> PriorityResult:
    if target_nice is None:
        return PriorityResult("nice", True, "nice unchanged")
    if os.name != "posix":
        return PriorityResult("nice", False, "nice unsupported on this platform")
    try:
        current = os.getpriority(os.PRIO_PROCESS, 0)
        os.setpriority(os.PRIO_PROCESS, 0, int(target_nice))
        new = os.getpriority(os.PRIO_PROCESS, 0)
        return PriorityResult("nice", True, f"nice {current} -> {new}")
    except Exception as exc:  # pragma: no cover - platform/capability dependent
        return PriorityResult("nice", False, f"nice failed: {exc}")


def set_realtime_fifo(priority: int | None, label: str = "thread") -> PriorityResult:
    if not priority or int(priority) <= 0:
        return PriorityResult(f"{label} realtime", True, "realtime disabled")
    if os.name != "posix" or not hasattr(os, "sched_setscheduler"):
        return PriorityResult(f"{label} realtime", False, "realtime scheduler unsupported")
    priority = max(1, min(99, int(priority)))
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(priority))
        return PriorityResult(f"{label} realtime", True, f"SCHED_FIFO priority {priority}")
    except Exception as exc:  # pragma: no cover - platform/capability dependent
        return PriorityResult(f"{label} realtime", False, f"SCHED_FIFO failed: {exc}")


def restore_normal_scheduler(label: str = "thread") -> PriorityResult:
    if os.name != "posix" or not hasattr(os, "sched_setscheduler"):
        return PriorityResult(f"{label} scheduler restore", False, "scheduler restore unsupported")
    try:
        os.sched_setscheduler(0, os.SCHED_OTHER, os.sched_param(0))
        return PriorityResult(f"{label} scheduler restore", True, "SCHED_OTHER")
    except Exception as exc:  # pragma: no cover - platform/capability dependent
        return PriorityResult(f"{label} scheduler restore", False, f"restore failed: {exc}")


def parse_cpu_set(value: str | int | None) -> set[int]:
    """Parse CPU affinity strings like "0-2,4" into a set of CPU ids."""
    if value is None:
        return set()
    if isinstance(value, int):
        return {value}
    text = str(value).strip()
    if not text:
        return set()
    result: set[int] = set()
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start_s, end_s = part.split('-', 1)
            start = int(start_s.strip())
            end = int(end_s.strip())
            if end < start:
                start, end = end, start
            result.update(range(start, end + 1))
        else:
            result.add(int(part))
    return result


def _online_cpus() -> set[int]:
    try:
        return parse_cpu_set(Path('/sys/devices/system/cpu/online').read_text(encoding='utf-8').strip())
    except Exception:
        try:
            return set(range(os.cpu_count() or 1))
        except Exception:
            return {0}


def _fmt_cpu_set(cpus: set[int]) -> str:
    if not cpus:
        return 'none'
    values = sorted(cpus)
    ranges: list[str] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(str(start) if start == prev else f'{start}-{prev}')
        start = prev = value
    ranges.append(str(start) if start == prev else f'{start}-{prev}')
    return ','.join(ranges)


def get_cpu_affinity() -> set[int]:
    if os.name != 'posix' or not hasattr(os, 'sched_getaffinity'):
        return set()
    try:
        return set(os.sched_getaffinity(0))
    except Exception:
        return set()


def set_cpu_affinity(cpu_spec: str | int | None, label: str = 'thread') -> PriorityResult:
    if cpu_spec is None or str(cpu_spec).strip() == '':
        return PriorityResult(f'{label} affinity', True, 'affinity unchanged')
    if os.name != 'posix' or not hasattr(os, 'sched_setaffinity'):
        return PriorityResult(f'{label} affinity', False, 'CPU affinity unsupported')
    try:
        requested = parse_cpu_set(cpu_spec)
        online = _online_cpus()
        cpus = requested & online
        if not cpus:
            return PriorityResult(f'{label} affinity', False, f'no requested CPUs are online: requested {_fmt_cpu_set(requested)}, online {_fmt_cpu_set(online)}')
        before = get_cpu_affinity()
        os.sched_setaffinity(0, cpus)
        after = get_cpu_affinity()
        return PriorityResult(f'{label} affinity', True, f'{_fmt_cpu_set(before)} -> {_fmt_cpu_set(after)}')
    except Exception as exc:  # pragma: no cover - platform/capability dependent
        return PriorityResult(f'{label} affinity', False, f'affinity failed: {exc}')


def cmdline_cpu_isolation_status(matrix_core: int = 3) -> dict[str, object]:
    text = ''
    try:
        text = Path('/proc/cmdline').read_text(encoding='utf-8').strip()
    except Exception:
        pass
    def has_core(key: str) -> bool:
        if f'{key}=' not in text:
            return False
        value = text.split(f'{key}=', 1)[1].split()[0]
        if key == 'isolcpus':
            # isolcpus can contain flags before the CPU list, for example
            # isolcpus=domain,managed_irq,3
            parts = [p for p in value.split(',') if p.strip().isdigit() or '-' in p]
            value = ','.join(parts)
        try:
            return int(matrix_core) in parse_cpu_set(value)
        except Exception:
            return str(int(matrix_core)) in value

    checks = {
        'isolcpus': has_core('isolcpus'),
        'nohz_full': has_core('nohz_full'),
        'rcu_nocbs': has_core('rcu_nocbs'),
        'irqaffinity': 'irqaffinity=' in text,
    }
    return {
        'cmdline': text,
        'matrix_core': int(matrix_core),
        'checks': checks,
        'ok': bool(checks['isolcpus'] and checks['nohz_full'] and checks['rcu_nocbs'] and checks['irqaffinity']),
    }
