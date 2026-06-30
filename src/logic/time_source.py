"""Playback time source: feed frames → produce (cycle, tick) on the cost-bar axis.

Mirrors AAO's ``aao/core/timing/time_source.py``.  Drives ``get_game_time()``
in playback: every screencap is fed in, the source detects the calibrated
tick, counts cycle wraps, and exposes ``current_tick`` / ``cycle_counter`` /
``total_elapsed_frames``.  Replaces the OCR-based cost reading that used to
drive the time axis.

Cycle wrap detection follows ArknightsCostBarRuler / TickStateTracker: a wrap
is only counted when the tick drops from the top quarter of the bar to the
bottom quarter, filtering single-frame noise.

If no valid tick is seen for ``reset_timeout`` seconds (game out of battle,
window obscured), all counters reset so the next battle starts at (0, 0).
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PIL import Image

from src.frame.detector import CostBarDetector
from src.logger import logger

__all__ = ["PlaybackTimeSource"]

_RESET_TIMEOUT_S = 1.5
_WRAP_HIGH_RATIO = 0.75
_WRAP_LOW_RATIO = 0.25


class PlaybackTimeSource:
    """Stateful time source driven by per-frame ``update(frame)`` calls."""

    def __init__(
        self,
        calibration_data: dict,
        reset_timeout: float = _RESET_TIMEOUT_S,
    ):
        self.detector = CostBarDetector(calibration_data)
        if not self.detector.is_ready():
            raise ValueError("PlaybackTimeSource requires a ready CostBarDetector")
        self.reset_timeout = reset_timeout
        self.ticks_per_cycle = self._read_ticks_per_cycle(calibration_data)

        self.cycle_counter: int = 0
        self.current_tick: Optional[int] = None
        self._last_tick: Optional[int] = None
        self._last_detect_time: float = 0.0

    @staticmethod
    def _read_ticks_per_cycle(calibration_data: dict) -> int:
        profiles = calibration_data.get("profiles") or []
        if not profiles:
            raise ValueError("Calibration has no profiles")
        total = profiles[0].get("total_frames")
        if not total or total <= 0:
            raise ValueError("Calibration profile has invalid total_frames")
        return int(total)

    # ------------------------------------------------------------------
    # Frame-driven state machine
    # ------------------------------------------------------------------
    def update(self, frame) -> Optional[int]:
        """Feed one frame.  Returns the in-cycle tick (None if not detected).

        ``frame`` accepts a numpy array (grayscale or BGR/RGB) or a PIL Image.
        After the call, ``cycle_counter`` and ``total_elapsed_frames`` reflect
        the latest reading.
        """
        tick = self._detect_tick(frame)
        now = time.time()

        if tick is None:
            # No detection — keep state but reset wrap reference so a later
            # observation doesn't spuriously trigger a wrap.
            self._last_tick = None
            if (
                self._last_detect_time
                and now - self._last_detect_time > self.reset_timeout
            ):
                if self.cycle_counter or self.current_tick is not None:
                    logger.debug(
                        f"PlaybackTimeSource: {self.reset_timeout}s without detection, "
                        f"resetting (cycle={self.cycle_counter})"
                    )
                    self._reset_state()
            return None

        # Valid tick — apply wrap detection (high→low jump).
        if self._last_tick is not None:
            high = self.ticks_per_cycle * _WRAP_HIGH_RATIO
            low = self.ticks_per_cycle * _WRAP_LOW_RATIO
            if self._last_tick > high and tick < low:
                self.cycle_counter += 1
                logger.debug(
                    f"PlaybackTimeSource: cycle wrap {self._last_tick}→{tick}, "
                    f"cycle={self.cycle_counter}"
                )

        self._last_tick = tick
        self.current_tick = tick
        self._last_detect_time = now
        return tick

    def _detect_tick(self, frame) -> Optional[int]:
        """Normalize ``frame`` and delegate to the calibrated detector."""
        if frame is None:
            return None
        if isinstance(frame, Image.Image):
            pil = frame.convert("RGB") if frame.mode != "RGB" else frame
        elif isinstance(frame, np.ndarray):
            if frame.ndim == 2:
                pil = Image.fromarray(frame).convert("RGB")
            elif frame.ndim == 3 and frame.shape[2] == 3:
                pil = Image.fromarray(frame).convert("RGB")
            else:
                return None
        else:
            return None
        return self.detector.detect_tick(pil)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @property
    def total_elapsed_frames(self) -> int:
        if self.current_tick is None:
            return self.cycle_counter * self.ticks_per_cycle
        return self.cycle_counter * self.ticks_per_cycle + self.current_tick

    @property
    def is_running(self) -> bool:
        return self.current_tick is not None

    def _reset_state(self) -> None:
        self.cycle_counter = 0
        self.current_tick = None
        self._last_tick = None
        self._last_detect_time = 0.0

    def reset(self) -> None:
        """Explicit reset (e.g., between playback sessions)."""
        self._reset_state()
        logger.debug("PlaybackTimeSource reset")
