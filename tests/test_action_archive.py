"""Tests for recorder/action_archive.py."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from recorder.action_archive import ActionArchive
from recorder.action_recognizer import SemanticAction, ActionType


class ActionArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_creates_separate_folders(self):
        archive = ActionArchive(
            base_dir=self.tmpdir,
            session_id="test_session",
            archive_all=False,
        )

        action1 = {"type": "click", "start_ts": 1.0}
        action2 = {"type": "drag", "start_ts": 2.0}
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        folder1 = archive.save(
            action=action1,
            frame=frame,
            frame_ts=1.0,
            tick_state={"tick": 5},
            semantic=SemanticAction(action_type=ActionType.SELECT, oper="芬"),
            final_state={
                "current_view": True,
                "selected_oper": "芬",
                "side_source": "deployed",
                "deployed": {"芬": (3, 4)},
            },
        )
        folder2 = archive.save(
            action=action2,
            frame=frame,
            frame_ts=2.0,
            tick_state={"tick": 6},
            semantic=SemanticAction(action_type=ActionType.DEPLOY, oper="斑点"),
            final_state={
                "current_view": True,
                "selected_oper": None,
                "side_source": None,
                "deployed": {"斑点": (3, 3)},
            },
        )

        self.assertNotEqual(folder1, folder2)
        self.assertTrue((folder1 / "action.json").exists())
        self.assertTrue((folder1 / "frame.png").exists())
        self.assertTrue((folder1 / "semantic.json").exists())
        self.assertTrue((folder2 / "action.json").exists())
        self.assertTrue((folder2 / "frame.png").exists())
        self.assertTrue((folder2 / "semantic.json").exists())

    def test_skip_ignore_when_not_archive_all(self):
        archive = ActionArchive(
            base_dir=self.tmpdir,
            session_id="test_session",
            archive_all=False,
        )

        folder = archive.save(
            action={"type": "click"},
            frame=None,
            frame_ts=0.0,
            tick_state=None,
            semantic=SemanticAction(action_type=ActionType.IGNORE),
            final_state={"current_view": False, "selected_oper": None, "side_source": None, "deployed": {}},
        )
        self.assertIsNone(folder)


if __name__ == "__main__":
    unittest.main()
