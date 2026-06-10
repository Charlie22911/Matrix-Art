from __future__ import annotations

import argparse
import datetime
import os
import signal
import threading
import sys
from pathlib import Path

from .config import load_config, set_config_bool
from .database import Database
from .display.mock_driver import MockDisplayDriver
from .display.rgbmatrix_driver import RGBMatrixDisplayDriver
from .display.worker import DisplayWorker
from .demos.builtins import ensure_builtin_demos
from .demos.runner import DemoRunner, render_demo_thumbnail
from .runtime_priority import restore_normal_scheduler, set_cpu_affinity, set_process_nice, set_realtime_fifo
from .artwork.processor import image_to_png_bytes
from .slideshow.controller import SlideshowController
from .state import AppState
from .startup import prepare_startup_network, start_ip_countdown_thread
from .web.app import MatrixArtServices, create_app
from PIL import Image


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Matrix-Art RGB matrix art server")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    parser.add_argument("--mock-display", action="store_true", help="Use mock display instead of rgbmatrix")
    parser.add_argument("--no-sudo-reexec", action="store_true", help="Do not auto re-run with sudo")
    parser.add_argument("--web-host", default=None, help="Override web host")
    parser.add_argument("--web-port", type=int, default=None, help="Override web port")
    parser.add_argument("--clear-db", action="store_true", help="Delete the SQLite database before startup")
    return parser.parse_args(argv)


def maybe_reexec_with_sudo(args: argparse.Namespace, config_path: Path, mock_display: bool, auto_sudo: bool) -> None:
    if mock_display or not auto_sudo or args.no_sudo_reexec:
        return
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() == 0:
        return
    cmd = [
        "sudo",
        "-E",
        "env",
        f"PATH={os.environ.get('PATH', '')}",
        sys.executable,
        "-m",
        "matrix_art",
        "--config",
        str(config_path),
        "--no-sudo-reexec",
    ]
    if args.web_host:
        cmd += ["--web-host", args.web_host]
    if args.web_port:
        cmd += ["--web-port", str(args.web_port)]
    if args.clear_db:
        cmd.append("--clear-db")
    print("RGB matrix access usually requires root. Re-running with sudo...")
    os.execvp("sudo", cmd)


def _setting_bool(db: Database, key: str, default: bool) -> bool:
    raw = db.get_setting(key, "1" if default else "0").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _setting_float(db: Database, key: str, default: float) -> float:
    try:
        return float(db.get_setting(key, f"{default:g}"))
    except Exception:
        return default


def _setting_int(db: Database, key: str, default: int) -> int:
    try:
        return int(float(db.get_setting(key, str(default))))
    except Exception:
        return default


def _setting_str(db: Database, key: str, default: str) -> str:
    value = db.get_setting(key, default)
    return value if value else default


def _clear_settings_pin_from_startup(db: Database) -> None:
    db.set_setting("settings_pin_salt", "")
    db.set_setting("settings_pin_hash", "")
    db.set_setting("settings_pin_iterations", "200000")
    db.set_setting("settings_pin_reset_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    db.set_setting("settings_pin_reset_source", "config.toml")


def _handle_config_pin_reset(db: Database, config, config_path: Path) -> str:
    if not getattr(config.security, "reset_settings_pin", False):
        return ""
    _clear_settings_pin_from_startup(db)
    try:
        changed = set_config_bool(config_path, "security", "reset_settings_pin", False)
        if changed:
            return "settings PIN reset by config.toml; reset_settings_pin flipped back to false"
        return "settings PIN reset by config.toml; could not auto-clear reset_settings_pin"
    except Exception as exc:
        return f"settings PIN reset by config.toml; could not auto-clear reset_settings_pin: {exc}"


def sync_code_artworks(db: Database, config) -> dict[str, int]:
    """Mirror saved Python code effects into the normal artwork library."""
    created_or_updated = 0
    skipped = 0
    failed = 0
    for demo in db.list_demos():
        if db.get_setting(f"code_thumbnail_manual:{demo.id}", "0").strip().lower() in {"1", "true", "yes", "on"}:
            skipped += 1
            continue
        try:
            image = render_demo_thumbnail(
                code=demo.code,
                title=demo.title,
                width=config.image.target_width,
                height=config.image.target_height,
                fps=demo.default_fps,
                frame_number=10,
                timeout=2.5,
            )
        except Exception:
            failed += 1
            image = Image.new("RGB", (config.image.target_width, config.image.target_height), (12, 12, 24))
        try:
            row = db.upsert_code_artwork(demo, image_to_png_bytes(image), config.image, folder_path="Code")
            if row is None:
                skipped += 1
            else:
                created_or_updated += 1
        except Exception:
            failed += 1
    return {"updated": created_or_updated, "skipped": skipped, "failed": failed}

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    if args.web_host:
        config.server.host = args.web_host
    if args.web_port:
        config.server.port = args.web_port
    if args.mock_display:
        config.runtime.mock_display = True
    maybe_reexec_with_sudo(args, config_path, config.runtime.mock_display, config.runtime.auto_sudo)

    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    if args.clear_db and config.paths.database.exists():
        config.paths.database.unlink()

    db = Database(config.paths.database)
    pin_reset_action = _handle_config_pin_reset(db, config, config_path)
    startup_action = pin_reset_action or "starting"
    demos_result = ensure_builtin_demos(db)
    startup_action = f"{startup_action}; startup code effects: {demos_result}" if pin_reset_action else f"startup code effects: {demos_result}"

    brightness = max(1, min(100, _setting_int(db, "brightness", config.panel.brightness)))
    config.panel.brightness = brightness
    display_enabled = _setting_bool(db, "display_enabled", True)
    slideshow_enabled = _setting_bool(db, "slideshow_enabled", config.slideshow.enabled)
    shuffle_enabled = _setting_bool(db, "slideshow_shuffle", config.slideshow.shuffle)
    interval_seconds = max(1.0, _setting_float(db, "slideshow_interval_seconds", config.slideshow.interval_seconds))
    transition_enabled = _setting_bool(db, "transition_enabled", config.transitions.enabled)
    transition_effect = _setting_str(db, "transition_effect", config.transitions.effect)
    transition_duration_ms = max(0, min(10000, _setting_int(db, "transition_duration_ms", config.transitions.duration_ms)))
    transition_fps = max(1, min(120, _setting_int(db, "transition_fps", config.transitions.fps)))
    transition_smoothing = _setting_bool(db, "transition_smoothing", config.transitions.smoothing)
    transition_smoothing_strength = max(0, min(100, _setting_int(db, "transition_smoothing_strength", config.transitions.smoothing_strength)))
    config.demos.default_fps = max(1, min(1000, _setting_int(db, "code_default_fps", config.demos.default_fps)))
    config.demos.max_fps = max(0, min(1000, _setting_int(db, "code_max_fps", config.demos.max_fps)))
    config.animation.max_gif_frames = max(1, min(1000, _setting_int(db, "animation_max_gif_frames", config.animation.max_gif_frames)))
    config.animation.default_frame_duration_ms = max(1, min(60000, _setting_int(db, "animation_default_frame_duration_ms", config.animation.default_frame_duration_ms)))
    config.animation.min_frame_duration_ms = max(1, min(60000, _setting_int(db, "animation_min_frame_duration_ms", config.animation.min_frame_duration_ms)))
    config.animation.max_frame_duration_ms = max(config.animation.min_frame_duration_ms, min(60000, _setting_int(db, "animation_max_frame_duration_ms", config.animation.max_frame_duration_ms)))

    state = AppState(
        brightness=brightness,
        display_enabled=display_enabled,
        slideshow_enabled=slideshow_enabled,
        shuffle_enabled=shuffle_enabled,
        interval_seconds=interval_seconds,
        transition_enabled=transition_enabled,
        transition_effect=transition_effect,
        transition_duration_ms=transition_duration_ms,
        transition_fps=transition_fps,
        transition_smoothing=transition_smoothing,
        transition_smoothing_strength=transition_smoothing_strength,
        display_driver="mock" if config.runtime.mock_display else "rgbmatrix",
        last_action=startup_action,
    )

    priority_messages: list[str] = []
    if not config.runtime.mock_display:
        nice_result = set_process_nice(config.runtime.process_nice)
        priority_messages.append(nice_result.message)
        if config.runtime.enable_matrix_core_affinity:
            affinity_result = set_cpu_affinity(config.runtime.matrix_cpu_core, "matrix init")
            priority_messages.append(affinity_result.message)
        rt_result = set_realtime_fifo(config.runtime.matrix_realtime_priority, "matrix init")
        priority_messages.append(rt_result.message)

    if config.runtime.mock_display:
        driver = MockDisplayDriver(
            width=config.image.target_width,
            height=config.image.target_height,
            brightness=config.panel.brightness,
            snapshot_path=config.paths.data_dir / "mock-current.png",
        )
    else:
        driver = RGBMatrixDisplayDriver(config.panel)
        if config.runtime.restore_main_scheduler_after_matrix_init:
            restore_result = restore_normal_scheduler("main/web")
            priority_messages.append(restore_result.message)
        if config.runtime.enable_matrix_core_affinity:
            app_affinity_result = set_cpu_affinity(config.runtime.app_cpu_cores, "main/web")
            priority_messages.append(app_affinity_result.message)

    if priority_messages:
        state.update(priority_status="; ".join(priority_messages))

    display = DisplayWorker(
        driver,
        state,
        realtime_priority=0 if config.runtime.mock_display else config.runtime.display_thread_realtime_priority,
        transition_enabled=transition_enabled,
        transition_effect=transition_effect,
        transition_duration_ms=transition_duration_ms,
        transition_fps=transition_fps,
        transition_smoothing=transition_smoothing,
        transition_smoothing_strength=transition_smoothing_strength,
    )
    display.start()
    if not display_enabled:
        display.set_display_enabled(False)

    startup_network = prepare_startup_network(db, config, state)
    if startup_network.get("ip"):
        state.update(last_action=f"network ready: {startup_network.get('ip')} ({startup_network.get('mode')})")
    elif startup_network.get("error"):
        state.update(last_error=str(startup_network.get("error")), last_action="network startup warning")

    demos = DemoRunner(
        display,
        state,
        width=config.image.target_width,
        height=config.image.target_height,
        default_fps=config.demos.default_fps,
        max_fps=config.demos.max_fps,
        queue_size=config.demos.frame_queue_size,
    )

    code_sync = sync_code_artworks(db, config)
    state.update(last_action=f"{state.last_action}; code library: {code_sync}")

    startup_screen_enabled = bool(config.startup.show_ip_on_start)
    desired_slideshow_enabled = bool(slideshow_enabled)
    startup_ap_ssid = ""
    startup_ap_password = ""
    if "hotspot" in str(startup_network.get("mode") or ""):
        startup_ap_ssid = db.get_setting("hotspot_ssid", config.startup.default_hotspot_ssid).strip() or config.startup.default_hotspot_ssid
        startup_ap_password = db.get_setting("hotspot_password", config.startup.default_hotspot_password).strip() or config.startup.default_hotspot_password

    slideshow = SlideshowController(
        db,
        display,
        state,
        interval_seconds=interval_seconds,
        shuffle=shuffle_enabled,
        enabled=False if startup_screen_enabled else desired_slideshow_enabled,
        code_runner=demos,
    )
    slideshow.start()

    shutdown_event = threading.Event()
    startup_thread: threading.Thread | None = None

    def startup_screen_then_resume() -> None:
        try:
            start_ip_countdown_thread(
                display,
                state,
                seconds=max(1, int(config.startup.ip_display_seconds)),
                stop_event=shutdown_event,
                server_port=config.server.port,
                ap_ssid=startup_ap_ssid,
                ap_password=startup_ap_password,
            ).join()
            if shutdown_event.is_set():
                return
            if desired_slideshow_enabled:
                slideshow.set_enabled(True)
            if config.slideshow.show_first_on_start:
                slideshow.show_first()
        except Exception as exc:
            state.update(last_error=str(exc), last_action="startup display failed")

    if startup_screen_enabled:
        startup_thread = threading.Thread(target=startup_screen_then_resume, name="matrix-art-startup-resume", daemon=True)
        startup_thread.start()
    elif config.slideshow.show_first_on_start:
        slideshow.show_first()

    services = MatrixArtServices(config=config, db=db, display=display, state=state, slideshow=slideshow, demos=demos)
    app = create_app(services)

    shutting_down = False
    shutdown_lock = threading.RLock()

    def clean_shutdown(reason: str = "shutdown") -> None:
        nonlocal shutting_down
        with shutdown_lock:
            if shutting_down:
                return
            shutting_down = True
            shutdown_event.set()
            print(f"Matrix-Art clean shutdown: {reason}", flush=True)
            try:
                demos.stop(timeout=2.0)
            except Exception as exc:
                print(f"Demo runner stop failed: {exc}", flush=True)
            try:
                slideshow.stop(timeout=2.0)
            except Exception as exc:
                print(f"Slideshow stop failed: {exc}", flush=True)
            try:
                display.stop(timeout=3.0)
            except Exception as exc:
                print(f"Display worker stop failed: {exc}", flush=True)
            try:
                db.close()
            except Exception as exc:
                print(f"Database close failed: {exc}", flush=True)

    def shutdown_handler(signum, frame):  # noqa: ANN001
        print(f"Received signal {signum}.", flush=True)
        clean_shutdown(f"signal {signum}")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    print(f"Matrix-Art serving on http://{config.server.host}:{config.server.port}/")
    print(f"Database: {config.paths.database}")
    try:
        app.run(host=config.server.host, port=config.server.port, threaded=True, debug=False, use_reloader=False)
    finally:
        clean_shutdown("server stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
