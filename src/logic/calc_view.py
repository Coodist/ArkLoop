import numpy as np
import math
from typing import List, Tuple, Dict, Any, Optional

from src.logger import logger
from src.config import ViewCalculationConfig as viewconfig

# Cache for forward view maps to avoid recomputing the expensive projection.
# Key: (level["levelId"], side)
_VIEW_CACHE: Dict[Tuple[str, bool], List[List[Tuple[float, float]]]] = {}


def _get_view_cache_key(level: Dict[str, Any], side: bool) -> Tuple[str, bool]:
    return (level.get("levelId", id(level)), side)


def _build_final_matrix(level: Dict[str, Any], side: bool) -> np.ndarray:
    """Build the camera/projection matrix for the given map and view side."""
    DEGREE = math.pi / 180
    try:
        height, width = level["height"], level["width"]
        x, y, z = level["view"][1 if side else 0]
    except KeyError as e:
        logger.error(f"Error loading map data: {e}")
        raise KeyError(f"Error loading map data: {e}")

    # Matrix for transforming map coordinates to view coordinates
    transform_matrix = np.array([
        [1, 0, 0, -x],
        [0, 1, 0, -y],
        [0, 0, 1, -z],
        [0, 0, 0, 1]
    ])

    # Transformation matrices
    perspective_matrix = np.array([
        [viewconfig.FROM_RATIO / math.tan(20 * DEGREE), 0, 0, 0],
        [0, 1 / math.tan(20 * DEGREE), 0, 0],
        [0, 0, -(viewconfig.FAR + viewconfig.NEAR) / (viewconfig.FAR - viewconfig.NEAR), -(viewconfig.FAR * viewconfig.NEAR * 2) / (viewconfig.FAR - viewconfig.NEAR)],
        [0, 0, -1, 0]
    ])
    rotate_x_matrix = np.array([
        [1, 0, 0, 0],
        [0, math.cos(30 * DEGREE), -math.sin(30 * DEGREE), 0],
        [0, -math.sin(30 * DEGREE), -math.cos(30 * DEGREE), 0],
        [0, 0, 0, 1]
    ])
    rotate_y_matrix = np.array([
        [math.cos(10 * DEGREE), 0, math.sin(10 * DEGREE), 0],
        [0, 1, 0, 0],
        [-math.sin(10 * DEGREE), 0, math.cos(10 * DEGREE), 0],
        [0, 0, 0, 1]
    ])

    # Final transformation matrix
    if side:
        return perspective_matrix @ rotate_x_matrix @ rotate_y_matrix @ transform_matrix.copy()
    else:
        return perspective_matrix @ rotate_x_matrix @ transform_matrix.copy()


def transform_tile_to_view(
    level: Dict[str, Any],
    side: bool,
    row: float,
    col: float,
    height_type: int = 0,
) -> Tuple[float, float]:
    """
    Transform a single tile coordinate (possibly fractional) to a screen ratio.

    Args:
        level: Map data dict.
        side: Use side-view matrix if True, otherwise front-view.
        row: Tile row (0-based, increasing downward on the map).
        col: Tile column (0-based, increasing to the right).
        height_type: Tile height type (0 for ground, 1 for high ground, etc.).

    Returns:
        ``(ratio_x, ratio_y)`` in screen coordinates (origin top-left).
    """
    final_matrix = _build_final_matrix(level, side)
    height = level["height"]
    width = level["width"]

    map_point = np.array([
        col - (width - 1) / 2.0,
        (height - 1) / 2.0 - row,
        height_type * -0.4,
        1,
    ])
    view_point = final_matrix @ map_point
    view_point = view_point / view_point[3]
    view_point = (view_point + 1) / 2
    return float(view_point[0]), float(1 - view_point[1])


def transform_map_to_view(level: Dict[str, Any], side: bool) -> List[List[Tuple[float, float]]]:
    """
    Transforms a map to a view based on the given parameters.

    Parameters:
    level (dict): The map data.

    Returns:
    list: A 2D list of tuples representing the transformed map points in ratio form.
    """
    key = _get_view_cache_key(level, side)
    if key in _VIEW_CACHE:
        return _VIEW_CACHE[key]

    final_matrix = _build_final_matrix(level, side)
    height = level["height"]
    width = level["width"]

    # Transform each map point to view point
    out_pos = []
    for i in range(height):
        tmp_pos = []
        for j in range(width):
            tile = level["tiles"][i][j]
            map_point = np.array([
                j - (width - 1) / 2.0,
                (height - 1) / 2.0 - i,
                tile["heightType"] * -0.4,
                1])
            view_point = final_matrix @ map_point
            view_point = view_point / view_point[3]
            view_point = (view_point + 1) / 2
            tmp_pos.append((view_point[0], 1 - view_point[1]))
        out_pos.append(tmp_pos)

    logger.info(f"Transformed map to view, size: {height}x{width}")
    _VIEW_CACHE[key] = out_pos
    return out_pos


def transform_view_to_map(
    level: Dict[str, Any],
    ratio_pos: Tuple[float, float],
    side: bool,
) -> Optional[Tuple[int, int]]:
    """
    Inverse transform: find the map tile whose view position is closest to the
    given screen ratio coordinate.

    Args:
        level: Map data dict (must contain ``tiles``, ``height``, ``width``,
            ``view``).
        ratio_pos: ``(ratio_x, ratio_y)`` in the same coordinate system used by
            ``transform_map_to_view`` (0-1, origin top-left).
        side: If True, use the side-view camera matrix; otherwise front-view.

    Returns:
        ``(row, col)`` of the nearest tile, or ``None`` if the map has no
        tiles.
    """
    view_positions = transform_map_to_view(level, side)
    if not view_positions or not view_positions[0]:
        return None

    target_x, target_y = ratio_pos
    best_row, best_col = 0, 0
    best_distance = float("inf")

    for row, row_tiles in enumerate(view_positions):
        for col, (vx, vy) in enumerate(row_tiles):
            dx = vx - target_x
            dy = vy - target_y
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best_distance = distance
                best_row, best_col = row, col

    return best_row, best_col


if __name__ == "__main__":
    # Usage and Testing
    from src.cache import get_map_by_code
    map = get_map_by_code('1-7')
    res = transform_map_to_view(map, True)
    # Note: result seems to have reversed x and y, compared to showen on map.ark-nights.com
    # the left most deployable position
    logger.info(f"Left most deployable position with side view: {res[3][1]}")
    res = transform_map_to_view(map, False)
    logger.info(f"Left most deployable position with front view: {res[3][1]}")
