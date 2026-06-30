"""Debug script for MAA recognition in prts-plus.

Run with::

    .venv/Scripts/python -m src.maa.debug_maa

It will:
1. Capture the current game window.
2. Save the raw screenshot to ``debug/maa_capture.png``.
3. Run every state / speed / slot node and print hit + score.
4. Draw all configured ROIs on a copy of the screenshot and save it
   to ``debug/maa_rois.png``.
5. Print the ROI values used by each node.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from src.logger import logger
from src.maa.recognizer import MaaRecognizer, _SPEED_NODES, _STATE_NODES
from src.mumu.mumu_vision import capture_game_window


_DEBUG_DIR = Path("debug")
_CAPTURE_PATH = _DEBUG_DIR / "maa_capture.png"
_ROI_PATH = _DEBUG_DIR / "maa_rois.png"


def _color_for_node(name: str) -> Tuple[int, int, int]:
    """Return a deterministic BGR color for a node name."""
    palette = [
        (0, 0, 255),    # red
        (0, 255, 0),    # green
        (255, 0, 0),    # blue
        (0, 255, 255),  # yellow
        (255, 0, 255),  # magenta
        (255, 255, 0),  # cyan
        (128, 128, 255),
        (128, 255, 128),
        (255, 128, 128),
        (128, 255, 255),
    ]
    return palette[hash(name) % len(palette)]


def _draw_roi(
    image: np.ndarray,
    roi: Tuple[int, int, int, int],
    label: str,
    color: Tuple[int, int, int],
    hit: Optional[bool] = None,
    score: Optional[float] = None,
) -> np.ndarray:
    """Draw a labeled rectangle for an ROI."""
    x, y, w, h = roi
    if w <= 0 or h <= 0:
        return image
    canvas = image.copy()
    cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 2)
    status = "?"
    if hit is True:
        status = f"HIT {score:.3f}" if score is not None else "HIT"
    elif hit is False:
        status = f"miss {score:.3f}" if score is not None else "miss"
    text = f"{label}: {status}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(canvas, (x, y - th - 6), (x + tw + 4, y), color, -1)
    cv2.putText(canvas, text, (x + 2, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return canvas


def main() -> int:
    _DEBUG_DIR.mkdir(exist_ok=True)
    logger.info("=== MAA debug run ===")

    # 1. Initialize recognizer.
    try:
        maa = MaaRecognizer()
    except Exception as exc:
        logger.exception(f"Failed to initialize MAA: {exc}")
        return 1

    # 2. Capture and save raw screenshot.
    try:
        image = capture_game_window(ratio=None, color=True)
        logger.info(f"Captured image shape: {image.shape}")
    except Exception as exc:
        logger.exception(f"Failed to capture: {exc}")
        return 1

    cv2.imwrite(str(_CAPTURE_PATH), image)
    logger.info(f"Raw screenshot saved to: {_CAPTURE_PATH.resolve()}")

    # 3. Run every state/speed node and collect results.
    roi_canvas = image.copy()
    all_nodes: Dict[str, str] = {**_SPEED_NODES, **_STATE_NODES, "DetectSlots": "DetectSlots"}
    results: list[Dict[str, Any]] = []

    for label, node_name in all_nodes.items():
        node = maa._get_node(node_name)
        if node is None:
            logger.warning(f"Node '{node_name}' not found in pipeline")
            continue

        roi = node.get("roi", [0, 0, 0, 0])
        reco_type = node.get("recognition")
        template = node.get("template", "N/A")

        detail = maa._run_node(node_name, image)
        hit = bool(detail.hit) if detail is not None else None
        score = None
        box = None
        if detail is not None:
            score = getattr(detail.best_result, "score", None)
            box = getattr(detail, "box", None)

        results.append({
            "label": label,
            "node": node_name,
            "type": reco_type,
            "roi": roi,
            "template": template,
            "hit": hit,
            "score": score,
            "box": box,
        })

        color = _color_for_node(label)
        roi_canvas = _draw_roi(roi_canvas, tuple(int(v) for v in roi), label, color, hit, score)

    # 4. Save ROI visualization.
    cv2.imwrite(str(_ROI_PATH), roi_canvas)
    logger.info(f"ROI visualization saved to: {_ROI_PATH.resolve()}")

    # 5. Print summary table.
    print("\n" + "=" * 90)
    print(f"{'Label':<16} {'Node':<22} {'Type':<14} {'Hit':<6} {'Score':<8} ROI")
    print("=" * 90)
    for r in results:
        hit_str = {True: "YES", False: "no", None: "ERR"}.get(r["hit"], "?")
        score_str = f"{r['score']:.3f}" if r["score"] is not None else "-"
        roi_str = f"[{', '.join(str(v) for v in r['roi'])}]"
        print(f"{r['label']:<16} {r['node']:<22} {r['type']:<14} {hit_str:<6} {score_str:<8} {roi_str}")

    print("\nTemplate paths used:")
    for r in results:
        if r["type"] == "TemplateMatch":
            print(f"  {r['label']:<16} -> {r['template']}")

    print(f"\nFiles saved:\n  {_CAPTURE_PATH.resolve()}\n  {_ROI_PATH.resolve()}")
    print("Open maa_rois.png to see whether the colored boxes land on the actual UI elements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
