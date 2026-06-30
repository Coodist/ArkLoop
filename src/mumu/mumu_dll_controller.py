"""
MuMu DLL screenshot controller.

The implementation logic is adapted from MaaFramework
(https://github.com/MaaXYZ/MaaFramework), and this file follows LGPL-3.0.
"""
import ctypes
import logging
from ctypes import wintypes
from pathlib import Path
import sys
import time
from typing import Optional, Tuple, List

from PIL import Image

from src.mumu.capture_controller import BaseCaptureController

logger = logging.getLogger(__name__)

# Known Arknights package names for display id lookup
KNOWN_PACKAGE_NAMES: List[str] = [
    "com.hypergryph.arknights",          # Official server
    "com.hypergryph.arknights.bilibili", # Bilibili server
    "com.YoStarJP.Arknights",            # JP
    "com.YoStarEN.Arknights",            # EN
    "com.YoStarKR.Arknights",            # KR
    "tw.txwy.and.arknights",             # TW
]


class MuMuPlayerController(BaseCaptureController):
    """Capture screen via MuMu emulator's external_renderer_ipc.dll."""

    def __init__(
        self,
        mumu_install_path: str,
        instance_index: int = 0,
        package_name_list: Optional[List[str]] = None,
    ):
        logger.info(
            f"MuMuPlayerController init: path='{mumu_install_path}', instance={instance_index}"
        )
        if sys.platform != "win32":
            raise NotImplementedError("MuMuPlayerController only supports Windows.")

        self.install_path = Path(mumu_install_path)
        if not self.install_path.exists():
            raise FileNotFoundError(f"MuMu install path does not exist: {self.install_path}")

        self.instance_index = instance_index
        self.package_name_list = package_name_list or KNOWN_PACKAGE_NAMES

        self.dll: Optional[ctypes.WinDLL] = None
        self.handle: int = 0
        self.display_id: int = -1

        self.width: int = 0
        self.height: int = 0
        self.buffer: Optional[ctypes.Array] = None

    def _find_and_load_dll(self) -> Tuple[Path, Path]:
        """Find the core DLL under MuMu install directory and return correct root."""
        logger.info(f"Searching for DLL under '{self.install_path}' and its parent...")
        initial_path = self.install_path
        search_bases = [initial_path]
        if initial_path.parent != initial_path:
            search_bases.append(initial_path.parent)

        relative_dll_paths = [
            Path("nx_device") / "12.0" / "shell" / "sdk" / "external_renderer_ipc.dll",
            Path("nx_main") / "sdk" / "external_renderer_ipc.dll",
            Path("shell") / "sdk" / "external_renderer_ipc.dll",
        ]

        for base in search_bases:
            for rel_path in relative_dll_paths:
                dll_candidate_path = base / rel_path
                if dll_candidate_path.exists():
                    logger.info(f"Found DLL at '{dll_candidate_path}' with base '{base}'")
                    return dll_candidate_path, base

        raise FileNotFoundError(
            "Could not find 'external_renderer_ipc.dll' in the specified MuMu path.\n"
            "Please provide the MuMu root directory or the 'shell' subdirectory."
        )

    def _setup_function_prototypes(self):
        logger.debug("Setting up DLL function prototypes...")
        self.dll.nemu_connect.argtypes = [wintypes.LPCWSTR, ctypes.c_int]
        self.dll.nemu_connect.restype = ctypes.c_int

        self.dll.nemu_disconnect.argtypes = [ctypes.c_int]

        self.dll.nemu_capture_display.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        self.dll.nemu_capture_display.restype = ctypes.c_int

        self.dll.nemu_get_display_id.argtypes = [
            ctypes.c_int,
            wintypes.LPCSTR,
            ctypes.c_int,
        ]
        self.dll.nemu_get_display_id.restype = ctypes.c_int
        logger.debug("DLL function prototypes set.")

    def connect(self):
        logger.info("Connecting to MuMu instance...")
        dll_path, correct_root_path = self._find_and_load_dll()
        self.install_path = correct_root_path
        logger.info(f"Corrected MuMu root: {self.install_path}")

        logger.info(f"Loading DLL: {dll_path}")
        self.dll = ctypes.WinDLL(str(dll_path))
        logger.info("DLL loaded.")

        self._setup_function_prototypes()

        logger.info("Connecting to MuMu instance via DLL...")
        self.handle = self.dll.nemu_connect(str(self.install_path), self.instance_index)
        if self.handle == 0:
            raise ConnectionError(
                f"Failed to connect to MuMu (handle=0). Check instance index {self.instance_index}."
            )
        logger.info(f"Connected, handle: {self.handle}")

        logger.info("Querying display id for known packages...")
        for pkg_name in self.package_name_list:
            logger.debug(f"Trying package: '{pkg_name}'...")
            pkg_bytes = pkg_name.encode("utf-8")
            current_display_id = self.dll.nemu_get_display_id(self.handle, pkg_bytes, 0)
            if current_display_id >= 0:
                self.display_id = current_display_id
                logger.info(f"Display id {self.display_id} found for package '{pkg_name}'")
                break
            else:
                logger.debug(f"Package '{pkg_name}' not found (code: {current_display_id}).")

        if self.display_id < 0:
            logger.warning("No display id found for known packages, falling back to 0.")
            self.display_id = 0

        logger.info("Initializing capture...")
        width_ptr = ctypes.pointer(ctypes.c_int())
        height_ptr = ctypes.pointer(ctypes.c_int())

        ret = self.dll.nemu_capture_display(
            self.handle, self.display_id, 0, width_ptr, height_ptr, None
        )
        if ret != 0:
            raise RuntimeError(f"Failed to get screen size, error code: {ret}")

        self.width = width_ptr.contents.value
        self.height = height_ptr.contents.value
        logger.info(f"Screen size: {self.width}x{self.height}")

        buffer_size = self.width * self.height * 4
        self.buffer = (ctypes.c_ubyte * buffer_size)()
        logger.info(f"Image buffer created (size: {buffer_size} bytes).")
        return self

    def capture_frame(self) -> Image.Image:
        if not all([self.dll, self.handle, self.buffer]):
            raise ConnectionError("Not connected. Please call connect() first.")

        ret = self.dll.nemu_capture_display(
            self.handle,
            self.display_id,
            len(self.buffer),
            ctypes.pointer(ctypes.c_int(self.width)),
            ctypes.pointer(ctypes.c_int(self.height)),
            self.buffer,
        )

        if ret != 0:
            raise RuntimeError(f"Capture failed, error code: {ret}")

        return self._conv()

    def _conv(self) -> Image.Image:
        """Convert raw buffer to PIL Image (RGB)."""
        image_raw = Image.frombuffer(
            "RGBA", (self.width, self.height), self.buffer, "raw", "RGBA", 0, 1
        )
        image_flipped = image_raw.transpose(Image.FLIP_TOP_BOTTOM)
        return image_flipped.convert("RGB")

    def disconnect(self):
        if self.dll and self.handle != 0:
            logger.info("Disconnecting from MuMu...")
            self.dll.nemu_disconnect(self.handle)
            self.handle = 0
            logger.info("Disconnected.")

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test MuMuPlayerController")
    parser.add_argument("--path", required=True, help="MuMu install path")
    parser.add_argument("--instance", type=int, default=0, help="Instance index")
    args = parser.parse_args()

    controller = MuMuPlayerController(args.path, args.instance)
    controller.connect()
    try:
        img = controller.capture_frame()
        print(f"Captured: {img.size}")
        img.save("mumu_capture.jpg")
        print("Saved to mumu_capture.jpg")
    finally:
        controller.disconnect()
