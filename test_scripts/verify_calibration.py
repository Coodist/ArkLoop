"""Live verification of the cost bar calibration.

Usage:
    .venv\Scripts\python scripts\verify_calibration.py

Continuously captures the game window and prints the detected tick.
Press Ctrl+C to stop.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import ImageProcessingConfig as imgconfig
from src.frame.detector import CostBarDetector
from src.logic.game_time import GameTime
from src.logger import logger


def main():
    logger.info("Starting calibration verification.")
    std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE
    detector = CostBarDetector.from_resolution(std_w, std_h)
    if not detector.is_ready():
        logger.error(f"No calibration found for {std_w}x{std_h}. Run scripts/calibrate.py first.")
        return

    GameTime.apply_calibration(detector.calibration_data)
    logger.info(f"Calibration loaded. TICK_MAX = {GameTime.get_tick_max()}")
    logger.info("Reading ticks from the game window. Press Ctrl+C to stop.")

    last_tick = None
    try:
        while True:
            tick = detector.detect_tick_from_game()
            if tick is None:
                logger.info("Tick detection returned None (cost bar not visible?)")
            elif tick != last_tick:
                logger.info(f"Tick: {tick}")
                last_tick = tick
            time.sleep(0.033)
    except KeyboardInterrupt:
        logger.info("Verification stopped.")


if __name__ == "__main__":
    main()
