"""Interactive verifier for event-driven avatar patch capture.

Run this script and perform deploy drags inside the MuMu window.  It will:
- Print every mouse event (down/move/up) with normalized ratio coordinates.
- Show when a drag is detected and when a patch is saved.
- Save both a grayscale patch (for matching) and a color preview.
- List all saved patches on exit.

Usage:
    .venv\Scripts\python scripts/verify_avatar_patch_capture.py --duration 10

Press Ctrl+C or wait for duration to finish.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from src.config import RecordingConfig as recconfig
from src.input.mouse_listener import MouseListener
from src.input.coordinate_mapper import CoordinateMapper
from src.mumu.mumu_vision import capture_game_window
from src.logger import logger
from recorder.avatar_patch_recorder import AvatarPatchRecorder, make_patch_callback


def _timestamp():
    return time.strftime("%H:%M:%S") + f".{(time.perf_counter() % 1) * 1000:03.0f}"


def main():
    parser = argparse.ArgumentParser(description="Verify avatar patch capture.")
    parser.add_argument("--duration", type=float, default=10.0, help="How long to run in seconds.")
    parser.add_argument("--fps", type=int, default=recconfig.FPS, help="Screenshot FPS.")
    parser.add_argument("--output-dir", type=str, default="recordings/verify_patches", help="Where to save patches.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    mapper = CoordinateMapper()
    recorder = AvatarPatchRecorder(output_dir=args.output_dir, max_recent_frames=60)
    patch_callback = make_patch_callback(mapper, recorder)

    def verbose_callback(ev):
        mapped = mapper.map_point(ev.x, ev.y, clamp=True)
        area = "operator" if mapped.ratio_y >= 0.80 else "map"
        print(
            f"[{_timestamp()}] MOUSE {ev.type:<9} "
            f"ratio=({mapped.ratio_x:.3f}, {mapped.ratio_y:.3f}) "
            f"button={ev.button} area={area}"
        )
        # Forward to patch recorder.
        patch_callback(ev)

    mouse_listener = MouseListener(callback=verbose_callback, record_moves=True)
    mouse_listener.start()

    print("=" * 60)
    print(f"[{_timestamp()}] Verifying avatar patch capture")
    print(f"[{_timestamp()}] Output dir: {args.output_dir}")
    print(f"[{_timestamp()}] Perform deploy drags in MuMu now...")
    print("=" * 60)

    interval = 1.0 / args.fps
    start_ts = time.perf_counter()
    frame_idx = 0
    saved_paths = set()

    try:
        while True:
            now = time.perf_counter()
            elapsed = now - start_ts
            if elapsed >= args.duration:
                break

            frame = capture_game_window(ratio=None, color=True)
            if frame is not None:
                recorder.on_frame(frame, elapsed, frame_idx)
                frame_idx += 1

                # Detect newly saved patches.
                current_paths = set(recorder.flush().values())
                new_paths = current_paths - saved_paths
                for path in new_paths:
                    print(f"[{_timestamp()}] ✓ SAVED PATCH: {path}")
                    saved_paths.add(path)

            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n[{_timestamp()}] Interrupted by user.")
    finally:
        mouse_listener.stop()
        # Try to flush any pending drag at the end.
        recorder._try_save_patch(force=True)
        final_paths = set(recorder.flush().values())
        new_paths = final_paths - saved_paths
        for path in new_paths:
            print(f"[{_timestamp()}] ✓ SAVED PATCH (flush): {path}")
            saved_paths.add(path)

    print("=" * 60)
    print(f"[{_timestamp()}] Done. Total frames captured: {frame_idx}")
    print(f"[{_timestamp()}] Total patches saved: {len(saved_paths)}")
    if saved_paths:
        print("Saved files:")
        for path in sorted(saved_paths):
            print(f"  - {path}")
    else:
        print("No patches were saved.")
    print("=" * 60)


if __name__ == "__main__":
    main()
