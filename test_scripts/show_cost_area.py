"""Visualize the cost bar / cost number crop regions and run OCR on them.

Run with::

    .venv/Scripts/python -m scripts.show_cost_area

The script captures the current game window (or loads ``debug/maa_capture.png``),
draws the configured ``COST_AREA_RATIO`` and ``COST_NUMBER_AREA_RATIO`` boxes,
runs OCR on the number area, and saves the visualization to
``debug/cost_area.png``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from src.config import GameRatioConfig as ratioconfig
from src.logger import logger

try:
    from src.mumu.mumu_vision import capture_game_window
except Exception as exc:
    logger.warning(f"Cannot import capture_game_window: {exc}")
    capture_game_window = None

try:
    from src.logic.analyze_time import get_cost
except Exception as exc:
    logger.warning(f"Cannot import get_cost: {exc}")
    get_cost = None


_OUT_PATH = Path("debug") / "cost_area.png"


def _combined_cost_number_box() -> Tuple[float, float, float, float]:
    """Return the absolute (left, top, right, bottom) of the cost number box."""
    cost_left, cost_top, cost_right, cost_bottom = ratioconfig.COST_AREA_RATIO
    num_left, num_top, num_right, num_bottom = ratioconfig.COST_NUMBER_AREA_RATIO
    return (
        cost_left + (cost_right - cost_left) * num_left,
        cost_top + (cost_bottom - cost_top) * num_top,
        cost_left + (cost_right - cost_left) * num_right,
        cost_top + (cost_bottom - cost_top) * num_bottom,
    )


def _draw_box(
    image: np.ndarray,
    box: Tuple[float, float, float, float],
    label: str,
    color: Tuple[int, int, int],
) -> None:
    h, w = image.shape[:2]
    left, top, right, bottom = box
    x1, y1 = int(left * w), int(top * h)
    x2, y2 = int(right * w), int(bottom * h)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
    cv2.putText(
        image,
        label,
        (x1, max(0, y1 - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
    )


def _ocr_cost(image: np.ndarray) -> Optional[int]:
    if get_cost is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h, w = gray.shape[:2]
    left, top, right, bottom = _combined_cost_number_box()
    cost_img = gray[
        int(h * top) : int(h * bottom),
        int(w * left) : int(w * right),
    ]
    if cost_img.size == 0:
        return None
    try:
        return get_cost(cost_img.tobytes(), cost_img.shape[1], cost_img.shape[0])
    except Exception as exc:
        logger.warning(f"OCR failed: {exc}")
        return None


def _load_image() -> Optional[np.ndarray]:
    existing = Path("debug") / "maa_capture.png"
    if existing.exists():
        logger.info(f"Loading existing capture: {existing.resolve()}")
        img = cv2.imread(str(existing))
        if img is not None:
            return img
    if capture_game_window is not None:
        logger.info("Capturing game window...")
        try:
            return capture_game_window(ratio=None, color=True)
        except Exception as exc:
            logger.exception(f"Failed to capture: {exc}")
    return None


def main() -> int:
    image = _load_image()
    if image is None:
        print("无法加载截图。请确保游戏窗口可用或存在 debug/maa_capture.png")
        return 1

    canvas = image.copy()
    _draw_box(
        canvas,
        ratioconfig.COST_AREA_RATIO,
        "COST_AREA_RATIO",
        (0, 255, 0),
    )
    _draw_box(
        canvas,
        _combined_cost_number_box(),
        "COST_NUMBER_AREA_RATIO",
        (0, 0, 255),
    )

    cost = _ocr_cost(image)
    label = f"OCR cost: {cost}" if cost is not None else "OCR cost: failed"
    cv2.putText(
        canvas,
        label,
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 0, 255),
        2,
    )

    _OUT_PATH.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(_OUT_PATH), canvas)
    print(f"Saved visualization to: {_OUT_PATH.resolve()}")
    print(f"Current COST_AREA_RATIO:           {ratioconfig.COST_AREA_RATIO}")
    print(f"Current COST_NUMBER_AREA_RATIO:    {ratioconfig.COST_NUMBER_AREA_RATIO}")
    print(f"Combined cost number box:          {_combined_cost_number_box()}")
    print(f"OCR result:                        {cost}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
