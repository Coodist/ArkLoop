"""Visualize MAA-detected operator slot layout and recognize each slot.

This debug script now validates the main-flow slot-detection pipeline by
reusing the same helpers that ``MaaRecognizer.detect_slot_layout`` uses
internally.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make imports from repo root work when running the script directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.config import SlotDetectionConfig
from src.logger import logger
from src.maa import MaaRecognizer
from src.maa.slot_layout import compute_mouse_zones, deduplicate_slot_flags
from src.mumu.mumu_vision import capture_game_window
from recorder.action_recognizer import AvatarMatcher


def _color_for_index(i: int) -> Tuple[int, int, int]:
    palette = [
        (0, 0, 255),
        (0, 255, 0),
        (255, 0, 0),
        (0, 255, 255),
        (255, 0, 255),
        (255, 255, 0),
    ]
    return palette[i % len(palette)]


def _load_chinese_font(size: int = 18) -> Optional[ImageFont.FreeTypeFont]:
    """Try common Windows Chinese fonts; return None if none load."""
    candidates = [
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return None


def _draw_text_on_bgr(
    image: np.ndarray,
    text: str,
    org: Tuple[int, int],
    color_bgr: Tuple[int, int, int] = (0, 255, 0),
    font_size: int = 18,
) -> np.ndarray:
    """Draw text on a BGR image, using PIL for Chinese and cv2 as fallback."""
    font = _load_chinese_font(font_size)
    if font is None:
        ascii_text = text.encode("ascii", "ignore").decode("ascii") or "?"
        x, y = org
        cv2.putText(
            image,
            ascii_text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color_bgr,
            2,
            cv2.LINE_AA,
        )
        return image

    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)
    color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
    draw.text(org, text, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def _draw_slot_label(
    canvas: np.ndarray,
    box: Tuple[int, int, int, int],
    label: str,
    color: Tuple[int, int, int],
) -> np.ndarray:
    """Draw a label above or inside a slot box."""
    x1, y1, x2, y2 = box
    margin = 2
    text_org = (x1 + margin, max(y1 - 22, margin))
    if text_org[1] < 10:
        text_org = (x1 + margin, y1 + margin + 18)
    return _draw_text_on_bgr(canvas, label, text_org, color_bgr=color)


def _parse_int(text: Optional[str]) -> Optional[int]:
    """Strictly parse OCR text as an integer."""
    if text is None:
        return None
    try:
        return int(text.strip())
    except Exception:
        return None


@contextlib.contextmanager
def _quiet_logger():
    """Temporarily raise the shared logger level to WARNING."""
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        logger.setLevel(old_level)


def _flag_center(flag: Dict[str, Any], w: int, h: int) -> Tuple[float, float]:
    x, y, fw, fh = flag["box"]
    return (x + fw / 2.0) / w, (y + fh / 2.0) / h


def _id_set(flags: List[Dict[str, Any]]) -> set[int]:
    return {id(f) for f in flags}


def _norm_to_pixel(
    rect: Tuple[float, float, float, float], w: int, h: int
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = rect
    return (
        int(max(0.0, x1) * w),
        int(max(0.0, y1) * h),
        int(min(1.0, x2) * w),
        int(min(1.0, y2) * h),
    )


def _ocr_roi_around_flag_center(
    cx: float, cy: float
) -> Tuple[float, float, float, float]:
    half = SlotDetectionConfig.OCR_ROI_HALF_WIDTH
    top = SlotDetectionConfig.OCR_ROI_TOP_OFFSET
    bottom = SlotDetectionConfig.OCR_ROI_BOTTOM_OFFSET
    return (cx - half, cy + top, cx + half, cy + bottom)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visualize slot layout and avatar matching using the main-flow pipeline."
    )
    parser.add_argument(
        "--mouse-zone",
        action="store_true",
        help="Draw mouse-click judgment zones instead of detection crop/OCR boxes.",
    )
    args = parser.parse_args()

    cfg = SlotDetectionConfig
    logger.info("=== Slot layout visualization (main-flow pipeline) ===")

    logger.info("Initializing MAA recognizer...")
    with _quiet_logger():
        maa = MaaRecognizer()

    logger.info("Loading avatar matcher...")
    with _quiet_logger():
        matcher = AvatarMatcher()
        loaded_count = matcher.prewarm()
    logger.info(f"Avatar templates loaded for {loaded_count} operators")

    logger.info("Capturing screenshot...")
    image = capture_game_window(ratio=None, color=True)
    h, w = image.shape[:2]
    logger.info(f"Image size: {w}x{h}")

    # 1. Detect raw flags (same as main flow).
    raw_flags = maa.detect_slot_flags(image)
    all_flags = sorted(raw_flags, key=lambda f: f["box"][0])
    logger.info(f"Raw detected {len(all_flags)} flag(s)")

    # 2. X-gap deduplication (same helper as main flow).
    dedup_flags = deduplicate_slot_flags(
        all_flags, w, h, min_x_gap=cfg.MIN_FLAG_X_GAP
    )
    dedup_dropped = [f for f in all_flags if id(f) not in _id_set(dedup_flags)]
    logger.info(f"After x-gap dedup: {len(dedup_flags)} flag(s), dropped {len(dedup_dropped)}")
    for f in dedup_dropped:
        cx, cy = _flag_center(f, w, h)
        print(f"  [x-gap drop] pixel=({int(cx*w)},{int(cy*h)}) ratio=({cx:.4f},{cy:.4f})")

    # 3. Mouse-zone validation (same helper as main flow).
    zone_flags, zones = compute_mouse_zones(
        dedup_flags,
        w,
        h,
        midline_offset=cfg.MOUSE_ZONE_MIDLINE_OFFSET,
        bottom_offset=cfg.MOUSE_ZONE_BOTTOM_OFFSET,
        min_x_gap=cfg.MIN_FLAG_X_GAP,
    )
    zone_dropped = [f for f in dedup_flags if id(f) not in _id_set(zone_flags)]
    logger.info(
        f"After mouse-zone validation: {len(zone_flags)} zone(s), dropped {len(zone_dropped)}"
    )
    for f in zone_dropped:
        cx, cy = _flag_center(f, w, h)
        print(f"  [zone drop] pixel=({int(cx*w)},{int(cy*h)}) ratio=({cx:.4f},{cy:.4f})")

    # 4. Run OCR + avatar matching on every validated zone.
    # detect_slot_layout() below no longer drops zones when OCR fails; it keeps
    # them and logs a warning. We replicate that behavior here.
    zone_results: List[Dict[str, Any]] = []
    print(f"\nRunning OCR/avatar matching on {len(zones)} validated zone(s)...")
    for i, (flag, zone) in enumerate(zip(zone_flags, zones)):
        cx, cy = zone["cx"], zone["cy"]
        ocr_rect = _ocr_roi_around_flag_center(cx, cy)
        ox1, oy1, ox2, oy2 = _norm_to_pixel(ocr_rect, w, h)
        raw_text = maa.ocr_region(
            image,
            roi=(ox1, oy1, ox2 - ox1, oy2 - oy1),
            return_all=True,
        )
        raw_best = raw_text[0]["text"] if raw_text else ""
        cost = _parse_int(raw_best)
        used_fallback = False
        if cost is None:
            fallback_text = maa.ocr_cost_in_zone(
                image,
                roi=(ox1, oy1, ox2 - ox1, oy2 - oy1),
            )
            if fallback_text and fallback_text != raw_best:
                used_fallback = True
            cost = _parse_int(fallback_text)
            best_text = fallback_text if fallback_text is not None else ""
        else:
            best_text = raw_best

        ocr_failed = cost is None
        px1, py1, px2, py2 = _norm_to_pixel(
            (zone["left"], zone["top"], zone["right"], zone["bottom"]), w, h
        )

        crop = (
            image[py1:py2, px1:px2]
            if px2 > px1 and py2 > py1
            else None
        )
        name: Optional[str] = None
        score = 0.0
        if crop is not None and crop.size > 0:
            name, score = matcher.match_slot(crop)
        label = f"{name} {score:.2f}" if name is not None else f"? {score:.2f}"
        if used_fallback:
            label += " [FB]"
        if ocr_failed:
            label += " [OCR_FAIL]"

        print(
            f"  Zone {i}: center=({cx:.4f},{cy:.4f}) "
            f"ocr={best_text!r} parsed={cost} match={label}"
        )
        if ocr_failed:
            logger.warning(
                f"Zone {i} at ({cx:.4f},{cy:.4f}) passed flag+zone checks "
                f"but OCR unreadable (ocr={best_text!r}); keeping box"
            )

        zone_results.append(
            {
                "status": "passed",
                "zone": zone,
                "box_px": (px1, py1, px2, py2),
                "ocr_rect_px": (ox1, oy1, ox2, oy2),
                "cost": cost,
                "label": label,
                "ocr_text": best_text,
                "fallback": used_fallback,
                "ocr_failed": ocr_failed,
            }
        )

    passed_results = [r for r in zone_results if not r["ocr_failed"]]
    ocr_failed_results = [r for r in zone_results if r["ocr_failed"]]
    excluded_results: List[Dict[str, Any]] = []
    logger.info(
        f"Zones: {len(passed_results)} OCR-OK, {len(ocr_failed_results)} OCR-failed (kept)"
    )

    # 5. Verify against the main-flow detect_slot_layout() result.
    layout = maa.detect_slot_layout(image)
    main_flow_count = layout.get("count", 0) if layout is not None else 0
    logger.info(f"Main-flow detect_slot_layout returned {main_flow_count} slot(s)")
    if main_flow_count != len(zone_results):
        logger.warning(
            f"Mismatch: script counted {len(zone_results)} kept zones, "
            f"main flow returned {main_flow_count}"
        )

    canvas = image.copy()

    def _draw_flag_dot(flag: Dict[str, Any], color: Tuple[int, int, int]) -> None:
        cx, cy = _flag_center(flag, w, h)
        cv2.circle(canvas, (int(cx * w), int(cy * h)), 5, color, -1)

    # Draw dropped flags first.
    for f in dedup_dropped:
        _draw_flag_dot(f, (0, 0, 255))  # red: x-gap excluded
    for f in zone_dropped:
        _draw_flag_dot(f, (255, 0, 0))  # blue: mouse-zone validation excluded

    # Draw all validated flag centers yellow (all are kept now).
    for r in zone_results:
        cx, cy = r["zone"]["cx"], r["zone"]["cy"]
        cv2.circle(canvas, (int(cx * w), int(cy * h)), 6, (0, 255, 255), -1)

    if args.mouse_zone:
        logger.info("Drawing mode: mouse-click judgment zones")
        # Draw mouse-click judgment zones.
        for i, r in enumerate(passed_results):
            box_px = r["box_px"]
            if box_px[2] <= box_px[0] or box_px[3] <= box_px[1]:
                continue
            color = _color_for_index(i)
            cv2.rectangle(
                canvas, (box_px[0], box_px[1]), (box_px[2], box_px[3]), color, 2
            )
            canvas = _draw_slot_label(canvas, box_px, r["label"], color)

        for r in ocr_failed_results:
            box_px = r["box_px"]
            if box_px[2] <= box_px[0] or box_px[3] <= box_px[1]:
                continue
            cv2.rectangle(
                canvas, (box_px[0], box_px[1]), (box_px[2], box_px[3]), (0, 165, 255), 2
            )
            canvas = _draw_slot_label(canvas, box_px, r["label"], (0, 165, 255))
    else:
        logger.info("Drawing mode: OCR boxes (default)")
        # Draw zone boxes and OCR regions with thicker, more visible lines.
        for r in passed_results:
            box_px = r["box_px"]
            if box_px[2] > box_px[0] and box_px[3] > box_px[1]:
                cv2.rectangle(
                    canvas, (box_px[0], box_px[1]), (box_px[2], box_px[3]), (0, 255, 0), 2
                )
                canvas = _draw_slot_label(canvas, box_px, r["label"], (0, 255, 0))

            ox1, oy1, ox2, oy2 = r["ocr_rect_px"]
            if ox2 > ox1 and oy2 > oy1:
                cv2.rectangle(
                    canvas, (ox1, oy1), (ox2, oy2), (0, 255, 255), 2
                )
                ocr_label = f"ocr='{r['ocr_text']}'"
                canvas = _draw_slot_label(
                    canvas, (ox1, oy1, ox2, oy2), ocr_label, (0, 255, 255)
                )

        # OCR-failed zones: orange box + orange OCR ROI.
        for r in ocr_failed_results:
            box_px = r["box_px"]
            if box_px[2] > box_px[0] and box_px[3] > box_px[1]:
                cv2.rectangle(
                    canvas, (box_px[0], box_px[1]), (box_px[2], box_px[3]), (0, 165, 255), 2
                )
                canvas = _draw_slot_label(canvas, box_px, r["label"], (0, 165, 255))

            ox1, oy1, ox2, oy2 = r["ocr_rect_px"]
            if ox2 > ox1 and oy2 > oy1:
                cv2.rectangle(
                    canvas, (ox1, oy1), (ox2, oy2), (0, 165, 255), 2
                )
                ocr_label = f"ocr='{r['ocr_text']}'"
                canvas = _draw_slot_label(
                    canvas, (ox1, oy1, ox2, oy2), ocr_label, (0, 165, 255)
                )

    out_dir = Path("debug")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "slot_layout.png"
    cv2.imwrite(str(out_path), canvas)
    logger.info(f"Saved visualization to: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
