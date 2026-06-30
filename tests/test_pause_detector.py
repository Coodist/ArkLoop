"""Tests for src/frame/pause_detector.py."""

import unittest

import numpy as np

from src.frame.pause_detector import PauseDetector, is_paused, mark_stuck_ticks_as_paused


class PauseDetectorTests(unittest.TestCase):
    def test_normal_frame_not_paused(self):
        # Uniform bright frame: no center/border contrast.
        frame = np.full((720, 1280, 3), 200, dtype=np.uint8)
        self.assertFalse(is_paused(frame))

    def test_dark_center_paused_fallback(self):
        # Simulate pause overlay: dark center ROI, bright surrounding border.
        frame = np.full((720, 1280, 3), 220, dtype=np.uint8)
        h, w = frame.shape[:2]
        # Match the current pause-detection ROI.
        cx1, cy1 = int(w * 0.25), int(h * 0.30)
        cx2, cy2 = int(w * 0.75), int(h * 0.70)
        frame[cy1:cy2, cx1:cx2] = 20
        self.assertTrue(is_paused(frame))

    def test_rolling_average_window(self):
        detector = PauseDetector(window_size=3)
        # Two pauses + one non-pause = majority paused.
        detector._history = [True, True]
        detector.update(np.full((720, 1280, 3), 200, dtype=np.uint8))
        self.assertTrue(detector.paused)


    def test_stuck_tick_heuristic(self):
        frames = [
            {"frame_id": i, "tick": i % 30, "paused": False}
            for i in range(40)
        ]
        # Inject a 12-frame stuck run at tick 5.
        for i in range(10, 22):
            frames[i]["tick"] = 5

        changed = mark_stuck_ticks_as_paused(frames, consecutive_threshold=10)
        self.assertEqual(changed, 12)
        for i in range(10, 22):
            self.assertTrue(frames[i]["paused"])
        # Normal frames should remain unpaused.
        self.assertFalse(frames[0]["paused"])
        self.assertFalse(frames[25]["paused"])

    def test_stuck_tick_heuristic_ignores_short_runs(self):
        frames = [
            {"frame_id": i, "tick": 0 if 5 <= i < 8 else i, "paused": False}
            for i in range(10)
        ]
        changed = mark_stuck_ticks_as_paused(frames, consecutive_threshold=10)
        self.assertEqual(changed, 0)


if __name__ == "__main__":
    unittest.main()
