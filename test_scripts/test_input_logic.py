"""Offline unit tests for the input recording modules.

These tests do NOT install a global mouse hook or move the cursor. They
exercise coordinate mapping and action aggregation with mocked window data.

Usage:
    .venv\Scripts\python scripts/test_input_logic.py
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import win32gui

from src.input.coordinate_mapper import CoordinateMapper, MappedCoordinates
from src.input.mouse_listener import MouseEvent, MouseListener
from src.input.action_recorder import ActionRecorder


class FakeWin32:
    """Patch win32gui functions used by CoordinateMapper."""

    def __init__(self, client_left, client_top, client_width, client_height):
        self.client_left = client_left
        self.client_top = client_top
        self.client_width = client_width
        self.client_height = client_height
        self._orig = {}

    def is_window(self, hwnd):
        return hwnd == 12345

    def get_client_rect(self, hwnd):
        return (0, 0, self.client_width, self.client_height)

    def client_to_screen(self, hwnd, point):
        return (point[0] + self.client_left, point[1] + self.client_top)

    def patch(self):
        self._orig["IsWindow"] = win32gui.IsWindow
        self._orig["GetClientRect"] = win32gui.GetClientRect
        self._orig["ClientToScreen"] = win32gui.ClientToScreen
        win32gui.IsWindow = self.is_window
        win32gui.GetClientRect = self.get_client_rect
        win32gui.ClientToScreen = self.client_to_screen

    def unpatch(self):
        win32gui.IsWindow = self._orig["IsWindow"]
        win32gui.GetClientRect = self._orig["GetClientRect"]
        win32gui.ClientToScreen = self._orig["ClientToScreen"]


class TestCoordinateMapper(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWin32(client_left=100, client_top=80, client_width=1920, client_height=1080)
        self.fake.patch()
        self.mapper = CoordinateMapper(hwnd=12345)

    def tearDown(self):
        self.fake.unpatch()

    def test_center_point(self):
        # Client center is (100 + 960, 80 + 540) = (1060, 620)
        mapped = self.mapper.map_point(1060, 620)
        self.assertTrue(mapped.valid)
        self.assertAlmostEqual(mapped.ratio_x, 0.5)
        self.assertAlmostEqual(mapped.ratio_y, 0.5)
        self.assertAlmostEqual(mapped.game_x, 640.0)
        self.assertAlmostEqual(mapped.game_y, 360.0)

    def test_outside_client_is_clamped(self):
        mapped = self.mapper.map_point(50, 50)
        self.assertFalse(mapped.valid)
        self.assertAlmostEqual(mapped.ratio_x, 0.0)
        self.assertAlmostEqual(mapped.ratio_y, 0.0)


class TestActionRecorder(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWin32(client_left=0, client_top=0, client_width=1280, client_height=720)
        self.fake.patch()

    def tearDown(self):
        self.fake.unpatch()

    def _make_events(self):
        start_ts = time.perf_counter()
        return [
            MouseEvent(type="mousedown", x=100, y=100, button="left", pressed=True, ts=0.1),
            MouseEvent(type="mouseup", x=105, y=105, button="left", pressed=False, ts=0.2),
            MouseEvent(type="mousedown", x=200, y=200, button="left", pressed=True, ts=0.5),
            MouseEvent(type="mouseup", x=600, y=400, button="left", pressed=False, ts=0.7),
        ], start_ts

    def test_click_and_drag_aggregation(self):
        events, start_ts = self._make_events()
        mapper = CoordinateMapper(hwnd=12345)
        recorder = ActionRecorder(mapper=mapper, start_ts=start_ts)
        data = recorder.export(raw_events=events, duration=1.0)

        self.assertEqual(data["event_count"], 4)
        self.assertEqual(data["action_count"], 2)

        click, drag = data["actions"]
        self.assertEqual(click["type"], "click")
        self.assertEqual(drag["type"], "drag")
        self.assertEqual(click["button"], "left")
        self.assertAlmostEqual(click["start_ratio"]["x"], 100 / 1280)
        self.assertAlmostEqual(drag["start_ratio"]["x"], 200 / 1280)
        self.assertAlmostEqual(drag["end_ratio"]["x"], 600 / 1280)


if __name__ == "__main__":
    unittest.main()
