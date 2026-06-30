"""Main application entry point for real-time overlay and frame analysis."""

import os
import sys
import threading
import queue
from queue import Queue
from typing import Optional

from PIL import Image

from src.config import ImageProcessingConfig as imgconfig, RecordingConfig as recconfig
from src.frame.calibration import calibrate, save_calibration_data
from src.frame.detector import AnalysisWorker, CostBarDetector
from src.frame.frame_source import FrameSource
from src.logger import logger
from src.logic.game_time import GameTime
from src.mumu.mumu_vision import capture_game_window
from src.ui.overlay import OverlayWindow

__all__ = ["run_overlay_app"]


class OverlayApp:
    """
    Wire together frame capture, tick analysis, and the overlay UI.

    Usage:
        app = OverlayApp()
        app.run()
    """

    def __init__(
        self,
        fps: float = recconfig.FPS,
        detector: Optional[CostBarDetector] = None,
    ):
        self.fps = fps
        self.detector = detector

        self.frame_queue: Queue = Queue(maxsize=1)
        self.ui_queue: Queue = Queue(maxsize=1)

        self.frame_source = FrameSource(fps=fps, frame_queue=self.frame_queue)
        self.worker = AnalysisWorker(
            frame_queue=self.frame_queue,
            ui_queue=self.ui_queue,
            detector=self.detector,
            fps=fps,
        )
        # OverlayWindow creates its own root window; no hidden parent needed.
        self.overlay = OverlayWindow(
            ui_queue=self.ui_queue,
            master_callback=self._on_overlay_message,
        )

        self._running = False
        self._calibrating = False
        self._timer_offset_frames: int = 0

    def _on_overlay_message(self, msg: dict) -> None:
        """Handle messages sent from the overlay context menu."""
        msg_type = msg.get("type")
        logger.debug(f"Overlay message: {msg}")

        if msg_type == "prepare_calibration":
            self.ui_queue.put({
                "type": "state_change",
                "state": "pre_calibration",
                "display_total": "",
                "active_profile": "",
                "display_mode": "0_to_n-1",
            })
        elif msg_type == "start_calibration":
            self._start_calibration()
        elif msg_type == "set_display_mode":
            # Display mode changes are cosmetic only for now.
            self.ui_queue.put({
                "type": "state_change",
                "state": "running" if self.worker.detector is not None and self.worker.detector.is_ready() else "idle",
                "display_total": f"/{self.worker._get_tick_max()}",
                "active_profile": "default" if self.worker.detector is not None and self.worker.detector.is_ready() else "",
                "display_mode": msg.get("mode", "0_to_n-1"),
            })
        elif msg_type == "adjust_timer":
            self._timer_offset_frames += msg.get("frames", 0)
        elif msg_type == "reset_timer":
            self._timer_offset_frames = -self.worker.total_elapsed_frames
        elif msg_type == "toggle_lap_timer":
            logger.info("Lap timer toggle requested (not implemented)")

    def _start_calibration(self) -> None:
        """Run cost bar calibration in a background thread."""
        if self._calibrating:
            return
        self._calibrating = True

        def calibrate_thread():
            try:
                self.ui_queue.put({"type": "state_change", "state": "calibrating"})

                def capture_func():
                    gray = capture_game_window(ratio=None)
                    return Image.fromarray(gray).convert("RGB")

                std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE

                def progress_cb(percent: float):
                    self.ui_queue.put({
                        "type": "calibration_progress",
                        "progress": percent,
                    })

                data = calibrate(capture_func, std_w, std_h, num_cycles=6, progress_callback=progress_cb)
                save_calibration_data(data, std_w, std_h, basename="default")
                GameTime.apply_calibration(data)

                # Reload detector after calibration.
                self.worker.detector = CostBarDetector.from_resolution(std_w, std_h)
                logger.info(f"Calibration finished. TICK_MAX = {GameTime.get_tick_max()}")

                self.ui_queue.put({
                    "type": "state_change",
                    "state": "running",
                    "display_total": f"/{GameTime.get_tick_max()}",
                    "active_profile": "default",
                    "display_mode": "0_to_n-1",
                })
            except Exception as e:
                logger.exception(f"Calibration failed: {e}")
                self.ui_queue.put({
                    "type": "state_change",
                    "state": "idle",
                    "display_total": "",
                    "active_profile": "",
                    "display_mode": "0_to_n-1",
                })
            finally:
                self._calibrating = False

        threading.Thread(target=calibrate_thread, daemon=True).start()

    def _ensure_detector(self) -> None:
        """Load a detector if none is ready."""
        if self.worker.detector is not None and self.worker.detector.is_ready():
            return

        std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE
        try:
            self.worker.detector = CostBarDetector.from_resolution(std_w, std_h)
            if self.worker.detector.is_ready():
                logger.info(f"Loaded calibration for {std_w}x{std_h}")
                GameTime.apply_calibration(self.worker.detector.calibration_data)
            else:
                logger.warning(
                    f"No calibration found for {std_w}x{std_h}. "
                    "Right-click the overlay and choose Calibrate."
                )
        except Exception as e:
            logger.warning(f"Failed to load calibration: {e}")

    def run(self) -> None:
        """Start capture, analysis, and the overlay UI."""
        self._running = True
        self._ensure_detector()

        self.frame_source.start()
        self.worker.start()

        # Make sure initial messages don't get stuck behind worker updates.
        while not self.ui_queue.empty():
            try:
                self.ui_queue.get_nowait()
            except queue.Empty:
                break

        if self.worker.detector is not None and self.worker.detector.is_ready():
            self.overlay.set_initial_state(
                state="running",
                display_total=f"/{self.worker._get_tick_max()}",
                active_profile="default",
                display_mode="0_to_n-1",
            )
        else:
            self.overlay.set_initial_state(
                state="idle",
                display_total="",
                active_profile="",
                display_mode="0_to_n-1",
            )

        try:
            self.overlay.run()
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop all threads and close the overlay."""
        self._running = False
        self.overlay._quit_application()
        self.worker.stop()
        self.frame_source.stop()
        logger.info("OverlayApp stopped")


def run_overlay_app() -> None:
    """Convenience entry point used by scripts."""
    app = OverlayApp()
    app.run()


if __name__ == "__main__":
    run_overlay_app()
