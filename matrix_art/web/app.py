from __future__ import annotations

from base64 import b64encode
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import hmac
import json
import secrets

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from PIL import Image

from ..artwork.processor import image_to_png_bytes, process_gif_bytes
from ..diagnostics import diagnostics_snapshot, matrix_timing_snapshot
from ..startup import start_ip_countdown_thread

from ..config import AppConfig
from ..database import Database, normalize_folder_path
from ..display.transitions import TRANSITION_EFFECTS, normalize_transition_name
from ..display.worker import DisplayWorker
from ..demos.runner import DemoRunner, render_demo_thumbnail
from ..wifi_tools import (
    WifiError,
    connect_wifi,
    connect_wifi_entry,
    create_or_update_wifi_profile,
    delete_wifi_profile,
    disconnect_wifi,
    normalize_wifi_entry,
    profile_name_wifi,
    scan_wifi_networks,
    wifi_status,
    start_hotspot,
    set_matrix_art_hotspots_autoconnect,
    stop_matrix_art_hotspots,
    wait_for_ipv4,
)
from ..slideshow.controller import SlideshowController
from ..state import AppState


ALLOWED_UPLOAD_EXTENSIONS = {".png"}


class MatrixArtServices:
    def __init__(self, config: AppConfig, db: Database, display: DisplayWorker, state: AppState, slideshow: SlideshowController, demos: DemoRunner):
        self.config = config
        self.db = db
        self.display = display
        self.state = state
        self.slideshow = slideshow
        self.demos = demos


def _bool_from_json(value: object, default: bool) -> bool:
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


def _ids_from_json() -> list[int]:
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("ids", [])
    ids: list[int] = []
    if isinstance(raw_ids, list):
        for raw in raw_ids:
            try:
                value = int(raw)
            except Exception:
                continue
            if value > 0:
                ids.append(value)
    return sorted(set(ids))


def _prepare_panel_for_ip_screen(services: MatrixArtServices, *, reason: str = "network IP screen") -> None:
    """Stop active display producers before showing a network/IP status screen."""
    try:
        services.slideshow.set_enabled(False)
    except Exception:
        pass
    try:
        services.demos.stop(timeout=2.0)
    except Exception:
        pass
    try:
        services.display.clear()
    except Exception:
        pass
    services.state.update(slideshow_enabled=False, last_action=reason, frame_changed=True)


UI_DEFAULTS = {
    "title": "Matrix-Art",
    "library_subtitle": "Folders, trash, uploads, browser drawing, GIF playback, transitions, and Python code effects.",
    "upload_subtitle": "Upload an image or animated GIF, crop/scale it, preview the 64×64 result, then save it to the library.",
    "draw_subtitle": "Draw directly on a 64×64 RGB matrix-style canvas, then save the exact result to the library.",
    "code_subtitle": "Edit, save, and run Python-generated visual effects from the browser.",
    "settings_subtitle": "Customize the app text, code timing, animation defaults, diagnostics, and Wi-Fi.",
}


def _ui_text(services: MatrixArtServices) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, default in UI_DEFAULTS.items():
        value = services.db.get_setting(f"ui_{key}", default).strip()
        result[key] = value or default
    return result


def _code_editor_enabled(services: MatrixArtServices) -> bool:
    return services.db.get_setting("code_editor_enabled", "1").strip().lower() not in {"0", "false", "no", "off"}


SETTINGS_PIN_ITERATIONS = 200_000


def _settings_pin_enabled(services: MatrixArtServices) -> bool:
    return bool(services.db.get_setting("settings_pin_hash", "") and services.db.get_setting("settings_pin_salt", ""))


def _settings_unlocked(services: MatrixArtServices) -> bool:
    if not _settings_pin_enabled(services):
        return True
    return bool(session.get("settings_unlocked"))


def _hash_settings_pin(pin: str, salt_hex: str, iterations: int = SETTINGS_PIN_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations),
    ).hex()


def _verify_settings_pin(services: MatrixArtServices, pin: str) -> bool:
    pin = str(pin or "")
    salt = services.db.get_setting("settings_pin_salt", "")
    expected = services.db.get_setting("settings_pin_hash", "")
    try:
        iterations = int(services.db.get_setting("settings_pin_iterations", str(SETTINGS_PIN_ITERATIONS)))
    except Exception:
        iterations = SETTINGS_PIN_ITERATIONS
    if not pin or not salt or not expected:
        return False
    try:
        actual = _hash_settings_pin(pin, salt, iterations)
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def _set_settings_pin(services: MatrixArtServices, pin: str) -> None:
    pin = str(pin or "").strip()
    if not (4 <= len(pin) <= 12) or not pin.isdigit():
        raise ValueError("PIN must be 4 to 12 digits.")
    salt = secrets.token_hex(16)
    services.db.set_setting("settings_pin_salt", salt)
    services.db.set_setting("settings_pin_hash", _hash_settings_pin(pin, salt, SETTINGS_PIN_ITERATIONS))
    services.db.set_setting("settings_pin_iterations", str(SETTINGS_PIN_ITERATIONS))


def _clear_settings_pin(services: MatrixArtServices) -> None:
    services.db.set_setting("settings_pin_salt", "")
    services.db.set_setting("settings_pin_hash", "")
    services.db.set_setting("settings_pin_iterations", str(SETTINGS_PIN_ITERATIONS))
    session.pop("settings_unlocked", None)


def _settings_security_snapshot(services: MatrixArtServices) -> dict[str, object]:
    enabled = _settings_pin_enabled(services)
    return {
        "pin_enabled": enabled,
        "unlocked": _settings_unlocked(services),
    }


def _settings_api_requires_unlock(path: str) -> bool:
    if path.startswith("/api/settings"):
        return True
    if path.startswith("/api/wifi"):
        return True
    if path in {"/api/diagnostics", "/api/matrix/timing"}:
        return True
    if path in {"/api/folders/settings", "/api/folders/delete", "/api/folders/protect"}:
        return True
    return False


def _code_max_fps(services: MatrixArtServices) -> int:
    try:
        value = int(float(services.db.get_setting("code_max_fps", str(services.config.demos.max_fps))))
    except Exception:
        value = int(services.config.demos.max_fps)
    return max(0, min(1000, value))


def _code_default_fps(services: MatrixArtServices) -> int:
    try:
        value = int(float(services.db.get_setting("code_default_fps", str(services.config.demos.default_fps))))
    except Exception:
        value = int(services.config.demos.default_fps)
    max_fps = _code_max_fps(services)
    value = max(1, min(1000, value))
    if max_fps > 0:
        value = min(max_fps, value)
    return value


WIFI_SAVED_SETTING_KEY = "wifi_saved_networks"


def _wifi_bool(value: object, default: bool = False) -> bool:
    return _bool_from_json(value, default)


def _safe_saved_wifi_entry(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    entry = normalize_wifi_entry(raw)
    if not entry["ssid"]:
        return None
    # Keep the browser payload stable and avoid leaking internal aliases.
    return {
        "ssid": entry["ssid"],
        "password": entry.get("password", ""),
        "interface": entry.get("interface"),
        "hidden": bool(entry.get("hidden", False)),
        "autoconnect": bool(entry.get("autoconnect", True)),
        "priority": int(entry.get("priority", 0) or 0),
        "profile_name": entry.get("profile_name") or profile_name_wifi(entry["ssid"], entry.get("interface")),
        "notes": str(entry.get("notes") or ""),
    }


def _load_saved_wifi(services: MatrixArtServices) -> list[dict[str, object]]:
    raw = services.db.get_setting(WIFI_SAVED_SETTING_KEY, "[]")
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = []
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    if isinstance(parsed, list):
        for item in parsed:
            entry = _safe_saved_wifi_entry(item)
            if entry is None:
                continue
            key = (str(entry["ssid"]), str(entry.get("interface") or ""))
            if key in seen:
                continue
            seen.add(key)
            result.append(entry)
    result.sort(key=lambda x: (str(x.get("interface") or ""), str(x.get("ssid") or "").lower()))
    return result


def _store_saved_wifi(services: MatrixArtServices, entries: list[dict[str, object]]) -> None:
    cleaned: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in entries:
        entry = _safe_saved_wifi_entry(item)
        if entry is None:
            continue
        key = (str(entry["ssid"]), str(entry.get("interface") or ""))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(entry)
    cleaned.sort(key=lambda x: (str(x.get("interface") or ""), str(x.get("ssid") or "").lower()))
    services.db.set_setting(WIFI_SAVED_SETTING_KEY, json.dumps(cleaned, sort_keys=True))


def _wifi_entry_from_request(data: dict[str, object]) -> dict[str, object]:
    ssid = str(data.get("ssid") or "").strip()
    password = str(data.get("password") or "")
    interface = str(data.get("interface") or "").strip() or None
    hidden = _wifi_bool(data.get("hidden"), False)
    autoconnect = _wifi_bool(data.get("autoconnect"), True)
    try:
        priority = int(float(data.get("priority", 0) or 0))
    except Exception:
        priority = 0
    return _safe_saved_wifi_entry({
        "ssid": ssid,
        "password": password,
        "interface": interface,
        "hidden": hidden,
        "autoconnect": autoconnect,
        "priority": priority,
    }) or {}


def _upsert_saved_wifi(services: MatrixArtServices, entry: dict[str, object]) -> list[dict[str, object]]:
    if not entry.get("ssid"):
        raise WifiError("SSID is required.")
    entries = _load_saved_wifi(services)
    key = (str(entry.get("ssid") or ""), str(entry.get("interface") or ""))
    out: list[dict[str, object]] = []
    replaced = False
    for existing in entries:
        existing_key = (str(existing.get("ssid") or ""), str(existing.get("interface") or ""))
        if existing_key == key:
            out.append(entry)
            replaced = True
        else:
            out.append(existing)
    if not replaced:
        out.append(entry)
    _store_saved_wifi(services, out)
    return _load_saved_wifi(services)


def _find_saved_wifi(services: MatrixArtServices, ssid: str, interface: str | None) -> dict[str, object] | None:
    key = (ssid, interface or "")
    for entry in _load_saved_wifi(services):
        if (str(entry.get("ssid") or ""), str(entry.get("interface") or "")) == key:
            return entry
    return None


def _float_form(name: str, default: float) -> float:
    try:
        return float(request.form.get(name, default))
    except Exception:
        return default


def _int_form(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(float(request.form.get(name, default)))
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _bool_form(name: str, default: bool = False) -> bool:
    return _bool_from_json(request.form.get(name), default)


def _safe_hex_color(value: str | None, default: str = "#000000") -> str:
    if not value:
        return default
    value = value.strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            return default
    return default


def _gif_upload_options(services: MatrixArtServices) -> dict[str, object]:
    scale_mode = (request.form.get("scale_mode") or services.config.image.scale_mode).strip().lower()
    if scale_mode not in {"crop", "fit", "fill", "stretch"}:
        scale_mode = "fit"

    resample = (request.form.get("resample") or services.config.image.resample).strip().lower()
    if resample not in {"nearest", "pixel", "smooth", "bicubic", "bilinear", "lanczos"}:
        resample = "nearest"

    background = _safe_hex_color(request.form.get("background_color"), services.config.image.background_color)
    crop_x = _float_form("crop_x", 0.0)
    crop_y = _float_form("crop_y", 0.0)
    crop_size = _float_form("crop_size", 0.0)
    max_frames = _int_form(
        "max_frames",
        services.config.animation.max_gif_frames,
        minimum=1,
        maximum=max(1, services.config.animation.max_gif_frames),
    )
    default_duration_ms = _int_form(
        "default_duration_ms",
        services.config.animation.default_frame_duration_ms,
        minimum=1,
        maximum=60000,
    )
    min_duration_ms = _int_form(
        "min_duration_ms",
        services.config.animation.min_frame_duration_ms,
        minimum=1,
        maximum=60000,
    )
    max_duration_ms = _int_form(
        "max_duration_ms",
        services.config.animation.max_frame_duration_ms,
        minimum=1,
        maximum=60000,
    )
    if max_duration_ms < min_duration_ms:
        max_duration_ms = min_duration_ms
    default_duration_ms = max(min_duration_ms, min(max_duration_ms, default_duration_ms))

    return {
        "scale_mode": scale_mode,
        "resample": resample,
        "background": background,
        "crop_x": max(0.0, crop_x),
        "crop_y": max(0.0, crop_y),
        "crop_size": max(0.0, crop_size),
        "max_frames": max_frames,
        "default_duration_ms": default_duration_ms,
        "min_duration_ms": min_duration_ms,
        "max_duration_ms": max_duration_ms,
    }


def _decode_gif_upload(services: MatrixArtServices) -> tuple[list[tuple[Image.Image, int]] | None, bytes | None, str | None, dict[str, object]]:
    upload = request.files.get("gif")
    options = _gif_upload_options(services)
    if upload is None or not upload.filename:
        return None, None, "no GIF received", options
    data = upload.read()
    if not data:
        return None, None, "GIF was empty", options
    try:
        decoded = process_gif_bytes(
            data,
            target_size=(services.config.image.target_width, services.config.image.target_height),
            scale_mode=str(options["scale_mode"]),
            resample=str(options["resample"]),
            background_color=str(options["background"]),
            crop_x=float(options.get("crop_x", 0.0)),
            crop_y=float(options.get("crop_y", 0.0)),
            crop_size=(float(options.get("crop_size", 0.0)) or None),
            max_frames=int(options["max_frames"]),
            default_duration_ms=int(options["default_duration_ms"]),
            min_duration_ms=int(options["min_duration_ms"]),
            max_duration_ms=int(options["max_duration_ms"]),
        )
    except Exception as exc:
        return None, data, f"GIF import failed: {exc}", options
    if not decoded:
        return None, data, "GIF contained no frames", options
    return decoded, data, None, options


def _read_64x64_png_upload(field_name: str, services: MatrixArtServices, label: str) -> tuple[bytes | None, Image.Image | None, str | None]:
    upload = request.files.get(field_name)
    if upload is None or not upload.filename:
        return None, None, f"no 64x64 {label} image received"

    data = upload.read()
    if not data:
        return None, None, f"{label} image was empty"

    try:
        with Image.open(BytesIO(data)) as probe:
            probe.load()
            target = (services.config.image.target_width, services.config.image.target_height)
            if probe.size != target:
                return None, None, f"{label} must be {target[0]}x{target[1]}, got {probe.width}x{probe.height}"
            image = probe.convert("RGB")
    except Exception as exc:
        return None, None, f"{label} image could not be read: {exc}"
    return data, image, None



def _sync_code_artwork_for_demo(services: MatrixArtServices, demo) -> object | None:
    """Render frame 10 and mirror a saved code effect into the artwork library.

    This is intentionally called on every Code save/copy/create so the normal
    Library thumbnail tracks the currently saved code.
    """
    try:
        image = render_demo_thumbnail(
            code=demo.code,
            title=demo.title,
            width=services.config.image.target_width,
            height=services.config.image.target_height,
            fps=demo.default_fps,
            frame_number=10,
            timeout=2.5,
        )
    except Exception:
        image = Image.new("RGB", (services.config.image.target_width, services.config.image.target_height), (12, 12, 24))
    row = services.db.upsert_code_artwork(demo, image_to_png_bytes(image), services.config.image, folder_path="Code")
    services.db.set_setting(f"code_thumbnail_manual:{demo.id}", "0")
    return row


def _code_artwork_json(row) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "title": row.title,
        "kind": row.kind,
        "folder_path": row.folder_path,
        "updated_at": row.updated_at,
        "thumbnail_url": f"/thumb/{row.id}.png?v={row.updated_at}",
    }

def create_app(services: MatrixArtServices) -> Flask:
    app = Flask(__name__)
    secret = services.db.get_setting("flask_secret_key", "")
    if not secret:
        secret = secrets.token_hex(32)
        services.db.set_setting("flask_secret_key", secret)
    app.secret_key = secret
    app.config["MATRIX_ART"] = services
    app.config["MAX_CONTENT_LENGTH"] = 128 * 1024 * 1024

    @app.before_request
    def require_settings_unlock():
        path = request.path or ""
        if path == "/settings":
            return None
        if path == "/settings/unlock":
            return None
        if path == "/api/settings/security/status":
            return None
        if _settings_api_requires_unlock(path) and not _settings_unlocked(services):
            return jsonify({"ok": False, "locked": True, "error": "Settings are locked."}), 423
        return None

    @app.context_processor
    def inject_ui_text():
        return {"ui": _ui_text(services), "code_editor_enabled": _code_editor_enabled(services)}

    @app.get("/")
    def index():
        q = request.args.get("q", "").strip()
        enabled = request.args.get("enabled", "all")
        folder = request.args.get("folder", "all")
        if enabled not in {"all", "yes", "no"}:
            enabled = "all"
        folder_norm = normalize_folder_path(folder)
        is_trash = folder_norm.lower() == "trash"
        rows = services.db.list_artwork(q=q, enabled=enabled, folder=folder, limit=800, offset=0)
        folders = services.db.list_folders()
        folder_summary = services.db.folder_enabled_summary(folder)
        return render_template(
            "index.html",
            state=services.state.snapshot(),
            rows=rows,
            folders=folders,
            q=q,
            enabled=enabled,
            folder=folder,
            is_trash=is_trash,
            folder_all_enabled=bool(folder_summary.get("total") and folder_summary.get("enabled") == folder_summary.get("total")),
            folder_summary=folder_summary,
            total=services.db.count_artwork(),
            enabled_count=services.db.count_enabled(),
            config=services.config,
            transition_effects=TRANSITION_EFFECTS,
        )

    @app.get("/upload")
    def upload_page():
        return render_template("upload.html", state=services.state.snapshot(), config=services.config, folders=services.db.list_folders())

    @app.get("/draw")
    def draw_page():
        services.slideshow.set_enabled(False)
        services.demos.stop()
        return render_template("draw.html", state=services.state.snapshot(), config=services.config, folders=services.db.list_folders())

    @app.get("/demos")
    def demos_redirect():
        return redirect(url_for("code_page"))

    @app.get("/code")
    def code_page():
        if not _code_editor_enabled(services):
            return "Code editor is disabled in Settings.", 403
        demos = services.db.list_demos()
        return render_template(
            "code.html",
            config=services.config,
            state=services.state.snapshot(),
            demos=demos,
            demo_status=services.demos.snapshot(),
            code_default_fps=_code_default_fps(services),
            code_max_fps=_code_max_fps(services),
        )

    @app.get("/code/help")
    def code_help_page():
        if not _code_editor_enabled(services):
            return "Code editor is disabled in Settings.", 403
        return render_template("code_help.html", config=services.config, state=services.state.snapshot())

    @app.get("/settings")
    def settings_page():
        if not _settings_unlocked(services):
            return render_template("settings_lock.html", state=services.state.snapshot(), error="", security=_settings_security_snapshot(services))
        def setting_int(key: str, default: int) -> int:
            try:
                return int(float(services.db.get_setting(key, str(default))))
            except Exception:
                return int(default)
        return render_template(
            "settings.html",
            state=services.state.snapshot(),
            config=services.config,
            ui=_ui_text(services),
            code_default_fps=_code_default_fps(services),
            code_max_fps=_code_max_fps(services),
            code_editor_enabled=_code_editor_enabled(services),
            security=_settings_security_snapshot(services),
            hotspot={
                "ssid": services.db.get_setting("hotspot_ssid", services.config.startup.default_hotspot_ssid),
                "password": services.db.get_setting("hotspot_password", services.config.startup.default_hotspot_password),
                "interface": services.db.get_setting("hotspot_interface", ""),
                "mode": services.db.get_setting("wifi_mode", "wifi"),
            },
            animation={
                "max_gif_frames": setting_int("animation_max_gif_frames", services.config.animation.max_gif_frames),
                "default_frame_duration_ms": setting_int("animation_default_frame_duration_ms", services.config.animation.default_frame_duration_ms),
                "min_frame_duration_ms": setting_int("animation_min_frame_duration_ms", services.config.animation.min_frame_duration_ms),
                "max_frame_duration_ms": setting_int("animation_max_frame_duration_ms", services.config.animation.max_frame_duration_ms),
            },
        )

    @app.post("/settings/unlock")
    def settings_unlock_page():
        pin = str(request.form.get("pin") or "")
        if _verify_settings_pin(services, pin):
            session["settings_unlocked"] = True
            services.state.update(last_action="settings unlocked")
            return redirect(url_for("settings_page"))
        return render_template("settings_lock.html", state=services.state.snapshot(), error="Incorrect PIN.", security=_settings_security_snapshot(services)), 401

    @app.get("/api/settings/security/status")
    def api_settings_security_status():
        return jsonify({"ok": True, "security": _settings_security_snapshot(services)})

    @app.post("/api/settings/security/pin")
    def api_settings_security_pin():
        data = request.get_json(silent=True) or {}
        action = str(data.get("action") or "set").strip().lower()
        current_pin = str(data.get("current_pin") or "")
        new_pin = str(data.get("new_pin") or "")
        confirm_pin = str(data.get("confirm_pin") or "")
        pin_enabled = _settings_pin_enabled(services)

        try:
            if action == "lock":
                if pin_enabled:
                    session.pop("settings_unlocked", None)
                return jsonify({"ok": True, "security": _settings_security_snapshot(services)})

            if action == "disable":
                if pin_enabled and not _verify_settings_pin(services, current_pin):
                    return jsonify({"ok": False, "error": "Current PIN is incorrect."}), 400
                _clear_settings_pin(services)
                services.state.update(last_action="settings PIN disabled")
                return jsonify({"ok": True, "security": _settings_security_snapshot(services)})

            if action not in {"set", "change"}:
                return jsonify({"ok": False, "error": "Unknown security action."}), 400

            if pin_enabled and not _verify_settings_pin(services, current_pin):
                return jsonify({"ok": False, "error": "Current PIN is incorrect."}), 400
            if new_pin != confirm_pin:
                return jsonify({"ok": False, "error": "New PIN fields do not match."}), 400
            _set_settings_pin(services, new_pin)
            session["settings_unlocked"] = True
            services.state.update(last_action="settings PIN updated")
            return jsonify({"ok": True, "security": _settings_security_snapshot(services)})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/settings/ui")
    def api_settings_ui():
        data = request.get_json(silent=True) or {}
        updated: dict[str, str] = {}
        for key, default in UI_DEFAULTS.items():
            value = str(data.get(key, default)).strip()[:220]
            if not value:
                value = default
            services.db.set_setting(f"ui_{key}", value)
            updated[key] = value
        services.state.update(last_action="updated page text")
        return jsonify({"ok": True, "ui": updated})

    @app.post("/api/settings/code")
    def api_settings_code():
        data = request.get_json(silent=True) or {}
        try:
            default_fps = int(float(data.get("default_fps", _code_default_fps(services))))
        except Exception:
            default_fps = _code_default_fps(services)
        try:
            max_fps = int(float(data.get("max_fps", _code_max_fps(services))))
        except Exception:
            max_fps = _code_max_fps(services)
        max_fps = max(0, min(1000, max_fps))
        default_fps = max(1, min(1000, default_fps))
        if max_fps > 0:
            default_fps = min(default_fps, max_fps)
        editor_enabled = _bool_from_json(data.get("editor_enabled"), _code_editor_enabled(services))
        services.db.set_setting("code_default_fps", str(default_fps))
        services.db.set_setting("code_max_fps", str(max_fps))
        services.db.set_setting("code_editor_enabled", "1" if editor_enabled else "0")
        services.demos.default_fps = default_fps
        services.demos.max_fps = max_fps
        services.config.demos.default_fps = default_fps
        services.config.demos.max_fps = max_fps
        if not editor_enabled:
            services.demos.stop()
        services.state.update(last_action=f"code timing default={default_fps} max={max_fps or 'uncapped'}; editor {'on' if editor_enabled else 'off'}")
        return jsonify({"ok": True, "default_fps": default_fps, "max_fps": max_fps, "editor_enabled": editor_enabled})

    @app.post("/api/settings/animation")
    def api_settings_animation():
        data = request.get_json(silent=True) or {}
        def intval(name: str, default: int, lo: int, hi: int) -> int:
            try:
                value = int(float(data.get(name, default)))
            except Exception:
                value = default
            return max(lo, min(hi, value))
        max_frames = intval("max_gif_frames", services.config.animation.max_gif_frames, 1, 1000)
        default_ms = intval("default_frame_duration_ms", services.config.animation.default_frame_duration_ms, 1, 60000)
        min_ms = intval("min_frame_duration_ms", services.config.animation.min_frame_duration_ms, 1, 60000)
        max_ms = intval("max_frame_duration_ms", services.config.animation.max_frame_duration_ms, 1, 60000)
        if max_ms < min_ms:
            max_ms = min_ms
        default_ms = max(min_ms, min(max_ms, default_ms))
        services.config.animation.max_gif_frames = max_frames
        services.config.animation.default_frame_duration_ms = default_ms
        services.config.animation.min_frame_duration_ms = min_ms
        services.config.animation.max_frame_duration_ms = max_ms
        values = {
            "animation_max_gif_frames": max_frames,
            "animation_default_frame_duration_ms": default_ms,
            "animation_min_frame_duration_ms": min_ms,
            "animation_max_frame_duration_ms": max_ms,
        }
        for key, value in values.items():
            services.db.set_setting(key, str(value))
        services.state.update(last_action="updated animation defaults")
        return jsonify({"ok": True, "animation": {
            "max_gif_frames": max_frames,
            "default_frame_duration_ms": default_ms,
            "min_frame_duration_ms": min_ms,
            "max_frame_duration_ms": max_ms,
        }})

    @app.get("/api/settings/database/backup")
    def api_settings_database_backup():
        payload = services.db.export_backup_payload()
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        return send_file(
            BytesIO(raw),
            mimetype="application/json",
            as_attachment=True,
            download_name=f"matrix-art-backup-{stamp}.json",
            max_age=0,
        )

    @app.post("/api/settings/database/restore")
    def api_settings_database_restore():
        upload = request.files.get("backup")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "error": "Choose a Matrix-Art backup file first."}), 400
        try:
            raw = upload.read()
            if not raw:
                raise ValueError("backup file is empty")
            payload = json.loads(raw.decode("utf-8"))
            _prepare_panel_for_ip_screen(services, reason="database restore")
            result = services.db.import_backup_payload(payload)
            services.state.update(
                slideshow_enabled=False,
                last_action=f"database restored from backup ({result.get('restored_rows', 0)} rows)",
                frame_changed=True,
            )
            session.pop("settings_unlocked", None)
            return jsonify({"ok": True, "result": result, "security": _settings_security_snapshot(services)})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/api/diagnostics")
    def api_diagnostics():
        diag = diagnostics_snapshot()
        diag["matrix_timing"] = matrix_timing_snapshot(services.config, services.display, services.state)
        return jsonify({"ok": True, "diagnostics": diag})

    @app.get("/api/matrix/timing")
    def api_matrix_timing():
        return jsonify({"ok": True, "timing": matrix_timing_snapshot(services.config, services.display, services.state)})

    @app.get("/api/wifi/status")
    def api_wifi_status():
        status = wifi_status()
        status["saved"] = _load_saved_wifi(services)
        status["mode"] = services.db.get_setting("wifi_mode", "wifi")
        status["hotspot"] = {
            "ssid": services.db.get_setting("hotspot_ssid", services.config.startup.default_hotspot_ssid),
            "interface": services.db.get_setting("hotspot_interface", ""),
        }
        return jsonify(status)

    @app.get("/api/wifi/saved")
    def api_wifi_saved():
        return jsonify({"ok": True, "saved": _load_saved_wifi(services)})

    @app.post("/api/wifi/scan")
    def api_wifi_scan():
        data = request.get_json(silent=True) or {}
        iface = str(data.get("interface") or "").strip() or None
        try:
            networks = scan_wifi_networks(iface)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "networks": networks})

    @app.post("/api/wifi/connect")
    def api_wifi_connect():
        data = request.get_json(silent=True) or {}
        ssid = str(data.get("ssid") or "").strip()
        password = str(data.get("password") or "")
        interface = str(data.get("interface") or "").strip() or None
        hidden = _bool_from_json(data.get("hidden"), False)
        try:
            message = connect_wifi(ssid, password=password, interface=interface, hidden=hidden)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.db.set_setting("wifi_mode", "wifi")
        set_matrix_art_hotspots_autoconnect(False)
        services.state.update(last_action=f"Wi-Fi connect requested for {ssid}")
        return jsonify({"ok": True, "message": message, "saved": _load_saved_wifi(services)})

    @app.post("/api/wifi/save")
    def api_wifi_save():
        data = request.get_json(silent=True) or {}
        entry = _wifi_entry_from_request(data)
        try:
            profile_entry = create_or_update_wifi_profile(entry)
            saved = _upsert_saved_wifi(services, profile_entry)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.db.set_setting("wifi_mode", "wifi")
        set_matrix_art_hotspots_autoconnect(False)
        services.state.update(last_action=f"saved Wi-Fi network {entry.get('ssid')}")
        return jsonify({"ok": True, "message": f"Saved {entry.get('ssid')}", "entry": profile_entry, "saved": saved})

    @app.post("/api/wifi/connect-save")
    def api_wifi_connect_save():
        data = request.get_json(silent=True) or {}
        entry = _wifi_entry_from_request(data)
        try:
            message = connect_wifi_entry(entry)
            saved_entry = normalize_wifi_entry(entry)
            saved_entry["profile_name"] = saved_entry.get("profile_name") or profile_name_wifi(saved_entry["ssid"], saved_entry.get("interface"))
            saved = _upsert_saved_wifi(services, saved_entry)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.db.set_setting("wifi_mode", "wifi")
        set_matrix_art_hotspots_autoconnect(False)
        services.state.update(last_action=f"saved and connected Wi-Fi {entry.get('ssid')}")
        return jsonify({"ok": True, "message": message, "entry": saved_entry, "saved": saved})

    @app.post("/api/wifi/connect-saved")
    def api_wifi_connect_saved():
        data = request.get_json(silent=True) or {}
        ssid = str(data.get("ssid") or "").strip()
        interface = str(data.get("interface") or "").strip() or None
        entry = _find_saved_wifi(services, ssid, interface)
        if entry is None:
            return jsonify({"ok": False, "error": "saved network not found"}), 404
        try:
            message = connect_wifi_entry(entry)
            saved = _upsert_saved_wifi(services, normalize_wifi_entry(entry))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.db.set_setting("wifi_mode", "wifi")
        set_matrix_art_hotspots_autoconnect(False)
        services.state.update(last_action=f"connected saved Wi-Fi {ssid}")
        return jsonify({"ok": True, "message": message, "entry": entry, "saved": saved})

    @app.post("/api/wifi/remove-saved")
    def api_wifi_remove_saved():
        data = request.get_json(silent=True) or {}
        ssid = str(data.get("ssid") or "").strip()
        interface = str(data.get("interface") or "").strip() or None
        delete_profile = _bool_from_json(data.get("delete_profile"), True)
        removed: dict[str, object] | None = None
        kept: list[dict[str, object]] = []
        for entry in _load_saved_wifi(services):
            if (str(entry.get("ssid") or ""), str(entry.get("interface") or "")) == (ssid, interface or ""):
                removed = entry
            else:
                kept.append(entry)
        if removed is None:
            return jsonify({"ok": False, "error": "saved network not found"}), 404
        if delete_profile:
            try:
                delete_wifi_profile(str(removed.get("profile_name") or profile_name_wifi(ssid, interface)))
            except Exception:
                pass
        _store_saved_wifi(services, kept)
        services.state.update(last_action=f"removed saved Wi-Fi {ssid}")
        return jsonify({"ok": True, "removed": removed, "saved": _load_saved_wifi(services)})

    @app.post("/api/wifi/disconnect")
    def api_wifi_disconnect():
        data = request.get_json(silent=True) or {}
        interface = str(data.get("interface") or "").strip()
        try:
            message = disconnect_wifi(interface)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.state.update(last_action=f"Wi-Fi disconnect requested for {interface}")
        return jsonify({"ok": True, "message": message})

    @app.post("/api/wifi/hotspot/start")
    def api_wifi_hotspot_start():
        data = request.get_json(silent=True) or {}
        ssid = str(data.get("ssid") or services.config.startup.default_hotspot_ssid).strip()
        password = str(data.get("password") or services.config.startup.default_hotspot_password)
        interface = str(data.get("interface") or "").strip() or None
        if not ssid:
            return jsonify({"ok": False, "error": "Hotspot SSID is required."}), 400
        try:
            _prepare_panel_for_ip_screen(services, reason=f"starting hotspot {ssid}")
            stop_matrix_art_hotspots()
            message = start_hotspot(ssid, password, interface, persist=True)
            services.db.set_setting("wifi_mode", "hotspot")
            services.db.set_setting("hotspot_ssid", ssid)
            services.db.set_setting("hotspot_password", password)
            services.db.set_setting("hotspot_interface", interface or "")
            ip = wait_for_ipv4(20)
            start_ip_countdown_thread(
                services.display,
                services.state,
                seconds=max(1, int(services.config.startup.ip_display_seconds)),
                server_port=services.config.server.port,
                ap_ssid=ssid,
                ap_password=password,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.state.update(last_action=f"started hotspot {ssid}")
        return jsonify({"ok": True, "message": message, "ip": ip, "mode": "hotspot", "ssid": ssid, "interface": interface})

    @app.get("/api/status")
    def api_status():
        snap = services.state.snapshot()
        snap["artwork_count"] = services.db.count_artwork()
        snap["enabled_count"] = services.db.count_enabled()
        return jsonify(snap)

    @app.post("/api/upload")
    def api_upload():
        data, _image, error = _read_64x64_png_upload("image", services, "preview")
        if error:
            return jsonify({"ok": False, "error": error}), 400
        assert data is not None

        title = (request.form.get("title") or "Uploaded image").strip()
        enabled = _bool_form("enabled", True)
        show_now = _bool_form("show_now", True)
        folder_path = normalize_folder_path(request.form.get("folder_path"), default="Uploads")

        try:
            row = services.db.add_uploaded_frame(
                panel_png_bytes=data,
                title=title,
                image_config=services.config.image,
                enabled=enabled,
                folder_path=folder_path,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"upload failed: {exc}"}), 500

        services.state.update(last_action=f"uploaded {row.title}")
        if show_now:
            services.demos.stop()
            services.slideshow.show_artwork(row.id)
        return jsonify({
            "ok": True,
            "artwork_id": row.id,
            "title": row.title,
            "kind": row.kind,
            "enabled": row.enabled,
            "folder_path": row.folder_path,
            "thumb_url": url_for("thumb", artwork_id=row.id),
        })

    @app.post("/api/gif")
    def api_gif_upload():
        decoded, data, error, options = _decode_gif_upload(services)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        assert decoded is not None
        assert data is not None

        upload = request.files.get("gif")
        filename = upload.filename if upload is not None else "animation.gif"
        title = (request.form.get("title") or filename.rsplit(".", 1)[0] or "Animated GIF").strip()
        enabled = _bool_form("enabled", True)
        show_now = _bool_form("show_now", True)
        folder_path = normalize_folder_path(request.form.get("folder_path"), default="Animations")

        try:
            frame_rows = [(image_to_png_bytes(frame), duration_ms) for frame, duration_ms in decoded]
            row = services.db.add_animation_frames(
                frame_rows,
                title=title,
                image_config=services.config.image,
                kind="gif",
                enabled=enabled,
                folder_path=folder_path,
                source_path=None,
                source_mime="image/gif",
                checksum=None,
                settings_label=(
                    f"gif:{options['scale_mode']}:{options['resample']}:"
                    f"crop={options.get('crop_x', 0)}:{options.get('crop_y', 0)}:{options.get('crop_size', 0)}:"
                    f"{options['max_frames']}:{options['default_duration_ms']}:"
                    f"{options['min_duration_ms']}:{options['max_duration_ms']}"
                ),
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"GIF import failed: {exc}"}), 500

        total_ms = sum(duration for _frame, duration in decoded)
        services.state.update(last_action=f"uploaded GIF {row.title} ({row.frame_count} frames)")
        if show_now:
            services.demos.stop()
            services.slideshow.show_artwork(row.id)
        return jsonify({
            "ok": True,
            "artwork_id": row.id,
            "title": row.title,
            "kind": row.kind,
            "enabled": row.enabled,
            "folder_path": row.folder_path,
            "frame_count": row.frame_count,
            "total_ms": total_ms,
            "thumb_url": url_for("thumb", artwork_id=row.id),
        })

    @app.post("/api/gif/browser-preview")
    def api_gif_browser_preview():
        decoded, _data, error, _options = _decode_gif_upload(services)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        assert decoded is not None
        frames = []
        total_ms = 0
        for image, duration_ms in decoded:
            png = image_to_png_bytes(image)
            frames.append({
                "data_url": "data:image/png;base64," + b64encode(png).decode("ascii"),
                "duration_ms": duration_ms,
            })
            total_ms += duration_ms
        return jsonify({
            "ok": True,
            "frame_count": len(frames),
            "total_ms": total_ms,
            "frames": frames,
        })

    @app.post("/api/gif/preview")
    def api_gif_preview():
        decoded, _data, error, _options = _decode_gif_upload(services)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        assert decoded is not None
        title = (request.form.get("title") or "GIF panel preview").strip()
        services.slideshow.set_enabled(False)
        services.demos.stop()
        services.display.show_frames(decoded, artwork_id=None, title=title, kind="preview-gif", transition=False)
        return jsonify({
            "ok": True,
            "title": title,
            "frame_count": len(decoded),
            "total_ms": sum(duration for _frame, duration in decoded),
        })

    @app.post("/api/drawing")
    def api_drawing():
        data, _image, error = _read_64x64_png_upload("image", services, "drawing")
        if error:
            return jsonify({"ok": False, "error": error}), 400
        assert data is not None

        title = (request.form.get("title") or "Drawing").strip()
        enabled = _bool_form("enabled", True)
        show_now = _bool_form("show_now", True)
        folder_path = normalize_folder_path(request.form.get("folder_path"), default="Drawings")

        try:
            row = services.db.add_drawing_frame(
                panel_png_bytes=data,
                title=title,
                image_config=services.config.image,
                enabled=enabled,
                folder_path=folder_path,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"save drawing failed: {exc}"}), 500

        services.state.update(last_action=f"saved drawing {row.title}")
        if show_now:
            services.demos.stop()
            services.slideshow.show_artwork(row.id)
        services.display.flash()
        return jsonify({
            "ok": True,
            "artwork_id": row.id,
            "title": row.title,
            "kind": row.kind,
            "enabled": row.enabled,
            "folder_path": row.folder_path,
            "thumb_url": url_for("thumb", artwork_id=row.id),
        })

    @app.post("/api/display/live-preview")
    def api_live_preview():
        _data, image, error = _read_64x64_png_upload("image", services, "live preview")
        if error:
            return jsonify({"ok": False, "error": error}), 400
        assert image is not None
        title = (request.form.get("title") or "Live drawing preview").strip()
        services.slideshow.set_enabled(False)
        services.demos.stop()
        services.display.preview_image(image, title=title)
        return jsonify({"ok": True, "title": title})


    @app.get("/api/artworks")
    def api_artworks():
        q = request.args.get("q", "").strip()
        enabled = request.args.get("enabled", "all")
        folder = request.args.get("folder", "all")
        rows = services.db.list_artwork(q=q, enabled=enabled, folder=folder, limit=800, offset=0)
        return jsonify([
            {
                "id": row.id,
                "title": row.title,
                "kind": row.kind,
                "enabled": row.enabled,
                "source_path": row.source_path,
                "folder_path": row.folder_path,
                "frame_count": row.frame_count,
                "thumb_url": url_for("thumb", artwork_id=row.id),
            }
            for row in rows
        ])


    @app.get("/api/folders")
    def api_folders():
        return jsonify({"ok": True, "folders": services.db.list_folders()})

    @app.post("/api/folders")
    def api_create_folder():
        data = request.get_json(silent=True) or {}
        raw = str(data.get("folder_path", ""))
        try:
            folder = services.db.create_folder(raw)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.state.update(last_action=f"created folder {folder['path']}")
        return jsonify({"ok": True, "folder": folder, "folders": services.db.list_folders()})

    @app.get("/api/folders/settings")
    def api_folders_settings():
        return jsonify({"ok": True, "folders": services.db.list_folders_for_settings()})

    @app.post("/api/folders/delete")
    def api_delete_folder():
        data = request.get_json(silent=True) or {}
        raw = str(data.get("folder_path", ""))
        try:
            result = services.db.delete_folder(raw)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.state.update(last_action=f"deleted folder {result['path']}; moved {result['moved_count']} item(s) to Unfiled")
        return jsonify({"ok": True, "result": result, "folders": services.db.list_folders()})

    @app.post("/api/folders/protect")
    def api_protect_folder():
        data = request.get_json(silent=True) or {}
        raw = str(data.get("folder_path", ""))
        protected = _bool_from_json(data.get("protected"), True)
        try:
            result = services.db.set_folder_protected(raw, protected)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.state.update(last_action=f"{'protected' if result.get('protected') else 'unprotected'} folder {result.get('path')}")
        return jsonify({"ok": True, "folder": result, "folders": services.db.list_folders_for_settings()})

    @app.post("/api/artwork/<int:artwork_id>/folder")
    def api_folder(artwork_id: int):
        data = request.get_json(silent=True) or {}
        row = services.db.set_folder(artwork_id, str(data.get("folder_path", "")))
        if row is None:
            return jsonify({"ok": False, "error": "artwork not found"}), 404
        return jsonify({"ok": True, "artwork_id": row.id, "folder_path": row.folder_path})

    @app.post("/api/artwork/<int:artwork_id>/rename")
    def api_rename_artwork(artwork_id: int):
        data = request.get_json(silent=True) or {}
        title = str(data.get("title", "")).strip()
        if not title:
            return jsonify({"ok": False, "error": "title cannot be empty"}), 400
        try:
            row = services.db.rename_artwork(artwork_id, title)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if row is None:
            return jsonify({"ok": False, "error": "artwork not found"}), 404
        snap = services.state.snapshot()
        if snap.get("current_artwork_id") == artwork_id:
            services.state.update(current_title=row.title, last_action=f"renamed current item to {row.title}")
        else:
            services.state.update(last_action=f"renamed item to {row.title}")
        return jsonify({"ok": True, "artwork_id": row.id, "title": row.title, "updated_at": row.updated_at})

    @app.post("/api/artworks/move")
    def api_move_artworks():
        data = request.get_json(silent=True) or {}
        ids = [int(x) for x in data.get("ids", []) if str(x).isdigit()]
        folder_path = str(data.get("folder_path", ""))
        if not ids:
            return jsonify({"ok": False, "error": "no images selected"}), 400
        try:
            rows = services.db.move_artworks(ids, folder_path)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        folder_label = normalize_folder_path(folder_path) or "Unfiled"
        services.state.update(last_action=f"moved {len(rows)} image(s) to {folder_label}")
        return jsonify({"ok": True, "count": len(rows), "folder_path": normalize_folder_path(folder_path), "ids": [row.id for row in rows]})

    @app.post("/api/artworks/folder-enabled")
    def api_folder_enabled():
        data = request.get_json(silent=True) or {}
        folder_path = str(data.get("folder", data.get("folder_path", "all")))
        enabled = _bool_from_json(data.get("enabled"), True)
        try:
            result = services.db.set_folder_enabled(folder_path, enabled)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.state.update(last_action=f"{'enabled' if enabled else 'disabled'} {result['count']} item(s)")
        return jsonify({"ok": True, **result})

    @app.post("/api/artwork/<int:artwork_id>/delete")
    def api_delete_artwork(artwork_id: int):
        rows = services.db.trash_artworks([artwork_id])
        if not rows:
            return jsonify({"ok": False, "error": "artwork not found"}), 404
        if services.state.snapshot().get("current_artwork_id") == artwork_id:
            services.display.clear()
        services.state.update(last_action=f"moved {rows[0].title} to Trash")
        return jsonify({"ok": True, "artwork_id": artwork_id, "title": rows[0].title})

    @app.post("/api/artworks/trash")
    def api_trash_artworks():
        ids = _ids_from_json()
        if not ids:
            return jsonify({"ok": False, "error": "no images selected"}), 400
        rows = services.db.trash_artworks(ids)
        current_id = services.state.snapshot().get("current_artwork_id")
        if current_id in ids:
            services.demos.stop()
            services.display.clear()
        services.state.update(last_action=f"moved {len(rows)} image(s) to Trash")
        return jsonify({"ok": True, "count": len(rows), "ids": [row.id for row in rows]})

    @app.post("/api/artworks/recover")
    def api_recover_artworks():
        ids = _ids_from_json()
        if not ids:
            return jsonify({"ok": False, "error": "no images selected"}), 400
        rows = services.db.recover_artworks(ids)
        services.state.update(last_action=f"recovered {len(rows)} image(s)")
        return jsonify({"ok": True, "count": len(rows), "ids": [row.id for row in rows]})

    @app.post("/api/artworks/destroy")
    def api_destroy_artworks():
        ids = _ids_from_json()
        if not ids:
            return jsonify({"ok": False, "error": "no images selected"}), 400
        rows = services.db.destroy_artworks(ids)
        current_id = services.state.snapshot().get("current_artwork_id")
        if current_id in ids:
            services.demos.stop()
            services.display.clear()
        services.state.update(last_action=f"destroyed {len(rows)} image(s)")
        return jsonify({"ok": True, "count": len(rows), "ids": [row.id for row in rows]})

    @app.post("/api/artwork/<int:artwork_id>/show")
    def api_show(artwork_id: int):
        services.demos.stop()
        result = services.slideshow.show_artwork(artwork_id)
        if not result.ok:
            return jsonify({"ok": False, "error": result.error}), 404
        return jsonify({"ok": True, "artwork_id": result.artwork_id, "title": result.title})

    @app.post("/api/artwork/<int:artwork_id>/enabled")
    def api_enabled(artwork_id: int):
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        if not services.db.get_artwork(artwork_id):
            return jsonify({"ok": False, "error": "artwork not found"}), 404
        services.db.set_enabled(artwork_id, enabled)
        return jsonify({"ok": True, "artwork_id": artwork_id, "enabled": enabled})

    @app.post("/api/display/clear")
    def api_clear():
        services.demos.stop()
        services.display.clear()
        return jsonify({"ok": True})

    @app.post("/api/display/brightness")
    def api_brightness():
        data = request.get_json(silent=True) or {}
        try:
            value = int(data.get("brightness", services.state.snapshot()["brightness"]))
        except Exception:
            value = services.state.snapshot()["brightness"]
        value = max(1, min(100, value))
        services.display.set_brightness(value)
        services.db.set_setting("brightness", str(value))
        return jsonify({"ok": True, "brightness": value})

    @app.post("/api/display/enabled")
    def api_display_enabled():
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        services.display.set_display_enabled(enabled)
        services.db.set_setting("display_enabled", "1" if enabled else "0")
        return jsonify({"ok": True, "display_enabled": enabled})

    @app.post("/api/transitions")
    def api_transitions():
        data = request.get_json(silent=True) or {}
        snap = services.state.snapshot()

        enabled = _bool_from_json(data.get("enabled"), bool(snap.get("transition_enabled", True))) if "enabled" in data else bool(snap.get("transition_enabled", True))
        effect = normalize_transition_name(str(data.get("effect", snap.get("transition_effect", "fade"))))
        try:
            duration_ms = int(float(data.get("duration_ms", snap.get("transition_duration_ms", 600))))
        except Exception:
            duration_ms = int(snap.get("transition_duration_ms", 600))
        try:
            fps = int(float(data.get("fps", snap.get("transition_fps", 30))))
        except Exception:
            fps = int(snap.get("transition_fps", 30))
        smoothing = _bool_from_json(data.get("smoothing"), bool(snap.get("transition_smoothing", True))) if "smoothing" in data else bool(snap.get("transition_smoothing", True))
        try:
            smoothing_strength = int(float(data.get("smoothing_strength", snap.get("transition_smoothing_strength", 35))))
        except Exception:
            smoothing_strength = int(snap.get("transition_smoothing_strength", 35))

        duration_ms = max(0, min(10000, duration_ms))
        fps = max(1, min(120, fps))
        smoothing_strength = max(0, min(100, smoothing_strength))

        services.display.set_transition_settings(
            enabled=enabled,
            effect=effect,
            duration_ms=duration_ms,
            fps=fps,
            smoothing=smoothing,
            smoothing_strength=smoothing_strength,
        )
        services.db.set_setting("transition_enabled", "1" if enabled else "0")
        services.db.set_setting("transition_effect", effect)
        services.db.set_setting("transition_duration_ms", str(duration_ms))
        services.db.set_setting("transition_fps", str(fps))
        services.db.set_setting("transition_smoothing", "1" if smoothing else "0")
        services.db.set_setting("transition_smoothing_strength", str(smoothing_strength))
        return jsonify({
            "ok": True,
            "transition_enabled": enabled,
            "transition_effect": effect,
            "transition_duration_ms": duration_ms,
            "transition_fps": fps,
            "transition_smoothing": smoothing,
            "transition_smoothing_strength": smoothing_strength,
        })



    @app.get("/api/demos/status")
    @app.get("/api/code/status")
    def api_demos_status():
        info = services.demos.snapshot()
        return jsonify({
            "ok": True,
            "running": info.running,
            "demo_id": info.demo_id,
            "title": info.title,
            "fps": info.fps,
            "frames_rendered": info.frames_rendered,
            "last_error": info.last_error,
            "started_at": info.started_at,
            "updated_at": info.updated_at,
        })

    def _demo_payload() -> tuple[str, str, str, int, bool]:
        data = request.get_json(silent=True) or {}
        title = str(data.get("title") or "New Demo").strip() or "New Demo"
        description = str(data.get("description") or "").strip()
        code = str(data.get("code") or "")
        if len(code.encode("utf-8", errors="ignore")) > 128 * 1024:
            raise ValueError("demo code is too large")
        try:
            fps = int(float(data.get("default_fps", services.config.demos.default_fps)))
        except Exception:
            fps = int(services.config.demos.default_fps)
        fps = max(1, min(1000, fps))
        max_fps = _code_max_fps(services)
        if max_fps > 0:
            fps = min(max_fps, fps)
        enabled = _bool_from_json(data.get("enabled", True), True)
        return title, description, code, fps, enabled

    def _demo_json(demo):
        return {
            "id": demo.id,
            "slug": demo.slug,
            "title": demo.title,
            "description": demo.description,
            "code": demo.code,
            "enabled": demo.enabled,
            "builtin": demo.builtin,
            "default_fps": demo.default_fps,
            "created_at": demo.created_at,
            "updated_at": demo.updated_at,
        }

    @app.get("/api/demos")
    @app.get("/api/code")
    def api_list_demos():
        return jsonify({
            "ok": True,
            "demos": [
                {
                    "id": demo.id,
                    "slug": demo.slug,
                    "title": demo.title,
                    "description": demo.description,
                    "enabled": demo.enabled,
                    "builtin": demo.builtin,
                    "default_fps": demo.default_fps,
                    "updated_at": demo.updated_at,
                }
                for demo in services.db.list_demos()
            ],
        })

    @app.get("/api/demos/<int:demo_id>")
    @app.get("/api/code/<int:demo_id>")
    def api_get_demo(demo_id: int):
        demo = services.db.get_demo(demo_id)
        if demo is None:
            return jsonify({"ok": False, "error": "demo not found"}), 404
        return jsonify({"ok": True, "demo": _demo_json(demo), "versions": services.db.list_demo_versions(demo_id)})

    @app.post("/api/demos/check")
    @app.post("/api/code/check")
    def api_check_demo_code():
        data = request.get_json(silent=True) or {}
        code = str(data.get("code") or "")
        try:
            compile(code, "<matrix-art-editor>", "exec")
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 400
        return jsonify({"ok": True, "message": "syntax check passed"})

    @app.post("/api/demos/new")
    @app.post("/api/code/new")
    def api_create_demo():
        try:
            title, description, code, fps, enabled = _demo_payload()
            demo = services.db.create_demo(title=title, description=description, code=code, default_fps=fps, enabled=enabled)
            artwork = _sync_code_artwork_for_demo(services, demo)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "demo": _demo_json(demo), "artwork": _code_artwork_json(artwork)})

    @app.post("/api/demos/<int:demo_id>/save")
    @app.post("/api/code/<int:demo_id>/save")
    def api_save_demo(demo_id: int):
        try:
            title, description, code, fps, enabled = _demo_payload()
            demo = services.db.update_demo(demo_id, title=title, description=description, code=code, default_fps=fps, enabled=enabled)
            artwork = _sync_code_artwork_for_demo(services, demo)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if not demo.enabled and services.demos.snapshot().demo_id == demo_id:
            services.demos.stop()
        return jsonify({"ok": True, "demo": _demo_json(demo), "artwork": _code_artwork_json(artwork)})

    @app.post("/api/code/<int:demo_id>/thumbnail-current")
    def api_code_thumbnail_current(demo_id: int):
        demo = services.db.get_demo(demo_id)
        if demo is None:
            return jsonify({"ok": False, "error": "code item not found"}), 404
        image = services.display.get_last_frame()
        if image is None:
            return jsonify({"ok": False, "error": "there is no current display frame to save"}), 400
        try:
            image = image.convert("RGB")
            if image.size != (services.config.image.target_width, services.config.image.target_height):
                image = image.resize((services.config.image.target_width, services.config.image.target_height), Image.Resampling.NEAREST)
            artwork = services.db.upsert_code_artwork(demo, image_to_png_bytes(image), services.config.image, folder_path="Code")
            services.db.set_setting(f"code_thumbnail_manual:{demo.id}", "1")
            services.state.update(last_action=f"saved current display as thumbnail for {demo.title}")
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "demo": _demo_json(demo), "artwork": _code_artwork_json(artwork)})

    @app.post("/api/demos/<int:demo_id>/copy")
    @app.post("/api/code/<int:demo_id>/copy")
    def api_copy_demo(demo_id: int):
        try:
            title, description, code, fps, enabled = _demo_payload()
            demo = services.db.duplicate_demo(demo_id, title=title, description=description, code=code, default_fps=fps, enabled=enabled)
            artwork = _sync_code_artwork_for_demo(services, demo)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "demo": _demo_json(demo), "artwork": _code_artwork_json(artwork)})

    @app.post("/api/demos/<int:demo_id>/delete")
    @app.post("/api/code/<int:demo_id>/delete")
    def api_delete_demo(demo_id: int):
        demo = services.db.get_demo(demo_id)
        if demo is None:
            return jsonify({"ok": False, "error": "code item not found"}), 404
        row = services.db.get_code_artwork_for_demo(demo_id)
        if row is not None:
            services.db.trash_artworks([row.id])
        elif not demo.builtin:
            services.db.delete_demo(demo_id)
        else:
            return jsonify({"ok": False, "error": "code item could not be moved to Trash"}), 400
        if services.demos.snapshot().demo_id == demo_id:
            services.demos.stop()
        services.state.update(last_action=f"moved code {demo.title} to Trash")
        return jsonify({"ok": True, "deleted": _demo_json(demo)})

    @app.post("/api/demos/run-draft")
    @app.post("/api/code/run-editor")
    def api_run_demo_draft():
        try:
            title, _description, code, fps, _enabled = _demo_payload()
            compile(code, f"<matrix-art-code-draft:{title}>", "exec")
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        services.slideshow.set_enabled(False)
        info = services.demos.start_demo(demo_id=0, title=f"Draft: {title}", code=code, fps=fps, artwork_id=None, kind="code")
        return jsonify({
            "ok": True,
            "running": info.running,
            "demo_id": info.demo_id,
            "title": info.title,
            "fps": info.fps,
            "frames_rendered": info.frames_rendered,
        })

    @app.post("/api/demos/<int:demo_id>/run")
    @app.post("/api/code/<int:demo_id>/run")
    def api_run_demo(demo_id: int):
        demo = services.db.get_demo(demo_id)
        if demo is None or not demo.enabled:
            return jsonify({"ok": False, "error": "demo not found or disabled"}), 404
        services.slideshow.set_enabled(False)
        row = services.db.get_code_artwork_for_demo(demo.id)
        info = services.demos.start_demo(demo_id=demo.id, title=demo.title, code=demo.code, fps=demo.default_fps, artwork_id=row.id if row else None, kind="code")
        return jsonify({
            "ok": True,
            "running": info.running,
            "demo_id": info.demo_id,
            "title": info.title,
            "fps": info.fps,
            "frames_rendered": info.frames_rendered,
        })

    @app.post("/api/demos/stop")
    @app.post("/api/code/stop")
    def api_stop_demo():
        info = services.demos.stop()
        return jsonify({"ok": True, "running": info.running, "title": info.title, "frames_rendered": info.frames_rendered})

    @app.post("/api/demos/<int:demo_id>/enabled")
    @app.post("/api/code/<int:demo_id>/enabled")
    def api_demo_enabled(demo_id: int):
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        demo = services.db.get_demo(demo_id)
        if demo is None:
            return jsonify({"ok": False, "error": "demo not found"}), 404
        services.db.set_demo_enabled(demo_id, enabled)
        if not enabled and services.demos.snapshot().demo_id == demo_id:
            services.demos.stop()
        return jsonify({"ok": True, "demo_id": demo_id, "enabled": enabled})

    @app.post("/api/slideshow")
    def api_slideshow():
        data = request.get_json(silent=True) or {}
        snap = services.state.snapshot()

        if "enabled" in data:
            enabled = _bool_from_json(data.get("enabled"), bool(snap["slideshow_enabled"]))
            if enabled:
                services.demos.stop()
            services.slideshow.set_enabled(enabled)
            services.db.set_setting("slideshow_enabled", "1" if enabled else "0")

        if "shuffle" in data:
            shuffle = _bool_from_json(data.get("shuffle"), bool(snap["shuffle_enabled"]))
            services.slideshow.set_shuffle(shuffle)
            services.db.set_setting("slideshow_shuffle", "1" if shuffle else "0")

        if "interval_seconds" in data:
            try:
                interval = float(data.get("interval_seconds"))
            except Exception:
                interval = float(snap["interval_seconds"])
            interval = max(1.0, min(3600.0, interval))
            services.slideshow.set_interval(interval)
            services.db.set_setting("slideshow_interval_seconds", f"{interval:g}")

        current = services.state.snapshot()
        return jsonify({
            "ok": True,
            "slideshow_enabled": current["slideshow_enabled"],
            "shuffle_enabled": current["shuffle_enabled"],
            "interval_seconds": current["interval_seconds"],
        })

    @app.post("/api/slideshow/next")
    def api_slideshow_next():
        services.demos.stop()
        result = services.slideshow.next()
        if not result.ok:
            return jsonify({"ok": False, "error": result.error}), 404
        return jsonify({"ok": True, "artwork_id": result.artwork_id, "title": result.title})

    @app.post("/api/slideshow/previous")
    def api_slideshow_previous():
        services.demos.stop()
        result = services.slideshow.previous()
        if not result.ok:
            return jsonify({"ok": False, "error": result.error}), 404
        return jsonify({"ok": True, "artwork_id": result.artwork_id, "title": result.title})

    @app.get("/thumb/<int:artwork_id>.png")
    @app.get("/thumb/<int:artwork_id>")
    def thumb(artwork_id: int):
        png = services.db.get_frame_png(artwork_id, 0)
        if not png:
            return "not found", 404
        response = send_file(BytesIO(png), mimetype="image/png", max_age=0)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/current.png")
    def current_png():
        image = services.display.get_last_frame()
        if image is None:
            image = Image.new("RGB", (services.config.image.target_width, services.config.image.target_height), (0, 0, 0))
        out = BytesIO()
        image.save(out, format="PNG")
        out.seek(0)
        return send_file(out, mimetype="image/png", max_age=0)

    return app
