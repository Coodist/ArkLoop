"""Tests for recorder/action_recognizer.py."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from src.config import DebugConfig
from recorder.action_recognizer import (
    ActionRecognizer,
    ActionType,
    AvatarMatcher,
    DirectionType,
    _make_contour,
)


class ActionRecognizerTests(unittest.TestCase):
    def setUp(self):
        # Do not write warning archive artifacts during tests.
        self._orig_save_warnings = DebugConfig.SAVE_RECOGNITION_WARNINGS
        DebugConfig.SAVE_RECOGNITION_WARNINGS = False
        self.map_data = {
            "levelId": "main_01-07",
            "code": "1-7",
            "name": "",
            "height": 7,
            "width": 11,
            "tiles": [[{"buildableType": 1, "heightType": 0} for _ in range(11)] for _ in range(7)],
            "view": [[0.0, -4.81, -7.76], [0.0, -4.81, -7.76]],
        }
        self.dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    def tearDown(self):
        DebugConfig.SAVE_RECOGNITION_WARNINGS = self._orig_save_warnings

    def _make_drag(self, sx, sy, ex, ey):
        return {
            "type": "drag",
            "start_ts": 1.0,
            "start_ratio": {"x": sx, "y": sy},
            "start_game": {"x": sx * 1280, "y": sy * 720},
            "end_ts": 2.0,
            "end_ratio": {"x": ex, "y": ey},
            "end_game": {"x": ex * 1280, "y": ey * 720},
        }

    def _make_click(self, x, y):
        return {
            "type": "click",
            "start_ts": 3.0,
            "start_ratio": {"x": x, "y": y},
            "start_game": {"x": x * 1280, "y": y * 720},
            "end_ratio": {"x": x, "y": y},
            "end_game": {"x": x * 1280, "y": y * 720},
        }

    def test_cancel_pending_deploy_restores_overwritten_operator(self):
        """Cancelling a deploy that overwrote a tile must restore the old occupant."""
        matcher = MagicMock()
        matcher.match.return_value = ("新干员", 0.95)
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=matcher,
            frame_provider=lambda ts: self.dummy_frame,
        )
        recognizer.deployed["旧干员"] = (3, 3)

        with patch(
            "recorder.action_recognizer.transform_view_to_map",
            return_value=(3, 3),
        ), patch(
            "recorder.action_recognizer.get_unit_metadata",
            return_value={"needs_direction": True},
        ):
            actions = [self._make_drag(0.8, 0.9, 0.5, 0.5)]
            result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action_type, ActionType.DEPLOY)
        self.assertEqual(recognizer.deployed.get("新干员"), (3, 3))
        self.assertNotIn("旧干员", recognizer.deployed)
        self.assertIsNotNone(recognizer.pending_deploy)

        recognizer._cancel_pending_deploy()

        self.assertIsNone(recognizer.pending_deploy)
        self.assertEqual(recognizer.deployed.get("旧干员"), (3, 3))
        self.assertNotIn("新干员", recognizer.deployed)

    def test_deploy_drag_recognized(self):
        matcher = MagicMock()
        matcher.match.return_value = ("斑点", 0.95)
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=matcher,
            frame_provider=lambda ts: self.dummy_frame,
        )
        recognizer.selected_oper = "芬"  # should be cleared by deploy drag

        with patch(
            "recorder.action_recognizer.transform_view_to_map",
            return_value=(3, 3),
        ):
            actions = [
                self._make_drag(0.8, 0.9, 0.5, 0.5),  # deploy
            ]
            result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action_type, ActionType.DEPLOY)
        self.assertEqual(result[0].oper, "斑点")
        self.assertEqual(result[0].tile_pos, (3, 3))
        self.assertIsNone(recognizer.selected_oper)

    def test_direction_drag_updates_deploy(self):
        matcher = MagicMock()
        matcher.match.return_value = ("芬", 0.95)
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=matcher,
            frame_provider=lambda ts: self.dummy_frame,
        )

        def _fake_transform(level, ratio, side):
            # tile center at ratio (0.5, 0.5) for deployed tile.
            if ratio == (0.5, 0.5):
                return (3, 3)
            return None

        with patch(
            "recorder.action_recognizer.transform_view_to_map",
            side_effect=_fake_transform,
        ):
            actions = [
                self._make_drag(0.8, 0.9, 0.5, 0.5),  # deploy at (0.5,0.5)
                # Direction selection drag; (0.35, 0.5) and (0.35, 0.4) both
                # lie inside the high-ground diamond around tile (3,3).
                self._make_drag(0.35, 0.5, 0.35, 0.4),  # direction up
            ]
            result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].action_type, ActionType.DEPLOY)
        self.assertEqual(result[0].direction, DirectionType.NONE)
        self.assertTrue(result[0].needs_direction)
        self.assertEqual(result[1].action_type, ActionType.DIRECTION)
        self.assertEqual(result[1].direction, DirectionType.UP)
        self.assertEqual(result[1].oper, "芬")
        self.assertIsNone(recognizer.selected_oper)

    def test_click_retreat_button(self):
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
        )
        recognizer.deployed["斑点"] = (3, 3)
        recognizer.selected_oper = "斑点"
        # Mock the dynamic action regions: retreat square around the click.
        click = (0.4569, 0.3352)
        recognizer._get_action_regions = lambda: (
            None,
            _make_contour([
                (click[0] - 0.02, click[1] - 0.02),
                (click[0] + 0.02, click[1] - 0.02),
                (click[0] + 0.02, click[1] + 0.02),
                (click[0] - 0.02, click[1] + 0.02),
            ]),
            None,
        )

        actions = [self._make_click(*click)]
        result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action_type, ActionType.RETREAT)
        self.assertEqual(result[0].oper, "斑点")
        self.assertIsNone(recognizer.selected_oper)
        self.assertFalse(recognizer.current_view)

    def test_click_skill_button(self):
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
        )
        recognizer.deployed["斑点"] = (3, 3)
        recognizer.selected_oper = "斑点"
        # Mock the dynamic action regions: skill square around the click.
        click = (0.6412, 0.5857)
        recognizer._get_action_regions = lambda: (
            None,
            None,
            _make_contour([
                (click[0] - 0.02, click[1] - 0.02),
                (click[0] + 0.02, click[1] - 0.02),
                (click[0] + 0.02, click[1] + 0.02),
                (click[0] - 0.02, click[1] + 0.02),
            ]),
        )

        actions = [self._make_click(*click)]
        result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action_type, ActionType.SKILL)
        self.assertEqual(result[0].oper, "斑点")
        self.assertIsNone(recognizer.selected_oper)
        self.assertFalse(recognizer.current_view)

    def test_click_on_deployed_tile_selects_operator(self):
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
        )
        recognizer.deployed["克洛丝"] = (2, 5)

        def _fake_transform(level, ratio, side):
            if ratio == (0.6, 0.4):
                return (2, 5)
            return None

        with patch(
            "recorder.action_recognizer.transform_view_to_map",
            side_effect=_fake_transform,
        ):
            actions = [self._make_click(0.6, 0.4)]
            result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action_type, ActionType.SELECT)
        self.assertEqual(result[0].oper, "克洛丝")

    def test_click_dead_zone_ignored(self):
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
        )
        recognizer.deployed["斑点"] = (3, 3)
        recognizer.selected_oper = "斑点"
        # Dead zone around the click; retreat/skill are outside.
        click = (0.5, 0.5)
        recognizer._get_action_regions = lambda: (
            _make_contour([
                (click[0] - 0.05, click[1]),
                (click[0], click[1] - 0.05),
                (click[0] + 0.05, click[1]),
                (click[0], click[1] + 0.05),
            ]),
            None,
            None,
        )

        actions = [self._make_click(*click)]
        result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 0)
        self.assertEqual(recognizer.selected_oper, "斑点")

    def test_click_outside_dead_zone_deselects(self):
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
        )
        recognizer.deployed["斑点"] = (3, 3)
        recognizer.selected_oper = "斑点"
        # Dead zone far from the click.
        recognizer._get_action_regions = lambda: (
            _make_contour([(0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.1, 0.2)]),
            None,
            None,
        )

        with patch.object(recognizer, "_tile_at", return_value=(None, True)):
            actions = [self._make_click(0.8, 0.3)]
            result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 0)
        self.assertIsNone(recognizer.selected_oper)

    def test_click_outside_dead_zone_switches_selection(self):
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
        )
        recognizer.deployed["斑点"] = (3, 3)
        recognizer.deployed["芬"] = (3, 4)
        recognizer.selected_oper = "斑点"
        recognizer._get_action_regions = lambda: (
            _make_contour([(0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.1, 0.2)]),
            None,
            None,
        )

        with patch.object(recognizer, "_tile_at", return_value=((3, 4), True)):
            actions = [self._make_click(0.8, 0.3)]
            result = recognizer.recognize(actions, [])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action_type, ActionType.SELECT)
        self.assertEqual(result[0].oper, "芬")
        self.assertEqual(recognizer.selected_oper, "芬")

    def test_unshift_click_for_selected_camera(self):
        from recorder.action_recognizer import _unshift_click_for_selected_camera
        adjusted = _unshift_click_for_selected_camera(
            self.map_data, (0.5, 0.5), (3, 3), True
        )
        self.assertIsInstance(adjusted, tuple)
        self.assertEqual(len(adjusted), 2)

    def test_drag_does_not_update_view(self):
        """Drag actions must not trigger the OCR view detector."""
        view_calls = []

        def _fake_detector(frame):
            view_calls.append(frame)
            return True

        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=lambda ts: self.dummy_frame,
            view_detector=_fake_detector,
        )

        actions = [self._make_drag(0.8, 0.9, 0.5, 0.5)]
        result = recognizer.recognize(actions, [])

        self.assertEqual(view_calls, [])

    def test_click_updates_view_in_batch_mode(self):
        """Batch recognize() should still refresh the view for click actions."""
        view_calls = []

        def _fake_detector(frame):
            view_calls.append(frame)
            return True

        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=lambda ts: self.dummy_frame,
            view_detector=_fake_detector,
        )

        actions = [self._make_click(0.5, 0.5)]
        result = recognizer.recognize(actions, [])

        self.assertEqual(len(view_calls), 1)
        self.assertTrue(recognizer.current_view)

    def test_update_view_sets_current_view(self):
        """update_view(frame) must refresh current_view without a frame provider."""
        view_calls = []

        def _fake_detector(frame):
            view_calls.append(frame)
            return True

        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
            view_detector=_fake_detector,
        )
        recognizer.update_view(self.dummy_frame)
        self.assertTrue(recognizer.current_view)
        self.assertEqual(len(view_calls), 1)

    def test_cancel_pending_deploy_reverts_to_front_view(self):
        """Cancelling a pending deploy must always revert to front view."""
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
            view_detector=lambda f: True,
        )
        recognizer.deployed["测试"] = (3, 3)
        recognizer.current_view = True
        recognizer.selected_oper = "测试"

        # Simulate a pending deploy by directly injecting a semantic action.
        from recorder.action_recognizer import SemanticAction, ActionType
        pending = SemanticAction(
            action_type=ActionType.DEPLOY,
            oper="测试",
            tile_pos=(3, 3),
            side=True,
        )
        recognizer.semantic_actions.append(pending)
        recognizer.pending_deploy = pending

        recognizer._cancel_pending_deploy()

        self.assertIsNone(recognizer.pending_deploy)
        self.assertIsNone(recognizer.selected_oper)
        self.assertFalse(recognizer.current_view)

    def test_operator_area_click_does_not_select_oper(self):
        """Clicking an operator card must not set or clear selected_oper."""
        recognizer = ActionRecognizer(
            map_data=self.map_data,
            avatar_matcher=None,
            frame_provider=None,
            view_detector=lambda f: True,
        )
        recognizer.deployed["斑点"] = (3, 3)
        recognizer.selected_oper = "斑点"

        # Simulate a click in the operator area.
        click = self._make_click(0.85, 0.9)
        result = recognizer.recognize([click], [])

        self.assertEqual(len(result), 0)
        # selected_oper must be untouched: it was a deployed operator before and
        # should remain so, because operator-area clicks do not affect map selection.
        self.assertEqual(recognizer.selected_oper, "斑点")


    def test_recognition_warning_archives_frame(self):
        """A warning from operator-area recognition must archive action+image."""
        import shutil

        tmpdir = tempfile.mkdtemp()
        orig_dir = DebugConfig.RECOGNITION_WARNING_DIR
        orig_save = DebugConfig.SAVE_RECOGNITION_WARNINGS
        try:
            DebugConfig.RECOGNITION_WARNING_DIR = tmpdir
            DebugConfig.SAVE_RECOGNITION_WARNINGS = True

            recognizer = ActionRecognizer(
                map_data=self.map_data,
                avatar_matcher=MagicMock(),
                frame_provider=lambda ts: self.dummy_frame,
                view_detector=lambda f: True,
            )
            # Force a layout so slot_index_at can run, but ratio falls outside slots.
            recognizer._detect_slot_layout = lambda frame: {
                "count": 2,
                "boxes": [(0.0, 0.8, 0.2, 1.0), (0.2, 0.8, 0.4, 1.0)],
            }
            recognizer._detect_slot_flags = lambda frame: []

            result = recognizer._match_avatar_with_fallback(
                self.dummy_frame, (0.5, 0.9)
            )
            self.assertIsNone(result)

            subdirs = list(Path(tmpdir).iterdir())
            self.assertEqual(len(subdirs), 1, "warning archive folder should be created")
            folder = subdirs[0]
            self.assertTrue((folder / "action.json").exists())
            self.assertTrue((folder / "frame.png").exists())

            with open(folder / "action.json", "r", encoding="utf-8") as f:
                info = json.load(f)
            self.assertEqual(info["ratio"], [0.5, 0.9])
            self.assertIn("不在任何 operator slot", info["warning"])
        finally:
            DebugConfig.RECOGNITION_WARNING_DIR = orig_dir
            DebugConfig.SAVE_RECOGNITION_WARNINGS = orig_save
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
