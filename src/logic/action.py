import dataclasses
from enum import Enum
from typing import Tuple, Optional

from src.utils.typecheck import is_valid_type
from src.logic.game_time import GameTime
from src.logger import logger


class ActionType(Enum):
    DEPLOY = "部署"
    SELECT = "选中"
    SKILL = "技能"
    RETREAT = "撤退"


class DirectionType(Enum):
    UP = "上"
    DOWN = "下"
    LEFT = "左"
    RIGHT = "右"
    NONE = "无"


@dataclasses.dataclass(order=True)
class Action:
    # `cycle` is the cost-bar wrap counter — monotonic, derived from the
    # calibrated tick detector (NOT the in-game cost number, which fluctuates
    # as operators are deployed).  Together with `tick` it forms the execution
    # time axis: total_frames = cycle * TICK_MAX + tick.
    cycle: Optional[int] = None
    tick: Optional[int] = None
    action_type: Optional[ActionType] = None
    oper: Optional[str] = None
    pos: Optional[str] = None
    direction: Optional[DirectionType] = None
    alias: Optional[str] = None
    tile_pos: Optional[Tuple[int, int]] = None
    avatar_pos: Optional[Tuple[float, float]] = None
    view_pos_front: Optional[Tuple[float, float]] = None
    view_pos_side: Optional[Tuple[float, float]] = None

    def get_game_time(self):
        return GameTime(self.cycle, self.tick)

    def is_valid(self) -> bool:
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if not is_valid_type(value, field.type):
                logger.warning(f"Invalid field: {field.name}={value}")
                return False
        if self.cycle is None or self.cycle < 0:
            return False
        if self.tick is None or self.tick < 0:
            return False
        if self.action_type is None:
            return False
        if self.oper is None and self.pos is None:
            return False
        if self.action_type == ActionType.DEPLOY:
            if self.pos is None:
                return False
            if self.direction is None:
                return False
        return True
