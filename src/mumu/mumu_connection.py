import json
import os
import sys
import win32gui
import win32con
import ctypes
import time

from src.logger import logger
from src.config import MuMuEmulatorConfig as config

__all__ = ["get_handle", "get_parent_handle", "WindowNotFoundException"]


def _user_config_path() -> str:
    """Return the path to the user-writable config.json.

    Frozen onedir: next to the EXE.  Source: project root (3 parents up
    from this file = ``<root>/src/mumu/mumu_connection.py`` → ``<root>``).
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config.json",
    )


def _resolve_names() -> tuple[str, str]:
    """Resolve (window_name, sub_window_name) from config.json with fallback.

    Reads on every refresh so a settings UI edit takes effect without an
    app restart.  Cheap: a couple of disk reads on each MuMu handle refind.
    """
    parent_name = config.WINDOW_NAME
    sub_name = config.SUB_WINDOW_NAME
    try:
        path = _user_config_path()
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mumu = (data or {}).get("mumu") or {}
            parent_name = (mumu.get("window_name") or parent_name).strip() or parent_name
            sub_name = (mumu.get("sub_window_name") or sub_name).strip() or sub_name
    except Exception as exc:
        logger.debug(f"Failed to read mumu window names from config: {exc}")
    return parent_name, sub_name


class WindowNotFoundException(Exception):
    """Exception raised when the game window is not found."""
    pass


_parent_cache: int = 0
_handle_cache: int = 0


def _enum_children(parent: int) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []

    def _cb(h: int, _lp) -> bool:
        try:
            out.append((h, win32gui.GetClassName(h), win32gui.GetWindowText(h)))
        except Exception:
            pass
        return True

    win32gui.EnumChildWindows(parent, _cb, None)
    return out


def _pick_sub(parent: int, sub_name: str) -> int:
    """Find the MuMu render/input child window.

    Only the exact configured title (``SUB_WINDOW_NAME`` in config.py) is
    accepted.  All fallbacks (``nemuwin`` / ``nemudisplay`` / largest-area)
    have been removed because they can silently select a non-interactive
    wrapper window and break axis input while screenshots still look correct.

    If the configured title is not found, return 0 so the caller can raise a
    clear error instead of continuing with the wrong window.
    """
    if not parent:
        return 0
    children = _enum_children(parent)
    if not children:
        return 0

    for h, _cls, title in children:
        if title == sub_name:
            logger.info(f"[mumu] sub matched by title={sub_name!r} h={h}")
            return h

    logger.error(
        f"[mumu] could not find sub-window with title={sub_name!r}; "
        f"candidates={[(c, t) for _h, c, t in children]}"
    )
    return 0


def _find_handles() -> tuple[int, int, str]:
    parent_name, sub_name = _resolve_names()
    parent = win32gui.FindWindow(None, parent_name)
    sub = _pick_sub(parent, sub_name)
    return parent, sub, parent_name


def _refresh() -> tuple[int, int]:
    """Re-resolve the MuMu parent + game sub-window handles.

    MuMu recreates its render sub-window when the game enters/leaves battle,
    switches scenes, or the user restarts the emulator.  The handle captured
    once at startup goes stale, surfacing as
    ``pywintypes.error: (1400, 'GetClientRect', '无效的窗口句柄')`` on the
    first mouse/capture call.  Caching here keeps the fast path branch-free
    while still recovering when the cached handle becomes invalid.
    """
    global _parent_cache, _handle_cache
    parent, sub, parent_name = _find_handles()
    _parent_cache, _handle_cache = parent, sub
    if parent and sub:
        logger.info(f"MuMu window resolved: handle={sub} parent={parent} (name={parent_name!r})")
        if win32gui.IsIconic(parent):
            win32gui.ShowWindow(parent, win32con.SW_RESTORE)
            time.sleep(0.01)
    else:
        logger.warning(
            f"MuMu window not found ({parent_name!r}); capture/control will fail until MuMu is running."
        )
    return parent, sub


def get_handle() -> int:
    """Return the (validated) game sub-window handle.  Re-finds if stale."""
    global _handle_cache, _parent_cache
    if _handle_cache and win32gui.IsWindow(_handle_cache):
        return _handle_cache
    _, sub = _refresh()
    if not sub:
        raise WindowNotFoundException(
            f"未找到 MuMu 游戏子窗口（标题={MuMuEmulatorConfig.SUB_WINDOW_NAME!r}）。"
            "请检查：1) MuMu 是否已启动；2) 设置中的子窗口标题是否与实际一致；"
            "3) 可用 spy++ 或项目提供的命令查看真实子窗口标题。"
        )
    return sub


def get_parent_handle() -> int:
    """Return the (validated) MuMu parent window handle.  Re-finds if stale."""
    global _parent_cache
    if _parent_cache and win32gui.IsWindow(_parent_cache):
        return _parent_cache
    parent, _ = _refresh()
    return parent


# Initial resolve so a log line at startup tells you whether MuMu was up.
_refresh()

# Attempt to set the program to be DPI aware to get correct window dimensions
try:
    # Set the process to be system DPI aware (2: Per-monitor DPI aware)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception as e:
    # Ignore the error if the function call is not supported
    logger.warning(f"Failed to set the program to be DPI aware: {e}")
