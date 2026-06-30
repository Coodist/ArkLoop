"""Synthetic test: how much does a mouse cursor occluding the operator
avatar degrade template-matching accuracy?

This loads a real avatar, draws a synthetic mouse cursor on top of it at
various positions/sizes, and measures the drop in cv2.matchTemplate score.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from PIL import Image


def load_avatar(path: str, size: tuple = (60, 60)) -> np.ndarray:
    img = Image.open(path).convert("L")
    img = img.resize(size, Image.Resampling.LANCZOS)
    return np.array(img, dtype=np.uint8)


def draw_cursor(
    patch: np.ndarray,
    cx: int,
    cy: int,
    cursor_size: int = 12,
) -> np.ndarray:
    """Draw a simple arrow-shaped cursor onto the patch."""
    out = patch.copy()
    h, w = out.shape[:2]

    # Simple arrow: a white triangle with black outline.
    pts = np.array(
        [
            [cx, cy],
            [cx + cursor_size, cy + cursor_size // 2],
            [cx + cursor_size // 3, cy + cursor_size // 2],
            [cx + cursor_size // 3, cy + cursor_size],
            [cx - cursor_size // 3, cy + cursor_size],
            [cx - cursor_size // 3, cy + cursor_size // 2],
            [cx - cursor_size, cy + cursor_size // 2],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(out, [pts], 255)
    cv2.polylines(out, [pts], True, 0, 1)
    return out


def match_score(patch: np.ndarray, templ: np.ndarray) -> float:
    if templ.shape[0] > patch.shape[0] or templ.shape[1] > patch.shape[1]:
        return 0.0
    result = cv2.matchTemplate(patch, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


def main():
    avatar_path = r"resource\avatar\char_002_amiya.png"
    if not os.path.isfile(avatar_path):
        print(f"Avatar not found: {avatar_path}")
        return

    avatar = load_avatar(avatar_path, size=(60, 60))
    # Template is the same clean avatar (center crop), matching AvatarMatcher logic.
    templ = avatar.copy()

    # Another avatar as negative sample.
    neg_path = r"resource\avatar\char_010_chen.png"
    negative = load_avatar(neg_path, size=(60, 60)) if os.path.isfile(neg_path) else None

    h, w = avatar.shape
    positions = {
        "center": (w // 2, h // 2),
        "upper_left": (w // 4, h // 4),
        "lower_right": (3 * w // 4, 3 * h // 4),
        "edge_top": (w // 2, h // 8),
    }
    cursor_sizes = [8, 12, 16, 20]

    base_score = match_score(avatar, templ)
    print(f"Base score (no occlusion): {base_score:.3f}")
    if negative is not None:
        neg_score = match_score(avatar, negative)
        print(f"Negative sample score: {neg_score:.3f}")
    print()

    print(f"{'position':<15} {'size':>5} {'score':>7} {'drop':>7}")
    print("-" * 45)
    for pos_name, (cx, cy) in positions.items():
        for size in cursor_sizes:
            occluded = draw_cursor(avatar, cx, cy, cursor_size=size)
            score = match_score(occluded, templ)
            drop = base_score - score
            print(f"{pos_name:<15} {size:>5} {score:>7.3f} {drop:>7.3f}")
        print()


if __name__ == "__main__":
    main()
