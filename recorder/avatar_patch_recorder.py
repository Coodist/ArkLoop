"""Event-driven capture of operator-avatar patches during recording.

When the player starts dragging an operator from the deploy area, the avatar
rises slightly and the mouse cursor covers part of it.  Instead of matching
that frame, we wait until the cursor leaves the operator area and then save a
patch centered on the original slot.  The patch is taller than the avatar to
absorb the "selected" upward offset.
"""

import os
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.config import GameRatioConfig as gameconfig
from src.config import ImageProcessingConfig as imgconfig
from src.logger import logger

__all__ = ["AvatarPatchRecorder", "make_patch_callback"]


# How far above the operator area the patch should extend, as a fraction of
# the operator-area height.  This absorbs the "selected" upward pop.
_PATCH_TOP_EXTRA = 0.35
# How far below the operator area the patch should extend.
_PATCH_BOTTOM_EXTRA = 0.10

# Minimum drag distance (ratio) before we consider it an operator deploy drag.
_DRAG_THRESHOLD_RATIO = 0.03

# Ratio threshold for "mouse has left the operator area".
_OPERATOR_AREA_TOP = gameconfig.OPERATOR_AREA_RATIO[1]
_LEAVE_THRESHOLD = _OPERATOR_AREA_TOP - 0.03


def make_patch_callback(mapper: Any, patch_recorder: "AvatarPatchRecorder") -> Callable[[Any], None]:
    """
    Build a callback suitable for ``MouseListener(callback=...)``.

    The raw ``MouseEvent`` carries screen pixel coordinates; this adapter
    converts them to normalized ratio coordinates and forwards them to the
    ``AvatarPatchRecorder``.
    """

    def callback(ev: Any) -> None:
        mapped = mapper.map_point(ev.x, ev.y, clamp=True)
        patch_recorder.on_mouse_event(
            {
                "type": ev.type,
                "ts": ev.ts,
                "button": ev.button,
                "ratio": {"x": mapped.ratio_x, "y": mapped.ratio_y},
            }
        )

    return callback


class AvatarPatchRecorder:
    """
    Capture avatar patches for drag actions without blocking the main loop.

    Usage:
        recorder = AvatarPatchRecorder(output_dir="recordings/patches")
        mouse_listener = MouseListener(callback=recorder.on_mouse_event)

        while recording:
            frame = capture_game_window(...)
            recorder.on_frame(frame, timestamp, frame_idx)

        patch_map = recorder.flush()  # start_ts -> patch_path
    """

    def __init__(
        self,
        output_dir: str,
        max_recent_frames: int = 60,
    ):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self._max_recent_frames = max_recent_frames
        self._recent_frames: Deque[Tuple[float, int, np.ndarray]] = deque(
            maxlen=max_recent_frames
        )

        self._lock = threading.Lock()
        self._current_ratio: Optional[Tuple[float, float]] = None
        self._pending_drag: Optional[Dict[str, Any]] = None
        self._saved_patches: Dict[str, str] = {}

    @staticmethod
    def _in_operator_area(ratio: Tuple[float, float]) -> bool:
        """Return True if the point lies inside the operator (deploy) area."""
        return ratio[1] >= _OPERATOR_AREA_TOP

    def on_mouse_event(self, event: Any) -> None:
        """Receive mouse events from a ``MouseListener`` callback.

        Accepts either a ``MouseEvent``-like object or a plain dict.  The
        event MUST carry normalized ``ratio`` coordinates; raw screen pixels
        are not accepted because this module needs to reason about the
        operator-area ratio.
        """
        # Normalize to dict form, but only accept ratio-based events.
        if hasattr(event, "type"):
            ev_type = getattr(event, "type")
            ts = getattr(event, "ts", 0.0)
            button = getattr(event, "button", None)
            ratio = getattr(event, "ratio", None)
            if ratio is None:
                logger.debug(
                    "AvatarPatchRecorder ignoring mouse event without ratio coordinates"
                )
                return
            event = {"type": ev_type, "ts": ts, "button": button, "ratio": ratio}

        ev_type = event.get("type")
        ratio = event.get("ratio")
        if ratio is None:
            return

        self._current_ratio = (ratio["x"], ratio["y"])

        with self._lock:
            if ev_type == "mousedown":
                # Only track left-button drags that actually start inside the
                # operator area.  Drags beginning on the map are camera pans,
                # direction selections, etc., and must not produce avatar patches.
                if (
                    event.get("button") == "left"
                    and self._current_ratio is not None
                    and self._in_operator_area(self._current_ratio)
                ):
                    self._pending_drag = {
                        "start_ts": round(event.get("ts", time.perf_counter()), 6),
                        "start_ratio": self._current_ratio,
                        "max_y": self._current_ratio[1],
                        "saved": False,
                    }

            elif ev_type == "mousemove" and self._pending_drag is not None:
                self._pending_drag["max_y"] = max(
                    self._pending_drag["max_y"], self._current_ratio[1]
                )
                if not self._pending_drag["saved"]:
                    self._try_save_patch_locked()

            elif ev_type == "mouseup" and self._pending_drag is not None:
                if not self._pending_drag["saved"] and self._drag_distance_meets_threshold():
                    self._try_save_patch_locked(force=True)
                self._pending_drag = None

    def on_frame(self, frame: np.ndarray, timestamp: float, frame_idx: int) -> None:
        """Push a new captured frame into the ring buffer."""
        self._recent_frames.append((timestamp, frame_idx, frame))
        with self._lock:
            if self._pending_drag is not None and not self._pending_drag["saved"]:
                self._try_save_patch_locked()

    def _drag_distance_meets_threshold(self) -> bool:
        """Return True if the cursor has moved enough to be a real drag."""
        if self._pending_drag is None or self._current_ratio is None:
            return False
        start_ratio = self._pending_drag["start_ratio"]
        dx = self._current_ratio[0] - start_ratio[0]
        dy = self._current_ratio[1] - start_ratio[1]
        return (dx * dx + dy * dy) ** 0.5 >= _DRAG_THRESHOLD_RATIO

    def _try_save_patch(self, force: bool = False) -> None:
        """Thread-safe wrapper around the actual save logic."""
        with self._lock:
            self._try_save_patch_locked(force=force)

    def _try_save_patch_locked(self, force: bool = False) -> None:
        """Save a patch when the cursor leaves the operator area.

        Must be called while holding ``self._lock``.
        """
        if self._pending_drag is None or self._pending_drag["saved"]:
            return
        if self._current_ratio is None:
            return
        if not self._recent_frames:
            return

        _, start_y = self._current_ratio
        start_ratio = self._pending_drag["start_ratio"]

        # Save when the cursor has clearly left the operator area, but only if
        # it has also moved far enough to be a real drag.  Forced saves (mouseup
        # or end-of-recording flush) still require the drag threshold so that
        # accidental clicks do not produce patches.
        leaving = start_y <= _LEAVE_THRESHOLD
        if not leaving and not force:
            return
        if not self._drag_distance_meets_threshold():
            return

        timestamp, frame_idx, frame = self._recent_frames[-1]
        result = self._crop_avatar_patch(frame, start_ratio)
        if result is None:
            return
        gray_patch, color_patch = result
        if gray_patch.size == 0 or color_patch.size == 0:
            return

        base_path = os.path.join(
            self.output_dir,
            f"avatar_patch_{self._pending_drag['start_ts']:.6f}",
        )
        try:
            cv2.imwrite(f"{base_path}.png", gray_patch)
            cv2.imwrite(f"{base_path}_color.png", color_patch)
            self._saved_patches[
                f"{self._pending_drag['start_ts']:.6f}"
            ] = f"{base_path}.png"
            self._pending_drag["saved"] = True
            logger.debug(
                f"Saved avatar patch at frame {frame_idx}: {base_path}.png"
            )
        except Exception as exc:
            logger.warning(f"Failed to save avatar patch: {exc}")

    def _crop_avatar_patch(
        self,
        frame: np.ndarray,
        center_ratio: Tuple[float, float],
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Crop both grayscale and color patches around the operator slot.

        The grayscale patch is used for template matching; the color patch is
        kept as a human-readable preview.
        """
        if frame.ndim == 3:
            color = frame
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            color = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            gray = frame

        h, w = gray.shape[:2]
        cx = int(w * center_ratio[0])

        op_top = int(h * _OPERATOR_AREA_TOP)
        op_bottom = h
        op_height = op_bottom - op_top

        patch_top = max(0, int(op_top - op_height * _PATCH_TOP_EXTRA))
        patch_bottom = min(h, int(op_bottom + op_height * _PATCH_BOTTOM_EXTRA))

        tw = max(imgconfig.AVATAR_STANDARD_SIZE[0], int(w * 0.09))
        x1 = max(0, cx - tw // 2)
        x2 = min(w, x1 + tw)

        gray_patch = gray[patch_top:patch_bottom, x1:x2]
        color_patch = color[patch_top:patch_bottom, x1:x2]
        return gray_patch, color_patch

    def flush(self) -> Dict[str, str]:
        """Return the mapping start_ts_str -> saved patch path."""
        return dict(self._saved_patches)
