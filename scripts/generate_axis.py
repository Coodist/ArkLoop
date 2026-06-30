#!/usr/bin/env python3
"""Generate an executable JSON axis from a recording analysis and actions file."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from recorder.axis_writer import AxisWriter


def _find_latest_pair(recordings_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Return the latest (analysis_path, actions_path) pair in ``recordings_dir``."""
    if not recordings_dir.is_dir():
        return None, None

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


def main():
    parser = argparse.ArgumentParser(
        description="Convert recording analysis + actions into an executable JSON axis."
    )
    parser.add_argument(
        "--analysis",
        type=Path,
        help="Path to recording_<ts>_analysis.json (default: newest in recordings/)",
    )
    parser.add_argument(
        "--actions",
        type=Path,
        help="Path to actions_<ts>.json (default: matching --analysis or newest)",
    )
    parser.add_argument(
        "--map-code",
        required=True,
        help="Map code, e.g. 1-7",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON path (default: axis_<ts>.json in project root)",
    )
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=project_root / "recordings",
        help="Directory to search for latest analysis/actions (default: recordings/)",
    )
    args = parser.parse_args()

    analysis_path = args.analysis
    actions_path = args.actions

    if analysis_path is None:
        analysis_path, actions_path = _find_latest_pair(args.recordings_dir)
        if analysis_path is None:
            print("错误：找不到任何 recording_*_analysis.json")
            sys.exit(1)
        print(f"自动选择最新分析：{analysis_path.name}")

    if actions_path is None:
        # Try to derive actions path from analysis filename.
        m = re.search(r"recording_(\d{8}_\d{6})", analysis_path.name)
        if m:
            candidate = analysis_path.parent / f"actions_{m.group(1)}.json"
            if candidate.is_file():
                actions_path = candidate
        if actions_path is None:
            print("错误：找不到对应的 actions_*.json")
            sys.exit(1)

    print(f"分析文件：{analysis_path}")
    print(f"动作文件：{actions_path}")

    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)
    with open(actions_path, "r", encoding="utf-8") as f:
        actions_data = json.load(f)

    output_path = args.output
    if output_path is None:
        m = re.search(r"recording_(\d{8}_\d{6})", analysis_path.name)
        ts = m.group(1) if m else "latest"
        output_path = project_root / f"axis_{ts}.json"

    with AxisWriter(analysis_data, actions_data, args.map_code) as writer:
        writer.write(str(output_path))

    print(f"已生成轴文件：{output_path}")


if __name__ == "__main__":
    main()
