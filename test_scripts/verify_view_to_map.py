"""Verify transform_view_to_map against real clicks inside a game level.

Usage:
    .venv\Scripts\python scripts/verify_view_to_map.py --map-code 1-7

The script does NOT move the mouse. Enter the specified level in MuMu, then
click deployable tiles. For each click it prints the detected map tile
(row, col). Press Ctrl+C to stop.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cache import get_map_by_code
from src.input.mouse_listener import MouseListener
from src.input.coordinate_mapper import CoordinateMapper
from src.logic.calc_view import transform_view_to_map
from src.config import ImageProcessingConfig as imgconfig
from src.logger import logger


def main():
    parser = argparse.ArgumentParser(description="Verify view-to-map transform with real clicks.")
    parser.add_argument("--map-code", type=str, default="1-7", help="Map code to verify against.")
    parser.add_argument("--side", action="store_true", help="Use side view camera instead of front view.")
    args = parser.parse_args()

    level = get_map_by_code(args.map_code)
    side = args.side

    print(f"Loaded map {args.map_code}: {level['height']}x{level['width']}")
    print(f"Using {'side' if side else 'front'} view camera.")
    print("Enter the level in MuMu and click tiles. Press Ctrl+C to stop.\n")

    mapper = CoordinateMapper()
    listener = MouseListener()
    listener.start()

    previous_len = 0
    try:
        while True:
            events = listener.events
            if len(events) > previous_len:
                for ev in events[previous_len:]:
                    if ev.type == "mouseup":
                        mapped = mapper.map_point(ev.x, ev.y, clamp=True)
                        if not mapped.valid:
                            print(f"Click outside MuMu client area: screen=({ev.x}, {ev.y})")
                            continue

                        tile = transform_view_to_map(level, (mapped.ratio_x, mapped.ratio_y), side)
                        if tile is None:
                            print(f"Click at ratio=({mapped.ratio_x:.4f}, {mapped.ratio_y:.4f}) did not map to any tile")
                        else:
                            row, col = tile
                            print(
                                f"Click at screen=({ev.x}, {ev.y}) "
                                f"ratio=({mapped.ratio_x:.4f}, {mapped.ratio_y:.4f}) "
                                f"-> tile=({row}, {col})"
                            )
                previous_len = len(events)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
