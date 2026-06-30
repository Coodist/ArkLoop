"""Tests for recorder/backend.py AxisBuilder."""

from __future__ import annotations

import unittest

from recorder.action_recognizer import ActionType, DirectionType, SemanticAction
from recorder.backend import AxisBuilder


class AxisBuilderTests(unittest.TestCase):
    def setUp(self):
        self.builder = AxisBuilder(map_height=7, max_tick=30)

    def _deploy(self, oper, tile_pos, needs_direction=False, tick=0, cycle=0):
        return SemanticAction(
            action_type=ActionType.DEPLOY,
            oper=oper,
            tile_pos=tile_pos,
            side=True,
            direction=DirectionType.NONE,
            game_time={"tick": tick, "cycle": cycle, "total_elapsed_frames": tick + cycle * 30},
            needs_direction=needs_direction,
        )

    def _direction(self, oper, tile_pos, direction, tick, cycle):
        return SemanticAction(
            action_type=ActionType.DIRECTION,
            oper=oper,
            tile_pos=tile_pos,
            side=True,
            direction=direction,
            game_time={"tick": tick, "cycle": cycle, "total_elapsed_frames": tick + cycle * 30},
        )

    def _retreat(self, oper, tile_pos, tick=5, cycle=1):
        return SemanticAction(
            action_type=ActionType.RETREAT,
            oper=oper,
            tile_pos=tile_pos,
            side=False,
            direction=DirectionType.NONE,
            game_time={"tick": tick, "cycle": cycle, "total_elapsed_frames": tick + cycle * 30},
        )

    def _skill(self, oper, tile_pos, tick=10, cycle=2):
        return SemanticAction(
            action_type=ActionType.SKILL,
            oper=oper,
            tile_pos=tile_pos,
            side=False,
            direction=DirectionType.NONE,
            game_time={"tick": tick, "cycle": cycle, "total_elapsed_frames": tick + cycle * 30},
        )

    def test_retreat_and_skill_emitted_immediately(self):
        self.builder.on_semantic_action(self._retreat("Castle-3", (1, 4), tick=5, cycle=1))
        self.builder.on_semantic_action(self._skill("斑点", (3, 1), tick=10, cycle=2))
        axis = self.builder.get_axis()
        self.assertEqual(len(axis), 2)
        self.assertEqual(axis[0]["action_type"], "撤退")
        self.assertEqual(axis[0]["oper"], "Castle-3")
        self.assertEqual(axis[0]["tick"], 5)
        self.assertEqual(axis[0]["cycle"], 1)
        self.assertEqual(axis[1]["action_type"], "技能")
        self.assertEqual(axis[1]["oper"], "斑点")
        self.assertEqual(axis[1]["tick"], 10)
        self.assertEqual(axis[1]["cycle"], 2)
        self.assertNotIn("cost", axis[0])
        self.assertNotIn("cost", axis[1])

    def test_deploy_without_direction_emitted_immediately(self):
        deploy = self._deploy("Lancet-2", (4, 5), needs_direction=False, tick=3, cycle=0)
        self.builder.on_semantic_action(deploy)
        axis = self.builder.get_axis()
        self.assertEqual(len(axis), 1)
        self.assertEqual(axis[0]["action_type"], "部署")
        self.assertEqual(axis[0]["oper"], "Lancet-2")
        self.assertEqual(axis[0]["pos"], "C6")
        self.assertEqual(axis[0]["tick"], 3)
        self.assertEqual(axis[0]["cycle"], 0)
        self.assertNotIn("cost", axis[0])

    def test_deploy_with_direction_aggregates_direction_tick_and_cycle(self):
        deploy = self._deploy("斑点", (3, 1), needs_direction=True, tick=0, cycle=0)
        direction = self._direction("斑点", (3, 1), DirectionType.RIGHT, tick=7, cycle=0)
        self.builder.on_semantic_action(deploy)
        self.assertEqual(len(self.builder.get_axis()), 0)
        self.assertEqual(self.builder.pending_count(), 1)

        self.builder.on_semantic_action(direction)
        axis = self.builder.get_axis()
        self.assertEqual(len(axis), 1)
        self.assertEqual(axis[0]["action_type"], "部署")
        self.assertEqual(axis[0]["oper"], "斑点")
        self.assertEqual(axis[0]["pos"], "D2")
        self.assertEqual(axis[0]["direction"], "右")
        # Must take the DIRECTION drag's tick / cycle.
        self.assertEqual(axis[0]["tick"], 7)
        self.assertEqual(axis[0]["cycle"], 0)
        self.assertEqual(self.builder.pending_count(), 0)

    def test_pending_deploy_without_direction_is_discarded(self):
        deploy = self._deploy("克洛丝", (5, 4), needs_direction=True, tick=0, cycle=0)
        self.builder.on_semantic_action(deploy)
        self.assertEqual(self.builder.pending_count(), 1)
        # Finalising without a direction drag should drop the pending deploy.
        axis = self.builder.get_axis()
        self.assertEqual(len(axis), 0)

    def test_direction_without_pending_is_ignored(self):
        direction = self._direction("斑点", (3, 1), DirectionType.RIGHT, tick=7, cycle=0)
        self.builder.on_semantic_action(direction)
        self.assertEqual(len(self.builder.get_axis()), 0)

    def test_pos_conversion_matches_sample(self):
        spots = [
            ("斑点", (3, 1), "D2"),
            ("克洛丝", (2, 5), "E6"),
            ("Lancet-2", (4, 5), "C6"),
        ]
        for oper, tile_pos, expected_pos in spots:
            self.builder.clear()
            deploy = self._deploy(oper, tile_pos, needs_direction=False)
            self.builder.on_semantic_action(deploy)
            axis = self.builder.get_axis()
            self.assertEqual(axis[0]["pos"], expected_pos, f"{oper} pos mismatch")


if __name__ == "__main__":
    unittest.main()
