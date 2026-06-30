"""Round-trip tests for map ↔ view coordinate transforms."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cache import get_map_by_code
from src.logic.calc_view import transform_map_to_view, transform_view_to_map


class TestCalcViewRoundTrip(unittest.TestCase):
    """Verify transform_map_to_view and transform_view_to_map are inverses."""

    def test_1_7_front_view_round_trip(self):
        level = get_map_by_code("1-7")
        side = False
        view = transform_map_to_view(level, side)

        for row in range(level["height"]):
            for col in range(level["width"]):
                with self.subTest(row=row, col=col, side=side):
                    ratio = view[row][col]
                    recovered = transform_view_to_map(level, ratio, side)
                    self.assertEqual(recovered, (row, col))

    def test_1_7_side_view_round_trip(self):
        level = get_map_by_code("1-7")
        side = True
        view = transform_map_to_view(level, side)

        for row in range(level["height"]):
            for col in range(level["width"]):
                with self.subTest(row=row, col=col, side=side):
                    ratio = view[row][col]
                    recovered = transform_view_to_map(level, ratio, side)
                    self.assertEqual(recovered, (row, col))

    def test_1_7_noisy_positions(self):
        """Nearest neighbor should tolerate small perturbations near a tile."""
        level = get_map_by_code("1-7")
        side = False
        view = transform_map_to_view(level, side)

        # Pick an interior tile and add tiny offsets.
        row, col = 3, 5
        base_x, base_y = view[row][col]
        for dx, dy in [(0.005, 0), (-0.005, 0), (0, 0.005), (0, -0.005)]:
            with self.subTest(dx=dx, dy=dy):
                recovered = transform_view_to_map(level, (base_x + dx, base_y + dy), side)
                self.assertEqual(recovered, (row, col))


if __name__ == "__main__":
    unittest.main()
