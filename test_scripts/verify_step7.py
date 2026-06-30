"""Step 7 verification script.

Run this after implementing Step 7 to verify the offline cost bar scanning
pipeline works end-to-end.

Usage:
    .venv\\Scripts\\python scripts/verify_step7.py

It will:
1. Run unit tests for the tick state tracker and offline scanner.
2. Check that the latest recording in recordings/ has a timestamps file.
3. Run scripts/analyze_recording.py on that pair.
4. Validate the output JSON structure.
5. Optionally annotate actions if a matching actions_*.json exists.
"""

import json
import os
import subprocess
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from recorder.offline_scanner import find_latest_recording_pair


def run(cmd: list) -> subprocess.CompletedProcess:
    """Run a command and print it."""
    print(f"\n>>> {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=project_root, check=False, text=True)


def step_1_unit_tests() -> bool:
    print("\n=== Step 1: Unit tests ===")
    result = run(
        [
            os.path.join(project_root, ".venv", "Scripts", "python.exe"),
            "-m",
            "unittest",
            "tests.test_offline_scanner",
            "tests.test_detector_worker",
            "-v",
        ]
    )
    ok = result.returncode == 0
    print("PASS" if ok else "FAIL")
    return ok


def step_2_check_recording_pair() -> tuple:
    print("\n=== Step 2: Check recording pair ===")
    pair = find_latest_recording_pair()
    if pair is None:
        print(
            "FAIL: No recording pair found.\n"
            "Run: .venv\\Scripts\\python scripts/record_actions.py --duration 10"
        )
        return False, None, None
    video_path, timestamps_path = pair
    print(f"Found:\n  video: {video_path}\n  timestamps: {timestamps_path}")
    print("PASS")
    return True, video_path, timestamps_path


def step_3_run_offline_scanner(video_path: str, timestamps_path: str) -> tuple:
    print("\n=== Step 3: Run offline scanner ===")
    base, _ = os.path.splitext(video_path)
    output_path = f"{base}_verify_analysis.json"

    # Build command relative to project root.
    cmd = [
        os.path.join(project_root, ".venv", "Scripts", "python.exe"),
        "scripts/analyze_recording.py",
        "--video",
        video_path,
        "--timestamps",
        timestamps_path,
        "--output",
        output_path,
    ]

    # Auto-annotate actions if matching actions file exists.
    actions_path = timestamps_path.replace("recording_", "actions_").replace(
        "_timestamps.json", ".json"
    )
    if os.path.isfile(actions_path):
        cmd.extend(["--actions", actions_path])
        print(f"Found actions file: {actions_path}")

    result = run(cmd)
    ok = result.returncode == 0 and os.path.isfile(output_path)
    print("PASS" if ok else "FAIL")
    return ok, output_path


def step_4_validate_output(output_path: str) -> bool:
    print("\n=== Step 4: Validate output JSON ===")
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    required_meta = {
        "video_path",
        "timestamps_path",
        "fps",
        "frame_count",
        "ticks_per_cycle",
        "scanned_frames",
    }
    missing_meta = required_meta - set(data.get("metadata", {}).keys())
    if missing_meta:
        print(f"FAIL: missing metadata keys: {missing_meta}")
        return False

    frames = data.get("frames", [])
    if not frames:
        print("FAIL: no frames in output")
        return False

    required_frame = {"frame_id", "timestamp", "tick", "cycle", "total_elapsed_frames", "paused"}
    missing_frame = required_frame - set(frames[0].keys())
    if missing_frame:
        print(f"FAIL: missing frame keys: {missing_frame}")
        return False

    print(f"metadata: {json.dumps(data['metadata'], ensure_ascii=False, indent=2)}")
    print(f"frames: {len(frames)}")
    print(f"first frame: {frames[0]}")
    print(f"last frame:  {frames[-1]}")

    if "actions" in data:
        actions = data["actions"].get("actions", [])
        print(f"annotated actions: {len(actions)}")
        if actions:
            print(f"first annotated action: {json.dumps(actions[0], ensure_ascii=False, indent=2)}")

    print("PASS")
    return True


def main():
    ok = True
    ok = step_1_unit_tests() and ok
    found, video_path, timestamps_path = step_2_check_recording_pair()
    ok = found and ok
    if found:
        scan_ok, output_path = step_3_run_offline_scanner(video_path, timestamps_path)
        ok = scan_ok and ok
        if scan_ok:
            ok = step_4_validate_output(output_path) and ok

    print("\n" + "=" * 50)
    if ok:
        print("Step 7 verification: ALL PASSED")
    else:
        print("Step 7 verification: SOME CHECKS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
