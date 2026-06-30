"""Self-test entry point for the MAA integration layer.

Run with::

    python -m src.maa

The script will:
1. Initialize the MAA Tasker.
2. Capture a screenshot via prts-plus's existing capture stack.
3. Run state detection, OCR, and template matching and print results.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from src.logger import logger
from src.maa import MaaRecognizer

try:
    from src.mumu.mumu_vision import capture_game_window
except Exception as exc:
    capture_game_window = None  # type: ignore[assignment]
    logger.warning(f"Could not import capture_game_window: {exc}")


def _synthetic_image() -> np.ndarray:
    """Return a blank 1280x720 BGR image for offline testing."""
    logger.info("Using synthetic blank image for offline testing")
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def main() -> int:
    logger.info("=== prts-plus MAA integration self-test ===")

    # 1. Initialize recognizer (and therefore MAA Tasker).
    try:
        maa = MaaRecognizer()
    except Exception as exc:
        logger.exception(f"Failed to initialize MAA: {exc}")
        return 1

    # 2. Capture or synthesize a test image.
    try:
        if capture_game_window is None:
            raise RuntimeError("Capture unavailable")
        image = capture_game_window(ratio=None, color=True)
        logger.info(f"Captured image shape: {image.shape}")
    except Exception as exc:
        logger.warning(f"Could not capture game window: {exc}")
        image = _synthetic_image()

    # 3. State detection.
    try:
        state = maa.detect_state(image)
        logger.info(f"Detected state: {state}")
    except Exception as exc:
        logger.exception(f"detect_state failed: {exc}")

    # 4. OCR a sample region (top-left corner of the screen).
    try:
        text = maa.ocr_region(image, roi=(10, 10, 200, 40))
        logger.info(f"OCR sample region text: {text!r}")
    except Exception as exc:
        logger.exception(f"ocr_region failed: {exc}")

    # 5. Template matching against a built-in template.
    try:
        result = maa.match_template(
            image,
            template_path="Play.png",
            roi=(1194, 31, 41, 35),
            threshold=0.8,
        )
        logger.info(f"Template match result: {result}")
    except Exception as exc:
        logger.exception(f"match_template failed: {exc}")

    # 6. Slot flag detection (optional preview).
    try:
        slots = maa.detect_slot_flags(image)
        logger.info(f"Detected {len(slots)} operator slot flags")
    except Exception as exc:
        logger.exception(f"detect_slot_flags failed: {exc}")

    logger.info("=== self-test completed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
