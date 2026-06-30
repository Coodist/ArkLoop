"""CLI for offline cost bar scanning / semantic annotation.

Usage examples:
    .venv\\Scripts\\python scripts/analyze_recording.py
        Analyze the most recent recording pair in recordings/.

    .venv\\Scripts\\python scripts/analyze_recording.py \\
        --video recordings/recording_20260619_123456.mp4 \\
        --timestamps recordings/recording_20260619_123456_timestamps.json \\
        --output analysis/recording_20260619_123456_analysis.json

    .venv\\Scripts\\python scripts/analyze_recording.py \\
        --video recordings/recording_20260619_123456.mp4 \\
        --timestamps recordings/recording_20260619_123456_timestamps.json \\
        --actions recordings/actions_20260619_123456.json \\
        --output analysis/recording_20260619_123456_analysis.json
"""

import argparse
import json
import os
import sys
import time

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.logger import logger
from src.frame.pause_detector import PauseDetector
from recorder.offline_scanner import OfflineScanner, find_latest_recording_pair


def _default_output_path(video_path: str) -> str:
    base, _ = os.path.splitext(video_path)
    return f"{base}_analysis.json"


def main():
    parser = argparse.ArgumentParser(description="Offline cost bar scanner")
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="Path to recorded MP4 video",
    )
    parser.add_argument(
        "--timestamps",
        type=str,
        default=None,
        help="Path to recording_<ts>_timestamps.json",
    )
    parser.add_argument(
        "--actions",
        type=str,
        default=None,
        help="Optional path to actions_<ts>.json for semantic annotation",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: <video>_analysis.json)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Limit scan to first N frames (for quick tests)",
    )
    parser.add_argument(
        "--detect-pause",
        action="store_true",
        help="Enable pause detection overlay on top of tick-based pause state",
    )

    args = parser.parse_args()

    if args.video and args.timestamps:
        video_path = args.video
        timestamps_path = args.timestamps
    elif not args.video and not args.timestamps:
        pair = find_latest_recording_pair()
        if pair is None:
            logger.error("No recording pair found in recordings/")
            sys.exit(1)
        video_path, timestamps_path = pair
        logger.info(f"Using latest recording pair:\n  {video_path}\n  {timestamps_path}")
    else:
        logger.error("Provide both --video and --timestamps, or neither to use latest pair")
        sys.exit(1)

    output_path = args.output or _default_output_path(video_path)

    pause_detector = PauseDetector(window_size=3) if args.detect_pause else None

    start_time = time.perf_counter()
    scanner = OfflineScanner(
        video_path=video_path,
        timestamps_path=timestamps_path,
        pause_detector=pause_detector,
    )
    result = scanner.scan(max_frames=args.max_frames)
    elapsed = time.perf_counter() - start_time
    logger.info(f"Scanned {result['metadata']['scanned_frames']} frames in {elapsed:.2f}s")

    if args.actions:
        with open(args.actions, "r", encoding="utf-8") as f:
            actions_data = json.load(f)
        annotated = scanner.annotate_actions(actions_data)
        result["actions"] = annotated
        logger.info(f"Annotated {len(annotated.get('actions', []))} actions")

    scanner.save(output_path)
    logger.info(f"Analysis written to: {output_path}")

    # Final visibility: list any suspicious tick jumps detected during scan.
    anomalies = result["metadata"].get("tick_anomalies", [])
    if anomalies:
        print("\n[Tick anomaly warning]")
        print(f"Detected {len(anomalies)} suspicious tick change(s):")
        for a in anomalies:
            print(
                f"  frame {a['frame_id']} ({a['timestamp']:.3f}s): "
                f"{a['from_tick']} -> {a['to_tick']} ({a['type']})"
            )
        print("These frames may indicate OCR/calibration instability.\n")
    else:
        print("\n[Tick check] No suspicious tick jumps detected.\n")


if __name__ == "__main__":
    main()
