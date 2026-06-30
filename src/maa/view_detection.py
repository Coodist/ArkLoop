"""OCR-based side-view detector for Arknights.

The detector inspects two fixed screen regions:

1. Stats panel on the left side of an operator detail panel. If any of
   ``攻击`` (attack), ``防御`` (defense), ``法抗`` (resistance) or ``阻挡``
   (block) is visible, the screen is in side view.
2. Skill / trait tabs near the bottom of the operator detail panel. If
   ``技能`` (skill) or ``特性`` (trait) is visible, the screen is in side view.

If either region matches, the frame is classified as side view; otherwise it
is front view.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np

from src.maa import MaaRecognizer


def create_side_view_detector(
    maa: Optional[MaaRecognizer] = None,
    region1: Tuple[int, int, int, int] = (12, 251, 36, 69),
    region1_keywords: Optional[List[str]] = None,
    region2: Tuple[int, int, int, int] = (4, 379, 292, 26),
    region2_keywords: Optional[List[str]] = None,
    threshold: float = 0.3,
) -> Callable[[np.ndarray], bool]:
    """Return a callable ``image -> bool`` that reports side view.

    Args:
        maa: ``MaaRecognizer`` instance. If None, a fresh one is created.
        region1: (x, y, w, h) of the stats panel region.
        region1_keywords: Text tokens that indicate side view in region 1.
        region2: (x, y, w, h) of the skill/trait tab region.
        region2_keywords: Text tokens that indicate side view in region 2.
        threshold: OCR confidence threshold.

    Returns:
        A function that takes a BGR numpy image and returns True for side view.
    """
    if maa is None:
        maa = MaaRecognizer()

    if region1_keywords is None:
        region1_keywords = ["攻击", "防御", "法抗", "阻挡"]
    if region2_keywords is None:
        region2_keywords = ["技能", "特性"]

    def _has_keyword(image: np.ndarray, roi: Tuple[int, int, int, int], keywords: List[str]) -> bool:
        results = maa.ocr_region(image, roi=roi, return_all=True)
        if not results:
            return False
        for r in results:
            text = r.get("text", "")
            for kw in keywords:
                if kw in text:
                    return True
        return False

    def detect(image: np.ndarray) -> bool:
        return _has_keyword(image, region1, region1_keywords) or _has_keyword(
            image, region2, region2_keywords
        )

    return detect
