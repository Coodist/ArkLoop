from dataclasses import dataclass
from typing import Any, ClassVar, Dict

from src.config import GameTimeConfig as config


@dataclass(order=True, frozen=True)
class GameTime:
    """
    Represents game time as a (cycle, tick) pair on the cost-bar axis.

    `cycle` is how many times the cost bar has wrapped from full back to empty
    since the battle started (NOT the in-game cost number).  `tick` is the
    logical frame within the current cycle, in [0, TICK_MAX).

    Class Attributes:
        TICK_MAX: number of logical frames per cycle (from calibration).
    """

    cycle: int
    tick: int

    TICK_MAX: ClassVar[int] = config.TICK_MAX_DEFAULT

    def __post_init__(self):
        # Ensure ticks stay within range
        object.__setattr__(self, 'cycle', self.cycle + self.tick // self.TICK_MAX)
        object.__setattr__(self, 'tick', self.tick % self.TICK_MAX)

    @classmethod
    def set_tick_max(cls, max_value: int):
        """Set global maximum tick value."""
        if max_value <= 0:
            raise ValueError("TICK_MAX must be a positive integer.")
        cls.TICK_MAX = max_value

    @classmethod
    def get_tick_max(cls) -> int:
        """Get global maximum tick value."""
        return cls.TICK_MAX

    @classmethod
    def apply_calibration(cls, calibration_data: Dict[str, Any]):
        """
        Set TICK_MAX from a calibration data dict.

        Uses the first profile's total_frames by default.  Multi-profile
        (alternating) calibration is supported by the file format but not
        needed for the current tick detection pipeline.
        """
        profiles = calibration_data.get("profiles")
        if not profiles:
            raise ValueError("Calibration data contains no profiles.")
        total_frames = profiles[0].get("total_frames")
        if total_frames is None:
            raise ValueError("Calibration profile missing total_frames.")
        cls.set_tick_max(int(total_frames))
        logger = __import__("src.logger", fromlist=["logger"]).logger
        logger.info(f"Set TICK_MAX to {cls.TICK_MAX} from calibration.")

    @classmethod
    def apply_calibration_if_available(cls, width: int, height: int) -> bool:
        """
        Try to load and apply the newest calibration for the given resolution.

        Returns True if a calibration was found and applied, False otherwise.
        """
        from src.frame.calibration import find_calibration

        data = find_calibration(width, height)
        if data is None:
            return False
        cls.apply_calibration(data)
        return True

    def __add__(self, other: 'GameTime') -> 'GameTime':
        total_cycle = self.cycle + other.cycle + (self.tick + other.tick) // self.TICK_MAX
        total_tick = (self.tick + other.tick) % self.TICK_MAX
        return GameTime(total_cycle, total_tick)

    def __sub__(self, other: 'GameTime') -> 'GameTime':
        total_cycle = self.cycle - other.cycle + (self.tick - other.tick) // self.TICK_MAX
        total_tick = (self.tick - other.tick) % self.TICK_MAX
        return GameTime(total_cycle, total_tick)


if __name__ == "__main__":
    GameTime.set_tick_max(30)
    time1 = GameTime(cycle=50, tick=10)
    time2 = GameTime(cycle=3, tick=25)
    print(time1, time2, time1 + time2)
