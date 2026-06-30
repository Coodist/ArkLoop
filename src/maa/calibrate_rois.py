"""Interactive ROI calibration for MAA pipeline nodes.

Run with::

    .venv/Scripts/python -m src.maa.calibrate_rois

Usage:
1. Make sure the game is in the state you want to calibrate for
   (e.g. paused battle with slots visible).
2. Run this script. It will capture a fresh screenshot or load
   ``debug/maa_capture.png`` if it exists.
3. For each listed node, an OpenCV window appears. Drag a rectangle
   around the UI element, then press SPACE or click "OK" to confirm.
   Press ``c`` to cancel and keep the current ROI.
4. When all nodes are done, corrected ROIs are written to
   ``src/maa/nodes/pipeline/prts_plus_override.json``.
5. Run ``.venv/Scripts/python -m src.maa.debug_maa`` again to verify.

Tip: You can edit ``_NODES_TO_CALIBRATE`` below to add/remove nodes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.logger import logger
from src.maa.recognizer import _get_pipeline
from src.mumu.mumu_vision import capture_game_window


# Nodes to calibrate, with a short hint for the user.
_NODES_TO_CALIBRATE: List[Tuple[str, str]] = [
    ("BattlePaused", "top-right play/triangle button when paused"),
    ("Speed1x", "top-right 1x speed indicator"),
    ("Speed2x", "top-right 2x speed indicator"),
    ("Farm@BattleOn", "in-battle indicator (top area)"),
    ("Farm@Settlement", "settlement screen label/area"),
    ("Farm@Stars3", "3-star reward mark"),
    ("Farm@StarsNo3", "0/2-star reward mark"),
    ("Farm@MissionFailed", "mission failed popup"),
    ("Farm@LeakDetect", "HP/leak indicator (top-middle bar area)"),
    ("Farm@Abandon", "top-left settings/gear icon"),
    ("DetectSlots", "bottom operator avatar bar"),
]

_OVERRIDE_PATH = Path(__file__).resolve().parent / "prts_plus_override.json"


def _maybe_migrate_old_override() -> None:
    """Move any override accidentally placed inside the pipeline directory."""
    old_path = Path(__file__).resolve().parent / "nodes" / "pipeline" / "prts_plus_override.json"
    if old_path.exists() and not _OVERRIDE_PATH.exists():
        try:
            old_path.rename(_OVERRIDE_PATH)
            logger.info(f"Migrated old override from {old_path} to {_OVERRIDE_PATH}")
        except Exception as exc:
            logger.warning(f"Failed to migrate old override: {exc}")


def _load_image() -> np.ndarray:
    """Load existing debug capture or capture a fresh screenshot."""
    existing = Path("debug") / "maa_capture.png"
    if existing.exists():
        logger.info(f"Loading existing capture: {existing.resolve()}")
        image = cv2.imread(str(existing))
        if image is not None:
            return image
    logger.info("Capturing fresh screenshot...")
    return capture_game_window(ratio=None, color=True)


def _draw_roi_hint(
    image: np.ndarray,
    roi: Tuple[int, int, int, int],
    label: str,
    description: str,
) -> np.ndarray:
    """Draw the current ROI and instructions on a copy of the image."""
    canvas = image.copy()
    x, y, w, h = roi
    if w > 0 and h > 0:
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cv2.putText(
            canvas,
            f"current: {label}",
            (x, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )

    instructions = [
        f"Calibrating: {label}",
        f"Hint: {description}",
        "Drag rectangle, then SPACE/OK to confirm, 'c' to keep current",
    ]
    y0 = 30
    for i, line in enumerate(instructions):
        cv2.putText(
            canvas,
            line,
            (10, y0 + i * 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )
    return canvas


def _select_roi(image: np.ndarray, node_name: str, description: str, current_roi: List[int]) -> List[int]:
    """Open cv2.selectROI and return the new ROI."""
    display = _draw_roi_hint(image, tuple(current_roi), node_name, description)
    roi = cv2.selectROI(f"Calibrate {node_name}", display, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(f"Calibrate {node_name}")

    x, y, w, h = (int(v) for v in roi)
    if w <= 0 or h <= 0:
        logger.info(f"  {node_name}: cancelled, keeping {current_roi}")
        return current_roi
    logger.info(f"  {node_name}: updated ROI to [{x}, {y}, {w}, {h}]")
    return [x, y, w, h]


def main() -> int:
    logger.info("=== MAA ROI calibration ===")
    _maybe_migrate_old_override()

    image = _load_image()
    logger.info(f"Image shape: {image.shape}")

    pipeline = _get_pipeline()
    existing_override: Dict[str, Dict[str, any]] = {}
    if _OVERRIDE_PATH.exists():
        try:
            existing_override = json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not read existing override: {exc}")

    override: Dict[str, Dict[str, any]] = {}

    for node_name, description in _NODES_TO_CALIBRATE:
        node = pipeline.get(node_name)
        if node is None:
            logger.warning(f"Node '{node_name}' not found in pipeline, skipping")
            continue

        # Show the effective ROI: base node + existing override.
        current_roi = list(node.get("roi", [0, 0, 0, 0]))
        if node_name in existing_override:
            current_roi = list(existing_override[node_name].get("roi", current_roi))
        if not isinstance(current_roi, list) or len(current_roi) != 4:
            current_roi = [0, 0, 0, 0]

        new_roi = _select_roi(image, node_name, description, current_roi)
        if new_roi != current_roi:
            override[node_name] = {"roi": new_roi}

    # Merge with any existing override so we don't lose previous corrections.
    existing: Dict[str, Dict[str, any]] = {}
    if _OVERRIDE_PATH.exists():
        try:
            existing = json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not read existing override: {exc}")

    existing.update(override)

    _OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDE_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Saved ROI overrides to: {_OVERRIDE_PATH.resolve()}")

    # Clear pipeline cache so the new override is picked up immediately.
    import src.maa.recognizer as recognizer_module
    recognizer_module._pipeline_cache = None

    print("\nNext steps:")
    print("  1. .venv/Scripts/python -m src.maa.debug_maa")
    print("  2. Check debug/maa_rois.png to confirm boxes now land on the UI elements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
