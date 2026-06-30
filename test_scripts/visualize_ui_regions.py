"""Capture the game window and overlay detection regions.

This helps verify whether the hard-coded retreat/skill/operator-area regions
and the computed direction-drag diamond match the actual MuMu UI.  It draws:

- green rectangle:  operator deploy area (bottom bar)
- red polygon:      retreat button region
- blue polygon:     skill button region
- orange polygon:   direction-drag diamond for the specified tile
- purple polygon:   draggable diamond with radius 2.7 tiles
- mint polygon:     draggable diamond with radius 2.5 tiles
- gray polygon:     scaled r=2.7 diamond outline (only shown with --scale for comparison)
- green polygon:    test square 1 (--test-new x,...), x = half diagonal in tiles
- yellow polygon:   test square 2 (--test-new ...,y), y = half diagonal in tiles
- cyan circle:      pause button
- magenta circle:   speed button
- yellow circle:    start button

Usage:
    .venv\Scripts\python scripts/visualize_ui_regions.py --map-code 1-7 --tile 3,8 --test-new 1.5,2.0
    .venv\Scripts\python scripts/visualize_ui_regions.py --map-code 1-7 --tile 3,8 --forward --test-new 1.5,2.0

Press any key to close the image window.
"""
import argparse
import math
import os
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from src.config import GameRatioConfig as ratioconfig
from src.mumu.mumu_vision import capture_game_window
from src.cache import get_map_by_code
from recorder.action_recognizer import (
    RETREAT_CONTOUR,
    SKILL_CONTOUR,
    _direction_drag_quad,
    _make_contour,
)


def _draw_contour(overlay, contour, color, label, w, h):
    pts = np.array(
        [(int(w * x), int(h * y)) for x, y in contour.reshape(-1, 2)],
        np.int32,
    ).reshape((-1, 1, 2))
    cv2.polylines(overlay, [pts], isClosed=True, color=color, thickness=2)
    # Label near the first vertex.
    cx, cy = pts[0][0]
    cv2.putText(overlay, label, (cx + 8, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    # Mark vertices.
    for (x, y) in pts.reshape(-1, 2):
        cv2.circle(overlay, (x, y), 3, color, -1)


def _test_squares_on_diamond_plane(
    map_data,
    tile_pos: Tuple[int, int],
    half_diag_x: float = 0.77,
    half_diag_y: float = 0.81,
    radius: float = 2.7,
    side: bool = True,
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Return two side-view squares built on the draggable diamond plane.

    The draggable diamond lives on the high-ground plane.  For each target
    edge (left-top and right-bottom) we take its midpoint, build an
    axis-aligned square in tile coordinates whose diagonal half-length is
    ``half_diag_x`` / ``half_diag_y`` tiles, then project the four corners
    through ``transform_tile_to_view`` with the same high-ground type used by
    the diamond.  The square diagonal lies exactly on the corresponding
    diamond edge.
    """
    from src.logic.calc_view import transform_tile_to_view

    row, col = tile_pos
    high_ground_type = max(
        1,
        max(
            tile["heightType"]
            for row_tiles in map_data["tiles"]
            for tile in row_tiles
        ),
    )

    # Diamond corners in tile coordinates (same order as _direction_drag_quad).
    left = (row, col - radius)
    bottom = (row + radius, col)
    right = (row, col + radius)
    top = (row - radius, col)

    def _make_square(mid_r: float, mid_c: float, half_diag: float):
        d = half_diag / math.sqrt(2)
        corners = [
            (mid_r + d, mid_c + d),
            (mid_r - d, mid_c + d),
            (mid_r - d, mid_c - d),
            (mid_r + d, mid_c - d),
        ]
        return [
            transform_tile_to_view(map_data, side, r, c, high_ground_type)
            for r, c in corners
        ]

    # Left-top edge midpoint, shifted right 0.015 and up 0.01 tiles.
    m1_r = (left[0] + top[0]) / 2.0 - 0.01
    m1_c = (left[1] + top[1]) / 2.0 + 0.015
    square1 = _make_square(m1_r, m1_c, half_diag_x)

    # Right-bottom edge midpoint, shifted left 0.01 tiles.
    m2_r = (right[0] + bottom[0]) / 2.0
    m2_c = (right[1] + bottom[1]) / 2.0 - 0.01
    square2 = _make_square(m2_r, m2_c, half_diag_y)

    return square1, square2


def _scaled_radius_for_visual_match(
    map_data,
    tile_pos: Tuple[int, int],
    target_radius: float,
    ref_map_code: str = "1-7",
    side: bool = True,
) -> float:
    """Return a radius for ``map_data`` whose diamond looks as big as ``target_radius`` on the reference map.

    1-7 is the reference because the hard-coded UI boxes (retreat/skill) were
    tuned against it.  The scaling is based on the average screen distance from
    the tile center to the four diamond arms, so the visual size stays roughly
    constant across maps even though their ``view`` matrices differ.
    """
    from src.cache import get_map_by_code
    from src.logic.calc_view import transform_tile_to_view

    ref_map = get_map_by_code(ref_map_code)

    def _high_ground_type(level):
        return max(
            1,
            max(
                tile["heightType"]
                for row_tiles in level["tiles"]
                for tile in row_tiles
            ),
        )

    def _avg_arm_length(level, pos, radius):
        row, col = pos
        hgt = _high_ground_type(level)
        center = transform_tile_to_view(level, side, row, col, hgt)
        arms = [
            transform_tile_to_view(level, side, row, col - radius, hgt),
            transform_tile_to_view(level, side, row + radius, col, hgt),
            transform_tile_to_view(level, side, row, col + radius, hgt),
            transform_tile_to_view(level, side, row - radius, col, hgt),
        ]
        return sum(
            math.hypot(a[0] - center[0], a[1] - center[1]) for a in arms
        ) / 4.0

    ref_pos = tile_pos
    ref_h, ref_w = ref_map["height"], ref_map["width"]
    if not (0 <= ref_pos[0] < ref_h and 0 <= ref_pos[1] < ref_w):
        ref_pos = ((ref_h - 1) / 2.0, (ref_w - 1) / 2.0)

    ref_len = _avg_arm_length(ref_map, ref_pos, target_radius)
    cur_len = _avg_arm_length(map_data, tile_pos, target_radius)

    if cur_len == 0:
        return target_radius
    return target_radius * (ref_len / cur_len)


def _draw_transformed_grid(
    overlay,
    map_data,
    side: bool,
    color,
    label_color,
    w,
    h,
    highlight_tile=None,
):
    """Draw the 3D-tilted tile grid and label each tile with (row,col)."""
    from src.logic.calc_view import transform_map_to_view

    view_positions = transform_map_to_view(map_data, side)
    rows = len(view_positions)
    cols = len(view_positions[0]) if rows else 0

    # Draw grid lines.
    for r in range(rows):
        for c in range(cols):
            x1, y1 = int(w * view_positions[r][c][0]), int(h * view_positions[r][c][1])
            if c + 1 < cols:
                x2, y2 = int(w * view_positions[r][c + 1][0]), int(h * view_positions[r][c + 1][1])
                cv2.line(overlay, (x1, y1), (x2, y2), color, 1)
            if r + 1 < rows:
                x2, y2 = int(w * view_positions[r + 1][c][0]), int(h * view_positions[r + 1][c][1])
                cv2.line(overlay, (x1, y1), (x2, y2), color, 1)

    # Draw labels and tile centers.
    for r in range(rows):
        for c in range(cols):
            x, y = int(w * view_positions[r][c][0]), int(h * view_positions[r][c][1])
            is_highlight = highlight_tile is not None and (r, c) == highlight_tile
            dot_color = (0, 0, 255) if is_highlight else color
            cv2.circle(overlay, (x, y), 3 if is_highlight else 2, dot_color, -1)
            label = f"{r},{c}"
            cv2.putText(
                overlay,
                label,
                (x + 4, y - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (0, 0, 255) if is_highlight else label_color,
                1,
            )


def _parse_tile(value: str) -> Tuple[int, int]:
    """Parse a tile spec like '3,8' into (row, col)."""
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("tile must be in the form row,col, e.g. 3,8")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid tile: {value}") from exc


def _parse_two_floats(value: str) -> Tuple[float, float]:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("must be x,y with two floats")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid value: {value}") from exc


def main():
    parser = argparse.ArgumentParser(description="Visualize UI detection regions.")
    parser.add_argument("--map-code", default="1-7", help="Map code for direction diamond")
    parser.add_argument(
        "--tile",
        type=_parse_tile,
        default=(3, 8),
        help="Tile (row,col) for which to draw the direction-drag diamond (default: 3,8)",
    )
    parser.add_argument(
        "--test-new",
        type=_parse_two_floats,
        default=None,
        metavar="X,Y",
        help="Draw two test squares with diagonals on the draggable diamond edges (default halves 0.77,0.81)",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="Use front view (side=False) for map grid, diamonds and test squares",
    )
    parser.add_argument(
        "--scale",
        action="store_true",
        help="Enable 1-7 visual-size scaling for diamonds and squares (for comparison)",
    )
    args = parser.parse_args()

    tile_row, tile_col = args.tile
    side = not args.forward

    frame = capture_game_window(ratio=None, color=True)
    if frame is None:
        print("Failed to capture game window. Is MuMu running?")
        return

    h, w = frame.shape[:2]
    overlay = frame.copy()

    # Operator area.
    left, top, right, bottom = ratioconfig.OPERATOR_AREA_RATIO
    x1, y1 = int(w * left), int(h * top)
    x2, y2 = int(w * right), int(h * bottom)
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(overlay, "operator area", (x1 + 5, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Polygon detection regions.
    if args.test_new is None and not args.forward:
        _draw_contour(overlay, RETREAT_CONTOUR, (0, 0, 255), "retreat", w, h)
        _draw_contour(overlay, SKILL_CONTOUR, (255, 0, 0), "skill", w, h)
    else:
        # Hide retreat/skill boxes when running the diamond test overlay.
        reason = "--test-new" if args.test_new else "--forward"
        cv2.putText(
            overlay,
            f"retreat/skill boxes hidden ({reason})",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (200, 200, 200),
            1,
        )

    # Direction-drag diamond for the requested tile using side view.
    map_data = get_map_by_code(args.map_code)
    direction_quad = _direction_drag_quad(map_data, (tile_row, tile_col), side=side)
    if direction_quad:
        direction_contour = _make_contour(direction_quad)
        _draw_contour(overlay, direction_contour, (0, 140, 255), f"dir({tile_row},{tile_col})", w, h)

    # Scale diamond radii so the visual size matches 1-7 for any map.
    if args.scale:
        radius_27 = _scaled_radius_for_visual_match(
            map_data, (tile_row, tile_col), 2.7, side=side
        )
        radius_25 = _scaled_radius_for_visual_match(
            map_data, (tile_row, tile_col), 2.5, side=side
        )
    else:
        radius_27 = 2.7
        radius_25 = 2.5

    # Larger "draggable" diamonds using radius 2.7 and 2.5 tiles (visually matched to 1-7).
    draggable_quad_27 = _direction_drag_quad(
        map_data, (tile_row, tile_col), side=side, radius=radius_27
    )
    if draggable_quad_27:
        draggable_contour = _make_contour(draggable_quad_27)
        label_27 = f"drag2.7({tile_row},{tile_col})"
        if args.scale:
            label_27 += f" r={radius_27:.2f}"
        _draw_contour(
            overlay,
            draggable_contour,
            (255, 0, 255),
            label_27,
            w,
            h,
        )

    # Optional unscaled r=2.7 outline for comparison when scaling is active.
    if args.scale:
        unscaled_quad_27 = _direction_drag_quad(
            map_data, (tile_row, tile_col), side=side, radius=2.7
        )
        if unscaled_quad_27:
            unscaled_contour = _make_contour(unscaled_quad_27)
            pts = np.array(
                [(int(w * x), int(h * y)) for x, y in unscaled_contour.reshape(-1, 2)],
                np.int32,
            ).reshape((-1, 1, 2))
            cv2.polylines(overlay, [pts], isClosed=True, color=(128, 128, 128), thickness=1)

    draggable_quad_25 = _direction_drag_quad(
        map_data, (tile_row, tile_col), side=side, radius=radius_25
    )
    if draggable_quad_25:
        draggable_contour_25 = _make_contour(draggable_quad_25)
        label_25 = f"drag2.5({tile_row},{tile_col})"
        if args.scale:
            label_25 += f" r={radius_25:.2f}"
        _draw_contour(
            overlay,
            draggable_contour_25,
            (0, 255, 128),
            label_25,
            w,
            h,
        )

    # Optional test squares whose diagonals sit on the draggable diamond edges.
    if args.test_new:
        x_len, y_len = args.test_new
        square1, square2 = _test_squares_on_diamond_plane(
            map_data, (tile_row, tile_col), x_len, y_len, radius=radius_27, side=side
        )
        _draw_contour(overlay, _make_contour(square1), (0, 255, 0), f"test1({x_len})", w, h)
        _draw_contour(overlay, _make_contour(square2), (255, 255, 0), f"test2({y_len})", w, h)

    # 3D transformed tile grid, with the requested tile highlighted.
    _draw_transformed_grid(
        overlay,
        map_data,
        side=side,
        color=(128, 128, 128),
        label_color=(200, 200, 200),
        w=w,
        h=h,
        highlight_tile=(tile_row, tile_col),
    )

    # Point buttons.
    buttons = [
        ("pause", ratioconfig.PAUSE_BUTTON_RATIO, (255, 255, 0)),
        ("speed", ratioconfig.SPEED_BUTTON_RATIO, (255, 0, 255)),
        ("start", ratioconfig.START_BUTTON_RATIO, (0, 255, 255)),
    ]
    for name, ratio, color in buttons:
        cx, cy = int(w * ratio[0]), int(h * ratio[1])
        cv2.circle(overlay, (cx, cy), 15, color, 2)
        cv2.circle(overlay, (cx, cy), 2, color, -1)
        cv2.putText(overlay, name, (cx + 18, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    print("Current detection regions (relative to 1280x720 game canvas):")
    print(f"  view:          {'front' if args.forward else 'side'}")
    print(f"  operator area: {ratioconfig.OPERATOR_AREA_RATIO}")
    if args.test_new is None and not args.forward:
        print(f"  retreat quad:  {RETREAT_CONTOUR.reshape(-1, 2).tolist()}")
        print(f"  skill quad:    {SKILL_CONTOUR.reshape(-1, 2).tolist()}")
    if direction_quad:
        print(f"  direction diamond for tile ({tile_row},{tile_col}): {direction_quad}")
    if draggable_quad_27:
        scale_info_27 = f" (scaled {radius_27:.3f})" if args.scale else ""
        print(f"  draggable diamond r=2.7{scale_info_27} for tile ({tile_row},{tile_col}): {draggable_quad_27}")
    if args.scale and 'unscaled_quad_27' in locals() and unscaled_quad_27:
        print(f"  unscaled r=2.7 outline for tile ({tile_row},{tile_col}): {unscaled_quad_27}")
    if draggable_quad_25:
        scale_info_25 = f" (scaled {radius_25:.3f})" if args.scale else ""
        print(f"  draggable diamond r=2.5{scale_info_25} for tile ({tile_row},{tile_col}): {draggable_quad_25}")
    if args.test_new and draggable_quad_27:
        x_len, y_len = args.test_new
        print(f"  test square 1 (half-diag={x_len}) for tile ({tile_row},{tile_col}): {square1}")
        print(f"  test square 2 (half-diag={y_len}) for tile ({tile_row},{tile_col}): {square2}")
    for name, ratio, _ in buttons:
        print(f"  {name}: ratio=({ratio[0]:.4f}, {ratio[1]:.4f})")

    output_path = "recordings/ui_regions_overlay.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, overlay)
    print(f"\nOverlay saved to: {output_path}")
    print("Close the image window to exit.")

    cv2.imshow("UI detection regions", overlay)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
