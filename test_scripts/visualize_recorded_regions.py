"""Visualize the *actual* retreat/skill squares used by the recorder.

Unlike ``scripts/visualize_ui_regions.py`` (which draws the hard-coded
RETREAT_QUAD/SKILL_QUAD), this script draws the dynamically computed regions
from ``recorder/action_recognizer._operator_action_regions()``.  It also
overlays the hard-coded quads as dashed polygons for easy comparison.

Usage::

    .venv\\Scripts\\python scripts/visualize_recorded_regions.py --map-code 1-7
    .venv\\Scripts\\python scripts/visualize_recorded_regions.py --map-code 1-7 --tile D2 --view front
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import cv2
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from recorder.action_recognizer import (
    RETREAT_QUAD,
    SKILL_QUAD,
    _direction_drag_quad,
    _high_ground_type,
    _make_contour,
    _operator_action_regions,
)
from src.cache import get_map_by_code
from src.config import ImageProcessingConfig as imgconfig
from src.logic.calc_view import transform_map_to_view, transform_tile_to_view
from src.logger import logger

# BGR colors.
COL_DEAD = (0, 255, 255)          # yellow
COL_RETREAT = (0, 0, 255)         # red (computed)
COL_SKILL = (255, 255, 0)         # cyan (computed)
COL_RETREAT_HARD = (255, 0, 255)  # magenta (hard-coded)
COL_SKILL_HARD = (0, 140, 255)    # orange (hard-coded)
COL_GRID = (128, 128, 128)
COL_LABEL = (255, 255, 255)


def _polygon_area(pts) -> float:
    """Shoelace formula for a closed polygon (ratio units).

    Accepts either a list of (x, y) tuples or an OpenCV contour
    with shape (N, 1, 2) from ``cv2.convexHull``.
    """
    if pts is None:
        return 0.0
    arr = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    if arr.shape[0] < 3:
        return 0.0
    x, y = arr[:, 0], arr[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _parse_tile(spec: str, height: int) -> Tuple[int, int]:
    """Parse a pos string like ``D2`` into ``(row, col)``."""
    spec = spec.strip().upper()
    letter, number = spec[0], spec[1:]
    row = height - 1 - (ord(letter) - ord("A"))
    col = int(number) - 1
    return row, col


def _capture_or_blank(image_path: str | None) -> np.ndarray:
    std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE
    if image_path:
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")
        return cv2.resize(img, (std_w, std_h))
    try:
        from src.mumu.mumu_vision import capture_game_window

        frame = capture_game_window(ratio=None, color=True)
        return cv2.resize(frame, (std_w, std_h))
    except Exception as exc:
        logger.warning(f"Live capture failed ({exc}); using a blank canvas.")
        return np.full((std_h, std_w, 3), 30, dtype=np.uint8)


def _ratio_to_px(pts: Sequence[Tuple[float, float]], w: int, h: int) -> np.ndarray:
    arr = np.asarray(pts, dtype=np.float32).reshape(-1, 2).copy()
    arr[:, 0] *= w
    arr[:, 1] *= h
    return arr.round().astype(np.int32)


def _draw_poly(
    img: np.ndarray,
    pts: Sequence[Tuple[float, float]] | None,
    color: Tuple[int, int, int],
    thickness: int,
    label: str,
    dashed: bool = False,
) -> None:
    if pts is None or len(pts) < 3:
        return
    h, w = img.shape[:2]
    px = _ratio_to_px(pts, w, h)
    if dashed:
        # Draw dashed polyline by segment.
        pts_closed = np.vstack([px, px[0]])
        for i in range(len(pts_closed) - 1):
            p1 = tuple(pts_closed[i])
            p2 = tuple(pts_closed[i + 1])
            cv2.line(img, p1, p2, color, thickness, lineType=cv2.LINE_AA)
    else:
        cv2.polylines(img, [px], isClosed=True, color=color, thickness=thickness, lineType=cv2.LINE_AA)
    top = px[px[:, 1].argmin()]
    cv2.putText(img, label, (int(top[0]) + 4, int(top[1]) - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def _draw_tile_grid(img: np.ndarray, map_data: Dict[str, Any], side: bool) -> None:
    h, w = img.shape[:2]
    view = transform_map_to_view(map_data, side)
    height, width = map_data["height"], map_data["width"]

    for r in range(height):
        for c in range(width):
            vx, vy = view[r][c]
            cx, cy = int(vx * w), int(vy * h)
            cv2.circle(img, (cx, cy), 2, COL_GRID, -1, cv2.LINE_AA)
            if c + 1 < width:
                vx2, vy2 = view[r][c + 1]
                cv2.line(img, (cx, cy), (int(vx2 * w), int(vy2 * h)), COL_GRID, 1, cv2.LINE_AA)
            if r + 1 < height:
                vx2, vy2 = view[r + 1][c]
                cv2.line(img, (cx, cy), (int(vx2 * w), int(vy2 * h)), COL_GRID, 1, cv2.LINE_AA)
            letter = chr(ord("A") + (height - 1 - r))
            cv2.putText(img, f"{letter}{c + 1}", (cx - 10, cy - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, COL_LABEL, 1, cv2.LINE_AA)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visualize the recorder's actual retreat/skill/dead regions."
    )
    parser.add_argument("--map-code", required=True, help="Map code, e.g. 1-7")
    parser.add_argument("--tile", default=None, help="Anchor tile, e.g. D2 (default: map center)")
    parser.add_argument("--view", choices=["side", "front"], default="side",
                        help="Camera view (default: side)")
    parser.add_argument("--image", default=None, help="Use a saved screenshot as background")
    parser.add_argument("--output", default="recorded_regions.png", help="Output image path")
    parser.add_argument("--show", action="store_true", help="Open a preview window")
    args = parser.parse_args()

    map_data = get_map_by_code(args.map_code)
    side = args.view == "side"
    height, width = map_data["height"], map_data["width"]

    if args.tile:
        tile = _parse_tile(args.tile, height)
    else:
        tile = ((height - 1) / 2.0, (width - 1) / 2.0)

    img = _capture_or_blank(args.image)
    _draw_tile_grid(img, map_data, side)

    # Actual recorder regions.
    dead, retreat, skill = _operator_action_regions(map_data, tile, side)
    _draw_poly(img, dead, COL_DEAD, 2, "dead")
    _draw_poly(img, retreat, COL_RETREAT, 2, "retreat (computed)")
    _draw_poly(img, skill, COL_SKILL, 2, "skill (computed)")

    # Direction-drag diamond for reference.
    drag = _direction_drag_quad(map_data, tile, side)
    _draw_poly(img, drag, (0, 255, 0), 2, "drag r=2.5")

    # Hard-coded quads for comparison (dashed).
    _draw_poly(img, RETREAT_QUAD, COL_RETREAT_HARD, 2, "retreat (hard-coded)", dashed=True)
    _draw_poly(img, SKILL_QUAD, COL_SKILL_HARD, 2, "skill (hard-coded)", dashed=True)

    # Anchor dot (geometric center may not be an integer tile).
    h, w = img.shape[:2]
    hgt = _high_ground_type(map_data)
    vx, vy = transform_tile_to_view(map_data, side, tile[0], tile[1], hgt)
    cv2.circle(img, (int(vx * w), int(vy * h)), 5, (0, 0, 255), -1, cv2.LINE_AA)

    out_path = Path(args.output)
    cv2.imwrite(str(out_path), img)

    print(f"Saved to: {out_path.resolve()}")
    print(f"  map={args.map_code}  view={args.view}  anchor tile(row,col)={tile}")
    print("Screen-ratio polygon areas:")
    print(f"  computed retreat : {_polygon_area(retreat):.6f}")
    print(f"  computed skill   : {_polygon_area(skill):.6f}")
    print(f"  computed dead    : {_polygon_area(dead):.6f}")
    print(f"  hard-coded retreat: {_polygon_area(RETREAT_QUAD):.6f}")
    print(f"  hard-coded skill  : {_polygon_area(SKILL_QUAD):.6f}")

    if args.show:
        cv2.imshow("recorded regions", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
