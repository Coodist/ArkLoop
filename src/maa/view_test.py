"""Interactive side-view detector test.

Run with::

    .venv/Scripts/python -m src.maa.view_test

The script captures the current game window and prints whether it is detected
as side view or front view, along with the raw OCR results from both regions.
"""

from __future__ import annotations

import sys

from src.logger import logger
from src.maa import create_side_view_detector
from src.mumu.mumu_vision import capture_game_window


def main() -> int:
    logger.info("=== MAA side-view detector test ===")

    logger.info("Initializing detector...")
    detector = create_side_view_detector()

    logger.info("Capturing screenshot...")
    image = capture_game_window(ratio=None, color=True)
    logger.info(f"Image shape: {image.shape}")

    is_side = detector(image)
    print("\n" + "=" * 50)
    print(f"Detected view: {'侧视图 (side)' if is_side else '正视图 (front)'}")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
