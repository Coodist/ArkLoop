"""Crop saved avatar templates with custom offsets for testing.

Run with::

    .venv\Scripts\python scripts/crop_avatar_test.py &\
        --offsets -0.0398 0.0172 0.043 0.1653 &\
        --unit 令

Loads all avatar templates for the given operator, crops each one using the
provided center-relative offsets (left, right, top, bottom), and saves the
results to debug/crop_avatar_test/.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple

import cv2
import glob
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cache import OPERATOR_MAPPING, RESOURCE_PATH


def _parse_offsets(parts: list[str]) -> Tuple[float, float, float, float]:
    if len(parts) != 4:
        raise ValueError("--offsets must be followed by 4 values: left right top bottom")
    return tuple(float(p) for p in parts)


def _crop_centered(
    image: np.ndarray,
    offsets: Tuple[float, float, float, float],
) -> np.ndarray:
    """Crop image using center-relative ratios: (left, right, top, bottom)."""
    h, w = image.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    left, right, top, bottom = offsets

    x1 = int(cx + left * w)
    x2 = int(cx + right * w)
    y1 = int(cy + top * h)
    y2 = int(cy + bottom * h)

    x1 = max(0, min(w, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h, y1))
    y2 = max(0, min(h, y2))

    if x2 <= x1:
        x2 = x1 + 1
    if y2 <= y1:
        y2 = y1 + 1

    return image[y1:y2, x1:x2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Crop avatar templates for testing.")
    parser.add_argument(
        "--offsets",
        type=str,
        nargs=4,
        required=True,
        metavar=("LEFT", "RIGHT", "TOP", "BOTTOM"),
        help="Center-relative crop offsets as 4 ratios: left right top bottom.",
    )
    parser.add_argument(
        "--unit",
        type=str,
        required=True,
        help="Operator/unit name to load avatars for.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="debug/crop_avatar_test",
        help="Directory to save cropped images.",
    )
    args = parser.parse_args()

    offsets = _parse_offsets(args.offsets)
    print(f"Cropping avatars for '{args.unit}' with offsets {offsets}")

    try:
        filename = OPERATOR_MAPPING[args.unit]
    except KeyError:
        print(f"No operator mapping found for '{args.unit}'")
        return 1

    avatar_dir = os.path.join(RESOURCE_PATH, "avatar")
    filepaths = sorted(glob.glob(f"{avatar_dir}/*{filename}*"))
    if not filepaths:
        print(f"No avatar files found for '{args.unit}' (pattern: *{filename}*)")
        return 1

    avatars = [cv2.imread(p, cv2.IMREAD_GRAYSCALE) for p in filepaths]
    avatars = [a for a in avatars if a is not None]
    if not avatars:
        print(f"Failed to load any avatar images for '{args.unit}'")
        return 1

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, avatar in enumerate(avatars):
        cropped = _crop_centered(avatar, offsets)
        out_path = out_dir / f"{args.unit}_{i:02d}.png"
        cv2.imwrite(str(out_path), cropped)
        h, w = cropped.shape[:2]
        print(f"  Saved {out_path} ({w}x{h})")

    print(f"\nDone. {len(avatars)} image(s) saved to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
