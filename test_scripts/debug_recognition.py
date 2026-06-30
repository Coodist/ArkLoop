"""Debug why recorded actions are not recognized as deploy/skill/retreat.

Loads the latest recording analysis + actions (or explicit paths) and prints:
- each raw action
- which semantic type the recognizer assigned
- why it was ignored, if it was
- avatar match score for deploy drags

Usage:
    .venv\Scripts\python scripts/debug_recognition.py --map-code 1-7

Or explicit paths:
    .venv\Scripts\python scripts/debug_recognition.py `
      --analysis recordings/recording_<ts>_analysis.json `
      --actions recordings/actions_<ts>.json `
      --map-code 1-7
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from src.cache import get_map_by_code
from src.config import GameRatioConfig as ratioconfig
from src.config import InputRecordingConfig as inputconfig
from src.logger import logger
from recorder.action_recognizer import (
    ActionRecognizer,
    AvatarMatcher,
    RETREAT_CONTOUR,
    SKILL_CONTOUR,
    _direction_drag_quad,
    _make_contour,
)

try:
    from src.maa import create_side_view_detector
except Exception as exc:
    create_side_view_detector = None  # type: ignore[assignment, misc]
    logger.warning(f"MAA side-view detector unavailable: {exc}")
from recorder.axis_writer import _VideoFrameProvider


def _find_latest_pair(recordings_dir: Path):
    analyses = sorted(
        recordings_dir.glob("recording_*_analysis.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for analysis in analyses:
        m = re.search(r"recording_(\d{8}_\d{6})", analysis.name)
        if not m:
            continue
        ts = m.group(1)
        actions = recordings_dir / f"actions_{ts}.json"
        if actions.is_file():
            return analysis, actions
    return None, None


def _distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def main():
    parser = argparse.ArgumentParser(description="Debug action recognition.")
    parser.add_argument("--analysis", type=Path, help="Path to analysis JSON")
    parser.add_argument("--actions", type=Path, help="Path to actions JSON")
    parser.add_argument("--map-code", required=True, help="Map code, e.g. 1-7")
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=Path("recordings"),
        help="Directory to search for latest recording pair",
    )
    args = parser.parse_args()

    analysis_path = args.analysis
    actions_path = args.actions

    if analysis_path is None or actions_path is None:
        analysis_path, actions_path = _find_latest_pair(args.recordings_dir)
        if analysis_path is None:
            print("Could not find a recording pair in recordings/")
            return

    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)
    with open(actions_path, "r", encoding="utf-8") as f:
        actions_data = json.load(f)

    map_data = get_map_by_code(args.map_code)
    frames = analysis_data.get("frames", [])
    metadata = analysis_data.get("metadata", {})
    video_path = metadata.get("video_path")
    timestamps_path = metadata.get("timestamps_path")
    timestamps = []
    if timestamps_path and Path(timestamps_path).is_file():
        with open(timestamps_path, "r", encoding="utf-8") as f:
            timestamps = [float(t) for t in json.load(f).get("frame_timestamps", [])]

    frame_provider = None
    if video_path:
        frame_provider = _VideoFrameProvider(video_path, timestamps)

    avatar_matcher = AvatarMatcher()

    view_detector = None
    if create_side_view_detector is not None and frame_provider is not None:
        try:
            view_detector = create_side_view_detector()
            logger.info("Using MAA OCR side-view detector")
        except Exception as exc:
            logger.warning(f"Failed to create side-view detector: {exc}")

    recognizer = ActionRecognizer(
        map_data=map_data,
        avatar_matcher=avatar_matcher,
        frame_provider=frame_provider,
        view_detector=view_detector,
    )

    raw_actions = actions_data.get("actions", [])
    print(f"Raw actions: {len(raw_actions)}")
    print("=" * 70)

    for i, action in enumerate(raw_actions):
        start = action.get("start_ratio") or {}
        end = action.get("end_ratio") or {}
        start_t = (start.get("x", 0.0), start.get("y", 0.0))
        end_t = (end.get("x", 0.0), end.get("y", 0.0))
        dist = _distance(start_t, end_t)

        print(f"\nAction #{i}: type={action.get('type')} button={action.get('button')}")
        print(f"  start_ts={action.get('start_ts'):.3f}")
        print(f"  start_ratio=({start_t[0]:.3f}, {start_t[1]:.3f})")
        print(f"  end_ratio=  ({end_t[0]:.3f}, {end_t[1]:.3f})")
        print(f"  drag_distance={dist:.4f} (threshold={inputconfig.DRAG_THRESHOLD_RATIO})")

        in_op = recognizer._in_operator_area(start_t)
        in_map = recognizer._in_map_area(end_t)
        print(f"  start_in_operator_area={in_op}, end_in_map_area={in_map}")

        if action.get("type") == "drag":
            # Try avatar match.
            patch_path = action.get("avatar_patch")
            oper = None
            score = 0.0
            if patch_path and Path(patch_path).is_file():
                patch = cv2.imread(patch_path, cv2.IMREAD_GRAYSCALE)
                if patch is not None:
                    oper, score = avatar_matcher.match_patch(patch)
                    print(f"  avatar_patch={patch_path}")
                    print(f"  avatar_match={oper}, score={score:.3f} (threshold={avatar_matcher.threshold})")
            elif frame_provider is not None:
                frame = frame_provider(action.get("start_ts", 0.0))
                if frame is not None:
                    oper, score = avatar_matcher.match(frame, start_t)
                    print(f"  avatar_match={oper}, score={score:.3f} (threshold={avatar_matcher.threshold})")
            else:
                print("  no avatar patch or frame provider available")

            if in_op and in_map:
                tile, side = recognizer._tile_at(end_t)
                print(f"  target_tile={tile}, side={side}")
                if tile is not None:
                    # Direction diamond is defined on the high-ground plane;
                    # here we project it with the same view used to find tile.
                    quad = _direction_drag_quad(
                        recognizer.map_data, tile, side=side
                    )
                    if quad:
                        contour = _make_contour(quad)
                        in_dir_start = ActionRecognizer._point_in_quad(start_t, contour)
                        in_dir_end = ActionRecognizer._point_in_quad(end_t, contour)
                        print(f"  direction_diamond={quad}")
                        print(f"  in_direction_diamond: start={in_dir_start}, end={in_dir_end}")
            else:
                print("  -> not a deploy drag (needs operator start + map end)")

        elif action.get("type") == "click":
            in_retreat = ActionRecognizer._point_in_quad(start_t, RETREAT_CONTOUR)
            in_skill = ActionRecognizer._point_in_quad(start_t, SKILL_CONTOUR)
            print(f"  in_retreat_quad={in_retreat}, in_skill_quad={in_skill}")

    print("\n" + "=" * 70)
    semantic = recognizer.recognize(raw_actions, frames)
    meaningful = [s for s in semantic if s.action_type.value != "忽略"]
    print(f"Recognized meaningful actions: {len(meaningful)} / {len(raw_actions)}")
    for s in meaningful:
        print(f"  {s.action_type.value}: oper={s.oper} pos={s.tile_pos} dir={s.direction.value}")

    if frame_provider is not None:
        frame_provider.close()


if __name__ == "__main__":
    main()
