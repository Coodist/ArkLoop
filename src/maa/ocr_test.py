"""Interactive OCR test for MAA.

Run with::

    .venv/Scripts/python -m src.maa.ocr_test

An OpenCV window appears with the current screenshot. Drag a rectangle around
the text you want to recognize, then press SPACE or click OK. The recognized
text is printed to the terminal.

Press ``c`` in the ROI window to cancel and exit.
"""

from __future__ import annotations

import sys

import cv2

from src.logger import logger
from src.maa import MaaRecognizer
from src.mumu.mumu_vision import capture_game_window


def main() -> int:
    logger.info("=== MAA interactive OCR test ===")

    logger.info("Initializing recognizer...")
    maa = MaaRecognizer()

    logger.info("Capturing screenshot...")
    image = capture_game_window(ratio=None, color=True)
    logger.info(f"Image shape: {image.shape}")

    logger.info("Drag a rectangle around the text to OCR, then press SPACE/OK. Press 'c' to cancel.")
    roi = cv2.selectROI("Drag ROI for OCR", image, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("Drag ROI for OCR")

    x, y, w, h = (int(v) for v in roi)
    if w <= 0 or h <= 0:
        logger.info("No ROI selected, exiting")
        return 0

    logger.info(f"OCR region: ({x}, {y}, {w}, {h})")
    results = maa.ocr_region(image, roi=(x, y, w, h), return_all=True)

    print("\n" + "=" * 50)
    if not results:
        print("No text recognized")
    else:
        for i, r in enumerate(results, 1):
            print(f"[{i}] text={r['text']!r}, box={r['box']}, score={r['score']}")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
