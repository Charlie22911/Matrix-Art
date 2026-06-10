from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover, Python <3.11 fallback
    import tomli as tomllib  # type: ignore


def _get(section: dict[str, Any], key: str, default: Any) -> Any:
    return section.get(key, default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return default


@dataclass(slots=True)
class PanelConfig:
    rows: int = 64
    cols: int = 64
    chain_length: int = 1
    parallel: int = 1
    gpio_mapping: str = "adafruit-hat-pwm"
    brightness: int = 70
    slowdown_gpio: int = 1
    pwm_bits: int = 11
    pwm_lsb_nanoseconds: int = 130
    hardware_pulse: bool = True
    show_refresh_rate: bool = False
    limit_refresh_rate_hz: int = 0
    rgb_sequence: str = "RGB"
    pixel_mapper: str = ""
    panel_type: str = ""
    row_address_type: int = 0
    multiplexing: int = 0
    scan_mode: int = 0
    drop_privileges: bool = False


@dataclass(slots=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 80


@dataclass(slots=True)
class PathsConfig:
    root: Path
    data_dir: Path
    database: Path


@dataclass(slots=True)
class ImageConfig:
    target_width: int = 64
    target_height: int = 64
    scale_mode: str = "fit"
    resample: str = "nearest"
    background_color: str = "#000000"


@dataclass(slots=True)
class SlideshowConfig:
    enabled: bool = False
    shuffle: bool = True
    interval_seconds: float = 10.0
    show_first_on_start: bool = True


@dataclass(slots=True)
class AnimationConfig:
    max_gif_frames: int = 240
    default_frame_duration_ms: int = 100
    min_frame_duration_ms: int = 20
    max_frame_duration_ms: int = 5000


@dataclass(slots=True)
class DemoConfig:
    default_fps: int = 24
    # 0 means no configured cap. Runtime/UI still sanity-clamp to 1000 FPS.
    max_fps: int = 1000
    frame_queue_size: int = 3


@dataclass(slots=True)
class TransitionConfig:
    enabled: bool = True
    effect: str = "fade"
    duration_ms: int = 600
    fps: int = 30
    smoothing: bool = True
    smoothing_strength: int = 35


@dataclass(slots=True)
class RuntimeConfig:
    auto_sudo: bool = True
    mock_display: bool = False
    process_nice: int = -10
    matrix_realtime_priority: int = 55
    display_thread_realtime_priority: int = 45
    restore_main_scheduler_after_matrix_init: bool = True
    enable_matrix_core_affinity: bool = True
    matrix_cpu_core: int = 3
    app_cpu_cores: str = "0-2"


@dataclass(slots=True)
class StartupConfig:
    show_ip_on_start: bool = True
    ip_display_seconds: int = 60
    ip_wait_seconds: int = 35
    hotspot_fallback: bool = True
    default_hotspot_ssid: str = "Matrix-Art"
    default_hotspot_password: str = "matrixart1234"


@dataclass(slots=True)
class SecurityConfig:
    # One-shot recovery switch. Set true in config.toml to clear the Settings PIN
    # during startup. The app flips it back to false after a successful reset.
    reset_settings_pin: bool = False


@dataclass(slots=True)
class AppConfig:
    root: Path
    panel: PanelConfig
    server: ServerConfig
    paths: PathsConfig
    image: ImageConfig
    slideshow: SlideshowConfig
    animation: AnimationConfig
    transitions: TransitionConfig
    demos: DemoConfig
    runtime: RuntimeConfig
    startup: StartupConfig
    security: SecurityConfig


def set_config_bool(config_path: Path, section: str, key: str, value: bool) -> bool:
    """Best-effort in-place edit for simple TOML boolean flags.

    Returns True when the target key was found and updated. This intentionally
    avoids adding a TOML writer dependency and preserves the rest of config.toml.
    """
    config_path = config_path.resolve()
    if not config_path.exists():
        return False
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    target_section = f"[{section}]"
    replacement = "true" if value else "false"
    in_section = False
    changed = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == target_section
        if in_section and not changed:
            content = line.split("#", 1)[0]
            if "=" in content:
                left, _right = content.split("=", 1)
                if left.strip() == key:
                    newline = "\n" if line.endswith("\n") else ""
                    comment = ""
                    if "#" in line:
                        comment = "  #" + line.split("#", 1)[1].rstrip("\n")
                    line = f"{left.rstrip()} = {replacement}{comment}{newline}"
                    changed = True
        out.append(line)
    if changed:
        config_path.write_text("".join(out), encoding="utf-8")
    return changed


def load_config(config_path: Path) -> AppConfig:
    config_path = config_path.resolve()
    root = config_path.parent
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    panel_raw = raw.get("panel", {})
    server_raw = raw.get("server", {})
    paths_raw = raw.get("paths", {})
    image_raw = raw.get("image", {})
    slideshow_raw = raw.get("slideshow", {})
    animation_raw = raw.get("animation", {})
    transitions_raw = raw.get("transitions", {})
    demos_raw = raw.get("demos", {})
    runtime_raw = raw.get("runtime", {})
    startup_raw = raw.get("startup", {})
    security_raw = raw.get("security", {})

    data_dir = root / str(_get(paths_raw, "data_dir", "data"))
    database = root / str(_get(paths_raw, "database", "data/matrix_art.sqlite"))

    return AppConfig(
        root=root,
        panel=PanelConfig(
            rows=int(_get(panel_raw, "rows", 64)),
            cols=int(_get(panel_raw, "cols", 64)),
            chain_length=int(_get(panel_raw, "chain_length", 1)),
            parallel=int(_get(panel_raw, "parallel", 1)),
            gpio_mapping=str(_get(panel_raw, "gpio_mapping", "adafruit-hat-pwm")),
            brightness=int(_get(panel_raw, "brightness", 70)),
            slowdown_gpio=int(_get(panel_raw, "slowdown_gpio", 1)),
            pwm_bits=int(_get(panel_raw, "pwm_bits", 11)),
            pwm_lsb_nanoseconds=int(_get(panel_raw, "pwm_lsb_nanoseconds", 130)),
            hardware_pulse=_as_bool(_get(panel_raw, "hardware_pulse", True), True),
            show_refresh_rate=_as_bool(_get(panel_raw, "show_refresh_rate", False), False),
            limit_refresh_rate_hz=int(_get(panel_raw, "limit_refresh_rate_hz", 0)),
            rgb_sequence=str(_get(panel_raw, "rgb_sequence", "RGB")),
            pixel_mapper=str(_get(panel_raw, "pixel_mapper", "")),
            panel_type=str(_get(panel_raw, "panel_type", "")),
            row_address_type=int(_get(panel_raw, "row_address_type", 0)),
            multiplexing=int(_get(panel_raw, "multiplexing", 0)),
            scan_mode=int(_get(panel_raw, "scan_mode", 0)),
            drop_privileges=_as_bool(_get(panel_raw, "drop_privileges", False), False),
        ),
        server=ServerConfig(
            host=str(_get(server_raw, "host", "0.0.0.0")),
            port=int(_get(server_raw, "port", 80)),
        ),
        paths=PathsConfig(
            root=root,
            data_dir=data_dir,
            database=database,
        ),
        image=ImageConfig(
            target_width=int(_get(image_raw, "target_width", 64)),
            target_height=int(_get(image_raw, "target_height", 64)),
            scale_mode=str(_get(image_raw, "scale_mode", "fit")),
            resample=str(_get(image_raw, "resample", "nearest")),
            background_color=str(_get(image_raw, "background_color", "#000000")),
        ),
        slideshow=SlideshowConfig(
            enabled=_as_bool(_get(slideshow_raw, "enabled", False), False),
            shuffle=_as_bool(_get(slideshow_raw, "shuffle", True), True),
            interval_seconds=float(_get(slideshow_raw, "interval_seconds", 10.0)),
            show_first_on_start=_as_bool(_get(slideshow_raw, "show_first_on_start", True), True),
        ),
        animation=AnimationConfig(
            max_gif_frames=int(_get(animation_raw, "max_gif_frames", 240)),
            default_frame_duration_ms=int(_get(animation_raw, "default_frame_duration_ms", 100)),
            min_frame_duration_ms=int(_get(animation_raw, "min_frame_duration_ms", 20)),
            max_frame_duration_ms=int(_get(animation_raw, "max_frame_duration_ms", 5000)),
        ),
        transitions=TransitionConfig(
            enabled=_as_bool(_get(transitions_raw, "enabled", True), True),
            effect=str(_get(transitions_raw, "effect", "fade")),
            duration_ms=int(_get(transitions_raw, "duration_ms", 600)),
            fps=int(_get(transitions_raw, "fps", 30)),
            smoothing=_as_bool(_get(transitions_raw, "smoothing", True), True),
            smoothing_strength=int(_get(transitions_raw, "smoothing_strength", 35)),
        ),
        demos=DemoConfig(
            default_fps=int(_get(demos_raw, "default_fps", 24)),
            max_fps=int(_get(demos_raw, "max_fps", 1000)),
            frame_queue_size=int(_get(demos_raw, "frame_queue_size", 3)),
        ),
        runtime=RuntimeConfig(
            auto_sudo=_as_bool(_get(runtime_raw, "auto_sudo", True), True),
            mock_display=_as_bool(_get(runtime_raw, "mock_display", False), False),
            process_nice=int(_get(runtime_raw, "process_nice", -10)),
            matrix_realtime_priority=int(_get(runtime_raw, "matrix_realtime_priority", 55)),
            display_thread_realtime_priority=int(_get(runtime_raw, "display_thread_realtime_priority", 45)),
            restore_main_scheduler_after_matrix_init=_as_bool(_get(runtime_raw, "restore_main_scheduler_after_matrix_init", True), True),
            enable_matrix_core_affinity=_as_bool(_get(runtime_raw, "enable_matrix_core_affinity", True), True),
            matrix_cpu_core=int(_get(runtime_raw, "matrix_cpu_core", 3)),
            app_cpu_cores=str(_get(runtime_raw, "app_cpu_cores", "0-2")),
        ),
        startup=StartupConfig(
            show_ip_on_start=_as_bool(_get(startup_raw, "show_ip_on_start", True), True),
            ip_display_seconds=int(_get(startup_raw, "ip_display_seconds", 60)),
            ip_wait_seconds=int(_get(startup_raw, "ip_wait_seconds", 35)),
            hotspot_fallback=_as_bool(_get(startup_raw, "hotspot_fallback", True), True),
            default_hotspot_ssid=str(_get(startup_raw, "default_hotspot_ssid", "Matrix-Art")),
            default_hotspot_password=str(_get(startup_raw, "default_hotspot_password", "matrixart1234")),
        ),
        security=SecurityConfig(
            reset_settings_pin=_as_bool(_get(security_raw, "reset_settings_pin", False), False),
        ),
    )
