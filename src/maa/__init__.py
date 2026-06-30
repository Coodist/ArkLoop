"""MAA recognition integration layer for prts-plus."""

from src.maa.core import MaaInitError, get_tasker, reset_tasker
from src.maa.recognizer import MaaRecognizer
from src.maa.templates import crop_template, make_template_from_screenshot
from src.maa.view_detection import create_side_view_detector

__all__ = [
    "MaaInitError",
    "MaaRecognizer",
    "create_side_view_detector",
    "crop_template",
    "get_tasker",
    "make_template_from_screenshot",
    "reset_tasker",
]
