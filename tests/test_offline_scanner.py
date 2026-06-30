"""Unit tests for offline cost bar scanning."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from recorder.offline_scanner import (
    OfflineScanner,
    detect_tick_anomalies,
    load_timestamps,
)
from src.frame.tick_state import TickStateTracker


class DummyDetector:
    """Detector stub that returns a predefined sequence of ticks."""

    def __init__(self, tick_sequence, tick_max=30):
        self.tick_sequence = list(tick_sequence)
        self.tick_max = tick_max
        self.calibration_data = {
            "profiles": [{"total_frames": tick_max, "pixel_map": {}}]
        }
        self._index = 0

    def is_ready(self):
        return True

    def detect_tick(self, frame):
        tick = self.tick_sequence[self._index % len(self.tick_sequence)]
        self._index += 1
        return tick


def _make_video(path: str, frame_count: int, fps: float = 30.0) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (1280, 720))
    try:
        for _ in range(frame_count):
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


def _make_timestamps(path: str, frame_count: int, fps: float = 30.0) -> None:
    data = {
        "video_path": "dummy.mp4",
        "frame_timestamps": [round(i / fps, 6) for i in range(frame_count)],
        "frame_count": frame_count,
        "duration": round(frame_count / fps, 6),
        "fps": fps,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _make_timestamps_with_ticks(
    path: str,
    frame_count: int,
    frame_ticks: list,
    fps: float = 30.0,
) -> None:
    data = {
        "video_path": "dummy.mp4",
        "frame_timestamps": [round(i / fps, 6) for i in range(frame_count)],
        "frame_ticks": frame_ticks,
        "frame_count": frame_count,
        "duration": round(frame_count / fps, 6),
        "fps": fps,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class TestTickStateTracker(unittest.TestCase):
    def test_cycle_wrap_updates_total(self):
        tracker = TickStateTracker(ticks_per_cycle=30)
        tracker.update(5)
        tracker.update(28)
        state = tracker.update(3)
        self.assertEqual(state["cycle"], 1)
        self.assertEqual(state["total_elapsed_frames"], 33)

    def test_paused_state_on_none(self):
        tracker = TickStateTracker(ticks_per_cycle=30)
        tracker.update(5)
        state = tracker.update(None)
        self.assertTrue(state["paused"])
        # current_tick persists to show last known tick (matching AnalysisWorker).
        self.assertEqual(state["tick"], 5)
        self.assertEqual(tracker.total_elapsed_frames, 5)

    def test_resumed_flag(self):
        tracker = TickStateTracker(ticks_per_cycle=30)
        tracker.update(None)
        state = tracker.update(10)
        self.assertTrue(state["resumed"])
        self.assertFalse(state["paused"])
        self.assertEqual(state["total_elapsed_frames"], 10)


class TestOfflineScanner(unittest.TestCase):
    def test_scan_detects_cycle_wrap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            timestamps_path = os.path.join(tmpdir, "timestamps.json")

            _make_video(video_path, frame_count=5)
            _make_timestamps(timestamps_path, frame_count=5)

            # Ticks: 5, 10, 28, 3, 15 -> wrap between 28 and 3.
            detector = DummyDetector([5, 10, 28, 3, 15], tick_max=30)
            scanner = OfflineScanner(video_path, timestamps_path, detector=detector)
            result = scanner.scan()

            frames = result["frames"]
            self.assertEqual(len(frames), 5)
            self.assertEqual(frames[0]["tick"], 5)
            self.assertEqual(frames[0]["cycle"], 0)
            self.assertEqual(frames[2]["tick"], 28)
            self.assertEqual(frames[3]["tick"], 3)
            self.assertEqual(frames[3]["cycle"], 1)
            self.assertEqual(frames[3]["total_elapsed_frames"], 33)
            self.assertEqual(frames[4]["total_elapsed_frames"], 45)

    def test_scan_with_missing_ticks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            timestamps_path = os.path.join(tmpdir, "timestamps.json")

            _make_video(video_path, frame_count=4)
            _make_timestamps(timestamps_path, frame_count=4)

            # Two valid ticks, then two failed detections (paused/unknown).
            detector = DummyDetector([5, 10, None, None], tick_max=30)
            scanner = OfflineScanner(video_path, timestamps_path, detector=detector)
            result = scanner.scan()

            frames = result["frames"]
            self.assertEqual(frames[0]["tick"], 5)
            self.assertEqual(frames[1]["tick"], 10)
            # When detection fails, paused=True but tick keeps last known value.
            self.assertTrue(frames[2]["paused"])
            self.assertEqual(frames[2]["tick"], 10)
            self.assertTrue(frames[3]["paused"])

    def test_load_timestamps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            timestamps_path = os.path.join(tmpdir, "timestamps.json")
            _make_timestamps(timestamps_path, frame_count=3)
            data = load_timestamps(timestamps_path)
            self.assertEqual(len(data["frame_timestamps"]), 3)
            self.assertAlmostEqual(data["frame_timestamps"][1], 1 / 30.0, places=5)

    def test_save_analysis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            timestamps_path = os.path.join(tmpdir, "timestamps.json")
            output_path = os.path.join(tmpdir, "analysis.json")

            _make_video(video_path, frame_count=3)
            _make_timestamps(timestamps_path, frame_count=3)

            detector = DummyDetector([0, 1, 2], tick_max=30)
            scanner = OfflineScanner(video_path, timestamps_path, detector=detector)
            scanner.scan()
            scanner.save(output_path)

            self.assertTrue(os.path.isfile(output_path))
            with open(output_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["metadata"]["scanned_frames"], 3)
            self.assertEqual(len(saved["frames"]), 3)

    def test_annotate_actions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            timestamps_path = os.path.join(tmpdir, "timestamps.json")

            _make_video(video_path, frame_count=30)
            _make_timestamps(timestamps_path, frame_count=30)

            # Ticks 0..29 in order, no wrap.
            detector = DummyDetector(list(range(30)), tick_max=30)
            scanner = OfflineScanner(video_path, timestamps_path, detector=detector)
            scanner.scan()

            actions_data = {
                "version": 1,
                "start_ts": 123456.0,
                "actions": [
                    {"type": "drag", "start_ts": 0.0},
                    {"type": "drag", "start_ts": 1 / 30.0},
                    {"type": "drag", "start_ts": 2 / 30.0},
                ],
            }
            annotated = scanner.annotate_actions(actions_data)

            self.assertEqual(annotated["actions"][0]["game_time"]["frame_id"], 0)
            self.assertEqual(annotated["actions"][0]["game_time"]["tick"], 0)
            self.assertEqual(annotated["actions"][1]["game_time"]["frame_id"], 1)
            self.assertEqual(annotated["actions"][1]["game_time"]["tick"], 1)


class TestTickAnomalies(unittest.TestCase):
    """Tests for detect_tick_anomalies and OfflineScanner metadata reporting."""

    def _make_frames(self, ticks: list) -> list:
        return [
            {
                "frame_id": i,
                "timestamp": i / 30.0,
                "tick": tick,
                "paused": False,
            }
            for i, tick in enumerate(ticks)
        ]

    def test_forward_jump_flagged(self):
        # A single-frame jump of 2+ ticks inside a cycle is suspicious.
        frames = self._make_frames([5, 6, 8, 9])
        anomalies = detect_tick_anomalies(frames, ticks_per_cycle=30)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["frame_id"], 2)
        self.assertEqual(anomalies[0]["from_tick"], 6)
        self.assertEqual(anomalies[0]["to_tick"], 8)
        self.assertEqual(anomalies[0]["type"], "forward_jump")

    def test_backward_noise_flagged(self):
        # 26 -> 25 and 25 -> 24 are not valid wraps and should be flagged.
        frames = self._make_frames([26, 25, 24])
        anomalies = detect_tick_anomalies(frames, ticks_per_cycle=30)
        self.assertEqual(len(anomalies), 2)
        self.assertEqual(anomalies[0]["type"], "backward_noise")
        self.assertEqual(anomalies[0]["from_tick"], 26)
        self.assertEqual(anomalies[0]["to_tick"], 25)
        self.assertEqual(anomalies[1]["from_tick"], 25)
        self.assertEqual(anomalies[1]["to_tick"], 24)

    def test_valid_wrap_not_flagged(self):
        # A high-to-low boundary crossing is a valid cycle wrap.
        frames = self._make_frames([28, 29, 3, 4])
        anomalies = detect_tick_anomalies(frames, ticks_per_cycle=30)
        self.assertEqual(len(anomalies), 0)

    def test_single_tick_step_not_flagged(self):
        # Normal +1 progression should never be flagged.
        frames = self._make_frames([0, 1, 2, 3, 4, 5])
        anomalies = detect_tick_anomalies(frames, ticks_per_cycle=30)
        self.assertEqual(len(anomalies), 0)

    def test_scan_populates_tick_anomalies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            timestamps_path = os.path.join(tmpdir, "timestamps.json")
            _make_video(video_path, frame_count=5)
            _make_timestamps(timestamps_path, frame_count=5)
            # Ticks: 0,1,2,25,26 -> frame 3 should be a forward_jump (2->25).
            detector = DummyDetector([0, 1, 2, 25, 26], tick_max=30)
            scanner = OfflineScanner(video_path, timestamps_path, detector=detector)
            result = scanner.scan()
            anomalies = result["metadata"].get("tick_anomalies", [])
            self.assertEqual(len(anomalies), 1)
            self.assertEqual(anomalies[0]["frame_id"], 3)
            self.assertEqual(anomalies[0]["type"], "forward_jump")
            self.assertEqual(anomalies[0]["from_tick"], 2)
            self.assertEqual(anomalies[0]["to_tick"], 25)


    def test_scan_uses_precomputed_ticks_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            timestamps_path = os.path.join(tmpdir, "timestamps.json")

            # Pre-computed ticks: clean 0..29 progression.
            frame_ticks = [
                {"frame_id": i, "timestamp": i / 30.0, "tick": i % 30}
                for i in range(30)
            ]
            _make_timestamps_with_ticks(
                timestamps_path,
                frame_count=30,
                frame_ticks=frame_ticks,
            )
            # Video does not need to exist when pre-computed ticks are present.
            detector = DummyDetector([], tick_max=30)
            scanner = OfflineScanner(video_path, timestamps_path, detector=detector)
            result = scanner.scan()

            self.assertTrue(result["metadata"]["used_precomputed_ticks"])
            self.assertEqual(len(result["frames"]), 30)
            self.assertEqual(result["frames"][15]["tick"], 15)
            self.assertEqual(result["frames"][15]["total_elapsed_frames"], 15)
            # Clean progression should produce no anomalies.
            self.assertEqual(result["metadata"]["tick_anomalies"], [])

    def test_scan_falls_back_to_video_when_precomputed_ticks_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            timestamps_path = os.path.join(tmpdir, "timestamps.json")

            _make_video(video_path, frame_count=3)
            _make_timestamps(timestamps_path, frame_count=3)
            # No frame_ticks field -> must decode video.
            detector = DummyDetector([0, 1, 2], tick_max=30)
            scanner = OfflineScanner(video_path, timestamps_path, detector=detector)
            result = scanner.scan()

            self.assertFalse(result["metadata"]["used_precomputed_ticks"])
            self.assertEqual(len(result["frames"]), 3)


if __name__ == "__main__":
    unittest.main()
