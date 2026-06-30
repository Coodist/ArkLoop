"""Test the video recorder by recording the game window for N seconds.

Usage:
    .venv\Scripts\python scripts\record_test.py --duration 10

The recorded video will be saved to recordings/recording_*.mp4.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from recorder.video_recorder import VideoRecorder
from src.config import RecordingConfig as recconfig
from src.logger import logger
from src.mumu.mumu_vision import capture_game_window


def main():
    parser = argparse.ArgumentParser(description="Record the game window.")
    parser.add_argument("--duration", type=float, default=10.0, help="Recording duration in seconds.")
    parser.add_argument("--fps", type=int, default=recconfig.FPS, help="Target FPS.")
    args = parser.parse_args()

    logger.info(f"Recording for {args.duration:.1f} seconds at {args.fps} FPS...")

    # Capture one frame to determine shape.
    frame = capture_game_window(ratio=None, color=True)
    if frame is None:
        logger.error("Failed to capture game window.")
        return

    # capture_game_window(color=True) returns BGR; no conversion needed.
    frame_bgr = frame

    recorder = VideoRecorder(fps=args.fps)
    recorder.start(frame_bgr.shape)

    interval = 1.0 / args.fps
    start_time = time.perf_counter()
    # Give the capture pipeline a short warm-up gap after the initial shape frame.
    next_frame_time = start_time + max(interval, 0.05)
    try:
        while True:
            now = time.perf_counter()
            elapsed = now - start_time
            if elapsed >= args.duration:
                break

            if now >= next_frame_time:
                frame = capture_game_window(ratio=None, color=True)
                if frame is not None:
                    recorder.record_frame(frame)
                else:
                    logger.warning("Capture returned None, skipping frame.")
                next_frame_time += interval

            # Small sleep to avoid busy-waiting; leave a 1 ms margin.
            sleep_time = max(0, next_frame_time - time.perf_counter() - 0.001)
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        logger.info("Recording interrupted by user.")

    result = recorder.stop()
    logger.info(f"Saved to: {result.video_path}")
    logger.info(
        f"Frames: {result.frame_count}, Duration: {result.duration:.3f}s, "
        f"Average FPS: {result.average_fps:.2f}"
    )


if __name__ == "__main__":
    main()
