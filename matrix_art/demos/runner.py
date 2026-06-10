from __future__ import annotations

import inspect
import multiprocessing as mp
import queue
import threading
import time
import traceback
from dataclasses import dataclass, replace
from typing import Any

from PIL import Image

from .api import EffectContext, FrameBuffer
from ..display.worker import DisplayWorker
from ..state import AppState


@dataclass(slots=True)
class DemoRunInfo:
    running: bool = False
    demo_id: int | None = None
    title: str = "None"
    fps: int = 0
    frames_rendered: int = 0
    last_error: str = ""
    started_at: float = 0.0
    updated_at: float = 0.0


def _default_params(namespace: dict[str, Any]) -> dict[str, Any]:
    param_defs = namespace.get("PARAMS") or {}
    params: dict[str, Any] = {}
    if isinstance(param_defs, dict):
        for name, spec in param_defs.items():
            if isinstance(spec, dict) and "default" in spec:
                params[str(name)] = spec.get("default")
            else:
                params[str(name)] = spec
    return params


def _render_argc(render_func) -> int:
    try:
        return len(inspect.signature(render_func).parameters)
    except Exception:
        return 6


def _call_render(render_func, argc: int, ctx: EffectContext, t: float, dt: float, frame: FrameBuffer, params: dict[str, Any], state: dict[str, Any]) -> None:
    # Let learning examples stay simple while supporting persistent state.
    if argc <= 5:
        render_func(ctx, t, dt, frame, params)
    else:
        render_func(ctx, t, dt, frame, params, state)


def _demo_process_main(
    code: str,
    title: str,
    width: int,
    height: int,
    fps: int,
    output_queue,
    stop_event,
) -> None:
    try:
        namespace: dict[str, Any] = {
            "__name__": "matrix_art_user_code",
            "__file__": f"<matrix-art-code:{title}>",
        }
        compiled = compile(code, f"<matrix-art-code:{title}>", "exec")
        exec(compiled, namespace)
        render_func = namespace.get("render")
        if not callable(render_func):
            raise RuntimeError("demo must define render(ctx, t, dt, frame, params)")

        params = _default_params(namespace)
        render_argc = _render_argc(render_func)
        ctx = EffectContext(width=width, height=height, fps=fps)
        state: dict[str, Any] = {}
        setup_func = namespace.get("setup")
        if callable(setup_func):
            result = setup_func(ctx)
            if isinstance(result, dict):
                state.update(result)

        target_dt = 1.0 / max(1, int(fps))
        start = time.monotonic()
        last = start
        frame_index = 0
        while not stop_event.is_set():
            now = time.monotonic()
            t = now - start
            dt = min(0.25, max(0.0, now - last))
            last = now
            ctx.frame_index = frame_index
            ctx.time = t
            ctx.dt = dt
            frame = FrameBuffer(width, height)
            _call_render(render_func, render_argc, ctx, t, dt if dt > 0 else target_dt, frame, params, state)
            raw = frame.tobytes()
            try:
                output_queue.put_nowait(("frame", raw, frame_index))
            except queue.Full:
                try:
                    output_queue.get_nowait()
                except Exception:
                    pass
                try:
                    output_queue.put_nowait(("frame", raw, frame_index))
                except Exception:
                    pass
            frame_index += 1
            elapsed = time.monotonic() - now
            remaining = target_dt - elapsed
            if remaining > 0:
                stop_event.wait(remaining)
    except Exception:
        err = traceback.format_exc(limit=12)
        try:
            output_queue.put(("error", err, 0), timeout=0.5)
        except Exception:
            pass



def render_demo_thumbnail(
    *,
    code: str,
    title: str,
    width: int,
    height: int,
    fps: int = 24,
    frame_number: int = 10,
    timeout: float = 3.0,
) -> Image.Image:
    """Render a single preview frame from a Python code effect.

    The preview is generated in a child process using the same runner path as
    live playback. ``frame_number`` is 1-based, so frame 10 means index 9.
    """
    fps = max(1, min(1000, int(fps or 24)))
    target_index = max(0, int(frame_number or 10) - 1)
    ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else mp.get_context()
    output_queue = ctx.Queue(maxsize=4)
    stop_event = ctx.Event()
    process = ctx.Process(
        target=_demo_process_main,
        args=(code, title, int(width), int(height), fps, output_queue, stop_event),
        name="matrix-art-code-thumbnail",
        daemon=True,
    )
    process.start()
    best_raw: bytes | None = None
    best_index = -1
    deadline = time.time() + max(0.5, float(timeout or 3.0))
    try:
        while time.time() < deadline:
            remaining = max(0.05, min(0.25, deadline - time.time()))
            try:
                msg = output_queue.get(timeout=remaining)
            except queue.Empty:
                if not process.is_alive():
                    break
                continue
            kind = msg[0]
            if kind == "stop":
                break
            if kind == "frame":
                raw = bytes(msg[1])
                index = int(msg[2])
                best_raw = raw
                best_index = index
                if index >= target_index:
                    break
            elif kind == "error":
                raise RuntimeError(str(msg[1]).splitlines()[-1] if msg[1] else "code preview failed")
        if best_raw is None:
            raise RuntimeError("code preview produced no frames")
        return Image.frombytes("RGB", (int(width), int(height)), best_raw)
    finally:
        try:
            stop_event.set()
        except Exception:
            pass
        process.join(timeout=0.5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.5)
        if process.is_alive():
            try:
                process.kill()
            except Exception:
                pass


class DemoRunner:
    """Runs Python visual effects in a separate process and feeds frames to the display worker."""

    def __init__(
        self,
        display: DisplayWorker,
        state: AppState,
        *,
        width: int,
        height: int,
        default_fps: int = 24,
        max_fps: int = 1000,
        queue_size: int = 3,
    ):
        self.display = display
        self.state = state
        self.width = int(width)
        self.height = int(height)
        self.default_fps = max(1, int(default_fps or 24))
        self.max_fps = max(0, int(max_fps or 1000))
        self.queue_size = max(1, int(queue_size or 3))
        self.lock = threading.RLock()
        self.ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else mp.get_context()
        self.process = None
        self.stop_event = None
        self.output_queue = None
        self.pump_thread: threading.Thread | None = None
        self.info = DemoRunInfo(updated_at=time.time())

    def start_demo(self, *, demo_id: int, title: str, code: str, fps: int | None = None, artwork_id: int | None = None, kind: str = "code") -> DemoRunInfo:
        self.stop()
        fps = max(1, int(fps or self.default_fps))
        if self.max_fps > 0:
            fps = min(self.max_fps, fps)
        fps = min(1000, fps)
        output_queue = self.ctx.Queue(maxsize=self.queue_size)
        stop_event = self.ctx.Event()
        process = self.ctx.Process(
            target=_demo_process_main,
            args=(code, title, self.width, self.height, fps, output_queue, stop_event),
            name=f"matrix-art-code-{demo_id}",
            daemon=True,
        )
        now = time.time()
        with self.lock:
            self.output_queue = output_queue
            self.stop_event = stop_event
            self.process = process
            self.info = DemoRunInfo(True, int(demo_id), title, fps, 0, "", now, now)
            self.state.update(
                demo_running=True,
                demo_id=int(demo_id),
                demo_title=title,
                current_artwork_id=artwork_id,
                current_title=title,
                current_kind=kind,
                last_error="",
                last_action=f"starting demo {title}",
                frame_changed=True,
            )
        process.start()
        thread = threading.Thread(target=self._pump_frames, name="matrix-art-code-pump", daemon=True)
        with self.lock:
            self.pump_thread = thread
        thread.start()
        return self.snapshot()

    def stop(self, timeout: float = 1.0) -> DemoRunInfo:
        with self.lock:
            process = self.process
            stop_event = self.stop_event
            output_queue = self.output_queue
            pump_thread = self.pump_thread
            was_running = bool(self.info.running)
            title = self.info.title
        if stop_event is not None:
            try:
                stop_event.set()
            except Exception:
                pass
        if process is not None:
            process.join(timeout=timeout)
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.5)
                if process.is_alive():
                    try:
                        process.kill()
                    except Exception:
                        pass
                    process.join(timeout=0.5)
        # Nudge the pump thread out of queue.get() and let it exit before the service dies.
        if output_queue is not None:
            try:
                output_queue.put_nowait(("stop", "", 0))
            except Exception:
                pass
        if pump_thread is not None and pump_thread is not threading.current_thread():
            pump_thread.join(timeout=0.75)
        if output_queue is not None:
            try:
                output_queue.close()
            except Exception:
                pass
            try:
                output_queue.join_thread()
            except Exception:
                pass
        with self.lock:
            self.process = None
            self.stop_event = None
            self.output_queue = None
            self.pump_thread = None
            self.info.running = False
            self.info.updated_at = time.time()
            snap = replace(self.info)
        if was_running:
            self.state.update(
                demo_running=False,
                demo_id=None,
                demo_title="None",
                last_action=f"stopped code {title}",
            )
        return snap

    def snapshot(self) -> DemoRunInfo:
        with self.lock:
            return replace(self.info)

    def _pump_frames(self) -> None:
        while True:
            with self.lock:
                output_queue = self.output_queue
                process = self.process
                stop_event = self.stop_event
                title = self.info.title
            if output_queue is None:
                break
            try:
                msg = output_queue.get(timeout=0.25)
            except queue.Empty:
                if process is not None and not process.is_alive():
                    break
                if stop_event is not None and stop_event.is_set():
                    break
                continue
            except Exception:
                break
            kind = msg[0]
            if kind == "stop":
                break
            if kind == "frame":
                raw = msg[1]
                frame_index = int(msg[2])
                try:
                    image = Image.frombytes("RGB", (self.width, self.height), raw)
                    self.display.preview_image(image, title=title, kind="code")
                    with self.lock:
                        self.info.frames_rendered = frame_index + 1
                        self.info.updated_at = time.time()
                except Exception:
                    err = traceback.format_exc(limit=6)
                    with self.lock:
                        self.info.last_error = err
                        self.info.updated_at = time.time()
                    self.state.update(last_error=err, last_action="demo frame error")
            elif kind == "error":
                err = str(msg[1])
                with self.lock:
                    self.info.last_error = err
                    self.info.running = False
                    self.info.updated_at = time.time()
                self.state.update(demo_running=False, last_error=err, last_action="demo error")
                break
        with self.lock:
            process = self.process
            still_current = self.info.running
        if still_current and process is not None and not process.is_alive():
            with self.lock:
                self.info.running = False
                self.info.updated_at = time.time()
            self.state.update(demo_running=False, last_action=f"code {title} stopped")
