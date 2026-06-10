from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from time import time
from typing import Any


@dataclass
class AppState:
    display_enabled: bool = True
    brightness: int = 70
    slideshow_enabled: bool = False
    shuffle_enabled: bool = True
    interval_seconds: float = 10.0
    transition_enabled: bool = True
    transition_effect: str = "fade"
    transition_duration_ms: int = 600
    transition_fps: int = 30
    transition_smoothing: bool = True
    transition_smoothing_strength: int = 35
    demo_running: bool = False
    demo_id: int | None = None
    demo_title: str = "None"
    current_artwork_id: int | None = None
    current_title: str = "None"
    current_kind: str = "none"
    frame_version: int = 0
    display_driver: str = "unknown"
    last_error: str = ""
    last_action: str = "starting"
    priority_status: str = "not configured"
    started_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    lock: RLock = field(default_factory=RLock, repr=False)

    def update(self, frame_changed: bool = False, **kwargs: Any) -> None:
        with self.lock:
            for key, value in kwargs.items():
                setattr(self, key, value)
            if frame_changed:
                self.frame_version += 1
            self.updated_at = time()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "display_enabled": self.display_enabled,
                "brightness": self.brightness,
                "slideshow_enabled": self.slideshow_enabled,
                "shuffle_enabled": self.shuffle_enabled,
                "interval_seconds": self.interval_seconds,
                "transition_enabled": self.transition_enabled,
                "transition_effect": self.transition_effect,
                "transition_duration_ms": self.transition_duration_ms,
                "transition_fps": self.transition_fps,
                "transition_smoothing": self.transition_smoothing,
                "transition_smoothing_strength": self.transition_smoothing_strength,
                "demo_running": self.demo_running,
                "demo_id": self.demo_id,
                "demo_title": self.demo_title,
                "current_artwork_id": self.current_artwork_id,
                "current_title": self.current_title,
                "current_kind": self.current_kind,
                "frame_version": self.frame_version,
                "display_driver": self.display_driver,
                "last_error": self.last_error,
                "last_action": self.last_action,
                "priority_status": self.priority_status,
                "started_at": self.started_at,
                "updated_at": self.updated_at,
            }
