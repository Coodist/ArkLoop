"""Reusable tick/cycle state tracker for live and offline analysis."""

from typing import Optional

from src.logger import logger

__all__ = ["TickStateTracker"]


class TickStateTracker:
    """
    Track cost bar tick, cycle wraps, and total elapsed frames.

    Decoupled from threading/UI so it can be used both by ``AnalysisWorker``
    (live) and ``OfflineScanner`` (recorded video).
    """

    def __init__(self, ticks_per_cycle: int = 30):
        if ticks_per_cycle <= 0:
            raise ValueError("ticks_per_cycle must be positive")
        self.ticks_per_cycle = ticks_per_cycle
        self.cycle_counter: int = 0
        self.total_elapsed_frames: int = 0
        self.current_tick: Optional[int] = None
        self.last_tick: Optional[int] = None
        self.paused: bool = False

    def update(self, tick: Optional[int]) -> dict:
        """
        Update state with a new tick observation.

        Args:
            tick: Detected tick in ``[0, ticks_per_cycle - 1]``, or ``None``
                if detection failed / game paused.

        Returns:
            Snapshot dict with current state and transition flags.
        """
        previous_paused = self.paused
        wrapped = False

        if tick is None:
            self.paused = True
            # Reset last_tick so that a later valid observation does not
            # immediately wrap just because it is slightly lower than the
            # previous cycle's last known tick.
            self.last_tick = None
        else:
            self.paused = False
            self.last_tick = self.current_tick
            self.current_tick = tick

            if self.last_tick is not None:
                # Only count a cycle wrap when the tick drops from the high
                # end of the bar to the low end.  This matches the behaviour of
                # ArknightsCostBarRuler and filters out single-frame noise
                # (e.g. 26 -> 25) that would otherwise look like a wrap.
                high_threshold = self.ticks_per_cycle * 0.75
                low_threshold = self.ticks_per_cycle * 0.25
                if self.last_tick > high_threshold and tick < low_threshold:
                    self.cycle_counter += 1
                    wrapped = True
                    logger.debug(
                        f"Cycle wrap: {self.last_tick} -> {tick}, "
                        f"cycle={self.cycle_counter}"
                    )

            # Total elapsed frames = completed cycles * ticks per cycle + current tick.
            self.total_elapsed_frames = (
                self.cycle_counter * self.ticks_per_cycle + tick
            )

        return {
            "tick": self.current_tick,
            "cycle": self.cycle_counter,
            "total_elapsed_frames": self.total_elapsed_frames,
            "paused": self.paused,
            "resumed": previous_paused and not self.paused,
            "wrapped": wrapped,
        }

    def snapshot(self) -> dict:
        """Return current state without modifying it."""
        return {
            "tick": self.current_tick,
            "cycle": self.cycle_counter,
            "total_elapsed_frames": self.total_elapsed_frames,
            "paused": self.paused,
        }
