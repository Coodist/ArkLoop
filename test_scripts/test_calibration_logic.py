"""Synthetic unit tests for the cost bar calibration / detection logic.

These tests do NOT require the game or emulator to be running.  They draw
fake cost bars with Pillow and verify that the calibration pipeline produces
the expected tick values.

Usage:
    .venv\Scripts\python scripts\test_calibration_logic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw

from src.config import ImageProcessingConfig as imgconfig
from src.frame.calibration import (
    _get_raw_filled_pixel_width,
    calibrate,
    find_calibration,
    find_cost_bar_roi,
    get_tick_from_calibration,
    load_calibration_by_filename,
    save_calibration_data,
)
from src.frame.detector import CostBarDetector
from src.logic.game_time import GameTime


def make_frame(tick: int, total_frames: int = 30) -> Image.Image:
    """Draw a synthetic 1280x720 frame with the cost bar at the given tick."""
    w, h = imgconfig.SCREEN_STANDARD_SIZE
    roi = find_cost_bar_roi(w, h)
    max_width = roi[1] - roi[0]

    img = Image.new("RGBA", (w, h), (30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    if tick > 0:
        x2 = roi[0] + int(max_width * tick / (total_frames - 1))
        draw.rectangle([roi[0], roi[2] - 2, x2, roi[2] + 2], fill=(255, 255, 255, 255))
    return img


def test_roi_and_width():
    w, h = imgconfig.SCREEN_STANDARD_SIZE
    roi = find_cost_bar_roi(w, h)
    assert roi[1] > roi[0], "ROI x2 must be > x1"

    full = make_frame(29)
    assert _get_raw_filled_pixel_width(full, roi) == roi[1] - roi[0]

    empty = make_frame(0)
    assert _get_raw_filled_pixel_width(empty, roi) == 0

    half = make_frame(15)
    width = _get_raw_filled_pixel_width(half, roi)
    assert 0 < width < roi[1] - roi[0]


def test_calibration_clustering():
    frames = []
    for cycle in range(7):
        for tick in range(30):
            frames.append(make_frame(tick))

    idx = 0

    def fake_capture():
        nonlocal idx
        f = frames[idx]
        idx = (idx + 1) % len(frames)
        return f

    w, h = imgconfig.SCREEN_STANDARD_SIZE
    data = calibrate(fake_capture, w, h, num_cycles=6)
    assert data["profiles"][0]["total_frames"] == 30


def test_save_load():
    data = {
        "detection_mode": "single",
        "profiles": [{"total_frames": 30, "pixel_map": {"0": 0, "60": 15, "120": 29}}],
        "screen_width": 1280,
        "screen_height": 720,
    }
    filename = save_calibration_data(data, 1280, 720, basename="test")
    loaded = load_calibration_by_filename(filename)
    assert loaded["profiles"][0]["total_frames"] == 30
    found = find_calibration(1280, 720)
    assert found is not None
    os.remove(os.path.join("calibration", filename))


def test_detector_lookup():
    w, h = imgconfig.SCREEN_STANDARD_SIZE
    roi = find_cost_bar_roi(w, h)
    max_width = roi[1] - roi[0]

    pixel_map = {"0": 0}
    for tick in range(1, 30):
        pixel_map[str(int(max_width * tick / 29))] = tick

    cal = {
        "profiles": [{"total_frames": 30, "pixel_map": pixel_map}],
        "screen_width": w,
        "screen_height": h,
    }
    detector = CostBarDetector(cal)
    for expected_tick in [0, 5, 15, 29]:
        assert detector.detect_tick(make_frame(expected_tick)) == expected_tick


def test_game_time_apply_calibration():
    GameTime.set_tick_max(30)
    data = {"profiles": [{"total_frames": 37, "pixel_map": {}}]}
    GameTime.apply_calibration(data)
    assert GameTime.get_tick_max() == 37

    # Reset back to default for other tests.
    GameTime.set_tick_max(30)


def main():
    print("Running calibration logic tests...")
    test_roi_and_width()
    test_calibration_clustering()
    test_save_load()
    test_detector_lookup()
    test_game_time_apply_calibration()
    print("All calibration logic tests passed.")


if __name__ == "__main__":
    main()
