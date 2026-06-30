"""Write a JSON axis from an offline recording analysis and recorded actions."""

from __future__ import annotations

import bisect
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.cache import get_map_by_code
from src.config import ImageProcessingConfig as imgconfig
from src.config import PerformActionConfig as performconfig
from src.logger import logger
from recorder.action_recognizer import ActionRecognizer, ActionType, AvatarMatcher

try:
    from src.maa import create_side_view_detector
except Exception as exc:
    create_side_view_detector = None  # type: ignore[assignment, misc]
    logger.warning(f"MAA side-view detector unavailable: {exc}")

__all__ = ["AxisWriter"]


class _VideoFrameProvider:
    """Lazy video reader that seeks to the frame closest to a timestamp."""

    def __init__(self, video_path: str, timestamps: List[float]):
        self.video_path = video_path
        self.timestamps = timestamps
        self._cap: Optional[cv2.VideoCapture] = None
        self._last_idx: int = -1

    def _open(self) -> cv2.VideoCapture:
        if self._cap is None:
            self._cap = cv2.VideoCapture(self.video_path)
            if not self._cap.isOpened():
                raise RuntimeError(f"Cannot open video: {self.video_path}")
        return self._cap

    def __call__(self, ts: float) -> Optional[np.ndarray]:
        if not self.timestamps:
            return None
        idx = bisect.bisect_left(self.timestamps, ts)
        if idx >= len(self.timestamps):
            idx = len(self.timestamps) - 1
        elif idx > 0:
            if abs(self.timestamps[idx] - ts) >= abs(self.timestamps[idx - 1] - ts):
                idx -= 1

        cap = self._open()
        # Avoid unnecessary seeks if we are already nearby.
        if idx != self._last_idx:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            self._last_idx = idx

        ret, frame = cap.read()
        if not ret:
            return None
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class AxisWriter:
    """
    Build an executable JSON axis from:
      * ``analysis_data`` — output of ``OfflineScanner``
      * ``actions_data`` — output of the mouse recorder
      * ``map_code`` — e.g. ``"1-7"``
    """

    def __init__(
        self,
        analysis_data: Dict[str, Any],
        actions_data: Dict[str, Any],
        map_code: str,
        frame_provider: Optional[Callable[[float], Optional[np.ndarray]]] = None,
        avatar_threshold: float = imgconfig.TEMPLATE_MATCH_THRESHOLD,
    ):
        self.analysis_data = analysis_data
        self.actions_data = actions_data
        self.map_code = map_code
        self.map_data = get_map_by_code(map_code)

        self.frames: List[Dict[str, Any]] = analysis_data.get("frames", [])
        self.video_path = analysis_data.get("metadata", {}).get("video_path")
        timestamps = analysis_data.get("metadata", {}).get("timestamps_path")
        self.frame_timestamps: List[float] = self._load_timestamps(timestamps)

        if frame_provider is None and self.video_path:
            frame_provider = _VideoFrameProvider(self.video_path, self.frame_timestamps)
        self.frame_provider = frame_provider

        view_detector = None
        if create_side_view_detector is not None:
            try:
                view_detector = create_side_view_detector()
                logger.info("Using MAA OCR side-view detector")
            except Exception as exc:
                logger.warning(f"Failed to create side-view detector: {exc}")

        self.recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=AvatarMatcher(threshold=avatar_threshold),
            frame_provider=self.frame_provider,
            view_detector=view_detector,
        )

        self.semantic_actions: List[Any] = []

    @staticmethod
    def _load_timestamps(timestamps_path: Optional[str]) -> List[float]:
        if not timestamps_path or not Path(timestamps_path).is_file():
            return []
        try:
            import json

            with open(timestamps_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            timestamps = data.get("frame_timestamps", [])
            return [float(t) for t in timestamps]
        except Exception as exc:
            logger.warning(f"Could not load timestamps: {exc}")
            return []

    def build(self) -> Dict[str, Any]:
        """Run recognition and assemble the axis dict."""
        raw_actions = self.actions_data.get("actions", [])
        semantic_actions = self.recognizer.recognize(raw_actions, self.frames)

        axis_actions: List[Dict[str, Any]] = []
        pending_deploys: Dict[Tuple[str, Any], Any] = {}

        for sa in semantic_actions:
            if sa.action_type == ActionType.IGNORE:
                continue

            if sa.action_type == ActionType.DIRECTION:
                # Merge direction selection into the matching pending DEPLOY.
                key = (sa.oper, sa.tile_pos)
                deploy = pending_deploys.get(key)
                if deploy is not None:
                    deploy.direction = sa.direction
                    if sa.game_time:
                        deploy.game_time = sa.game_time
                continue

            if sa.action_type == ActionType.DEPLOY:
                key = (sa.oper, sa.tile_pos)
                pending_deploys[key] = sa

            axis_actions.append(sa.to_axis_dict(self.map_data.get("height", 0)))

        metadata = self.analysis_data.get("metadata", {})
        settings: Dict[str, Any] = {
            "map_code": self.map_code,
            "max_tick": metadata.get("ticks_per_cycle", 30),
            "wait_time1": performconfig.MINIMUM_WAITTIME,
            "wait_time2": performconfig.FRAME_WAITTIME,
            "wait_time3": performconfig.GENERAL_WAITTIME,
            "bullet_threshold": performconfig.BULLET_THRESHOLD,
            "frame_threshold": performconfig.FRAME_THRESHOLD,
        }
        if self.map_data.get("name"):
            settings["map_name"] = self.map_data["name"]

        return {"settings": settings, "actions": axis_actions}

    def write(self, output_path: str) -> str:
        """Build and write the axis JSON to ``output_path``."""
        axis = self.build()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(axis, f, ensure_ascii=False, indent=2)
        logger.info(f"Axis written to {output_path} ({len(axis['actions'])} actions)")
        return output_path

    def __enter__(self) -> "AxisWriter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if isinstance(self.frame_provider, _VideoFrameProvider):
            self.frame_provider.close()
