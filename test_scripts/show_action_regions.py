"""Visualize the action-recognition regions on the current screenshot.

Run with::

    .venv/Scripts/python -m scripts.show_action_regions

It captures the current game window, draws the operator area (red),
map area (green), and UI button exclusion zones (yellow), then saves
the result to ``debug/action_regions.png``.

Use this to verify whether your deploy drags start inside the red box
and end inside the green box.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

from src.config import GameRatioConfig as ratioconfig
from src.config import InputRecordingConfig as inputconfig
from src.logger import logger
from src.mumu.mumu_vision import capture_game_window


def main() -> int:
    logger.info("Capturing screenshot...")
    image = capture_game_window(ratio=None, color=True)
    h, w = image.shape[:2]
    logger.info(f"Image size: {w}x{h}")

    canvas = image.copy()

    # Operator area (red): bottom deploy bar.
    ol, ot, oright, obottom = ratioconfig.OPERATOR_AREA_RATIO
    ox1, oy1 = int(ol * w), int(ot * h)
    ox2, oy2 = int(oright * w), int(obottom * h)
    cv2.rectangle(canvas, (ox1, oy1), (ox2, oy2), (0, 0, 255), 2)
    cv2.putText(
        canvas,
        "operator area (deploy drag must start here)",
        (ox1 + 5, oy1 - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 255),
        2,
    )

    # Map area (green): everything above operator area.
    cv2.rectangle(canvas, (0, 0), (w, oy1), (0, 255, 0), 2)
    cv2.putText(
        canvas,
        "map area (deploy drag must end here)",
        (5, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2,
    )

    # UI button exclusion zones (yellow circles).
    buttons = {
        "pause": ratioconfig.PAUSE_BUTTON_RATIO,
        "speed": ratioconfig.SPEED_BUTTON_RATIO,
        "start": ratioconfig.START_BUTTON_RATIO,
    }
    for name, (rx, ry) in buttons.items():
        cx, cy = int(rx * w), int(ry * h)
        cv2.circle(canvas, (cx, cy), 20, (0, 255, 255), 2)
        cv2.putText(
            canvas,
            name,
            (cx + 25, cy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
        )

    # Drag threshold indicator.
    thresh = inputconfig.DRAG_THRESHOLD_RATIO
    cv2.putText(
        canvas,
        f"drag threshold = {thresh} ({int(thresh * 100)}% of screen height)",
        (5, h - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 255, 255),
        1,
    )

    out_dir = Path("debug")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "action_regions.png"
    cv2.imwrite(str(out_path), canvas)
    logger.info(f"Saved visualization to: {out_path.resolve()}")
    print(
        f"\nOperator area ratio: {ratioconfig.OPERATOR_AREA_RATIO}"
        f"\nMap area: y < {ratioconfig.OPERATOR_AREA_RATIO[1]}"
        f"\nDrag threshold: {inputconfig.DRAG_THRESHOLD_RATIO}"
        f"\nImage saved to: {out_path.resolve()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
