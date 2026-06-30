"""Tests for src.maa.slot_layout helpers."""

import unittest

from src.maa.slot_layout import compute_mouse_zones, deduplicate_slot_flags


class DedupSlotFlagsTests(unittest.TestCase):
    def _flag(self, cx: float, cy: float, w: int = 1280, h: int = 720) -> dict:
        # cx, cy in normalized coordinates; box is [x, y, w, h] in pixels.
        return {
            "box": [
                int((cx - 0.01) * w),
                int((cy - 0.01) * h),
                int(0.02 * w),
                int(0.02 * h),
            ]
        }

    def test_keep_flags_at_same_y(self):
        """Two flags with the same y and close x should both be kept."""
        flags = [self._flag(0.4, 0.85), self._flag(0.42, 0.85)]
        result = deduplicate_slot_flags(flags, 1280, 720, min_x_gap=0.04)
        self.assertEqual(len(result), 2)

    def test_drop_upper_flag_when_close(self):
        """Two flags with close x but different y: keep the lower one."""
        flags = [self._flag(0.4, 0.83), self._flag(0.4, 0.85)]
        result = deduplicate_slot_flags(flags, 1280, 720, min_x_gap=0.04)
        self.assertEqual(len(result), 1)
        # The kept flag should be the lower one (larger normalized y).
        _, y, _, h = result[0]["box"]
        cy = (y + h / 2.0) / 720
        self.assertAlmostEqual(cy, 0.85, places=2)

    def test_no_transitive_drop(self):
        """A flag far from the final survivor should not be dropped just because
        it is linked by intermediate close flags."""
        # A chain: A close to B, B close to C, but A far from C.
        # A and C are at similar height; B is higher (upper).
        flags = [
            self._flag(0.12, 0.85),  # A
            self._flag(0.15, 0.82),  # B (upper, dropped)
            self._flag(0.19, 0.85),  # C
        ]
        result = deduplicate_slot_flags(flags, 1280, 720, min_x_gap=0.04)
        # A survives because it is lower than B. C is >0.04 from A, so kept.
        self.assertEqual(len(result), 2)
        centers = [
            (f["box"][0] + f["box"][2] / 2.0) / 1280 for f in result
        ]
        self.assertAlmostEqual(min(centers), 0.12, places=2)
        self.assertAlmostEqual(max(centers), 0.19, places=2)

    def test_does_not_merge_far_apart(self):
        flags = [self._flag(0.3, 0.83), self._flag(0.5, 0.85)]
        result = deduplicate_slot_flags(flags, 1280, 720, min_x_gap=0.04)
        self.assertEqual(len(result), 2)


class ComputeMouseZonesTests(unittest.TestCase):
    def _flag(self, cx: float, cy: float, w: int = 1280, h: int = 720) -> dict:
        return {
            "box": [
                int((cx - 0.005) * w),
                int((cy - 0.005) * h),
                int(0.01 * w),
                int(0.01 * h),
            ]
        }

    def test_rightmost_zone_reaches_right_edge(self):
        flags = [self._flag(0.55, 0.85)]
        kept, zones = compute_mouse_zones(flags, 1280, 720)
        self.assertEqual(len(zones), 1)
        self.assertAlmostEqual(zones[0]["right"], 1.0, places=5)
        # left = 2 * (cx - midline_offset) - right
        expected_left = 2 * (zones[0]["cx"] - 0.0117) - 1.0
        self.assertAlmostEqual(zones[0]["left"], expected_left, places=5)

    def test_zones_are_ordered_left_to_right(self):
        flags = [self._flag(0.65, 0.85), self._flag(0.85, 0.85)]
        kept, zones = compute_mouse_zones(flags, 1280, 720)
        self.assertEqual(len(zones), 2)
        self.assertLess(zones[0]["left"], zones[1]["left"])
        # Adjacent zones share the boundary.
        self.assertAlmostEqual(zones[0]["right"], zones[1]["left"], places=5)

    def test_drop_flag_when_too_narrow(self):
        # Two flags very close: the left one cannot expand to min width.
        flags = [self._flag(0.7, 0.85), self._flag(0.705, 0.85)]
        kept, zones = compute_mouse_zones(flags, 1280, 720, min_x_gap=0.04)
        self.assertEqual(len(zones), 1)
        # The rightmost flag survives because it has room to the right edge.
        _, y, _, h = kept[0]["box"]
        cy = (y + h / 2.0) / 720
        self.assertAlmostEqual(cy, 0.85, places=2)

    def test_drop_flag_when_midline_inside_right_zone(self):
        # Left flag's midline is to the right of the right flag's left boundary.
        # This is an extreme closeness case.
        right_cx = 0.9
        left_cx = right_cx - 0.0117 + 0.02  # midline would intrude
        flags = [self._flag(left_cx, 0.85), self._flag(right_cx, 0.85)]
        kept, zones = compute_mouse_zones(flags, 1280, 720, min_x_gap=0.04)
        self.assertEqual(len(zones), 1)

    def test_clamped_to_image_bounds(self):
        flags = [self._flag(0.02, 0.85)]
        kept, zones = compute_mouse_zones(flags, 1280, 720)
        self.assertEqual(len(zones), 1)
        self.assertGreaterEqual(zones[0]["left"], 0.0)
        self.assertLessEqual(zones[0]["right"], 1.0)


if __name__ == "__main__":
    unittest.main()
