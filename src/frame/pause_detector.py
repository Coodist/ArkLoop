"""Pause detection for recorded gameplay frames.

The detector tries a lightweight OCR pass for the ``PAUSE`` text shown in the
center of the screen when the game is paused, and falls back to a brightness
contrast heuristic if OCR is unavailable or inconclusive.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np
from PIL import Image

try:
    import tesserocr
except Exception:  # pragma: no cover - tesserocr may be missing in some envs
    tesserocr = None

from src.config import ImageProcessingConfig as imgconfig
from src.logger import logger
from src.utils.tessdata import resolve_tessdata_path

__all__ = ["is_paused", "mark_stuck_ticks_as_paused", "PauseDetector"]


_TESSDATA_PATH = resolve_tessdata_path(check_for_lang="eng")

# Center ROI where the pause menu text appears.
# PAUSE text is large and can extend beyond a tight center crop, so we use a
# generous horizontal window and a moderate vertical one.
PAUSE_ROI_LEFT = 0.25
PAUSE_ROI_TOP = 0.30
PAUSE_ROI_RIGHT = 0.75
PAUSE_ROI_BOTTOM = 0.70

# Target height for the resized ROI before OCR.  Tesseract works best with
# text line height around 30-50 px; the raw in-game PAUSE text is much larger.
PAUSE_OCR_TARGET_HEIGHT = 150

# Minimum OCR confidence to trust a ``PAUSE`` detection.
PAUSE_OCR_CONFIDENCE = 60

# Brightness fallback: if the center of the screen is significantly darker
# than the surrounding border, we treat the frame as paused.
PAUSE_CENTER_DARK_RATIO = 0.55
PAUSE_CENTER_DARK_MAX = 100


def _to_gray(frame: Union[np.ndarray, Image.Image]) -> np.ndarray:
    """Convert a frame to a grayscale ``uint8`` numpy array."""
    if isinstance(frame, Image.Image):
        frame = frame.convert("RGB")
        frame = np.array(frame)

    if frame.ndim == 2:
        return frame.astype(np.uint8)

    # BGR / BGRA / RGB -> gray
    if frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _crop_center_roi(
    gray: np.ndarray,
    left: float = PAUSE_ROI_LEFT,
    top: float = PAUSE_ROI_TOP,
    right: float = PAUSE_ROI_RIGHT,
    bottom: float = PAUSE_ROI_BOTTOM,
) -> np.ndarray:
    """Crop the central pause-text ROI from a grayscale frame."""
    h, w = gray.shape[:2]
    x1, y1 = int(w * left), int(h * top)
    x2, y2 = int(w * right), int(h * bottom)
    return gray[y1:y2, x1:x2]


def _ocr_says_pause(roi: np.ndarray, confidence_threshold: int = PAUSE_OCR_CONFIDENCE) -> bool:
    """Run OCR on the ROI and look for the word ``PAUSE``.

    The in-game PAUSE text is very large and spans a wide horizontal band, so
    we Otsu-threshold and down-scale the ROI before giving it to Tesseract.
    """
    if tesserocr is None:
        return False

    try:
        # Otsu adapts to the local brightness of the pause overlay.
        _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Tesseract is most comfortable with text line height around 30-50 px.
        scale = PAUSE_OCR_TARGET_HEIGHT / max(binary.shape[0], 1)
        if scale < 1.0:
            binary = cv2.resize(
                binary, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
            )

        pil = Image.fromarray(binary)
        kwargs: Dict[str, Any] = {
            "lang": "eng",
            "psm": tesserocr.PSM.SINGLE_LINE,
        }
        if _TESSDATA_PATH is not None:
            kwargs["path"] = str(_TESSDATA_PATH)
        with tesserocr.PyTessBaseAPI(**kwargs) as api:
            api.SetImage(pil)
            text = api.GetUTF8Text() or ""
            confidence = api.MeanTextConf()
    except Exception as exc:
        logger.debug(f"Pause OCR failed: {exc}")
        return False

    cleaned = re.sub(r"[^A-Z]", "", text.upper())
    logger.debug(f"Pause OCR text='{text.strip()}', cleaned='{cleaned}', confidence={confidence}")

    # Accept if the cleaned text is exactly PAUSE (most reliable).
    if cleaned == "PAUSE":
        return True

    # Otherwise fall back to confidence-based detection.
    if "PAUSE" in cleaned and confidence >= confidence_threshold:
        return True

    return False


def _brightness_heuristic(gray: np.ndarray) -> bool:
    """Fallback pause detection based on center-vs-border brightness."""
    h, w = gray.shape[:2]
    cx1, cy1 = int(w * PAUSE_ROI_LEFT), int(h * PAUSE_ROI_TOP)
    cx2, cy2 = int(w * PAUSE_ROI_RIGHT), int(h * PAUSE_ROI_BOTTOM)

    center = gray[cy1:cy2, cx1:cx2]
    if center.size == 0:
        return False

    # Border is the outer ring around the center ROI.
    border_left = gray[cy1:cy2, max(0, cx1 - 1):cx1]
    border_right = gray[cy1:cy2, cx2:min(w, cx2 + 1)]
    border_top = gray[max(0, cy1 - 1):cy1, cx1:cx2]
    border_bottom = gray[cy2:min(h, cy2 + 1), cx1:cx2]

    border_parts = [p for p in (border_left, border_right, border_top, border_bottom) if p.size > 0]
    if not border_parts:
        return False

    border_mean = float(np.mean(np.concatenate([p.ravel() for p in border_parts])))
    center_mean = float(np.mean(center))

    logger.debug(
        f"Pause brightness fallback: center_mean={center_mean:.1f}, "
        f"border_mean={border_mean:.1f}"
    )

    if center_mean < PAUSE_CENTER_DARK_MAX and center_mean < PAUSE_CENTER_DARK_RATIO * border_mean:
        return True
    return False


def is_paused(frame: Union[np.ndarray, Image.Image]) -> bool:
    """Return ``True`` if the frame shows the in-game pause overlay.

    Args:
        frame: A video frame as ``np.ndarray`` (BGR/BGRA/gray) or ``PIL.Image``.

    Returns:
        ``True`` if paused, ``False`` otherwise.
    """
    try:
        gray = _to_gray(frame)
    except Exception as exc:
        logger.warning(f"Failed to convert frame for pause detection: {exc}")
        return False

    roi = _crop_center_roi(gray)
    if _ocr_says_pause(roi):
        logger.debug("Pause detected via OCR")
        return True

    if _brightness_heuristic(gray):
        logger.debug("Pause detected via brightness fallback")
        return True

    return False


def mark_stuck_ticks_as_paused(
    frames: List[Dict[str, Any]],
    consecutive_threshold: int = 10,
) -> int:
    """Mark long runs of identical ticks as paused.

    When the game enters bullet time, the cost bar tick advances much slower
    than normal (roughly 3 ticks per second at 30fps, i.e. ~10 frames per
    tick).  Normal gameplay advances one tick per frame.  Therefore, if the
    detected tick stays unchanged for ``consecutive_threshold`` or more
    consecutive video frames, it is almost certainly bullet time or a true
    pause, and we conservatively mark the whole run as ``paused=True``.

    Args:
        frames: Per-frame dicts from ``OfflineScanner``, each containing at
            least ``"tick"`` and ``"paused"`` keys.
        consecutive_threshold: Minimum number of consecutive frames with the
            same non-``None`` tick before marking them paused.

    Returns:
        Number of frames newly marked as paused.
    """
    if not frames:
        return 0

    changed = 0
    run_start = 0
    run_tick: Optional[int] = None

    def _flush(end: int) -> None:
        nonlocal changed
        length = end - run_start
        if run_tick is None or length < consecutive_threshold:
            return
        for idx in range(run_start, end):
            if not frames[idx]["paused"]:
                frames[idx]["paused"] = True
                changed += 1
        logger.debug(
            f"Bullet-time heuristic: tick={run_tick} stuck for {length} frames, "
            f"marked {changed} frames as paused"
        )

    for i, frame in enumerate(frames):
        tick = frame.get("tick")
        if tick != run_tick:
            _flush(i)
            run_start = i
            run_tick = tick

    _flush(len(frames))
    return changed


class PauseDetector:
    """Stateful pause detector with an optional rolling average.

    Useful when a single-frame heuristic flickers; ``update`` returns the
    majority vote over the last ``window_size`` observations.
    """

    def __init__(self, window_size: int = 1):
        if window_size < 1:
            raise ValueError("window_size must be positive")
        self.window_size = window_size
        self._history: list[bool] = []

    def update(self, frame: Union[np.ndarray, Image.Image]) -> bool:
        """Update rolling history and return current paused state."""
        paused = is_paused(frame)
        self._history.append(paused)
        if len(self._history) > self.window_size:
            self._history.pop(0)
        return sum(self._history) > len(self._history) // 2

    def reset(self) -> None:
        """Clear rolling history."""
        self._history.clear()

    @property
    def paused(self) -> bool:
        """Current rolling-averaged paused state."""
        if not self._history:
            return False
        return sum(self._history) > len(self._history) // 2
