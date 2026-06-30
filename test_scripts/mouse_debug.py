"""Standalone mouse-event debugger.

Run with:
    .venv\Scripts\python scripts\mouse_debug.py

Captures global mouse clicks and prints:
  - raw screen coordinates
  - foreground window handle/title
  - whether the foreground window is MuMu
  - mapped MuMu client ratio (same math ActionRecorder uses)
  - the cached MuMu client rectangle

Does not modify the main application.
"""

import sys
import time
import threading
from pathlib import Path

# Make imports from repo root work when running the script directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import win32gui
from pynput import mouse

from src.config import MuMuEmulatorConfig as mumu_config
from src.input.coordinate_mapper import CoordinateMapper
from src.logger import logger

# Reuse the same handle resolution logic as the main app.
try:
    from src.mumu.mumu_connection import HANDLE, PARENT_HANDLE
except Exception as exc:
    logger.error(f"Could not resolve MuMu window: {exc}")
    HANDLE = 0
    PARENT_HANDLE = 0

MUMU_HANDLES = {h for h in (HANDLE, PARENT_HANDLE) if h}


def get_window_title(hwnd: int) -> str:
    try:
        return win32gui.GetWindowText(hwnd)
    except Exception:
        return "<unknown>"


def main() -> None:
    mapper = CoordinateMapper()
    try:
        client_rect = mapper.get_client_rect_on_screen()
    except Exception as exc:
        logger.error(f"Failed to query MuMu client rect: {exc}")
        client_rect = None

    print(f"MuMu handles: {MUMU_HANDLES}")
    print(f"MuMu client rect (left, top, width, height): {client_rect}")
    print("Click anywhere. Press Ctrl+C to stop.\n")

    lock = threading.Lock()
    last_fg = 0

    def on_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        fg = win32gui.GetForegroundWindow()
        is_mumu = fg in MUMU_HANDLES
        mapped = mapper.map_point(x, y, clamp=True)

        nonlocal last_fg
        with lock:
            fg_changed = fg != last_fg
            last_fg = fg

        print(
            f"[{time.strftime('%H:%M:%S')}] "
            f"button={button.name} pressed={pressed} "
            f"raw=({x:5d},{y:5d}) "
            f"fg={fg} title='{get_window_title(fg)}' "
            f"is_mumu={is_mumu} "
            f"ratio=({mapped.ratio_x:.4f},{mapped.ratio_y:.4f}) "
            f"valid={mapped.valid}"
            + (" [FG_CHANGED]" if fg_changed else "")
        )

    listener = mouse.Listener(on_click=on_click)
    listener.start()
    try:
        while listener.is_alive():
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
