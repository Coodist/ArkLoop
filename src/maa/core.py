"""MAA core initialization for prts-plus.

Provides a lazily-initialized MAA Tasker in "feed-image" mode: we do not
rely on MAA's controller for screenshots because prts-plus already has its
own capture stack (MuMu DLL / Win32 BitBlt). Any BGR numpy frame can be
passed directly to ``Tasker.run_task`` / ``Tasker.post_recognition``.

A minimal no-op controller is bound only because ``Tasker.bind`` requires
one; it is never used for recognition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from maa.controller import CustomController
from maa.resource import Resource
from maa.tasker import Tasker

from src.logger import logger

__all__ = ["MaaInitError", "get_tasker", "reset_tasker"]


class MaaInitError(Exception):
    """Raised when MAA Resource/Tasker fails to initialize."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _NoOpController(CustomController):
    """A do-nothing controller used only to satisfy Tasker.bind().

    We never call its screencap/click methods; prts-plus feeds images
    directly into MAA recognition APIs.
    """

    def connect(self) -> bool:
        return True

    def request_uuid(self) -> str:
        return "prts-plus-noop"

    def start_app(self, intent: str) -> bool:
        return True

    def stop_app(self, intent: str) -> bool:
        return True

    def screencap(self) -> np.ndarray:
        # Return a tiny blank BGR image. Should never be used.
        return np.zeros((10, 10, 3), dtype=np.uint8)

    def click(self, x: int, y: int) -> bool:
        return True

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        return True

    def touch_down(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return True

    def touch_move(self, contact: int, x: int, y: int, pressure: int) -> bool:
        return True

    def touch_up(self, contact: int) -> bool:
        return True

    def click_key(self, keycode: int) -> bool:
        return True

    def input_text(self, text: str) -> bool:
        return True


# Module-level singletons.
_resource: Optional[Resource] = None
_tasker: Optional[Tasker] = None


def _maa_nodes_dir() -> Path:
    """Return the directory that acts as MAA ``resource/base`` bundle."""
    return Path(__file__).resolve().parent / "nodes"


def _init_maa() -> Tasker:
    """Initialize MAA Resource and Tasker, returning a usable Tasker."""
    global _resource, _tasker

    if _tasker is not None:
        return _tasker

    bundle = _maa_nodes_dir()
    if not bundle.is_dir():
        raise MaaInitError(f"MAA resource bundle not found: {bundle}")

    logger.info(f"Loading MAA resource bundle from {bundle}")
    resource = Resource()
    job = resource.post_bundle(str(bundle))
    if hasattr(job, "wait"):
        job.wait()

    controller = _NoOpController()
    controller.post_connection().wait()

    tasker = Tasker()
    tasker.bind(resource, controller)
    if not tasker.inited:
        raise MaaInitError("MAA Tasker initialization failed")

    _resource = resource
    _tasker = tasker
    logger.info("MAA Tasker initialized successfully")
    return _tasker


def get_tasker() -> Tasker:
    """Return the singleton MAA Tasker, initializing it on first call."""
    if _tasker is None:
        return _init_maa()
    return _tasker


def reset_tasker() -> None:
    """Reset the singleton so the next ``get_tasker`` call reinitializes.

    Useful for tests or when the resource bundle is modified at runtime.
    """
    global _resource, _tasker
    _tasker = None
    _resource = None
    logger.info("MAA tasker reset")
