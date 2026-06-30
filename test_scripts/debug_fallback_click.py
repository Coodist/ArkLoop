"""Debug script for fallback click + OCR.

This script helps verify:
1. Whether the clicked position is visually correct.
2. Whether mouseclick() actually opens the operator detail page.
3. Whether the OcrOperName ROI lands on the correct region.

Usage:
    .venv\Scripts\python scripts/debug_fallback_click.py

The script will:
- Detect the first deployment slot.
- Take a screenshot (before) and draw a red circle at the click position.
- Click the slot center using the project's mouseclick().
- Wait 1s.
- Take a screenshot (after).
- Run OCR on the OcrOperName ROI and print the result.
- Click the same slot again to close the detail page.
- Save before/after images to debug/fallback_click_debug/ for visual inspection.

If you want to test with move+down/up instead of mouseclick, edit the script
and set USE_SEPARATE_DOWN_UP = True.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from src.config import LocateAvatarFallbackConfig as fallbackconfig
from src.logic.locate_avatar_fallback import _detect_slots
from src.maa.recognizer import MaaRecognizer
from src.mumu.mumu_controller import mouseclick, mousemove, mousedown, mouseup
from src.mumu.mumu_vision import capture_game_window

# Set to True to test mousemove + mousedown + mouseup instead of mouseclick.
USE_SEPARATE_DOWN_UP = False


def main():
    out_dir = Path("debug") / "fallback_click_debug"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Capturing initial screenshot...")
    before = capture_game_window(ratio=None, color=True)
    h, w = before.shape[:2]
    cv2.imwrite(str(out_dir / "before.png"), before)

    slots = _detect_slots(before)
    if not slots:
        print("No slots detected!")
        return

    slot = slots[0]
    cx, cy = slot["cx"], slot["cy"]
    click_x = int(cx * w)
    # Move click position halfway between current slot y and the bottom of the screen.
    click_y = int((cy + 1.0) / 2.0 * h)
    click_ratio = (cx, (cy + 1.0) / 2.0)
    print(f"Slot 0 click position: pixel=({click_x}, {click_y}) ratio=({cx:.4f}, {(cy + 1.0) / 2.0:.4f})")

    # Mark click position on before image.
    before_annotated = before.copy()
    cv2.circle(before_annotated, (click_x, click_y), 8, (0, 0, 255), 2)
    cv2.putText(
        before_annotated,
        "CLICK",
        (click_x + 10, click_y - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 255),
        2,
    )
    cv2.imwrite(str(out_dir / "before_click_marker.png"), before_annotated)

    print("Clicking slot 0 to open detail page...")
    if USE_SEPARATE_DOWN_UP:
        print("Using move + down/up")
        mousemove(click_ratio)
        time.sleep(0.05)
        mousedown(click_ratio)
        time.sleep(0.05)
        mouseup(click_ratio)
    else:
        print("Using mouseclick")
        mouseclick(click_ratio)
    time.sleep(1.0)

    print("Capturing after click...")
    after = capture_game_window(ratio=None, color=True)
    cv2.imwrite(str(out_dir / "after.png"), after)

    # Draw OCR ROI on the after image for visual verification.
    ox, oy, ow, oh = fallbackconfig.OCR_OPER_NAME_ROI
    # Shift ROI up by half its height as observed from real captures.
    oy = max(0, oy - oh // 2)
    after_annotated = after.copy()
    cv2.rectangle(after_annotated, (ox, oy), (ox + ow, oy + oh), (0, 255, 0), 2)
    cv2.imwrite(str(out_dir / "after_ocr_roi.png"), after_annotated)

    print(f"OCR ROI: {(ox, oy, ow, oh)}")
    maa = MaaRecognizer()
    name = maa.ocr_region(after, roi=(ox, oy, ow, oh))
    print(f"OCR result: {name!r}")

    print("Clicking slot 0 again to close detail page...")
    if USE_SEPARATE_DOWN_UP:
        mousemove(click_ratio)
        time.sleep(0.05)
        mousedown(click_ratio)
        time.sleep(0.05)
        mouseup(click_ratio)
    else:
        mouseclick(click_ratio)
    time.sleep(0.5)

    print(f"Saved debug images to: {out_dir.resolve()}")
    print("  before.png              - screenshot before click")
    print("  before_click_marker.png - before click with red CLICK marker")
    print("  after.png               - screenshot after click")
    print("  after_ocr_roi.png       - after click with green OCR ROI rectangle")


if __name__ == "__main__":
    main()
