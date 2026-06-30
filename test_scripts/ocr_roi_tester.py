"""Interactive ROI + OCR tester for slot detection experiments.

Run with::

    .venv\Scripts\python scripts/ocr_roi_tester.py

Captures the current MuMu screenshot, lets you drag a rectangle around the
region you want to test, then prints:

- The four corners of the selected ROI in both pixel and normalized ratio.
- The number of OCR results found in the ROI.
- Each recognized text, its bounding box, and its confidence score.

Use this to pick a good ROI and evaluate OCR accuracy before designing an
OCR-based slot-detection pipeline.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple

# Make imports from repo root work when running the script directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from src.logger import logger
from src.maa import MaaRecognizer
from src.mumu.mumu_vision import capture_game_window


def _roi_corners(
    x: int, y: int, w: int, h: int
) -> Tuple[List[Tuple[int, int]], List[Tuple[float, float]]]:
    """Return pixel and normalized corners: TL, TR, BR, BL."""
    pixel = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    return pixel, pixel  # normalized will be computed separately


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive ROI OCR tester.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="OCR confidence threshold (default 0.3).",
    )
    parser.add_argument(
        "--expected",
        type=str,
        default=None,
        help="Optional expected text to improve OCR accuracy.",
    )
    args = parser.parse_args()

    logger.info("=== ROI + OCR tester ===")

    logger.info("Initializing MAA recognizer...")
    maa = MaaRecognizer()

    logger.info("Capturing MuMu screenshot...")
    image = capture_game_window(ratio=None, color=True)
    h, w = image.shape[:2]
    logger.info(f"Image size: {w}x{h}")

    logger.info(
        "Drag a rectangle around the region to OCR, then press SPACE/OK. "
        "Press 'c' to cancel."
    )
    roi = cv2.selectROI("Select ROI for OCR", image, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow("Select ROI for OCR")

    x, y, rw, rh = (int(v) for v in roi)
    if rw <= 0 or rh <= 0:
        logger.info("No ROI selected, exiting.")
        return 0

    # Four corners in pixel coordinates.
    corners_px = [
        ("top-left", (x, y)),
        ("top-right", (x + rw, y)),
        ("bottom-right", (x + rw, y + rh)),
        ("bottom-left", (x, y + rh)),
    ]

    # Four corners in normalized ratio coordinates.
    corners_ratio = [
        (name, (px / w, py / h)) for name, (px, py) in corners_px
    ]

    print("\n" + "=" * 50)
    print("Selected ROI corners (pixel):")
    for name, (px, py) in corners_px:
        print(f"  {name:12s} ({px:4d}, {py:4d})")

    print("\nSelected ROI corners (ratio):")
    for name, (rx, ry) in corners_ratio:
        print(f"  {name:12s} ({rx:.4f}, {ry:.4f})")

    print(f"\nROI (x, y, w, h): ({x}, {y}, {rw}, {rh})")
    print("=" * 50)

    logger.info(f"Running OCR on ROI ({x}, {y}, {rw}, {rh})...")
    expected = args.expected
    results = maa.ocr_region(
        image,
        roi=(x, y, rw, rh),
        expected=expected,
        threshold=args.threshold,
        return_all=True,
    )

    print("\n" + "=" * 50)
    if not results:
        print(f"OCR results count: 0")
        print("No text recognized.")
    else:
        print(f"OCR results count: {len(results)}")
        for i, r in enumerate(results, 1):
            text = r.get("text", "")
            box = r.get("box")
            score = r.get("score")
            print(f"[{i}] text={text!r}, box={box}, score={score}")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
