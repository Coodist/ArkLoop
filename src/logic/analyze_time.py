"""Game-time reader for playback.

Drives ``GameTime`` from a cost-bar ``PlaybackTimeSource`` (cycle counter +
calibrated tick).  The in-game cost number (OCR) is no longer used as the
time axis — cycle is monotonic, OCR cost is not (operators consume cost).

The time source is owned by ``AxisRunner`` (or any other caller) via
``set_time_source()``; this module just dereferences it.
"""

from __future__ import annotations

from typing import Callable, Optional

from src.config import ImageProcessingConfig as imgconfig
from src.logic.game_time import GameTime
from src.logic.time_source import PlaybackTimeSource
from src.mumu.mumu_vision import capture_game_window
from src.utils.error_to_log import ErrorToLog
from src.logger import logger

# Injected by AxisRunner.run() (and cleared in its finally block).
_time_source: Optional[PlaybackTimeSource] = None

# Optional observer notified of every ``get_game_time`` reading.  Playback uses
# this to stream the live (cycle, tick) to the UI at the runner's own read
# rate — accurate even when the game is paused / frame-stepped, because it
# reflects exactly the frames the runner samples.
_game_time_observer: Optional[Callable[[int, int], None]] = None


def set_time_source(ts: Optional[PlaybackTimeSource]) -> None:
    """Inject (or clear with ``None``) the active playback time source."""
    global _time_source
    _time_source = ts


def get_time_source() -> Optional[PlaybackTimeSource]:
    return _time_source


def set_game_time_observer(callback: Optional[Callable[[int, int], None]]) -> None:
    """Register (or clear with ``None``) a hook called on each game-time read."""
    global _game_time_observer
    _game_time_observer = callback


def get_game_time() -> GameTime:
    """Capture the game window and return current ``GameTime(cycle, tick)``.

    Raises ``ErrorToLog`` if no time source has been installed (no calibration
    available).  When the cost bar is momentarily undetectable (e.g., obscured
    by the deploy UI), the last known (cycle, tick) is returned so callers in
    bullet-time / frame-stepping loops continue working off the cached value.
    """
    ts = _time_source
    if ts is None:
        raise ErrorToLog("未初始化时间源，无法回放（需要先校准费用条）。")

    frame = capture_game_window(ratio=None)
    ts.update(frame)

    cycle = ts.cycle_counter
    tick = ts.current_tick if ts.current_tick is not None else 0

    observer = _game_time_observer
    if observer is not None:
        try:
            observer(int(cycle), int(tick))
        except Exception:
            logger.debug("game-time observer failed", exc_info=True)

    return GameTime(cycle, tick)


if __name__ == "__main__":
    import time as _time
    from src.frame.calibration import find_calibration

    std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE
    data = find_calibration(std_w, std_h)
    if data is None:
        logger.error("No calibration data available; cannot demo get_game_time().")
    else:
        set_time_source(PlaybackTimeSource(data))
        GameTime.apply_calibration(data)
        for _ in range(3):
            start = _time.time()
            gt = get_game_time()
            logger.info(f"Game time: {gt} ({(_time.time() - start) * 1000:.1f} ms)")
