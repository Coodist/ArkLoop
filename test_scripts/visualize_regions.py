"""Visualize the recognizer's detection regions on a live (or saved) frame.

Given a map and a camera view, this captures one frame from the emulator and
overlays the regions that ``recorder/action_recognizer.py`` uses to classify
clicks and drags:

* 撤退区  (retreat square)         — red
* 技能区  (skill square)           — cyan
* 死区    (dead-zone diamond)      — yellow
* 部署可拖拽区 (direction-drag diamond) — green
* 每个地块被判定为该地块的区域      — thin gray Voronoi cells, one per tile

The action squares / diamonds are anchored on a tile.  By default this is the
map's center tile, because the game pans the selected operator to the center
(this is exactly what ``ActionRecognizer._get_action_regions`` does).  Pass
``--tile`` to anchor them on a specific tile instead.

Usage::

    .venv\\Scripts\\python scripts/visualize_regions.py --map 1-7 --view side
    .venv\\Scripts\\python scripts/visualize_regions.py --map 1-7 --view front --tile D2
    .venv\\Scripts\\python scripts/visualize_regions.py --map 1-7 --view side --image shot.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from recorder.action_recognizer import (
    _direction_drag_quad,
    _high_ground_type,
    _operator_action_regions,
)
from src.cache import get_map_by_code, get_map_by_name
from src.config import ImageProcessingConfig as imgconfig
from src.logic.calc_view import transform_map_to_view
from src.logger import logger

# BGR colors.
COL_GRID = (170, 170, 170)
COL_LABEL = (255, 255, 255)
COL_DEAD = (0, 255, 255)     # yellow
COL_RETREAT = (0, 0, 255)    # red
COL_SKILL = (255, 230, 0)    # cyan
COL_DRAG = (0, 255, 0)       # green


def _load_map(spec: str) -> Dict[str, Any]:
    """Load a map by code (e.g. ``1-7``) or by name."""
    try:
        return get_map_by_code(spec)
    except Exception:
        return get_map_by_name(spec)


def _parse_tile(spec: str, height: int) -> Tuple[int, int]:
    """Parse a pos string like ``D2`` into a ``(row, col)`` tile coordinate."""
    spec = spec.strip().upper()
    letter, number = spec[0], spec[1:]
    row = height - 1 - (ord(letter) - ord("A"))
    col = int(number) - 1
    return row, col


def _capture_frame(image_path: Optional[str]) -> np.ndarray:
    """Return a BGR frame at the standard resolution, from disk or the emulator."""
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
    """Convert ratio-space points (or an OpenCV contour) to int pixel points."""
    arr = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    arr[:, 0] *= w
    arr[:, 1] *= h
    return arr.round().astype(np.int32)


def _draw_poly(img: np.ndarray, pts_ratio, color, thickness: int, label: str) -> None:
    if pts_ratio is None:
        return
    h, w = img.shape[:2]
    px = _ratio_to_px(pts_ratio, w, h)
    cv2.polylines(img, [px], isClosed=True, color=color, thickness=thickness, lineType=cv2.LINE_AA)
    # Put the label near the topmost vertex.
    top = px[px[:, 1].argmin()]
    cv2.putText(img, label, (int(top[0]) + 3, int(top[1]) - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def _draw_tile_voronoi(img: np.ndarray, map_data: Dict[str, Any], side: bool) -> None:
    """Draw the nearest-tile partition — the region judged to be each tile."""
    h, w = img.shape[:2]
    view = transform_map_to_view(map_data, side)
    height, width = map_data["height"], map_data["width"]

    centers: List[Tuple[float, float]] = []
    labels: List[str] = []
    for r in range(height):
        for c in range(width):
            vx, vy = view[r][c]
            centers.append((vx * w, vy * h))
            letter = chr(ord("A") + (height - 1 - r))
            labels.append(f"{letter}{c + 1}")
    cx = np.array([p[0] for p in centers], dtype=np.float32)
    cy = np.array([p[1] for p in centers], dtype=np.float32)

    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    label_map = np.zeros((h, w), dtype=np.int32)
    best = np.full((h, w), np.inf, dtype=np.float32)
    for i in range(len(centers)):
        d = (xs - cx[i]) ** 2 + (ys - cy[i]) ** 2
        closer = d < best
        best[closer] = d[closer]
        label_map[closer] = i

    # Cell boundaries: where the nearest-tile label changes between neighbors.
    edge = np.zeros((h, w), dtype=bool)
    edge[:, :-1] |= label_map[:, :-1] != label_map[:, 1:]
    edge[:-1, :] |= label_map[:-1, :] != label_map[1:, :]
    img[edge] = COL_GRID

    for (px, py), name in zip(centers, labels):
        cv2.circle(img, (int(px), int(py)), 2, COL_GRID, -1, cv2.LINE_AA)
        cv2.putText(img, name, (int(px) - 8, int(py) + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, COL_LABEL, 1, cv2.LINE_AA)


def _draw_legend(img: np.ndarray) -> None:
    items = [
        ("retreat 撤退区", COL_RETREAT),
        ("skill 技能区", COL_SKILL),
        ("dead 死区", COL_DEAD),
        ("drag 部署可拖拽区", COL_DRAG),
        ("tile cells 地块判定区", COL_GRID),
    ]
    x, y = 8, 16
    for text, color in items:
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
        y += 17


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize recognizer detection regions.")
    parser.add_argument("--map", required=True, help="Map code (e.g. 1-7) or map name")
    parser.add_argument("--view", choices=["side", "front"], default="side",
                        help="Camera view to use (default: side)")
    parser.add_argument("--tile", default=None,
                        help="Anchor tile for action regions, e.g. D2 (default: map center)")
    parser.add_argument("--image", default=None,
                        help="Use a saved screenshot instead of capturing live")
    parser.add_argument("--output", default="regions.png", help="Output image path")
    parser.add_argument("--show", action="store_true", help="Also open a preview window")
    args = parser.parse_args()

    map_data = _load_map(args.map)
    side = args.view == "side"
    height, width = map_data["height"], map_data["width"]

    if args.tile:
        tile = _parse_tile(args.tile, height)
    else:
        tile = ((height - 1) / 2.0, (width - 1) / 2.0)
    logger.info(f"Anchoring action regions on tile (row,col)={tile} in {args.view} view")

    img = _capture_frame(args.image)

    # Per-tile Voronoi partition (thin lines) first, so zone outlines draw on top.
    _draw_tile_voronoi(img, map_data, side)

    # Action regions around the anchor tile.
    dead, retreat, skill = _operator_action_regions(map_data, tile, side)
    _draw_poly(img, dead, COL_DEAD, 2, "dead")
    _draw_poly(img, retreat, COL_RETREAT, 2, "retreat")
    _draw_poly(img, skill, COL_SKILL, 2, "skill")

    drag = _direction_drag_quad(map_data, tile, side)
    _draw_poly(img, drag, COL_DRAG, 2, "drag")

    _draw_legend(img)

    out_path = Path(args.output)
    cv2.imwrite(str(out_path), img)
    logger.info(f"Wrote {out_path.resolve()}")
    print(f"Regions image written to: {out_path.resolve()}")
    print(f"  map={args.map}  view={args.view}  anchor tile(row,col)={tile}")
    print(f"  high-ground type used for diamonds: {_high_ground_type(map_data)}")

    if args.show:
        cv2.imshow("regions", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
