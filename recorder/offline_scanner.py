"""Offline cost bar scanner for recorded gameplay videos."""

import json
import os
from typing import Any, Dict, List, Optional

import cv2
from PIL import Image

from src.config import ImageProcessingConfig as imgconfig
from src.config import RecordingConfig as recconfig
from src.frame.detector import CostBarDetector
from src.frame.pause_detector import PauseDetector, mark_stuck_ticks_as_paused
from src.frame.tick_state import TickStateTracker
from src.logger import logger

__all__ = ["OfflineScanner", "load_timestamps", "find_latest_recording_pair"]


def load_timestamps(timestamps_path: str) -> Dict[str, Any]:
    """Load a frame timestamps JSON produced by ``scripts/record_actions.py``."""
    with open(timestamps_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Timestamps file must contain a JSON object: {timestamps_path}")
    return data


def detect_tick_anomalies(
    frames: List[Dict[str, Any]],
    ticks_per_cycle: int,
    high_ratio: float = 0.75,
    low_ratio: float = 0.25,
) -> List[Dict[str, Any]]:
    """Scan per-frame tick values and flag suspicious changes.

    Two classes of anomalies are reported:

    1. ``forward_jump`` - the tick advances by more than one step within a
       cycle.  Normal gameplay advances roughly one tick per video frame, so
       a jump of 2+ ticks in a single frame is suspicious.
    2. ``backward_noise`` - the tick decreases without crossing the valid
       cycle boundary.  This catches single-frame mis-detections such as
       ``26 -> 25`` or ``25 -> 24`` which would otherwise look like a wrap.

    A valid cycle wrap is defined exactly as in ``TickStateTracker``:
    ``previous > ticks_per_cycle * 0.75`` and ``current < ticks_per_cycle * 0.25``.

    Args:
        frames: Per-frame dicts from ``OfflineScanner.scan()``.
        ticks_per_cycle: Number of ticks in one full cost bar cycle.

    Returns:
        List of anomaly records, each with ``frame_id``, ``timestamp``,
        ``from_tick``, ``to_tick``, and ``type`` keys.
    """
    if ticks_per_cycle <= 0 or len(frames) < 2:
        return []

    high_threshold = ticks_per_cycle * high_ratio
    low_threshold = ticks_per_cycle * low_ratio
    anomalies: List[Dict[str, Any]] = []

    prev_frame = frames[0]
    prev_tick = prev_frame.get("tick")

    for frame in frames[1:]:
        curr_tick = frame.get("tick")
        if prev_tick is not None and curr_tick is not None:
            is_valid_wrap = prev_tick > high_threshold and curr_tick < low_threshold

            if curr_tick > prev_tick and not is_valid_wrap:
                step = curr_tick - prev_tick
                if step > 1:
                    anomalies.append(
                        {
                            "frame_id": frame["frame_id"],
                            "timestamp": frame["timestamp"],
                            "from_tick": prev_tick,
                            "to_tick": curr_tick,
                            "type": "forward_jump",
                            "step": step,
                        }
                    )

            elif curr_tick < prev_tick and not is_valid_wrap:
                anomalies.append(
                    {
                        "frame_id": frame["frame_id"],
                        "timestamp": frame["timestamp"],
                        "from_tick": prev_tick,
                        "to_tick": curr_tick,
                        "type": "backward_noise",
                        "step": prev_tick - curr_tick,
                    }
                )

        prev_frame = frame
        prev_tick = curr_tick

    return anomalies


def _resolve_video_path(video_path: str) -> str:
    if os.path.isabs(video_path):
        return video_path
    # If relative, resolve against project root (where recordings/ lives).
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, video_path)


def find_latest_recording_pair(
    recordings_dir: Optional[str] = None,
) -> Optional[tuple]:
    """
    Find the most recently created ``recording_<ts>.mp4`` +
    ``recording_<ts>_timestamps.json`` pair in ``recordings_dir``.

    Returns ``(video_path, timestamps_path)`` or ``None`` if no pair found.
    """
    recordings_dir = recordings_dir or recconfig.OUTPUT_DIR
    if not os.path.isdir(recordings_dir):
        return None

    candidates = []
    for name in os.listdir(recordings_dir):
        if not name.startswith("recording_") or not name.endswith(".mp4"):
            continue
        ts = name[len("recording_") : -len(".mp4")]
        timestamps_name = f"recording_{ts}_timestamps.json"
        timestamps_path = os.path.join(recordings_dir, timestamps_name)
        video_path = os.path.join(recordings_dir, name)
        if os.path.isfile(timestamps_path):
            candidates.append((os.path.getmtime(video_path), video_path, timestamps_path))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1], candidates[0][2]


class OfflineScanner:
    """
    Scan a recorded video frame-by-frame to reconstruct the cost bar timeline.

    Output is a JSON-compatible dict with per-frame metadata:
    ``frame_id``, ``timestamp``, ``tick``, ``cycle``, ``total_elapsed_frames``,
    ``paused``.
    """

    def __init__(
        self,
        video_path: str,
        timestamps_path: str,
        detector: Optional[CostBarDetector] = None,
        pause_detector: Optional[PauseDetector] = None,
    ):
        self.video_path = _resolve_video_path(video_path)
        self.timestamps_path = timestamps_path
        self.pause_detector = pause_detector
        self.detector = detector or CostBarDetector.from_resolution(
            *imgconfig.SCREEN_STANDARD_SIZE
        )

        calibration = self.detector.calibration_data
        if calibration:
            profiles = calibration.get("profiles", [])
            tick_max = profiles[0].get("total_frames", 30) if profiles else 30
        else:
            tick_max = 30
            logger.warning(
                "No calibration loaded; defaulting to ticks_per_cycle=30"
            )
        self.tracker = TickStateTracker(ticks_per_cycle=tick_max)

        self.frames: List[Dict[str, Any]] = []
        self.actions: Optional[Dict[str, Any]] = None
        self.metadata: Dict[str, Any] = {}

    def _load_timestamps_data(self) -> Dict[str, Any]:
        """Load and return the raw timestamps JSON object."""
        try:
            return load_timestamps(self.timestamps_path)
        except Exception:
            logger.exception(f"Failed to load timestamps from {self.timestamps_path}")
            return {}

    def _read_timestamps(self, frame_count_hint: int) -> List[float]:
        ts_data = self._load_timestamps_data()
        timestamps = ts_data.get("frame_timestamps", [])
        if not isinstance(timestamps, list):
            logger.error("frame_timestamps is not a list")
            return []

        if len(timestamps) != frame_count_hint:
            logger.warning(
                f"Timestamp count mismatch: {len(timestamps)} timestamps vs "
                f"{frame_count_hint} frames. Falling back to frame index / fps for missing entries."
            )
        return timestamps

    def _finalize_scan(self) -> Dict[str, Any]:
        """Run post-processing heuristics and return the scan result."""
        # Bullet-time / pause fallback: long runs of the same tick are almost
        # certainly not normal 1x-speed gameplay.
        stuck_count = mark_stuck_ticks_as_paused(self.frames, consecutive_threshold=12)
        if stuck_count:
            logger.info(
                f"Bullet-time heuristic marked {stuck_count} frames as paused"
            )

        # Tick anomaly visibility: flag frame-to-frame jumps that are not
        # valid cycle wraps so users can spot OCR/calibration problems.
        anomalies = detect_tick_anomalies(
            self.frames, self.tracker.ticks_per_cycle
        )
        self.metadata["tick_anomalies"] = anomalies
        if anomalies:
            anomaly_lines = ", ".join(
                f"frame {a['frame_id']} ({a['timestamp']:.3f}s): "
                f"{a['from_tick']} -> {a['to_tick']} ({a['type']})"
                for a in anomalies[:10]
            )
            suffix = " ..." if len(anomalies) > 10 else ""
            logger.warning(
                f"Detected {len(anomalies)} tick anomaly/anomalies: "
                f"{anomaly_lines}{suffix}"
            )

        logger.info(
            f"Offline scan complete: {len(self.frames)} frames, "
            f"{self.tracker.cycle_counter} cycles, "
            f"TICK_MAX={self.tracker.ticks_per_cycle}"
        )

        return {
            "metadata": self.metadata,
            "frames": self.frames,
        }

    def _scan_from_precomputed_ticks(
        self,
        precomputed_ticks: List[Dict[str, Any]],
        timestamps: List[float],
        max_frames: Optional[int],
    ) -> Dict[str, Any]:
        """Build frames directly from ticks captured during recording.

        This avoids decoding the compressed video and re-running tick
        detection, which is the source of the compression-related jitter.
        """
        logger.info(
            f"Using {len(precomputed_ticks)} pre-computed ticks from timestamps file."
        )
        self.frames = []
        for item in precomputed_ticks:
            frame_idx = item.get("frame_id", len(self.frames))
            if max_frames is not None and frame_idx >= max_frames:
                break

            tick = item.get("tick")
            state = self.tracker.update(tick)

            ts = item.get("timestamp")
            if ts is None and frame_idx < len(timestamps):
                ts = timestamps[frame_idx]
            if ts is None:
                ts = frame_idx / 30.0

            self.frames.append(
                {
                    "frame_id": frame_idx,
                    "timestamp": round(ts, 6),
                    "tick": state["tick"],
                    "cycle": state["cycle"],
                    "total_elapsed_frames": state["total_elapsed_frames"],
                    "paused": state["paused"],
                }
            )

        self.metadata["scanned_frames"] = len(self.frames)
        self.metadata["used_precomputed_ticks"] = True
        return self._finalize_scan()

    def _scan_from_video(
        self,
        timestamps: List[float],
        max_frames: Optional[int],
    ) -> Dict[str, Any]:
        """Fallback: decode the video and run tick detection frame-by-frame."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self.video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count_hint = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        self.metadata["fps"] = fps
        self.metadata["frame_count"] = frame_count_hint
        self.metadata["duration"] = timestamps[-1] if timestamps else None
        self.metadata["used_precomputed_ticks"] = False

        self.frames = []
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if max_frames is not None and frame_idx >= max_frames:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)

            tick: Optional[int] = None
            if self.detector.is_ready():
                try:
                    tick = self.detector.detect_tick(pil_img)
                except Exception as e:
                    logger.warning(f"Tick detection failed at frame {frame_idx}: {e}")
            else:
                logger.warning(f"Detector not ready at frame {frame_idx}; skipping detection")

            state = self.tracker.update(tick)
            paused = state["paused"]
            if self.pause_detector is not None:
                try:
                    paused = paused or self.pause_detector.update(frame)
                except Exception as e:
                    logger.warning(f"Pause detection failed at frame {frame_idx}: {e}")

            ts = (
                timestamps[frame_idx]
                if frame_idx < len(timestamps)
                else frame_idx / fps
            )

            self.frames.append(
                {
                    "frame_id": frame_idx,
                    "timestamp": round(ts, 6),
                    "tick": state["tick"],
                    "cycle": state["cycle"],
                    "total_elapsed_frames": state["total_elapsed_frames"],
                    "paused": paused,
                }
            )

            frame_idx += 1

        cap.release()
        self.metadata["scanned_frames"] = len(self.frames)
        return self._finalize_scan()

    def scan(self, max_frames: Optional[int] = None) -> Dict[str, Any]:
        """Reconstruct the cost bar timeline.

        If the timestamps JSON contains pre-computed ticks captured during
        recording, those are used directly.  Otherwise the video is decoded
        and tick detection is re-run frame-by-frame.

        Args:
            max_frames: Optional limit for faster testing or partial scans.

        Returns:
            Dict with ``metadata`` and ``frames`` keys.
        """
        ts_data = self._load_timestamps_data()
        timestamps = ts_data.get("frame_timestamps", [])
        if not isinstance(timestamps, list):
            logger.error("frame_timestamps is not a list")
            timestamps = []

        precomputed_ticks = ts_data.get("frame_ticks")

        self.metadata = {
            "video_path": self.video_path,
            "timestamps_path": self.timestamps_path,
            "fps": ts_data.get("fps") or 30.0,
            "frame_count": ts_data.get("frame_count"),
            "duration": ts_data.get("duration"),
            "ticks_per_cycle": self.tracker.ticks_per_cycle,
            "detector_ready": self.detector.is_ready(),
            "calibration_profile": self.detector.calibration_data,
        }

        if (
            isinstance(precomputed_ticks, list)
            and precomputed_ticks
            and (max_frames is None or len(precomputed_ticks) >= max_frames)
        ):
            return self._scan_from_precomputed_ticks(
                precomputed_ticks, timestamps, max_frames
            )

        return self._scan_from_video(timestamps, max_frames)

    def save(self, output_path: str) -> str:
        """Write scan result to ``output_path`` as JSON."""
        result: Dict[str, Any] = {
            "metadata": self.metadata,
            "frames": self.frames,
        }
        if self.actions is not None:
            result["actions"] = self.actions
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"Recording analysis saved to: {output_path}")
        return output_path

    def annotate_actions(self, actions_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map recorded mouse actions to the nearest scanned frame/tick.

        This is a lightweight semantic step: each action gets the
        ``frame_id``, ``tick``, ``cycle``, and ``total_elapsed_frames`` of the
        frame closest to its start timestamp.

        Args:
            actions_data: Parsed ``actions_*.json`` dict.

        Returns:
            Copy of ``actions_data`` with ``game_time`` added to each action.
        """
        if not self.frames:
            raise RuntimeError("Must run scan() before annotating actions")

        annotated = dict(actions_data)
        actions = annotated.get("actions", [])

        def _nearest_frame(ts: float) -> Dict[str, Any]:
            # Timestamps in frames are relative to recording start; actions ts are too.
            best = self.frames[0]
            best_diff = abs(best["timestamp"] - ts)
            for frame in self.frames[1:]:
                diff = abs(frame["timestamp"] - ts)
                if diff < best_diff:
                    best = frame
                    best_diff = diff
            return best

        for action in actions:
            frame = _nearest_frame(action.get("start_ts", 0.0))
            action["game_time"] = {
                "frame_id": frame["frame_id"],
                "tick": frame["tick"],
                "cycle": frame["cycle"],
                "total_elapsed_frames": frame["total_elapsed_frames"],
                "timestamp": frame["timestamp"],
            }

        annotated["actions"] = actions
        self.actions = annotated
        return annotated
