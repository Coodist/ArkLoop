"""Unit tests for the analysis worker state machine."""

import os
import sys
import time
import unittest
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from src.frame.detector import AnalysisWorker, CostBarDetector
from src.frame.frame_source import FrameSource


class DummyDetector:
    """Detector stub that returns a configurable tick value."""

    def __init__(self, tick_value=None):
        self.tick_value = tick_value
        self.calibration_data = {"profiles": [{"total_frames": 30}]}

    def is_ready(self):
        return True

    def detect_tick(self, frame):
        return self.tick_value


class TestAnalysisWorker(unittest.TestCase):
    def test_worker_starts_and_stops(self):
        frame_queue = Queue()
        worker = AnalysisWorker(frame_queue=frame_queue, detector=DummyDetector(0))
        worker.start()
        self.assertTrue(worker.is_running)
        worker.stop()
        self.assertFalse(worker.is_running)

    def _get_update(self, ui_queue, timeout=0.5):
        """Pull the next 'update' message, discarding state_change noise."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = ui_queue.get(timeout=0.05)
            except Exception:
                continue
            if msg.get("type") == "update":
                return msg
        raise TimeoutError("No update message received")

    def test_cycle_counter_increments_on_wrap(self):
        frame_queue = Queue()
        ui_queue = Queue()
        detector = DummyDetector(0)
        worker = AnalysisWorker(
            frame_queue=frame_queue,
            ui_queue=ui_queue,
            detector=detector,
            fps=1000,
        )
        worker.start()
        try:
            # First frame at tick 5
            detector.tick_value = 5
            frame_queue.put(np.zeros((10, 10, 3), dtype=np.uint8))
            msg = self._get_update(ui_queue)
            self.assertEqual(msg["display_frame"], "5")
            self.assertEqual(msg["display_total"], "/30")

            # Next frame at tick 28 (same cycle)
            detector.tick_value = 28
            frame_queue.put(np.zeros((10, 10, 3), dtype=np.uint8))
            msg = self._get_update(ui_queue)
            self.assertEqual(msg["display_frame"], "28")

            # Wrap to tick 3 (new cycle)
            detector.tick_value = 3
            frame_queue.put(np.zeros((10, 10, 3), dtype=np.uint8))
            msg = self._get_update(ui_queue)
            self.assertEqual(msg["display_frame"], "3")

            # total_elapsed_frames should be 1 * 30 + 3 = 33
            self.assertEqual(worker.total_elapsed_frames, 33)
        finally:
            worker.stop()

    def test_paused_state_when_no_tick(self):
        frame_queue = Queue()
        ui_queue = Queue()
        worker = AnalysisWorker(
            frame_queue=frame_queue,
            ui_queue=ui_queue,
            detector=DummyDetector(None),
        )
        worker.start()
        try:
            frame_queue.put(np.zeros((10, 10, 3), dtype=np.uint8))
            time.sleep(0.02)
            self.assertTrue(worker.paused)
            self.assertIsNone(worker.current_tick)
        finally:
            worker.stop()


if __name__ == "__main__":
    unittest.main()
