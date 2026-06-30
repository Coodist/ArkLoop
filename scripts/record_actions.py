"""Record game window video and mouse actions simultaneously.

Usage:
    .venv\Scripts\python scripts/record_actions.py --duration 10

Outputs:
    recordings/recording_<ts>.mp4
    recordings/recording_<ts>_timestamps.json
    recordings/actions_<ts>.json
    recordings/patches_<ts>/avatar_patch_*.png
"""
import argparse
import json
import os
import sys
import time

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import ImageProcessingConfig as imgconfig, RecordingConfig as recconfig
from src.frame.detector import CostBarDetector
from src.logger import logger
from src.mumu.mumu_vision import capture_game_window
from src.input.mouse_listener import MouseListener
from src.input.coordinate_mapper import CoordinateMapper
from src.input.action_recorder import ActionRecorder
from recorder.video_recorder import VideoRecorder
from recorder.avatar_patch_recorder import AvatarPatchRecorder, make_patch_callback


def main():
    parser = argparse.ArgumentParser(description="Record game video and mouse actions.")
    parser.add_argument("--duration", type=float, default=10.0, help="Recording duration in seconds.")
    parser.add_argument("--fps", type=int, default=recconfig.FPS, help="Target FPS.")
    parser.add_argument(
        "--record-moves",
        action="store_true",
        help="Record full mouse-move traces while a button is held. "
             "This enables drag-path reconstruction but installs a low-level move hook "
             "and may cause cursor lag on some systems.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=recconfig.OUTPUT_DIR,
        help="Directory for the output video and JSON files.",
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Skip MP4 recording; only save timestamps, actions, and avatar patches.",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    video_path = os.path.join(args.output_dir, f"recording_{timestamp}.mp4")
    actions_path = os.path.join(args.output_dir, f"actions_{timestamp}.json")
    patches_dir = os.path.join(args.output_dir, f"patches_{timestamp}")

    std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE
    detector = CostBarDetector.from_resolution(std_w, std_h)
    if not detector.is_ready():
        logger.error(
            f"No calibration found for {std_w}x{std_h}. "
            "Run 'scripts/calibrate.py' first, or use an existing calibration profile."
        )
        return

    tick_max = detector.calibration_data["profiles"][0]["total_frames"]
    logger.info(
        f"Preparing to record for {args.duration:.1f}s at {args.fps} FPS.\n"
        f"Outputs:\n  video -> {video_path if not args.no_video else '(disabled)'}\n"
        f"  actions -> {actions_path}\n"
        f"  patches -> {patches_dir}\n"
        f"Calibration loaded; TICK_MAX={tick_max}"
    )

    # Capture one frame up front to determine shape and warm up the capture
    # pipeline. The shared timestamp origin is set right after this frame so
    # that video frame timestamps and mouse event timestamps share the same
    # zero point.
    frame = capture_game_window(ratio=None, color=True)
    if frame is None:
        logger.error("Failed to capture game window. Is MuMu running?")
        return

    shared_start_ts = time.perf_counter()

    video_recorder = None
    if not args.no_video:
        video_recorder = VideoRecorder(
            output_path=video_path,
            fps=args.fps,
            start_ts=shared_start_ts,
        )
        video_recorder.start(frame.shape)

    # Patch recorder shares the same screenshot stream as the video recorder;
    # it does NOT capture extra frames.  The mouse listener callback only
    # updates lightweight state.
    patch_recorder = AvatarPatchRecorder(
        output_dir=patches_dir,
        max_recent_frames=max(60, args.fps * 2),
    )

    mapper = CoordinateMapper()
    patch_callback = make_patch_callback(mapper, patch_recorder)
    mouse_listener = MouseListener(
        callback=patch_callback,
        record_moves=True,  # needed to detect cursor leaving operator area
    )
    action_recorder = ActionRecorder(
        mouse_listener=mouse_listener,
        mapper=mapper,
        start_ts=shared_start_ts,
    )
    action_recorder.start()

    logger.info(
        "Recording started. Perform actions inside the MuMu window; "
        "press Ctrl+C to stop early."
    )

    interval = 1.0 / args.fps
    next_frame_time = shared_start_ts + interval
    frame_idx = 0
    frame_ticks = []
    try:
        while True:
            now = time.perf_counter()
            elapsed = now - shared_start_ts
            if elapsed >= args.duration:
                break

            if now >= next_frame_time:
                frame = capture_game_window(ratio=None, color=True)
                if frame is not None:
                    if video_recorder is not None:
                        video_recorder.record_frame(frame)

                    # Event-driven avatar patch capture reuses the same frame.
                    patch_recorder.on_frame(frame, now - shared_start_ts, frame_idx)

                    # Detect tick on the raw captured frame immediately, while
                    # the image is still uncompressed.  This matches the overlay
                    # code path and avoids H.264 compression artifacts later.
                    try:
                        pil_img = Image.fromarray(frame).convert("RGB")
                        tick = detector.detect_tick(pil_img)
                    except Exception as exc:
                        logger.warning(f"Tick detection failed for frame {frame_idx}: {exc}")
                        tick = None

                    frame_ticks.append({
                        "frame_id": frame_idx,
                        "timestamp": now - shared_start_ts,
                        "tick": tick,
                    })
                    frame_idx += 1
                else:
                    logger.warning("Capture returned None, skipping frame.")
                next_frame_time += interval

            sleep_time = max(0, next_frame_time - time.perf_counter() - 0.001)
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        logger.info("Recording interrupted by user.")

    video_result = None
    if video_recorder is not None:
        video_result = video_recorder.stop()

    # Build action data and attach pre-captured avatar patches to deploy drags.
    raw_events = action_recorder.stop()
    duration = video_result.duration if video_result else None
    actions_data = action_recorder.export(raw_events=raw_events, duration=duration)

    # Try to save any patch whose drag never left the operator area before
    # the recording stopped.
    patch_recorder._try_save_patch(force=True)
    patch_map = patch_recorder.flush()

    for action in actions_data.get("actions", []):
        if action.get("type") == "drag":
            key = f"{action.get('start_ts', 0.0):.6f}"
            patch_path = patch_map.get(key)
            if patch_path:
                action["avatar_patch"] = patch_path

    with open(actions_path, "w", encoding="utf-8") as f:
        json.dump(actions_data, f, ensure_ascii=False, indent=2)
    logger.info(f"Actions saved to: {actions_path}")

    timestamps_path = os.path.join(args.output_dir, f"recording_{timestamp}_timestamps.json")
    timestamps_data = {
        "video_path": video_path if video_result else None,
        "actions_path": actions_path,
        "patches_dir": patches_dir,
        "frame_timestamps": video_result.frame_timestamps if video_result else [ft["timestamp"] for ft in frame_ticks],
        "frame_ticks": frame_ticks,
        "frame_count": video_result.frame_count if video_result else len(frame_ticks),
        "duration": video_result.duration if video_result else (frame_ticks[-1]["timestamp"] if frame_ticks else 0.0),
        "fps": args.fps,
    }
    with open(timestamps_path, "w", encoding="utf-8") as f:
        json.dump(timestamps_data, f, ensure_ascii=False, indent=2)
    logger.info(f"Frame timestamps saved to: {timestamps_path}")

    missed_ticks = sum(1 for ft in frame_ticks if ft["tick"] is None)
    logger.info(
        f"Frames captured: {len(frame_ticks)}, "
        f"Tick detection failures: {missed_ticks}/{len(frame_ticks)}, "
        f"Avatar patches: {len(patch_map)}\n"
        f"Actions saved to: {actions_path}"
    )


if __name__ == "__main__":
    main()
