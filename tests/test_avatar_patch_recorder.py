"""Tests for recorder/avatar_patch_recorder.py."""

import os
import sys
import tempfile
import unittest
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from recorder.avatar_patch_recorder import AvatarPatchRecorder, make_patch_callback


class MockMouseEvent:
    def __init__(self, ev_type, ts, button=None, ratio=None, x=0, y=0):
        self.type = ev_type
        self.ts = ts
        self.button = button
        self.ratio = ratio
        self.x = x
        self.y = y


class MockMapper:
    """Maps screen pixels to the same normalized ratio, independent of window."""

    def map_point(self, screen_x, screen_y, clamp=True):
        # Pretend the client area is 1280x720 and maps 1:1 to screen pixels.
        ratio_x = max(0.0, min(1.0, screen_x / 1280.0)) if clamp else screen_x / 1280.0
        ratio_y = max(0.0, min(1.0, screen_y / 720.0)) if clamp else screen_y / 720.0
        return MockMapped(screen_x, screen_y, ratio_x, ratio_y)


@dataclass
class MockMapped:
    screen_x: int
    screen_y: int
    ratio_x: float
    ratio_y: float


def _gray_frame(h: int = 720, w: int = 1280) -> np.ndarray:
    return np.full((h, w), 128, dtype=np.uint8)


class AvatarPatchRecorderTests(unittest.TestCase):
    def test_saves_patch_when_cursor_leaves_operator_area(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AvatarPatchRecorder(output_dir=tmpdir, max_recent_frames=10)

            # Start a drag inside the operator area.
            recorder.on_mouse_event(
                MockMouseEvent("mousedown", 0.1, button="left", ratio={"x": 0.5, "y": 0.85})
            )

            # Push a few frames into the ring buffer.
            for i in range(5):
                recorder.on_frame(_gray_frame(), 0.05 + i * 0.033, i)

            # Cursor leaves operator area.
            recorder.on_mouse_event(
                MockMouseEvent("mousemove", 0.25, ratio={"x": 0.5, "y": 0.70})
            )

            # Mouse up.
            recorder.on_mouse_event(MockMouseEvent("mouseup", 0.30, ratio={"x": 0.5, "y": 0.60}))

            patch_map = recorder.flush()
            self.assertEqual(len(patch_map), 1)
            patch_path = list(patch_map.values())[0]
            self.assertTrue(os.path.isfile(patch_path))

    def test_no_patch_for_short_click(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AvatarPatchRecorder(output_dir=tmpdir, max_recent_frames=10)

            # Click inside operator area, no leave.
            recorder.on_mouse_event(
                MockMouseEvent("mousedown", 0.1, button="left", ratio={"x": 0.5, "y": 0.85})
            )
            recorder.on_frame(_gray_frame(), 0.12, 0)
            recorder.on_mouse_event(
                MockMouseEvent("mouseup", 0.15, ratio={"x": 0.51, "y": 0.85})
            )

            patch_map = recorder.flush()
            self.assertEqual(len(patch_map), 0)

    def test_no_patch_for_right_click(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AvatarPatchRecorder(output_dir=tmpdir, max_recent_frames=10)

            recorder.on_mouse_event(
                MockMouseEvent("mousedown", 0.1, button="right", ratio={"x": 0.5, "y": 0.85})
            )
            recorder.on_frame(_gray_frame(), 0.12, 0)
            recorder.on_mouse_event(
                MockMouseEvent("mouseup", 0.15, ratio={"x": 0.5, "y": 0.60})
            )

            patch_map = recorder.flush()
            self.assertEqual(len(patch_map), 0)

    def test_flush_forces_unsaved_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AvatarPatchRecorder(output_dir=tmpdir, max_recent_frames=10)

            recorder.on_mouse_event(
                MockMouseEvent("mousedown", 0.1, button="left", ratio={"x": 0.5, "y": 0.85})
            )
            for i in range(5):
                recorder.on_frame(_gray_frame(), 0.05 + i * 0.033, i)
            # Mouse up without ever leaving the operator area.
            recorder.on_mouse_event(
                MockMouseEvent("mouseup", 0.30, ratio={"x": 0.52, "y": 0.82})
            )

            # flush(force) should still save the patch.
            patch_map = recorder.flush()
            self.assertEqual(len(patch_map), 1)

    def test_no_patch_for_drag_starting_on_map(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AvatarPatchRecorder(output_dir=tmpdir, max_recent_frames=10)

            # Start a drag in the map area (camera pan / direction selection).
            recorder.on_mouse_event(
                MockMouseEvent("mousedown", 0.1, button="left", ratio={"x": 0.5, "y": 0.60})
            )
            for i in range(5):
                recorder.on_frame(_gray_frame(), 0.05 + i * 0.033, i)
            recorder.on_mouse_event(
                MockMouseEvent("mousemove", 0.25, ratio={"x": 0.5, "y": 0.40})
            )
            recorder.on_mouse_event(
                MockMouseEvent("mouseup", 0.30, ratio={"x": 0.5, "y": 0.40})
            )

            patch_map = recorder.flush()
            self.assertEqual(len(patch_map), 0)

    def test_make_patch_callback_triggers_png_from_real_mouse_event(self):
        """
        Simulate the exact flow used by record_actions.py:
        raw MouseEvent (screen pixels) -> make_patch_callback -> AvatarPatchRecorder.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = AvatarPatchRecorder(output_dir=tmpdir, max_recent_frames=10)
            mapper = MockMapper()
            callback = make_patch_callback(mapper, recorder)

            # Start drag in the operator area (bottom-center of a 1280x720 screen).
            callback(MockMouseEvent('mousedown', 0.1, button='left', x=640, y=650))

            # Push a few frames.
            for i in range(5):
                recorder.on_frame(_gray_frame(), 0.05 + i * 0.033, i)

            # Cursor moves to the map area (upper-center of the screen).
            callback(MockMouseEvent('mousemove', 0.25, x=640, y=360))

            # Mouse release.
            callback(MockMouseEvent('mouseup', 0.30, x=700, y=300))

            patch_map = recorder.flush()
            self.assertEqual(
                len(patch_map),
                1,
                'A real drag event routed through make_patch_callback should produce a PNG patch',
            )
            patch_path = list(patch_map.values())[0]
            self.assertTrue(os.path.isfile(patch_path))
            self.assertTrue(patch_path.endswith('.png'))


if __name__ == "__main__":
    unittest.main()
