import win32gui
import win32ui
import win32con
import cv2
import numpy as np
from typing import Tuple

from src.mumu.capture_controller import BaseCaptureController
from src.config import ImageProcessingConfig as imgconfig


class Win32CaptureController(BaseCaptureController):
    """
    Legacy Win32 BitBlt capture controller.
    Kept as a fallback when MuMu DLL capture is unavailable.
    """

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.window_dc = None
        self.mfc_dc = None
        self.save_dc = None
        self.save_bitmap = None
        self.width = 0
        self.height = 0

    def connect(self):
        # Use client area only so the captured content matches the MuMu DLL
        # screenshot (which returns the emulator display, not the window frame).
        window_left, window_top, _, _ = win32gui.GetWindowRect(self.hwnd)
        client_left, client_top = win32gui.ClientToScreen(self.hwnd, (0, 0))
        self.offset_x = client_left - window_left
        self.offset_y = client_top - window_top

        client_rect = win32gui.GetClientRect(self.hwnd)
        self.width = client_rect[2]
        self.height = client_rect[3]

        self.window_dc = win32gui.GetWindowDC(self.hwnd)
        self.mfc_dc = win32ui.CreateDCFromHandle(self.window_dc)
        self.save_dc = self.mfc_dc.CreateCompatibleDC()

        self.save_bitmap = win32ui.CreateBitmap()
        self.save_bitmap.CreateCompatibleBitmap(self.mfc_dc, self.width, self.height)
        self.save_dc.SelectObject(self.save_bitmap)
        return self

    def capture_frame(self, color: bool = False) -> np.ndarray:
        """Capture the full window as a grayscale or BGR numpy array."""
        if self.save_dc is None:
            raise RuntimeError("Win32CaptureController not connected")

        self.save_dc.BitBlt(
            (0, 0),
            (self.width, self.height),
            self.mfc_dc,
            (self.offset_x, self.offset_y),
            win32con.SRCCOPY,
        )

        bmpinfo = self.save_bitmap.GetInfo()
        signed_ints_array = self.save_bitmap.GetBitmapBits(True)
        img = np.frombuffer(signed_ints_array, dtype="uint8")
        img.shape = (bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4)

        if color:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        img = cv2.resize(img, imgconfig.SCREEN_STANDARD_SIZE)
        return img

    def capture_window_area(
        self, ratio: Tuple[float, float, float, float]
    ) -> np.ndarray:
        """Capture a ratio-defined sub-area as a grayscale numpy array."""
        if len(ratio) != 4:
            raise ValueError("Ratio must be a tuple of 4 floats")
        if not all(0 <= x <= 1 for x in ratio):
            raise ValueError("Ratio values must be between 0 and 1")
        if ratio[0] >= ratio[2] or ratio[1] >= ratio[3]:
            raise ValueError("Invalid ratio values")

        # Ratios are relative to the client area (game display).
        window_width = self.width
        window_height = self.height
        rect = (
            int(window_width * ratio[0]),
            int(window_height * ratio[1]),
            int(window_width * ratio[2]),
            int(window_height * ratio[3]),
        )

        capture_left, capture_top, capture_right, capture_bottom = rect
        capture_width = capture_right - capture_left
        capture_height = capture_bottom - capture_top

        area_bitmap = win32ui.CreateBitmap()
        area_bitmap.CreateCompatibleBitmap(self.mfc_dc, capture_width, capture_height)
        self.save_dc.SelectObject(area_bitmap)
        self.save_dc.BitBlt(
            (0, 0),
            (capture_width, capture_height),
            self.mfc_dc,
            (capture_left + self.offset_x, capture_top + self.offset_y),
            win32con.SRCCOPY,
        )

        bmpinfo = area_bitmap.GetInfo()
        signed_ints_array = area_bitmap.GetBitmapBits(True)
        img = np.frombuffer(signed_ints_array, dtype="uint8")
        img.shape = (bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

        standardized_width = capture_width * imgconfig.SCREEN_STANDARD_SIZE[0] // window_width
        standardized_height = capture_height * imgconfig.SCREEN_STANDARD_SIZE[1] // window_height
        img = cv2.resize(img, (standardized_width, standardized_height))
        return img

    def disconnect(self):
        if self.save_bitmap:
            win32gui.DeleteObject(self.save_bitmap.GetHandle())
            self.save_bitmap = None
        if self.save_dc:
            self.save_dc.DeleteDC()
            self.save_dc = None
        if self.mfc_dc:
            self.mfc_dc.DeleteDC()
            self.mfc_dc = None
        if self.window_dc:
            win32gui.ReleaseDC(self.hwnd, self.window_dc)
            self.window_dc = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
