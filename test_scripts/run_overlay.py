"""Launch the real-time overlay for tick/frame display.

Usage:
    .venv\Scripts\python scripts/run_overlay.py

The overlay will show the current cost bar tick. Click "Calibrate" if no
calibration data is found for 1280x720.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app import run_overlay_app

if __name__ == "__main__":
    run_overlay_app()
