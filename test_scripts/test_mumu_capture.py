"""
Test MuMu DLL capture and measure capture latency.

Usage:
    python scripts/test_mumu_capture.py --path "D:\\Program Files\\Netease\\MuMu Player 12" --instance 0
"""
import argparse
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mumu.mumu_dll_controller import MuMuPlayerController
from src.mumu.win32_capture import Win32CaptureController
from src.mumu.mumu_connection import HANDLE


def main():
    parser = argparse.ArgumentParser(description="Test MuMu DLL capture")
    parser.add_argument("--path", required=True, help="MuMu install root directory")
    parser.add_argument("--instance", type=int, default=0, help="MuMu instance index")
    parser.add_argument("--win32", action="store_true", help="Test Win32 fallback instead")
    args = parser.parse_args()

    if args.win32:
        print(f"Testing Win32 BitBlt fallback, hwnd={HANDLE}")
        controller = Win32CaptureController(HANDLE)
    else:
        print(f"Testing MuMu DLL capture: path={args.path}, instance={args.instance}")
        controller = MuMuPlayerController(args.path, args.instance)

    controller.connect()
    try:
        # Warmup
        controller.capture_frame()

        frames = 30
        start = time.perf_counter()
        for _ in range(frames):
            controller.capture_frame()
        elapsed = time.perf_counter() - start
        avg_ms = elapsed / frames * 1000

        print(f"Captured {frames} frames in {elapsed:.3f}s, avg {avg_ms:.2f}ms/frame")
        print(f"Estimated max FPS: {frames / elapsed:.1f}")

        img = controller.capture_frame()
        print(f"Image size: {img.size if hasattr(img, 'size') else img.shape}")

        if not args.win32:
            img.save("mumu_capture_test.jpg")
            print("Saved last frame to mumu_capture_test.jpg")
        else:
            import cv2
            cv2.imwrite("win32_capture_test.jpg", img)
            print("Saved last frame to win32_capture_test.jpg")
    finally:
        controller.disconnect()


if __name__ == "__main__":
    main()
