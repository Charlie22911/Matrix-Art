from __future__ import annotations

import json
import threading
import time
from typing import Any

from PIL import Image

from .config import AppConfig
from .database import Database
from .display.worker import DisplayWorker
from .state import AppState
from .wifi_tools import (
    WifiError,
    connect_wifi_entry,
    first_ipv4,
    start_hotspot,
    set_matrix_art_hotspots_autoconnect,
    visible_saved_networks,
    wait_for_ipv4,
)

WIFI_SAVED_SETTING_KEY = "wifi_saved_networks"

FONT3 = {
    " ": ["000", "000", "000", "000", "000"],
    ".": ["000", "000", "000", "000", "010"],
    ":": ["000", "010", "000", "010", "000"],
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["111", "100", "100", "100", "111"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "G": ["111", "100", "101", "101", "111"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "111"],
    "K": ["101", "101", "110", "101", "101"],
    "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["101", "111", "111", "111", "101"],
    "O": ["111", "101", "101", "101", "111"],
    "P": ["111", "101", "111", "100", "100"],
    "Q": ["111", "101", "101", "111", "001"],
    "R": ["110", "101", "110", "101", "101"],
    "S": ["111", "100", "111", "001", "111"],
    "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "Z": ["111", "001", "010", "100", "111"],
    "-": ["000", "000", "111", "000", "000"],
}


def _draw_text(img: Image.Image, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    px = img.load()
    cursor = int(x)
    for ch in str(text).upper():
        glyph = FONT3.get(ch, FONT3.get(" "))
        if glyph is None:
            glyph = FONT3[" "]
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    xx = cursor + gx
                    yy = y + gy
                    if 0 <= xx < img.width and 0 <= yy < img.height:
                        px[xx, yy] = color
        cursor += 4


def _text_width(text: str) -> int:
    return max(0, len(str(text)) * 4 - 1)


def _center_text(img: Image.Image, text: str, y: int, color: tuple[int, int, int]) -> None:
    x = max(0, (img.width - _text_width(text)) // 2)
    _draw_text(img, text, x, y, color)


def _fit_label(prefix: str, value: str, max_chars: int = 15) -> str:
    text = f"{prefix}{value}" if prefix else str(value)
    text = " ".join(text.replace("\n", " ").split())
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[:max_chars]


def startup_ip_frame(
    ip: str,
    seconds_left: int,
    *,
    width: int = 64,
    height: int = 64,
    server_port: int = 80,
    ap_ssid: str = "",
    ap_password: str = "",
) -> Image.Image:
    img = Image.new("RGB", (width, height), (0, 3, 10))
    ip_text = (ip or "NO IP")[:15]
    port_text = _fit_label("PORT:", str(server_port), max_chars=15)
    if ap_ssid:
        # Six compact rows fit on 64x64 with the 3x5 font.
        _center_text(img, ip_text, 1, (150, 220, 255))
        _center_text(img, port_text, 12, (130, 255, 180))
        _center_text(img, _fit_label("AP:", ap_ssid), 23, (255, 255, 255))
        _center_text(img, _fit_label("PW:", ap_password), 34, (255, 210, 80))
        _center_text(img, "STARTING", 47, (180, 220, 255))
        _center_text(img, f"{max(0, int(seconds_left)):02d} SEC", 57, (255, 210, 80))
    else:
        # Full IPv4 plus port fits in the 3x5 font at 64 px wide.
        _center_text(img, ip_text, 6, (150, 220, 255))
        _center_text(img, port_text, 19, (130, 255, 180))
        _center_text(img, "STARTING", 35, (255, 255, 255))
        _center_text(img, f"{max(0, int(seconds_left)):02d} SEC", 50, (255, 210, 80))
    return img


def show_ip_countdown(
    display: DisplayWorker,
    state: AppState,
    *,
    seconds: int = 60,
    stop_event: threading.Event | None = None,
    server_port: int = 80,
    ap_ssid: str = "",
    ap_password: str = "",
) -> None:
    total = max(1, int(seconds or 60))
    for remaining in range(total, 0, -1):
        if stop_event is not None and stop_event.is_set():
            break
        ip = first_ipv4() or "NO IP"
        frame = startup_ip_frame(
            ip,
            remaining,
            width=display.driver.width,
            height=display.driver.height,
            server_port=server_port,
            ap_ssid=ap_ssid,
            ap_password=ap_password,
        )
        display.preview_image(frame, title="Startup IP", kind="startup")
        time.sleep(1.0)


def start_ip_countdown_thread(
    display: DisplayWorker,
    state: AppState,
    *,
    seconds: int = 60,
    stop_event: threading.Event | None = None,
    server_port: int = 80,
    ap_ssid: str = "",
    ap_password: str = "",
) -> threading.Thread:
    thread = threading.Thread(
        target=show_ip_countdown,
        kwargs={
            "display": display,
            "state": state,
            "seconds": seconds,
            "stop_event": stop_event,
            "server_port": server_port,
            "ap_ssid": ap_ssid,
            "ap_password": ap_password,
        },
        name="matrix-art-startup-ip",
        daemon=True,
    )
    thread.start()
    return thread


def _load_saved_wifi(db: Database) -> list[dict[str, Any]]:
    raw = db.get_setting(WIFI_SAVED_SETTING_KEY, "[]")
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return [entry for entry in parsed if isinstance(entry, dict) and str(entry.get("ssid") or "").strip()]


def _hotspot_settings(db: Database, config: AppConfig) -> tuple[str, str, str | None]:
    ssid = db.get_setting("hotspot_ssid", config.startup.default_hotspot_ssid).strip() or config.startup.default_hotspot_ssid
    password = db.get_setting("hotspot_password", config.startup.default_hotspot_password).strip() or config.startup.default_hotspot_password
    interface = db.get_setting("hotspot_interface", "").strip() or None
    return ssid, password, interface


def start_saved_hotspot(db: Database, config: AppConfig, *, persist: bool) -> str:
    ssid, password, interface = _hotspot_settings(db, config)
    return start_hotspot(ssid, password, interface, persist=persist)


def prepare_startup_network(db: Database, config: AppConfig, state: AppState) -> dict[str, Any]:
    """Best-effort startup network policy.

    Manual hotspot mode persists. Automatic fallback hotspot starts when saved Wi-Fi
    is not available, but does not change the selected Wi-Fi mode.
    """
    if config.runtime.mock_display:
        return {"mode": "mock", "ip": "127.0.0.1", "message": "mock display, networking unchanged"}

    selected_mode = db.get_setting("wifi_mode", "wifi").strip().lower() or "wifi"
    if selected_mode not in {"wifi", "hotspot"}:
        selected_mode = "wifi"

    if selected_mode == "hotspot":
        try:
            message = start_saved_hotspot(db, config, persist=True)
            ip = wait_for_ipv4(config.startup.ip_wait_seconds)
            state.update(last_action=f"hotspot mode: {message}")
            return {"mode": "hotspot", "ip": ip, "message": message}
        except Exception as exc:
            state.update(last_error=str(exc), last_action="hotspot startup failed")
            return {"mode": "hotspot", "ip": first_ipv4(), "error": str(exc)}

    # Wi-Fi mode. Give NetworkManager autoconnect a chance first.
    ip = wait_for_ipv4(min(15, max(1, int(config.startup.ip_wait_seconds))))
    if ip:
        return {"mode": "wifi", "ip": ip, "message": "NetworkManager provided an IP"}

    saved = _load_saved_wifi(db)
    candidates = visible_saved_networks(saved)
    for entry in candidates:
        try:
            set_matrix_art_hotspots_autoconnect(False)
            message = connect_wifi_entry(entry)
            db.set_setting("wifi_mode", "wifi")
            ip = wait_for_ipv4(12)
            if ip:
                state.update(last_action=f"connected saved Wi-Fi {entry.get('ssid')}")
                return {"mode": "wifi", "ip": ip, "message": message}
        except Exception as exc:
            state.update(last_error=str(exc), last_action=f"saved Wi-Fi failed: {entry.get('ssid')}")

    if config.startup.hotspot_fallback:
        try:
            message = start_saved_hotspot(db, config, persist=False)
            ip = wait_for_ipv4(config.startup.ip_wait_seconds)
            state.update(last_action=f"fallback hotspot: {message}")
            return {"mode": "fallback-hotspot", "ip": ip, "message": message}
        except (WifiError, Exception) as exc:
            state.update(last_error=str(exc), last_action="fallback hotspot failed")
            return {"mode": "wifi", "ip": first_ipv4(), "error": str(exc)}

    return {"mode": "wifi", "ip": first_ipv4(), "message": "no IP and hotspot fallback disabled"}
