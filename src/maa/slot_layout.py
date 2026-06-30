"""Slot-layout helpers for MAA-based operator bar parsing.

``MaaRecognizer.detect_slot_layout`` returns normalized bounding boxes for
each operator card in the bottom deploy bar. This module provides convenience
functions to map a click/drag position to a slot and to crop a slot region.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


def slot_index_at(layout: Dict[str, Any], ratio: Tuple[float, float]) -> Optional[int]:
    """Return the slot index containing ``ratio`` (x, y), or None.

    Each box is treated as a 2-D mouse zone: a click must be inside both the
    horizontal span ``[left, right)`` and the vertical span ``[top, bottom)``.
    """
    x, y = ratio
    boxes = layout.get("boxes", [])
    if not boxes:
        return None
    for i, (left, top, right, bottom) in enumerate(boxes):
        if top <= y < bottom and left <= x < right:
            return i
    return None


def crop_slot(
    image: np.ndarray,
    layout: Dict[str, Any],
    slot_index: int,
) -> Optional[np.ndarray]:
    """Crop the ``slot_index``-th slot region from ``image``.

    Returns a grayscale image or None if the index is out of range.
    """
    boxes = layout.get("boxes", [])
    if slot_index < 0 or slot_index >= len(boxes):
        return None

    h, w = image.shape[:2]
    left, top, right, bottom = boxes[slot_index]
    x1, y1 = int(left * w), int(top * h)
    x2, y2 = int(right * w), int(bottom * h)
    cropped = image[y1:y2, x1:x2]
    if cropped.ndim == 3:
        cropped = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    return cropped


def deduplicate_slot_flags(
    flags: List[Dict[str, Any]],
    image_width: int,
    image_height: int,
    min_x_gap: float = 0.04,
) -> List[Dict[str, Any]]:
    """Remove vertically upper flag when two flags are horizontally too close.

    Flags are sorted left-to-right. A flag is dropped when it is within
    ``min_x_gap`` of the most recent kept flag and has a smaller y (is higher
    on screen). This sliding-window rule prevents a long chain of close flags
    from transitively dropping a flag that is actually far from the final
    survivor.

    Flags with exactly the same y coordinate are kept as separate candidates.
    """
    if not flags:
        return []

    centers = []
    for f in flags:
        x, y, fw, fh = f["box"]
        cx = (x + fw / 2.0) / image_width
        cy = (y + fh / 2.0) / image_height
        centers.append((cx, cy, f))

    centers.sort(key=lambda t: t[0])

    kept_centers: List[Tuple[float, float, Dict[str, Any]]] = [centers[0]]
    for c in centers[1:]:
        last_cx, last_cy, _ = kept_centers[-1]
        # y exactly equal -> not a duplicate, keep as separate slot.
        if c[1] == last_cy or c[0] - last_cx >= min_x_gap:
            kept_centers.append(c)
        else:
            # Same x-band and different y: keep the lower one (larger cy).
            if c[1] > last_cy:
                kept_centers[-1] = c

    kept = [c[2] for c in kept_centers]
    return kept


def compute_mouse_zones(
    flags: List[Dict[str, Any]],
    image_width: int,
    image_height: int,
    midline_offset: float = 0.0117,
    bottom_offset: float = 0.1653,
    min_x_gap: float = 0.04,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Compute mouse-click judgment zones from deduplicated flag centers.

    Zones are computed **right-to-left**:
      - The rightmost zone extends to the right window edge (x = 1.0).
      - Each subsequent zone's right border = the left border of the zone to
        its right.
      - Vertical split midline: x = cx - ``midline_offset``.
      - Left border = mirrored around the midline: left = 2 * midline - right.
      - Top = cy, bottom = cy + ``bottom_offset``.

    A flag is dropped when its zone cannot be expanded to at least
    ``min_x_gap`` width (i.e. ``right - midline < min_x_gap / 2``) or when its
    midline lies inside the right neighbor's zone. Invalid flags are removed
    and zones are recomputed until stable.

    Returns ``(valid_flags, zones)`` where ``zones`` corresponds 1:1 to
    ``valid_flags``. Each zone dict contains normalized ``left``/``top``/
    ``right``/``bottom`` (clamped to [0, 1]), the flag center ``cx``/``cy``,
    and the ``midline``.
    """
    flags = list(flags)

    while True:
        centers = []
        for f in flags:
            x, y, fw, fh = f["box"]
            cx = (x + fw / 2.0) / image_width
            cy = (y + fh / 2.0) / image_height
            centers.append((cx, cy))

        n = len(centers)
        zones: List[Dict[str, Any]] = [None] * n  # type: ignore[misc]
        next_left = 1.0
        for i in range(n - 1, -1, -1):
            cx, cy = centers[i]
            midline = cx - midline_offset
            right = next_left
            left = 2.0 * midline - right
            top = cy
            bottom = cy + bottom_offset

            zones[i] = {
                "cx": cx,
                "cy": cy,
                "midline": midline,
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
            }
            next_left = left

        invalid: set[int] = set()
        for idx, zone in enumerate(zones):
            width = zone["right"] - zone["left"]
            if width < min_x_gap:
                invalid.add(idx)
            if idx + 1 < len(zones) and zone["midline"] > zones[idx + 1]["left"] + 1e-6:
                invalid.add(idx)

        if not invalid:
            break
        flags = [f for i, f in enumerate(flags) if i not in invalid]

    # Clamp normalized coordinates to [0, 1] for downstream consumers.
    for zone in zones:
        zone["left"] = max(0.0, min(1.0, zone["left"]))
        zone["top"] = max(0.0, min(1.0, zone["top"]))
        zone["right"] = max(0.0, min(1.0, zone["right"]))
        zone["bottom"] = max(0.0, min(1.0, zone["bottom"]))

    return flags, zones
