"""Video recording of the game window with per-frame timestamps."""
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
from imageio_ffmpeg import get_ffmpeg_exe

import cv2
from src.config import RecordingConfig as recconfig
from src.logger import logger

__all__ = ["VideoRecorder", "RecordingResult"]


@dataclass
class RecordingResult:
    """Result of a completed recording session."""

    video_path: str
    frame_timestamps: List[float]
    frame_count: int
    duration: float
    average_fps: float


class VideoRecorder:
    """
    Records a sequence of BGR frames into an H.264 video file using FFmpeg.

    The recorder keeps a list of per-frame timestamps (seconds since start)
    so offline analysis can reason about real elapsed time even when the
    capture rate is not perfectly constant.
    """

    def __init__(
        self,
        output_path: Optional[str] = None,
        fps: int = 30,
        codec_preset: str = "ultrafast",
        pixel_format: str = "yuv420p",
        start_ts: Optional[float] = None,
    ):
        if output_path is None:
            output_dir = Path(recconfig.OUTPUT_DIR)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = str(output_dir / f"recording_{timestamp}.mp4")

        self.output_path = output_path
        self.fps = fps
        self.codec_preset = codec_preset
        self.pixel_format = pixel_format
        self._external_start_ts = start_ts

        self._ffmpeg: Optional[subprocess.Popen] = None
        self._frame_timestamps: List[float] = []
        self._start_ts: Optional[float] = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._is_recording = False

    def start(self, frame_shape: tuple) -> None:
        """
        Start FFmpeg and prepare to receive frames.

        Args:
            frame_shape: (height, width) or (height, width, channels) of incoming frames.
        """
        if self._is_recording:
            raise RuntimeError("Recorder already started.")

        height, width = frame_shape[:2]
        self._width = width
        self._height = height

        ffmpeg_exe = get_ffmpeg_exe()
        if not ffmpeg_exe or not os.path.isfile(ffmpeg_exe):
            raise RuntimeError("FFmpeg executable not found. Please install imageio-ffmpeg or ffmpeg.")

        # Ensure output directory exists.
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

        command = [
            ffmpeg_exe,
            "-y",  # overwrite output
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "bgr24",
            "-r", str(self.fps),
            "-i", "-",  # read from stdin
            "-c:v", "libx264",
            "-preset", self.codec_preset,
            "-pix_fmt", self.pixel_format,
            "-crf", "23",
            "-an",  # no audio
            self.output_path,
        ]

        logger.info(f"Starting FFmpeg: {' '.join(command)}")
        self._stderr_path = self.output_path + ".ffmpeg.log"
        self._stderr_file = open(self._stderr_path, "w", encoding="utf-8", errors="replace")
        self._ffmpeg = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=self._stderr_file,
        )
        self._start_ts = (
            self._external_start_ts
            if self._external_start_ts is not None
            else time.perf_counter()
        )
        self._frame_timestamps = []
        self._is_recording = True
        logger.info(f"Recording started: {self.output_path}")

    def record_frame(self, frame: np.ndarray) -> None:
        """Write a single BGR frame and record its timestamp."""
        if not self._is_recording or self._ffmpeg is None:
            raise RuntimeError("Recorder not started.")

        if frame.shape[:2] != (self._height, self._width):
            raise ValueError(
                f"Frame shape {frame.shape[:2]} does not match expected {(self._height, self._width)}"
            )

        # Ensure BGR format and contiguous memory.
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        elif frame.shape[2] == 3:
            frame = frame.copy()

        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)

        self._ffmpeg.stdin.write(frame.tobytes())
        self._frame_timestamps.append(time.perf_counter() - self._start_ts)

    def stop(self) -> RecordingResult:
        """Stop recording and wait for FFmpeg to finalize the video."""
        if not self._is_recording or self._ffmpeg is None:
            raise RuntimeError("Recorder not started.")

        self._ffmpeg.stdin.close()
        return_code = self._ffmpeg.wait()
        self._stderr_file.close()

        if return_code != 0:
            stderr = ""
            if os.path.isfile(self._stderr_path):
                with open(self._stderr_path, "r", encoding="utf-8", errors="replace") as f:
                    stderr = f.read()
            raise RuntimeError(f"FFmpeg exited with code {return_code}.\n{stderr}")

        duration = self._frame_timestamps[-1] if self._frame_timestamps else 0.0
        frame_count = len(self._frame_timestamps)
        average_fps = frame_count / duration if duration > 0 else 0.0

        self._is_recording = False
        logger.info(
            f"Recording finished: {frame_count} frames in {duration:.3f}s "
            f"(avg {average_fps:.2f} FPS)"
        )

        return RecordingResult(
            video_path=self.output_path,
            frame_timestamps=self._frame_timestamps.copy(),
            frame_count=frame_count,
            duration=duration,
            average_fps=average_fps,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._is_recording:
            self.stop()
        return False
