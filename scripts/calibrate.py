"""Interactive cost bar calibration script.

Usage:
    .venv\Scripts\python scripts\calibrate.py [--cycles N] [--width W] [--height H]

The script will capture the game window, resize the captured frame to the
target resolution, and calibrate the cost bar tick detector. The resulting
calibration file is tied to this resolution.
"""
import argparse
import os
import sys
import time

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import ImageProcessingConfig as imgconfig
from src.frame.calibration import calibrate, save_calibration_data
from src.logic.game_time import GameTime
from src.logger import logger
from src.mumu.mumu_vision import capture_game_window


def main():
    std_w_default, std_h_default = imgconfig.SCREEN_STANDARD_SIZE

    parser = argparse.ArgumentParser(
        description="Calibrate the Arknights cost bar tick detector."
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=6,
        help="Number of cost-bar cycles to capture and average (default: 6).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=std_w_default,
        help=f"Target screen width for calibration (default: {std_w_default}).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=std_h_default,
        help=f"Target screen height for calibration (default: {std_h_default}).",
    )
    args = parser.parse_args()

    std_w, std_h = args.width, args.height
    if (std_w, std_h) != imgconfig.SCREEN_STANDARD_SIZE:
        logger.warning(
            f"Calibrating for non-standard resolution {std_w}x{std_h}. "
            f"Make sure the game window matches this resolution."
        )

    logger.info("Starting cost bar calibration.")
    logger.info("Make sure the game is visible and a level is running (cost bar is filling).")

    def capture_func():
        gray = capture_game_window(ratio=None)
        im = Image.fromarray(gray).convert("RGB")
        if im.size != (std_w, std_h):
            im = im.resize((std_w, std_h), Image.LANCZOS)
        return im

    # Warm up the capture pipeline once.
    capture_func()
    logger.info("Capture pipeline ready. Calibrating...")

    data = calibrate(capture_func, std_w, std_h, num_cycles=args.cycles)
    filename = save_calibration_data(data, std_w, std_h, basename="default")
    logger.info(f"Calibration saved: {filename}")

    GameTime.apply_calibration(data)
    logger.info(f"TICK_MAX set to {GameTime.get_tick_max()}")


if __name__ == "__main__":
    main()
