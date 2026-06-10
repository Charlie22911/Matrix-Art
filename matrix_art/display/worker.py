from __future__ import annotations

import queue
import threading
import traceback
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any

from PIL import Image

from ..runtime_priority import set_realtime_fifo
from ..state import AppState
from .base import DisplayDriver
from .transitions import TRANSITION_EFFECTS, iter_transition_frames_dynamic, normalize_transition_name


@dataclass(slots=True)
class DisplayCommand:
    kind: str
    payload: Any = None


class DisplayWorker:
    def __init__(
        self,
        driver: DisplayDriver,
        state: AppState,
        max_queue: int = 3,
        realtime_priority: int = 0,
        *,
        transition_enabled: bool = True,
        transition_effect: str = "fade",
        transition_duration_ms: int = 600,
        transition_fps: int = 30,
        transition_smoothing: bool = True,
        transition_smoothing_strength: int = 35,
    ):
        self.driver = driver
        self.state = state
        self.realtime_priority = int(realtime_priority or 0)
        self.queue: queue.Queue[DisplayCommand] = queue.Queue(maxsize=max_queue)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="matrix-art-display", daemon=True)
        self.frame_lock = threading.RLock()
        self.last_frame: Image.Image | None = None
        self.last_frame_at = 0.0
        self.live_frame_lock = threading.RLock()
        self.latest_live_frame: Image.Image | None = None
        self.latest_live_kind = ""
        self.latest_live_at = 0.0
        self.animation_frames: list[tuple[Image.Image, int]] = []
        self.animation_index = 0
        self.animation_next_at = 0.0
        self.animation_artwork_id: int | None = None
        self.animation_title = ""
        self.animation_kind = "gif"
        self.transition_enabled = bool(transition_enabled)
        self.transition_effect = normalize_transition_name(transition_effect)
        self.transition_duration_ms = max(0, min(10000, int(transition_duration_ms or 0)))
        self.transition_fps = max(1, min(120, int(transition_fps or 30)))
        self.transition_smoothing = bool(transition_smoothing)
        self.transition_smoothing_strength = max(0, min(100, int(transition_smoothing_strength or 0)))
        self.state.update(
            transition_enabled=self.transition_enabled,
            transition_effect=self.transition_effect,
            transition_duration_ms=self.transition_duration_ms,
            transition_fps=self.transition_fps,
            transition_smoothing=self.transition_smoothing,
            transition_smoothing_strength=self.transition_smoothing_strength,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self.stop_event.set()
        self._put(DisplayCommand("stop"))
        self.thread.join(timeout=timeout)

    def show_image(self, image: Image.Image, artwork_id: int | None = None, title: str = "", *, transition: bool = True, after_transition=None) -> None:
        self._put(DisplayCommand("show", {"image": image.copy(), "artwork_id": artwork_id, "title": title, "transition": transition, "after_transition": after_transition}))

    def preview_image(self, image: Image.Image, title: str = "Live preview", *, kind: str = "preview", transition: bool = True) -> None:
        img = image.copy()
        # Code frames are produced by a separate process. Keep the newest frame
        # in a side buffer so transitions can sample it even while the display
        # worker is busy drawing the transition itself.
        if kind == "code":
            with self.live_frame_lock:
                self.latest_live_frame = img.copy()
                self.latest_live_kind = kind
                self.latest_live_at = monotonic()
        self._put(DisplayCommand("preview", {"image": img, "title": title, "kind": kind, "transition": transition}))

    def show_frames(
        self,
        frames: list[tuple[Image.Image, int]],
        artwork_id: int | None = None,
        title: str = "",
        kind: str = "gif",
        *,
        transition: bool = True,
        after_transition=None,
    ) -> None:
        payload_frames = [(image.copy(), max(20, min(5000, int(duration_ms or 100)))) for image, duration_ms in frames]
        self._put(DisplayCommand("show_frames", {"frames": payload_frames, "artwork_id": artwork_id, "title": title, "kind": kind, "transition": transition, "after_transition": after_transition}))

    def flash(self, duration_ms: int = 90) -> None:
        self._put(DisplayCommand("flash", max(20, min(500, int(duration_ms)))))

    def clear(self) -> None:
        self._put(DisplayCommand("clear"))

    def set_display_enabled(self, enabled: bool) -> None:
        self._put(DisplayCommand("display_enabled", bool(enabled)))

    def set_brightness(self, value: int) -> None:
        self._put(DisplayCommand("brightness", int(value)))

    def set_transition_settings(
        self,
        *,
        enabled: bool | None = None,
        effect: str | None = None,
        duration_ms: int | None = None,
        fps: int | None = None,
        smoothing: bool | None = None,
        smoothing_strength: int | None = None,
    ) -> None:
        self._put(DisplayCommand("transition_settings", {
            "enabled": enabled,
            "effect": effect,
            "duration_ms": duration_ms,
            "fps": fps,
            "smoothing": smoothing,
            "smoothing_strength": smoothing_strength,
        }))

    def get_last_frame(self) -> Image.Image | None:
        with self.frame_lock:
            return self.last_frame.copy() if self.last_frame is not None else None

    def _put(self, cmd: DisplayCommand) -> None:
        # Keep newest commands when the UI is clicked quickly.
        try:
            self.queue.put_nowait(cmd)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            self.queue.put_nowait(cmd)

    def _set_last_frame(self, image: Image.Image | None) -> None:
        with self.frame_lock:
            self.last_frame = image.copy() if image is not None else None
            self.last_frame_at = monotonic() if image is not None else 0.0

    def _redraw_last_frame_if_present(self) -> bool:
        frame = self.get_last_frame()
        if frame is None:
            return False
        self.driver.show_image(frame)
        return True

    def _get_latest_live_frame(self) -> Image.Image | None:
        with self.live_frame_lock:
            return self.latest_live_frame.copy() if self.latest_live_frame is not None else None

    def _clear_latest_live_frame(self) -> None:
        with self.live_frame_lock:
            self.latest_live_frame = None
            self.latest_live_kind = ""
            self.latest_live_at = 0.0

    def _make_animation_sampler(self, frames: list[tuple[Image.Image, int]], start_index: int = 0, next_at: float = 0.0):
        """Return a small sampler for transition-time animated frames.

        The sampler advances using each frame's own duration but never draws
        directly to the matrix. It returns the current frame and exposes its
        post-transition index so normal playback can resume from the right place.
        """
        if not frames:
            return None

        class _Sampler:
            def __init__(self, seq, index, due_at):
                self.frames = seq
                self.index = int(index or 0) % len(seq)
                self.next_at = float(due_at or 0.0)
                self.current = seq[self.index][0]
                now = monotonic()
                if self.next_at <= 0.0:
                    self.next_at = now

            def sample(self) -> Image.Image:
                now = monotonic()
                if self.next_at <= now:
                    image, duration_ms = self.frames[self.index]
                    self.current = image
                    self.index = (self.index + 1) % len(self.frames)
                    self.next_at = now + (max(20, int(duration_ms or 100)) / 1000.0)
                return self.current

        return _Sampler([(img.copy(), dur) for img, dur in frames], start_index, next_at)

    def _current_dynamic_old_sampler(self):
        # GIF/animation sources are owned by this display worker, so advance a
        # private sampler during transition and leave the real animation state
        # alone until the transition is complete. Code frames arrive from a
        # separate runner and are sampled from the latest live-frame buffer.
        if self.animation_frames:
            return self._make_animation_sampler(self.animation_frames, self.animation_index, self.animation_next_at)
        if self.state.snapshot().get("current_kind") == "code":
            return lambda: self._get_latest_live_frame()
        return None

    def _stop_animation(self) -> None:
        self.animation_frames = []
        self.animation_index = 0
        self.animation_next_at = 0.0
        self.animation_artwork_id = None
        self.animation_title = ""

    def _transition_is_active(self, allow_transition: bool = True) -> bool:
        return (
            bool(allow_transition)
            and bool(self.transition_enabled)
            and self.transition_effect in TRANSITION_EFFECTS
            and self.transition_effect != "none"
            and self.transition_duration_ms > 0
            and self.transition_fps > 0
        )

    def _show_image_with_optional_transition(
        self,
        image: Image.Image,
        *,
        allow_transition: bool = True,
        old_sampler=None,
        new_sampler=None,
        after_transition=None,
    ) -> None:
        target = image.convert("RGB")
        if target.size != (self.driver.width, self.driver.height):
            target = target.resize((self.driver.width, self.driver.height), Image.Resampling.NEAREST)
        previous = self.get_last_frame()
        if previous is None:
            previous = old_sampler() if callable(old_sampler) else None
        if previous is None or not self._transition_is_active(allow_transition):
            draw = new_sampler() if callable(new_sampler) else target
            if draw is None:
                draw = target
            self.driver.show_image(draw)
            if after_transition is not None:
                try:
                    after_transition()
                except Exception:
                    err = traceback.format_exc(limit=6)
                    print(err)
                    self.state.update(last_error=err, last_action="after-transition callback error")
            return

        frame_delay = 1.0 / max(1, self.transition_fps)
        if old_sampler is None:
            old_sampler = self._current_dynamic_old_sampler()
        for frame in iter_transition_frames_dynamic(
            previous,
            target,
            old_getter=old_sampler if callable(old_sampler) else None,
            new_getter=new_sampler if callable(new_sampler) else None,
            effect=self.transition_effect,
            duration_ms=self.transition_duration_ms,
            fps=self.transition_fps,
            smoothing=self.transition_smoothing,
            smoothing_strength=self.transition_smoothing_strength,
        ):
            if self.stop_event.is_set():
                break
            self.driver.show_image(frame)
            self._set_last_frame(frame)
            sleep(frame_delay)
        final = new_sampler() if callable(new_sampler) else target
        if final is None:
            final = target
        self.driver.show_image(final)
        if after_transition is not None:
            try:
                after_transition()
            except Exception:
                err = traceback.format_exc(limit=6)
                print(err)
                self.state.update(last_error=err, last_action="after-transition callback error")

    def _set_now_playing(self, *, artwork_id: int | None, title: str, kind: str, action: str) -> None:
        self.state.update(
            current_artwork_id=artwork_id,
            current_title=title,
            current_kind=kind,
            last_action=action,
            last_error="",
            frame_changed=True,
        )

    def _advance_animation(self) -> None:
        if not self.animation_frames:
            return
        image, duration_ms = self.animation_frames[self.animation_index]
        if self.state.snapshot()["display_enabled"]:
            self.driver.show_image(image)
        self._set_last_frame(image)
        self._set_now_playing(
            artwork_id=self.animation_artwork_id,
            title=self.animation_title or "Animated GIF",
            kind=self.animation_kind,
            action=f"playing {self.animation_title or 'animation'}",
        )
        self.animation_index = (self.animation_index + 1) % len(self.animation_frames)
        self.animation_next_at = monotonic() + (max(20, int(duration_ms)) / 1000.0)

    def _start_animation(self, payload: dict[str, Any]) -> None:
        frames: list[tuple[Image.Image, int]] = payload.get("frames") or []
        if not frames:
            self._stop_animation()
            self.state.update(last_error="animation had no frames", last_action="animation failed")
            return

        new_frames = [(image.copy(), max(20, min(5000, int(duration_ms or 100)))) for image, duration_ms in frames]
        title = payload.get("title") or "Animated GIF"
        kind = payload.get("kind") or "gif"
        artwork_id = payload.get("artwork_id")

        first, first_duration_ms = new_frames[0]
        old_sampler = self._current_dynamic_old_sampler()
        new_sampler = self._make_animation_sampler(new_frames, 0, 0.0)

        if self.state.snapshot()["display_enabled"]:
            self._show_image_with_optional_transition(
                first,
                allow_transition=bool(payload.get("transition", True)),
                old_sampler=old_sampler,
                new_sampler=(new_sampler.sample if new_sampler is not None else None),
                after_transition=payload.get("after_transition"),
            )
        elif payload.get("after_transition") is not None:
            try:
                payload.get("after_transition")()
            except Exception:
                err = traceback.format_exc(limit=6)
                print(err)
                self.state.update(last_error=err, last_action="after-transition callback error")

        # Release the old animated source after the transition and resume the new
        # animation from the sampler's post-transition position so its motion does
        # not jump backward to frame 0.
        self.animation_frames = new_frames
        self.animation_artwork_id = artwork_id
        self.animation_title = title
        self.animation_kind = kind
        if new_sampler is not None:
            self.animation_index = int(new_sampler.index) % len(new_frames)
            self.animation_next_at = float(new_sampler.next_at)
            current = new_sampler.current
        else:
            self.animation_index = 1 % len(new_frames)
            self.animation_next_at = monotonic() + (max(20, int(first_duration_ms)) / 1000.0)
            current = first

        self._set_last_frame(current)
        self._set_now_playing(
            artwork_id=self.animation_artwork_id,
            title=self.animation_title,
            kind=self.animation_kind,
            action=f"playing {self.animation_title}",
        )

    def _run(self) -> None:
        priority_message = ""
        if self.realtime_priority > 0:
            result = set_realtime_fifo(self.realtime_priority, "display worker")
            priority_message = f"; {result.message}"
        self.state.update(display_driver=self.driver.name, last_action=f"display worker ready{priority_message}")
        while not self.stop_event.is_set():
            timeout = 0.25
            if self.animation_frames:
                now = monotonic()
                if self.animation_next_at <= now:
                    try:
                        self._advance_animation()
                    except Exception:
                        err = traceback.format_exc(limit=6)
                        print(err)
                        self._stop_animation()
                        self.state.update(last_error=err, last_action="animation error")
                    continue
                timeout = min(timeout, max(0.0, self.animation_next_at - now))
            try:
                cmd = self.queue.get(timeout=timeout)
            except queue.Empty:
                continue
            try:
                if cmd.kind == "stop":
                    self._stop_animation()
                    self._clear_latest_live_frame()
                    try:
                        self.driver.clear()
                    except Exception:
                        pass
                    self._set_last_frame(None)
                    self.state.update(current_artwork_id=None, current_title="None", current_kind="none", last_action="display stopped", frame_changed=True)
                    break
                if cmd.kind == "show":
                    payload = cmd.payload
                    image: Image.Image = payload["image"]
                    title = payload.get("title") or "Untitled"
                    old_sampler = self._current_dynamic_old_sampler()
                    if not self.state.snapshot()["display_enabled"]:
                        self._stop_animation()
                        self._clear_latest_live_frame()
                        if payload.get("after_transition") is not None:
                            try:
                                payload.get("after_transition")()
                            except Exception:
                                err = traceback.format_exc(limit=6)
                                print(err)
                                self.state.update(last_error=err, last_action="after-transition callback error")
                        self._set_last_frame(image)
                        self._set_now_playing(
                            artwork_id=payload.get("artwork_id"),
                            title=title,
                            kind="image",
                            action="image queued, display disabled",
                        )
                        continue
                    self._show_image_with_optional_transition(
                        image,
                        allow_transition=bool(payload.get("transition", True)),
                        old_sampler=old_sampler,
                        after_transition=payload.get("after_transition"),
                    )
                    self._stop_animation()
                    self._clear_latest_live_frame()
                    self._set_last_frame(image)
                    self._set_now_playing(
                        artwork_id=payload.get("artwork_id"),
                        title=title,
                        kind="image",
                        action=f"showed {title}",
                    )
                elif cmd.kind == "show_frames":
                    self._start_animation(cmd.payload)
                elif cmd.kind == "preview":
                    payload = cmd.payload
                    image: Image.Image = payload["image"]
                    title = payload.get("title") or "Live preview"
                    kind = payload.get("kind") or "preview"
                    if kind == "code":
                        snap = self.state.snapshot()
                        if not snap.get("demo_running"):
                            continue
                        old_sampler = self._current_dynamic_old_sampler()
                        allow = bool(payload.get("transition", True)) and snap.get("current_kind") != "code"
                        if snap["display_enabled"]:
                            if allow:
                                self._show_image_with_optional_transition(
                                    image,
                                    allow_transition=True,
                                    old_sampler=old_sampler,
                                )
                            else:
                                self.driver.show_image(image)
                        self._stop_animation()
                    else:
                        self._stop_animation()
                        self._clear_latest_live_frame()
                        if self.state.snapshot()["display_enabled"]:
                            self.driver.show_image(image)
                    self._set_last_frame(image)
                    self._set_now_playing(
                        artwork_id=None,
                        title=title,
                        kind=kind,
                        action=title,
                    )
                elif cmd.kind == "flash":
                    duration_ms = max(20, min(500, int(cmd.payload or 90)))
                    restore = self.get_last_frame()
                    if self.state.snapshot()["display_enabled"]:
                        flash_frame = Image.new("RGB", (self.driver.width, self.driver.height), (255, 255, 255))
                        self.driver.show_image(flash_frame)
                        sleep(duration_ms / 1000.0)
                        if restore is not None:
                            self.driver.show_image(restore)
                        else:
                            self.driver.clear()
                    self.state.update(last_action="save flash")
                elif cmd.kind == "clear":
                    self._stop_animation()
                    self._clear_latest_live_frame()
                    self.driver.clear()
                    self._set_last_frame(None)
                    self.state.update(
                        current_artwork_id=None,
                        current_title="None",
                        current_kind="none",
                        last_action="cleared",
                        frame_changed=True,
                    )
                elif cmd.kind == "display_enabled":
                    enabled = bool(cmd.payload)
                    if enabled:
                        self.state.update(display_enabled=True, last_action="display enabled")
                        if self._redraw_last_frame_if_present():
                            self.state.update(last_action="display enabled, restored image")
                    else:
                        self.driver.clear()
                        self.state.update(display_enabled=False, last_action="display disabled")
                elif cmd.kind == "brightness":
                    value = max(1, min(100, int(cmd.payload)))
                    self.driver.set_brightness(value)
                    redrawn = False
                    if self.state.snapshot()["display_enabled"]:
                        redrawn = self._redraw_last_frame_if_present()
                    self.state.update(
                        brightness=value,
                        last_action=f"brightness {value}" + (" applied" if redrawn else ""),
                    )
                elif cmd.kind == "transition_settings":
                    payload = cmd.payload or {}
                    if payload.get("enabled") is not None:
                        self.transition_enabled = bool(payload.get("enabled"))
                    if payload.get("effect") is not None:
                        self.transition_effect = normalize_transition_name(str(payload.get("effect")))
                    if payload.get("duration_ms") is not None:
                        self.transition_duration_ms = max(0, min(10000, int(payload.get("duration_ms") or 0)))
                    if payload.get("fps") is not None:
                        self.transition_fps = max(1, min(120, int(payload.get("fps") or 30)))
                    if payload.get("smoothing") is not None:
                        self.transition_smoothing = bool(payload.get("smoothing"))
                    if payload.get("smoothing_strength") is not None:
                        self.transition_smoothing_strength = max(0, min(100, int(payload.get("smoothing_strength") or 0)))
                    self.state.update(
                        transition_enabled=self.transition_enabled,
                        transition_effect=self.transition_effect,
                        transition_duration_ms=self.transition_duration_ms,
                        transition_fps=self.transition_fps,
                        transition_smoothing=self.transition_smoothing,
                        transition_smoothing_strength=self.transition_smoothing_strength,
                        last_action=f"transition {self.transition_effect} {'on' if self.transition_enabled else 'off'}, smoothing {'on' if self.transition_smoothing else 'off'}",
                    )
            except Exception:
                err = traceback.format_exc(limit=6)
                print(err)
                self.state.update(last_error=err, last_action="display worker error")
