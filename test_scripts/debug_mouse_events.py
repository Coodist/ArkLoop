"""Debug raw mouse events from the MuMu emulator.

Prints every mousedown/mouseup/mousemove that pynput sees while MuMu is in the
foreground.  This is useful to check whether drag movements are actually being
delivered to the global hook.

Usage:
    .venv\Scripts\python scripts/debug_mouse_events.py

Press Ctrl+C to stop.
"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.input.mouse_listener import MouseListener
from src.input.coordinate_mapper import CoordinateMapper


def main():
    mapper = CoordinateMapper()
    listener = MouseListener(record_moves=True)

    move_count = 0
    last_printed = {"count": 0, "ts": 0.0}

    def on_event(event):
        nonlocal move_count
        mapped = mapper.map_point(event.x, event.y, clamp=True)
        if event.type == "mousemove":
            move_count += 1
            # Throttle move prints so the console is readable.
            now = time.time()
            if now - last_printed["ts"] >= 0.5:
                print(
                    f"[move] x={event.x} y={event.y} "
                    f"ratio=({mapped.ratio_x:.3f},{mapped.ratio_y:.3f}) "
                    f"total_moves={move_count}"
                )
                last_printed["ts"] = now
            return

        print(
            f"[{event.type}] button={event.button} pressed={event.pressed} "
            f"x={event.x} y={event.y} "
            f"ratio=({mapped.ratio_x:.3f},{mapped.ratio_y:.3f}) "
            f"ts={event.ts:.3f}"
        )

    listener._callback = on_event
    listener.start()

    print("Listening to raw mouse events. Make sure MuMu is in the foreground.")
    print("Try a deploy drag from the operator area to the map.")
    print("Press Ctrl+C to stop.\n")

    running = True

    def _stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)

    try:
        while running:
            time.sleep(0.2)
    finally:
        listener.stop()
        print(f"\nTotal move events captured: {move_count}")


if __name__ == "__main__":
    main()
