"""Tests for recorder/action_worker.py."""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from recorder.action_worker import ActionItem, ActionWorker


class ActionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.map_data = {
            "levelId": "main_01-07",
            "code": "1-7",
            "name": "",
            "height": 7,
            "width": 11,
            "tiles": [[{"buildableType": 1, "heightType": 0} for _ in range(11)] for _ in range(7)],
            "view": [[0.0, -4.81, -7.76], [0.0, -4.81, -7.76]],
        }
        self.dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    def _make_click(self, x, y):
        return {
            "type": "click",
            "start_ts": 1.0,
            "start_ratio": {"x": x, "y": y},
            "start_game": {"x": x * 1280, "y": y * 720},
            "end_ratio": {"x": x, "y": y},
            "end_game": {"x": x * 1280, "y": y * 720},
        }

    def test_worker_processes_click_and_updates_view(self):
        view_calls = []

        def _fake_view_detector(frame):
            view_calls.append(frame)
            return False

        matcher = MagicMock()
        events = []

        def _event_callback(event_type, **kwargs):
            events.append((event_type, kwargs))

        worker = ActionWorker(
            map_data=self.map_data,
            avatar_matcher=matcher,
            view_detector=_fake_view_detector,
            event_callback=_event_callback,
            use_slot_layout=False,
        ).start()

        try:
            worker.enqueue(
                ActionItem(action=self._make_click(0.5, 0.5), frame=self.dummy_frame)
            )
            deadline = time.time() + 2.0
            while len(events) == 0 and time.time() < deadline:
                time.sleep(0.05)
        finally:
            worker.stop()

        self.assertEqual(len(view_calls), 1)
        # The worker emits a view_change event because the detector returns
        # False while the recognizer starts in side view.
        self.assertTrue(any(ev[0] == "view_change" for ev in events))


if __name__ == "__main__":
    unittest.main()
