"""
Measure real capture FPS for 30 seconds using the configured capture source.

Usage:
    python scripts/test_capture_fps.py --duration 30
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mumu.mumu_vision import create_capture_controller


def main():
    parser = argparse.ArgumentParser(description="Measure capture FPS")
    parser.add_argument(
        "--duration", type=float, default=30.0, help="Duration in seconds"
    )
    args = parser.parse_args()

    controller = create_capture_controller()
    print(f"Controller: {type(controller).__name__}")

    # Warmup
    controller.capture_frame()

    duration = args.duration
    frames = 0
    start = time.perf_counter()
    next_report = start + 1.0

    while time.perf_counter() - start < duration:
        controller.capture_frame()
        frames += 1
        now = time.perf_counter()
        if now >= next_report:
            elapsed = now - start
            print(f"  {elapsed:5.1f}s  frames={frames}  avg_fps={frames / elapsed:.1f}")
            next_report += 1.0

    elapsed = time.perf_counter() - start
    print(f"\nFinished: {frames} frames in {elapsed:.3f}s")
    print(f"Average FPS: {frames / elapsed:.1f}")
    print(f"Target 30 FPS margin: {frames / elapsed / 30:.2f}x")

    controller.disconnect()


if __name__ == "__main__":
    main()
