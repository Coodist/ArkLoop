"""Synthetic test: avatar matching under cursor occlusion with realistic noise.

In addition to the clean test, this adds minor brightness/compression noise
and a border to better approximate the deploy-area patch.
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


def draw_cursor(patch: np.ndarray, cx: int, cy: int, cursor_size: int = 12) -> np.ndarray:
    out = patch.copy()
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


def make_deploy_patch(avatar: np.ndarray, border: int = 4, noise: int = 5) -> np.ndarray:
    """Embed avatar in a larger patch with border and mild noise."""
    h, w = avatar.shape
    patch = np.full((h + 2 * border, w + 2 * border), 60, dtype=np.uint8)
    patch[border:border + h, border:border + w] = avatar
    # Add mild random noise to simulate compression/screen artifacts.
    noise_arr = np.random.randint(-noise, noise + 1, patch.shape, dtype=np.int16)
    patch = np.clip(patch.astype(np.int16) + noise_arr, 0, 255).astype(np.uint8)
    return patch


def match_score(patch: np.ndarray, templ: np.ndarray) -> float:
    if templ.shape[0] > patch.shape[0] or templ.shape[1] > patch.shape[1]:
        return 0.0
    result = cv2.matchTemplate(patch, templ, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


def main():
    avatar_path = r"resource\avatar\char_002_amiya.png"
    neg_path = r"resource\avatar\char_010_chen.png"
    if not os.path.isfile(avatar_path):
        print(f"Avatar not found: {avatar_path}")
        return

    avatar = load_avatar(avatar_path, size=(60, 60))
    templ = avatar.copy()
    negative = load_avatar(neg_path, size=(60, 60)) if os.path.isfile(neg_path) else None

    # Match clean avatar as baseline.
    base_clean = match_score(avatar, templ)
    print(f"Clean avatar base score: {base_clean:.3f}")

    # Match realistic deploy patch (border + noise) as baseline.
    np.random.seed(42)
    patch_no_cursor = make_deploy_patch(avatar, border=4, noise=5)
    base_realistic = match_score(patch_no_cursor, templ)
    print(f"Realistic patch base score: {base_realistic:.3f}")
    if negative is not None:
        neg_realistic = match_score(make_deploy_patch(negative, border=4, noise=5), templ)
        print(f"Negative realistic score: {neg_realistic:.3f}")
    print()

    # Cursor in the center of the avatar.
    # Avatar is at offset (border, border), center is (border + 30, border + 30).
    border = 4
    cx = border + 30
    cy = border + 30
    cursor_sizes = [8, 12, 16, 20]

    print(f"{'scenario':<25} {'size':>5} {'score':>7} {'drop':>7} {'fail':<5}")
    print("-" * 55)

    for size in cursor_sizes:
        np.random.seed(42)
        patch = make_deploy_patch(avatar, border=4, noise=5)
        patch = draw_cursor(patch, cx, cy, cursor_size=size)
        score = match_score(patch, templ)
        drop = base_realistic - score
        fail = "YES" if score < 0.8 else "no"
        print(f"{'cursor center':<25} {size:>5} {score:>7.3f} {drop:>7.3f} {fail:<5}")


if __name__ == "__main__":
    main()
