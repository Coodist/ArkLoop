"""Utilities for creating MAA template images from screenshots.

MAA template matching works best with small, tightly-cropped PNGs that
contain only the UI element of interest. See AAO docs section 11 for best
practices.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.mumu.mumu_vision import capture_game_window

__all__ = ["crop_template", "make_template_from_screenshot"]


def crop_template(
    image: np.ndarray,
    roi: Tuple[int, int, int, int],
    save_path: Union[str, Path],
) -> Path:
    """Crop a region from a BGR image and save it as a PNG template.

    Args:
        image: BGR numpy array (H, W, 3).
        roi: (x, y, w, h) crop region.
        save_path: Destination path for the PNG file.

    Returns:
        The path to the saved template.
    """
    x, y, w, h = roi
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        raise ValueError(f"Invalid ROI: {roi}")

    cropped = image[y : y + h, x : x + w]
    if cropped.size == 0:
        raise ValueError(f"ROI {roi} is outside image shape {image.shape}")

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(save_path), cropped)
    return save_path


def make_template_from_screenshot(
    save_path: Union[str, Path],
    roi: Optional[Tuple[int, int, int, int]] = None,
    ratio: Optional[Tuple[float, float, float, float]] = None,
) -> Path:
    """Capture a screenshot and save a region as a PNG template.

    Args:
        save_path: Destination path for the PNG file.
        roi: Optional (x, y, w, h) pixel region on the captured image.
            If None, the entire captured image is saved.
        ratio: Optional relative crop region passed to ``capture_game_window``.
            Ignored if ``roi`` is provided.

    Returns:
        The path to the saved template.
    """
    from src.mumu.mumu_vision import capture_game_window

    image = capture_game_window(ratio=ratio, color=True)
    if roi is None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(save_path), image)
        return save_path
    return crop_template(image, roi, save_path)
