"""Live state-machine test for action recognition.

Captures mouse actions from the MuMu emulator in real time and feeds them to
``ActionWorker`` for asynchronous processing.  This avoids blocking the mouse
polling loop on OCR view detection.

Usage:
    .venv\Scripts\python scripts/test_action_state_machine.py --map-code 1-7

Press Ctrl+C to stop.
"""
import argparse
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cache import get_map_by_code
from src.input.action_recorder import ActionRecorder
from src.config import GameRatioConfig as ratioconfig
from src.config import ImageProcessingConfig as imgconfig
from src.config import DebugConfig
from src.logger import logger
from recorder.action_archive import ActionArchive
from recorder.action_recognizer import (
    AvatarMatcher,
)
from recorder.action_worker import ActionItem, ActionWorker

try:
    from src.maa import create_side_view_detector
except Exception as exc:
    create_side_view_detector = None  # type: ignore[assignment, misc]
    logger.warning(f"MAA side-view detector unavailable: {exc}")

try:
    from src.frame.frame_source import FrameSource
except Exception as exc:
    FrameSource = None  # type: ignore[assignment, misc]
    logger.warning(f"FrameSource unavailable: {exc}")

try:
    from src.frame.detector import AnalysisWorker, CostBarDetector
except Exception as exc:
    AnalysisWorker = None  # type: ignore[assignment, misc]
    CostBarDetector = None  # type: ignore[assignment, misc]
    logger.warning(f"Cost-bar analysis unavailable: {exc}")

# Number of operator card slots across the bottom deploy area.
NUM_OPERATOR_SLOTS = 12


def _setup_logging():
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)


class SlotAvatarMatcher:
    """Fake avatar matcher that identifies operators by bottom-bar slot."""

    def match(self, frame, center_ratio):
        x, y = center_ratio
        left, top, right, bottom = ratioconfig.OPERATOR_AREA_RATIO
        if not (left <= x <= right and top <= y <= bottom):
            return None, 0.0
        slot = min(int(x * NUM_OPERATOR_SLOTS), NUM_OPERATOR_SLOTS - 1)
        return f"op_slot_{slot}", 1.0

    def match_patch(self, patch):
        return None, 0.0


def format_event(event_type, kwargs):
    if event_type == "view_change":
        view = "侧视图" if kwargs.get("view") == "side" else "正视图"
        source = kwargs.get("source") or "无"
        return f"[视图] {view} (来源={source})"
    if event_type == "select_oper":
        return f"[选中] {kwargs.get('oper')} (来源={kwargs.get('source')})"
    if event_type == "cancel_deploy":
        oper = kwargs.get("oper")
        return f"[取消部署] {oper}" if oper else "[取消部署]"
    if event_type == "action":
        semantic = kwargs.get("semantic")
        if isinstance(semantic, dict):
            action_name = semantic.get("action_type", "?")
            oper = semantic.get("oper")
            tile = semantic.get("tile_pos")
            side = semantic.get("side")
        else:
            oper = getattr(semantic, "oper", None)
            tile = getattr(semantic, "tile_pos", None)
            action = getattr(semantic, "action_type", None)
            action_name = action.name if action else "?"
            side = getattr(semantic, "side", None)
        if action_name == "IGNORE":
            return None
        parts = [f"[动作] {action_name}"]
        if oper:
            parts.append(f"干员={oper}")
        if tile:
            parts.append(f"格子={tile}")
        parts.append(f"side={side}")
        return "  ".join(parts)
    return f"[{event_type}] {kwargs}"


def on_event(event_type, **kwargs):
    formatted = format_event(event_type, kwargs)
    if formatted is None:
        return
    print(formatted)


def _format_raw(action):
    s = action.get("start_ratio") or {}
    e = action.get("end_ratio") or {}
    return (
        f"type={action.get('type')} "
        f"button={action.get('button')} "
        f"start=({s.get('x', 0):.3f},{s.get('y', 0):.3f}) "
        f"end=({e.get('x', 0):.3f},{e.get('y', 0):.3f})"
    )


class StateOverlay:
    """Floating debug window showing the current ActionRecognizer state."""

    def __init__(self, action_worker: "ActionWorker", poll_ms: int = 100) -> None:
        self.action_worker = action_worker
        self.poll_ms = poll_ms
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> "StateOverlay":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:
            logger.warning(f"Tkinter unavailable, overlay disabled: {exc}")
            return

        root = tk.Tk()
        root.title("prts-plus state")
        root.attributes("-topmost", True)
        root.geometry("240x200+100+100")
        root.configure(bg="#2b2b2b")
        root.protocol("WM_DELETE_WINDOW", lambda: self._stop_event.set())

        labels: dict[str, tk.StringVar] = {}

        def add_row(name: str, row: int) -> None:
            tk.Label(
                root,
                text=name,
                fg="white",
                bg="#2b2b2b",
                anchor="w",
                font=("Consolas", 10),
            ).grid(row=row, column=0, sticky="w", padx=5)
            var = tk.StringVar(value="-")
            tk.Label(
                root,
                textvariable=var,
                fg="#00ff00",
                bg="#2b2b2b",
                anchor="w",
                font=("Consolas", 10),
            ).grid(row=row, column=1, sticky="ew")
            labels[name] = var

        add_row("view", 0)
        add_row("selected", 1)
        add_row("side_source", 2)
        add_row("deployed", 3)
        add_row("pending", 4)
        add_row("queue", 5)

        def update() -> None:
            if self._stop_event.is_set():
                root.destroy()
                return
            state = self.action_worker.latest_state
            labels["view"].set("side" if state.get("current_view") else "front")
            labels["selected"].set(str(state.get("selected_oper") or "-"))
            labels["side_source"].set(str(state.get("side_source") or "-"))
            deployed = state.get("deployed") or {}
            labels["deployed"].set(
                ", ".join(f"{k}@{v}" for k, v in deployed.items()) or "-"
            )
            labels["pending"].set(str(state.get("pending_oper") or "-"))
            labels["queue"].set(str(state.get("queue_size", 0)))
            root.after(self.poll_ms, update)

        root.after(self.poll_ms, update)
        root.mainloop()


def main():
    parser = argparse.ArgumentParser(
        description="Live test of the action recognition state machine."
    )
    parser.add_argument("--map-code", default="1-7", help="Map code, e.g. 1-7")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print raw actions (only state-machine events)",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=50,
        help="Polling interval in milliseconds (default: 50)",
    )
    parser.add_argument(
        "--origin",
        action="store_true",
        help="Print raw mouse events (mousedown/mouseup/move) from the hook",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Show a floating Tkinter window with the current recognizer state",
    )
    parser.add_argument(
        "--cost-bar",
        action="store_true",
        help="Enable cost-bar tick tracking (experimental, logs suppressed by default)",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        default=DebugConfig.SAVE_ACTION_KEYFRAMES,
        help="Archive consumed actions with their keyframes",
    )
    parser.add_argument(
        "--save-key",
        action="store_true",
        dest="save_key",
        help="Shortcut for --archive: save action keyframes to disk",
    )
    parser.add_argument(
        "--no-archive",
        action="store_false",
        dest="archive",
        help="Disable action archiving",
    )
    parser.add_argument(
        "--archive-all",
        action="store_true",
        default=DebugConfig.SAVE_ACTION_KEYFRAMES_ALL,
        help="Archive every action, including IGNORE actions",
    )
    parser.add_argument(
        "--archive-dir",
        default=DebugConfig.ACTION_ARCHIVE_DIR,
        help="Root directory for action archives (default: %(default)s)",
    )
    parser.add_argument(
        "--fake-avatar",
        action="store_true",
        help="Use a fake slot-based avatar matcher instead of OpenCV template matching",
    )
    parser.add_argument(
        "--avatar-threshold",
        type=float,
        default=imgconfig.TEMPLATE_MATCH_THRESHOLD,
        help="OpenCV avatar matching threshold (default: %(default)s)",
    )
    args = parser.parse_args()

    _setup_logging()

    map_data = get_map_by_code(args.map_code)
    if args.fake_avatar:
        matcher = SlotAvatarMatcher()
        logger.info("Using fake slot avatar matcher")
    else:
        matcher = AvatarMatcher(threshold=args.avatar_threshold)
        logger.info(
            f"Using OpenCV avatar matcher (threshold={args.avatar_threshold}, "
            f"loads templates from resource/avatar)"
        )

    view_detector = None
    if create_side_view_detector is not None:
        try:
            view_detector = create_side_view_detector()
            logger.info("Using MAA OCR side-view detector")
        except Exception as exc:
            logger.warning(f"Failed to create side-view detector: {exc}")

    view_detector = None
    if create_side_view_detector is not None:
        try:
            view_detector = create_side_view_detector()
            logger.info("Using MAA OCR side-view detector")
        except Exception as exc:
            logger.warning(f"Failed to create side-view detector: {exc}")

    # Start continuous frame capture for keyframes and optional cost-bar analysis.
    frame_source = None
    analysis_worker = None
    if FrameSource is not None:
        try:
            frame_source = FrameSource(fps=30).start()
        except Exception as exc:
            logger.warning(f"Failed to start frame source: {exc}")

    if (
        args.cost_bar
        and frame_source is not None
        and AnalysisWorker is not None
        and CostBarDetector is not None
    ):
        try:
            std_w, std_h = imgconfig.SCREEN_STANDARD_SIZE
            detector = CostBarDetector.from_resolution(std_w, std_h)
            if detector.is_ready():
                analysis_worker = AnalysisWorker(
                    frame_queue=frame_source.frame_queue,
                    detector=detector,
                    fps=30,
                ).start()
            else:
                logger.debug("Cost-bar calibration not ready; tick detection disabled")
        except Exception as exc:
            logger.debug(f"Failed to start cost-bar analysis: {exc}")

    if analysis_worker is not None:
        logger.info("Tick tracking enabled; actions will include tick_state")
    else:
        logger.info("Tick tracking disabled; run with --cost-bar after calibrating to enable it")

    archive = None
    if args.archive or args.save_key:
        archive = ActionArchive(
            base_dir=Path(args.archive_dir),
            archive_all=args.archive_all,
        )

    action_worker = ActionWorker(
        map_data=map_data,
        avatar_matcher=matcher,
        view_detector=view_detector,
        event_callback=on_event,
        use_slot_layout=True,
        archive=archive,
    ).start()

    overlay = None
    if args.overlay:
        overlay = StateOverlay(action_worker).start()

    recorder = ActionRecorder(record_moves=True)
    try:
        recorder.start()
    except Exception as exc:
        print(f"无法启动鼠标监听: {exc}")
        return

    print("开始监听。请把 MuMu 模拟器置于前台操作。")
    print("操作示例：")
    print("  1. 从待部署区拖到地图 -> 部署")
    print("  2. 在菱形内再拖一下 -> 方向")
    print("  3. 点已部署干员 -> 技能/选中")
    print("  4. 点撤退/技能按钮 -> 撤退/技能")
    if archive is not None:
        print(f"  动作存档目录: {archive._session_dir}")
    print("按 Ctrl+C 停止。\n")

    running = True

    def _stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)

    last_action_count = 0
    last_raw_count = 0
    raw_move_counter = 0
    try:
        while running:
            # Use a single snapshot of raw events for both origin printing and
            # action building, so the two views never race each other.
            raw_events = recorder.mouse.events
            new_raw = raw_events[last_raw_count:]
            if args.origin:
                for ev in new_raw:
                    if ev.type == "mousemove":
                        raw_move_counter += 1
                        if raw_move_counter % 20 == 0:
                            print(
                                f"[origin-move] x={ev.x} y={ev.y} "
                                f"button={ev.button} pressed={ev.pressed}"
                            )
                    else:
                        print(
                            f"[origin-{ev.type}] button={ev.button} "
                            f"pressed={ev.pressed} x={ev.x} y={ev.y} "
                            f"ts={ev.ts:.3f}"
                        )
            last_raw_count = len(raw_events)

            actions = recorder._build_actions(raw_events)
            for action in actions[last_action_count:]:
                if not args.quiet:
                    print(f"[原始] {_format_raw(action)}")

                frame, frame_ts = (
                    frame_source.latest()
                    if frame_source is not None
                    else (None, 0.0)
                )
                tick_state = (
                    analysis_worker.snapshot()
                    if analysis_worker is not None
                    else None
                )
                action_worker.enqueue(
                    ActionItem(
                        action=action,
                        frame=frame,
                        frame_ts=frame_ts,
                        tick_state=tick_state,
                    )
                )
            last_action_count = len(actions)
            time.sleep(args.poll_ms / 1000.0)
    finally:
        running = False
        try:
            action_worker.stop()
        except Exception:
            logger.exception("Failed to stop action worker")
        if overlay is not None:
            try:
                overlay.stop()
            except Exception:
                logger.exception("Failed to stop overlay")
        if frame_source is not None:
            try:
                frame_source.stop()
            except Exception:
                logger.exception("Failed to stop frame source")
        if analysis_worker is not None:
            try:
                analysis_worker.stop()
            except Exception:
                logger.exception("Failed to stop analysis worker")
        recorder.stop()
        print("\n已停止监听。")


if __name__ == "__main__":
    main()
