"""Verify that click coordinates are mapped correctly inside the MuMu window.

This script does NOT move the mouse. It starts a listener and asks you to
click specific points inside the MuMu game area. After each click it prints
the detected screen, ratio, and standardized game coordinates so you can
confirm they match expectations.

Usage:
    .venv\Scripts\python scripts/verify_click_positions.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.input.mouse_listener import MouseListener
from src.input.coordinate_mapper import CoordinateMapper
from src.config import GameRatioConfig as ratioconfig
from src.logger import logger


def main():
    print("=" * 60)
    print("MuMu click position verification")
    print("=" * 60)
    print("\nThis script will listen for your clicks inside the MuMu window.")
    print("Please click the following points in order:")
    print("  1. Top-left corner of the game area")
    print("  2. Top-right corner of the game area")
    print("  3. Bottom-left corner of the game area")
    print("  4. Bottom-right corner of the game area")
    print("  5. Center of the game area")
    print("  6. (Optional) A known UI button, e.g. the pause button")
    print("\nPress Ctrl+C to stop early.\n")

    mapper = CoordinateMapper()
    listener = MouseListener()
    listener.start()

    target_count = 6
    captured = 0
    try:
        previous_len = 0
        while captured < target_count:
            events = listener.events
            if len(events) > previous_len:
                # Take the latest mouseup event.
                for ev in events[previous_len:]:
                    if ev.type == "mouseup":
                        captured += 1
                        mapped = mapper.map_point(ev.x, ev.y, clamp=True)
                        print(
                            f"\nClick #{captured}: screen=({ev.x}, {ev.y})  "
                            f"ratio=({mapped.ratio_x:.4f}, {mapped.ratio_y:.4f})  "
                            f"game=({mapped.game_x:.1f}, {mapped.game_y:.1f})  "
                            f"valid={mapped.valid}"
                        )
                        if captured == 1:
                            print("  Expected: ratio near (0.00, 0.00)")
                        elif captured == 2:
                            print("  Expected: ratio near (1.00, 0.00)")
                        elif captured == 3:
                            print("  Expected: ratio near (0.00, 1.00)")
                        elif captured == 4:
                            print("  Expected: ratio near (1.00, 1.00)")
                        elif captured == 5:
                            print("  Expected: ratio near (0.50, 0.50)")
                        elif captured == 6:
                            px, py = ratioconfig.PAUSE_BUTTON_RATIO
                            print(f"  Pause button reference: ratio=({px:.4f}, {py:.4f})")
                previous_len = len(events)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        listener.stop()

    print("\nVerification finished.")
    if captured < target_count:
        print(f"Only captured {captured}/{target_count} clicks.")


if __name__ == "__main__":
    main()
