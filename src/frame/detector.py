import threading
import time
from queue import Empty, Queue
from typing import Callable, Dict, Any, Optional, Tuple

import numpy as np
from PIL import Image

from src.config import ImageProcessingConfig as imgconfig
from src.frame.calibration import (
    find_calibration,
    find_cost_bar_roi,
    get_tick_from_calibration,
)
from src.logger import logger

__all__ = ["CostBarDetector", "AnalysisWorker"]


class CostBarDetector:
    """
    Detect the current cost bar tick from a game frame or live capture.

    Uses calibration data produced by `src.frame.calibration.calibrate`.
    If no calibration is loaded, detection returns None and callers should
    fall back to the legacy white-pixel method.
    """

    def __init__(self, calibration_data: Optional[dict] = None):
        self.calibration_data = calibration_data
        self._resolution: Optional[Tuple[int, int]] = None
        self._roi: Optional[Tuple[int, int, int]] = None
        if calibration_data is not None:
            width = calibration_data.get("screen_width")
            height = calibration_data.get("screen_height")
            if width and height:
                self._resolution = (int(width), int(height))
                self._roi = find_cost_bar_roi(self._resolution[0], self._resolution[1])

    @classmethod
    def from_resolution(cls, width: int, height: int) -> "CostBarDetector":
        """Create a detector by loading the newest calibration for a resolution."""
        data = find_calibration(width, height)
        return cls(data)

    def is_ready(self) -> bool:
        return self.calibration_data is not None and self._roi is not None

    def detect_tick(self, frame: Image.Image) -> Optional[int]:
        """
        Detect tick from a PIL Image captured at the calibration resolution.

        The image must be in RGB/RGBA format.
        """
        if not self.is_ready():
            return None
        return get_tick_from_calibration(frame, self._roi, self.calibration_data)

    def detect_tick_from_game(self) -> Optional[int]:
        """Capture the full game window and detect the current tick."""
        if not self.is_ready():
            return None
        # Lazy import so that merely importing this module does not trigger
        # the MuMu window search performed by src.mumu.mumu_connection.
        from src.mumu.mumu_vision import capture_game_window
        gray = capture_game_window(ratio=None)
        if gray is None:
            return None
        rgb = Image.fromarray(gray).convert("RGB")
        return self.detect_tick(rgb)



class AnalysisWorker:
    """
    Consume frames from a ``FrameSource`` queue, detect the cost bar tick, and
    publish state updates to a UI queue.

    The worker maintains ``cycle_counter`` and ``total_elapsed_frames`` so that
    downstream components can reason about real game time even when the tick
    cycles repeatedly.
    """

    def __init__(
        self,
        frame_queue: Queue,
        ui_queue: Optional[Queue] = None,
        detector: Optional[CostBarDetector] = None,
        fps: float = 30.0,
        on_tick: Optional[Callable[[int, int, int], None]] = None,
    ):
        self.frame_queue = frame_queue
        self.ui_queue = ui_queue
        self.detector = detector
        self.fps = fps
        self.on_tick = on_tick

        self.cycle_counter: int = 0
        self.total_elapsed_frames: int = 0
        self.current_tick: Optional[int] = None
        self.last_tick: Optional[int] = None
        self.paused: bool = False

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _get_tick_max(self) -> int:
        if self.detector is not None and self.detector.calibration_data is not None:
            profiles = self.detector.calibration_data.get("profiles", [])
            if profiles:
                return profiles[0].get("total_frames", 1)
        return 1

    def _push_update(self) -> None:
        """Push a ruler-compatible update message to the UI queue."""
        if self.ui_queue is None:
            return

        tick = self.current_tick
        total = self.total_elapsed_frames
        tick_max = self._get_tick_max()

        # Format time as HH:MM:SS from total frames.
        seconds = total / self.fps if self.fps > 0 else 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        time_str = f"{hours:02d}:{minutes:02d}:{secs:02d}"

        display_frame = str(tick) if tick is not None else "--"
        display_total = f"/{tick_max}"

        try:
            if self.ui_queue.full():
                self.ui_queue.get_nowait()
            self.ui_queue.put_nowait({
                "type": "update",
                "display_frame": display_frame,
                "display_total": display_total,
                "time_str": time_str,
                "lap_frames": None,
                "totalFramesInCycle": tick_max,
            })
        except Exception:
            logger.exception("Failed to push update to UI queue")

    def _push_state_change(self, state: str) -> None:
        """Push a state change message to the UI queue."""
        if self.ui_queue is None:
            return

        tick_max = self._get_tick_max()
        active_profile = "default" if self.detector is not None and self.detector.is_ready() else ""

        try:
            if self.ui_queue.full():
                self.ui_queue.get_nowait()
            self.ui_queue.put_nowait({
                "type": "state_change",
                "state": state,
                "display_total": f"/{tick_max}",
                "active_profile": active_profile,
                "display_mode": "0_to_n-1",
            })
        except Exception:
            logger.exception("Failed to push state change to UI queue")

    def _update_state(self, tick: Optional[int]) -> None:
        """Update cycle/total frame counters based on the latest tick."""
        previous_paused = self.paused

        if tick is None:
            self.paused = True
            self.last_tick = None
        else:
            self.paused = False
            self.last_tick = self.current_tick
            self.current_tick = tick

            if self.last_tick is not None:
                tick_max = self._get_tick_max()
                high_threshold = tick_max * 0.75
                low_threshold = tick_max * 0.25
                if self.last_tick > high_threshold and tick < low_threshold:
                    self.cycle_counter += 1

            ticks_per_cycle = self._get_tick_max()
            self.total_elapsed_frames = self.cycle_counter * ticks_per_cycle + tick

        if self.on_tick is not None and tick is not None:
            try:
                self.on_tick(tick, self.cycle_counter, self.total_elapsed_frames)
            except Exception:
                logger.exception("AnalysisWorker on_tick callback failed")

        # Push state change on first valid tick or pause/resume transitions.
        if not previous_paused and self.paused:
            self._push_state_change("idle")
        elif previous_paused and not self.paused:
            self._push_state_change("running")
        elif self.current_tick is not None and self.last_tick is None:
            self._push_state_change("running")

        self._push_update()

    def snapshot(self) -> dict:
        """Return the current tick/cycle state without modifying it."""
        return {
            "tick": self.current_tick,
            "cycle": self.cycle_counter,
            "total_elapsed_frames": self.total_elapsed_frames,
            "paused": self.paused,
        }

    def _analysis_loop(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=0.1)
            except Empty:
                continue

            if frame is None:
                continue

            tick: Optional[int] = None
            if self.detector is not None and self.detector.is_ready():
                try:
                    pil_img = Image.fromarray(frame).convert("RGB")
                    tick = self.detector.detect_tick(pil_img)
                except Exception as e:
                    logger.warning(f"Tick detection failed: {e}")
            else:
                logger.debug("AnalysisWorker has no calibrated detector; skipping tick detection.")

            self._update_state(tick)
            self._stop_event.wait(interval)

    def start(self) -> "AnalysisWorker":
        """Start the analysis thread."""
        if self.is_running:
            raise RuntimeError("AnalysisWorker already started")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self._thread.start()
        logger.info("AnalysisWorker started")
        return self

    def stop(self) -> None:
        """Stop the analysis thread."""
        if not self.is_running:
            return

        self._stop_event.set()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            logger.warning("AnalysisWorker thread did not stop within 2 seconds")
        self._thread = None
        logger.info("AnalysisWorker stopped")

    def __enter__(self) -> "AnalysisWorker":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
