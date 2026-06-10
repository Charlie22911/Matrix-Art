from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from typing import Any

from ..artwork.processor import png_bytes_to_image
from ..database import ArtworkRow, Database
from ..display.worker import DisplayWorker
from ..state import AppState


@dataclass(slots=True)
class ShowResult:
    ok: bool
    artwork_id: int | None = None
    title: str = ""
    error: str = ""


class SlideshowController:
    """Coordinates manual navigation and timed slideshow playback.

    The web server calls into this object for show/next/previous/play/pause. A
    lightweight scheduler thread wakes independently so the web UI never waits
    for slideshow timing.
    """

    def __init__(self, db: Database, display: DisplayWorker, state: AppState, *, interval_seconds: float = 10.0, shuffle: bool = True, enabled: bool = False, code_runner: Any = None):
        self.db = db
        self.display = display
        self.state = state
        self.code_runner = code_runner
        self.lock = threading.RLock()
        self.wake_event = threading.Event()
        self.stop_event = threading.Event()
        self.last_shuffle_id: int | None = None
        self.thread = threading.Thread(target=self._run, name="matrix-art-slideshow", daemon=True)
        self.state.update(
            slideshow_enabled=bool(enabled),
            shuffle_enabled=bool(shuffle),
            interval_seconds=max(1.0, float(interval_seconds)),
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self.stop_event.set()
        self.wake_event.set()
        self.thread.join(timeout=timeout)

    def show_artwork(self, artwork_id: int, *, pause_slideshow: bool = False) -> ShowResult:
        with self.lock:
            if pause_slideshow:
                self.state.update(slideshow_enabled=False)
            result = self._show_artwork_locked(artwork_id)
            self.wake_event.set()
            return result

    def show_first(self) -> ShowResult:
        first = self.db.get_first_enabled()
        if not first:
            return ShowResult(False, error="no enabled artwork")
        return self.show_artwork(first.id)

    def next(self, *, pause_slideshow: bool = False) -> ShowResult:
        with self.lock:
            if pause_slideshow:
                self.state.update(slideshow_enabled=False)
            row = self._choose_next_locked(forward=True)
            if not row:
                return ShowResult(False, error="no enabled artwork")
            result = self._show_artwork_locked(row.id)
            self.wake_event.set()
            return result

    def previous(self, *, pause_slideshow: bool = False) -> ShowResult:
        with self.lock:
            if pause_slideshow:
                self.state.update(slideshow_enabled=False)
            row = self._choose_next_locked(forward=False)
            if not row:
                return ShowResult(False, error="no enabled artwork")
            result = self._show_artwork_locked(row.id)
            self.wake_event.set()
            return result

    def set_enabled(self, enabled: bool) -> None:
        self.state.update(slideshow_enabled=bool(enabled), last_action="slideshow started" if enabled else "slideshow paused")
        self.wake_event.set()

    def set_shuffle(self, enabled: bool) -> None:
        self.state.update(shuffle_enabled=bool(enabled), last_action="shuffle on" if enabled else "shuffle off")
        self.wake_event.set()

    def set_interval(self, seconds: float) -> None:
        value = max(1.0, min(3600.0, float(seconds)))
        self.state.update(interval_seconds=value, last_action=f"slideshow interval {value:g}s")
        self.wake_event.set()

    def snapshot(self) -> dict[str, object]:
        snap = self.state.snapshot()
        return {
            "enabled": snap["slideshow_enabled"],
            "shuffle": snap["shuffle_enabled"],
            "interval_seconds": snap["interval_seconds"],
        }

    def _show_artwork_locked(self, artwork_id: int) -> ShowResult:
        row = self.db.get_artwork(artwork_id)
        if not row:
            return ShowResult(False, error="artwork not found")
        if row.kind == "code":
            demo = self.db.get_demo_for_artwork(row.id)
            if demo is None or not demo.enabled:
                return ShowResult(False, error="code effect not found or disabled")
            if self.code_runner is None:
                return ShowResult(False, error="code runner is not available")
            self.code_runner.start_demo(
                demo_id=demo.id,
                title=demo.title,
                code=demo.code,
                fps=demo.default_fps,
                artwork_id=row.id,
                kind="code",
            )
            self.last_shuffle_id = row.id
            return ShowResult(True, artwork_id=row.id, title=row.title)

        after_transition = None
        if self.code_runner is not None:
            try:
                if self.code_runner.snapshot().running:
                    after_transition = lambda runner=self.code_runner: runner.stop()
            except Exception:
                after_transition = None
        frame_rows = self.db.get_frame_sequence(artwork_id)
        if not frame_rows:
            return ShowResult(False, error="frame not found")
        if len(frame_rows) > 1 or row.kind == "gif":
            frames = [(png_bytes_to_image(png), duration_ms) for png, duration_ms in frame_rows]
            self.display.show_frames(frames, artwork_id=row.id, title=row.title, kind=row.kind, after_transition=after_transition)
        else:
            image = png_bytes_to_image(frame_rows[0][0])
            self.display.show_image(image, artwork_id=row.id, title=row.title, after_transition=after_transition)
        self.last_shuffle_id = row.id
        return ShowResult(True, artwork_id=row.id, title=row.title)

    def _choose_next_locked(self, *, forward: bool) -> ArtworkRow | None:
        rows = self.db.list_enabled_artwork(limit=5000)
        if not rows:
            return None
        if self.state.snapshot()["shuffle_enabled"]:
            if len(rows) == 1:
                return rows[0]
            candidates = [row for row in rows if row.id != self.last_shuffle_id]
            if not candidates:
                candidates = rows
            return random.choice(candidates)

        current_id = self.state.snapshot()["current_artwork_id"]
        ids = [row.id for row in rows]
        if current_id in ids:
            idx = ids.index(current_id)
            idx = (idx + (1 if forward else -1)) % len(rows)
            return rows[idx]
        return rows[0] if forward else rows[-1]

    def _run(self) -> None:
        # The scheduler never touches rgbmatrix directly. It only queues display
        # commands, so timing-sensitive panel work stays in DisplayWorker.
        while not self.stop_event.is_set():
            snap = self.state.snapshot()
            if not snap["slideshow_enabled"]:
                self.wake_event.wait(0.5)
                self.wake_event.clear()
                continue

            interval = max(1.0, float(snap["interval_seconds"]))
            woke = self.wake_event.wait(interval)
            self.wake_event.clear()
            if self.stop_event.is_set():
                break
            if woke:
                continue
            if not self.state.snapshot()["slideshow_enabled"]:
                continue
            try:
                self.next(pause_slideshow=False)
            except Exception as exc:
                self.state.update(last_error=str(exc), last_action="slideshow error")
