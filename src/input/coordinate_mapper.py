"""Convert screen coordinates to normalized game coordinates."""

from dataclasses import dataclass
from typing import Optional, Tuple

import win32gui

from src.config import InputRecordingConfig as inputconfig
from src.mumu.mumu_connection import get_handle
from src.logger import logger

__all__ = ["CoordinateMapper", "MappedCoordinates"]


@dataclass
class MappedCoordinates:
    """Screen point mapped into the MuMu client area and standardized canvas."""

    screen_x: int
    screen_y: int
    client_x: float  # pixels inside the client area
    client_y: float
    ratio_x: float  # 0.0 - 1.0 inside the client area
    ratio_y: float
    game_x: float  # 0.0 - SCREEN_STANDARD_SIZE[0]
    game_y: float
    valid: bool  # False if the point falls outside the client area


class CoordinateMapper:
    """
    Map screen absolute coordinates to the normalized 1280x720 game canvas.

    The mapping is based on the MuMu emulator's client area (the actual game
    display, excluding window decorations), so it stays consistent with the
    screenshots produced by ``capture_game_window``.
    """

    def __init__(self, hwnd: Optional[int] = None):
        # Store the override (if any); resolve the live handle on each use so
        # we recover when MuMu recreates its render sub-window.
        self._hwnd_override = hwnd

    @property
    def hwnd(self) -> int:
        return self._hwnd_override if self._hwnd_override is not None else get_handle()

    def get_client_rect_on_screen(self) -> Tuple[int, int, int, int]:
        """
        Return (left, top, width, height) of the window's client area in screen
        coordinates. Raises ``RuntimeError`` if the window cannot be found.
        """
        if self.hwnd == 0 or not win32gui.IsWindow(self.hwnd):
            raise RuntimeError("MuMu game window handle is not valid")

        client_left, client_top = win32gui.ClientToScreen(self.hwnd, (0, 0))
        _, _, client_width, client_height = win32gui.GetClientRect(self.hwnd)
        return client_left, client_top, client_width, client_height

    def map_point(
        self,
        screen_x: int,
        screen_y: int,
        clamp: bool = True,
    ) -> MappedCoordinates:
        """
        Map a screen coordinate to game canvas coordinates.

        Args:
            screen_x: Absolute screen X coordinate.
            screen_y: Absolute screen Y coordinate.
            clamp: If True, clamp ratio values to [0, 1] so points just outside
                the client area still produce a valid mapping.

        Returns:
            MappedCoordinates with both ratio and pixel coordinates.
        """
        try:
            client_left, client_top, client_width, client_height = self.get_client_rect_on_screen()
        except Exception as e:
            logger.warning(f"Failed to query MuMu client rect: {e}")
            return MappedCoordinates(
                screen_x=screen_x,
                screen_y=screen_y,
                client_x=0.0,
                client_y=0.0,
                ratio_x=0.0,
                ratio_y=0.0,
                game_x=0.0,
                game_y=0.0,
                valid=False,
            )

        client_x = screen_x - client_left
        client_y = screen_y - client_top

        if client_width <= 0 or client_height <= 0:
            return MappedCoordinates(
                screen_x=screen_x,
                screen_y=screen_y,
                client_x=float(client_x),
                client_y=float(client_y),
                ratio_x=0.0,
                ratio_y=0.0,
                game_x=0.0,
                game_y=0.0,
                valid=False,
            )

        ratio_x = client_x / client_width
        ratio_y = client_y / client_height

        valid = 0.0 <= ratio_x <= 1.0 and 0.0 <= ratio_y <= 1.0

        if clamp:
            ratio_x = max(0.0, min(1.0, ratio_x))
            ratio_y = max(0.0, min(1.0, ratio_y))

        std_w, std_h = inputconfig.SCREEN_STANDARD_SIZE
        game_x = ratio_x * std_w
        game_y = ratio_y * std_h

        return MappedCoordinates(
            screen_x=screen_x,
            screen_y=screen_y,
            client_x=float(client_x),
            client_y=float(client_y),
            ratio_x=ratio_x,
            ratio_y=ratio_y,
            game_x=game_x,
            game_y=game_y,
            valid=valid,
        )

    def map_event(
        self,
        screen_x: int,
        screen_y: int,
    ) -> Tuple[float, float]:
        """
        Convenience helper returning just the normalized (ratio_x, ratio_y).

        This matches the ratio convention used elsewhere in the project.
        """
        mapped = self.map_point(screen_x, screen_y, clamp=True)
        return mapped.ratio_x, mapped.ratio_y
