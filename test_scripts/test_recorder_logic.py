"""Offline unit tests for the video recorder.

These tests draw synthetic frames and verify that FFmpeg produces a valid
video file and that timestamps are monotonically increasing.

Usage:
    .venv\Scripts\python scripts\test_recorder_logic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from recorder.video_recorder import VideoRecorder


def make_frame(index: int, total: int = 60) -> np.ndarray:
    """Create a synthetic 1280x720 BGR frame with a moving bar."""
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    x = int(1230 * index / max(total - 1, 1))
    frame[:, x:x + 50] = (0, 255, 0)
    return frame


def test_recorder_produces_valid_video():
    output_path = "recordings/test_logic.mp4"
    frames = [make_frame(i) for i in range(60)]

    recorder = VideoRecorder(output_path=output_path, fps=30)
    recorder.start(frames[0].shape)
    for f in frames:
        recorder.record_frame(f)
    result = recorder.stop()

    assert result.frame_count == 60
    assert os.path.exists(result.video_path)

    cap = cv2.VideoCapture(result.video_path)
    assert cap.isOpened()
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    assert width == 1280
    assert height == 720
    assert frame_count == 60
    assert abs(fps - 30.0) < 0.1

    os.remove(result.video_path)


def test_timestamps_are_monotonic():
    output_path = "recordings/test_ts.mp4"
    frames = [np.zeros((720, 1280, 3), dtype=np.uint8) for _ in range(30)]

    recorder = VideoRecorder(output_path=output_path, fps=30)
    recorder.start(frames[0].shape)
    for f in frames:
        recorder.record_frame(f)
    result = recorder.stop()

    timestamps = result.frame_timestamps
    assert len(timestamps) == 30
    assert all(timestamps[i] < timestamps[i + 1] for i in range(len(timestamps) - 1))

    os.remove(result.video_path)


def main():
    print("Running recorder logic tests...")
    test_recorder_produces_valid_video()
    test_timestamps_are_monotonic()
    print("All recorder logic tests passed.")


if __name__ == "__main__":
    main()
