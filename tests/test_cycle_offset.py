"""Tests for the cycle_offset / breakpoint / resume machinery."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from recorder.action_recognizer import ActionType, DirectionType, SemanticAction
from recorder.backend import AxisBuilder
from src.axis.axis_runner import AxisRunner, BreakpointHit
from src.logic.action import Action, ActionType as RunnerActionType, DirectionType as RunnerDirectionType
from src.logic.game_time import GameTime


# ----------------------------------------------------------------------
# AxisBuilder cycle_offset
# ----------------------------------------------------------------------
class AxisBuilderOffsetTests(unittest.TestCase):
    def _skill(self, cycle: int, tick: int) -> SemanticAction:
        return SemanticAction(
            action_type=ActionType.SKILL,
            oper="斑点",
            tile_pos=(3, 1),
            side=False,
            direction=DirectionType.NONE,
            game_time={"tick": tick, "cycle": cycle, "total_elapsed_frames": tick + cycle * 30},
        )

    def test_no_offset_writes_raw_cycle(self):
        b = AxisBuilder(map_height=7, max_tick=30, cycle_offset=0)
        b.on_semantic_action(self._skill(cycle=2, tick=10))
        axis = b.get_axis()
        self.assertEqual(axis[0]["cycle"], 2)
        self.assertEqual(axis[0]["tick"], 10)

    def test_offset_shifts_cycle_on_emit(self):
        b = AxisBuilder(map_height=7, max_tick=30, cycle_offset=5)
        # Recorder's time source restarts at 0 on resume; offset is added on emit.
        b.on_semantic_action(self._skill(cycle=0, tick=7))
        b.on_semantic_action(self._skill(cycle=3, tick=0))
        axis = b.get_axis()
        self.assertEqual(axis[0]["cycle"], 5)
        self.assertEqual(axis[0]["tick"], 7)
        self.assertEqual(axis[1]["cycle"], 8)
        self.assertEqual(axis[1]["tick"], 0)


# ----------------------------------------------------------------------
# AxisRunner cycle_offset + breakpoints (via stubs)
# ----------------------------------------------------------------------
def _make_action(cycle: int, tick: int, oper: str = "X") -> Action:
    return Action(
        cycle=cycle,
        tick=tick,
        action_type=RunnerActionType.SKILL,
        oper=oper,
        # SKILL doesn't need pos/direction in is_valid()
    )


class _StubRunner(AxisRunner):
    """Replaces I/O-heavy parts so the action-iteration logic can be unit tested.

    - _apply_settings / _load_map / view-transform replaced
    - perform_action replaced with a recorder
    - calibration / time source setup bypassed
    - is_valid relaxed (we trust the test inputs)
    """

    def __init__(self, *args, performed_log: list, gt_sequence: list, **kwargs):
        super().__init__(*args, **kwargs)
        self.performed_log = performed_log
        # Successive return values for get_game_time() during the breakpoint
        # poll loop.  Each is (cycle, tick).
        self._gt_iter = iter(gt_sequence)

    def run(self):  # type: ignore[override]
        # Skip all the calibration / map / view setup; replicate just the
        # iteration core that we're testing.
        self._apply_settings_stub()
        tick_max = GameTime.get_tick_max()
        # Simulate initial game time of 0 (no offset).
        self._breakpoint_totals = [
            (bp_cycle - self.cycle_offset) * tick_max + bp_tick
            for bp_cycle, bp_tick in self.breakpoints
        ]
        bp_idx = 0
        while bp_idx < len(self._breakpoint_totals):
            if self._breakpoint_totals[bp_idx] <= 0:
                bp_idx += 1
            else:
                break
        self._breakpoint_idx = bp_idx

        for action in self.actions:
            if self.is_paused():
                break
            if action.cycle is not None and action.cycle < self.cycle_offset:
                continue

            target_total = (action.cycle - self.cycle_offset) * GameTime.get_tick_max() + action.tick
            bp_idx = self._await_breakpoints_until(bp_idx, target_total)
            if self.is_paused():
                break

            action.cycle = action.cycle - self.cycle_offset
            self.performed_log.append((action.cycle, action.tick, action.oper))

    def _apply_settings_stub(self):
        GameTime.set_tick_max(30)


def _patched_get_game_time(seq_iter):
    """Return a function that pulls (cycle, tick) from the iterator."""
    def _gt():
        cycle, tick = next(seq_iter)
        return GameTime(cycle, tick)
    return _gt


class AxisRunnerOffsetTests(unittest.TestCase):
    def setUp(self):
        GameTime.set_tick_max(30)

    def test_actions_before_offset_are_skipped(self):
        actions = [
            _make_action(0, 5, "a"),
            _make_action(2, 10, "b"),
            _make_action(5, 0, "c"),
            _make_action(5, 15, "d"),
        ]
        log: list = []
        r = _StubRunner(
            actions=actions,
            settings={},
            is_paused=lambda: False,
            cycle_offset=3,
            performed_log=log,
            gt_sequence=[],
        )
        r.run()
        # actions 0,1 (cycle<3) are skipped; 5,5 are biased to 2,2
        self.assertEqual([(a[0], a[2]) for a in log], [(2, "c"), (2, "d")])

    def test_offset_zero_passes_actions_unchanged(self):
        actions = [_make_action(0, 0, "a"), _make_action(1, 15, "b")]
        log: list = []
        r = _StubRunner(
            actions=actions,
            settings={},
            is_paused=lambda: False,
            cycle_offset=0,
            performed_log=log,
            gt_sequence=[],
        )
        r.run()
        self.assertEqual([(a[0], a[2]) for a in log], [(0, "a"), (1, "b")])


class AxisRunnerBreakpointTests(unittest.TestCase):
    def setUp(self):
        GameTime.set_tick_max(30)

    def test_breakpoint_before_action_pauses_and_fires_on_pause(self):
        actions = [_make_action(5, 0, "skip_me")]
        log: list = []
        on_pause_calls: list = []

        r = _StubRunner(
            actions=actions,
            settings={},
            is_paused=lambda: False,
            cycle_offset=0,
            breakpoints=[(2, 0)],
            on_pause=lambda c, t: on_pause_calls.append((c, t)),
            performed_log=log,
            gt_sequence=[(1, 25), (2, 0)],  # second poll reaches breakpoint
        )

        # _await_breakpoints_until polls get_game_time() until the breakpoint.
        with patch(
            "src.axis.axis_runner.get_game_time", side_effect=_patched_get_game_time(iter([(1, 25), (2, 0)]))
        ):
            r.run()

        self.assertEqual(log, [])  # breakpoint fired before action 0 → nothing executed
        self.assertEqual(on_pause_calls, [(2, 0)])

    def test_breakpoint_after_all_actions_is_not_triggered_early(self):
        # Action at cycle 1 should execute before breakpoint at cycle 3 is checked.
        actions = [_make_action(1, 0, "x")]
        log: list = []
        on_pause_calls: list = []

        r = _StubRunner(
            actions=actions,
            settings={},
            is_paused=lambda: False,
            cycle_offset=0,
            breakpoints=[(3, 0)],
            on_pause=lambda c, t: on_pause_calls.append((c, t)),
            performed_log=log,
            gt_sequence=[],  # no polling happens (bp is past the only action)
        )
        with patch(
            "src.axis.axis_runner.get_game_time", side_effect=AssertionError("get_game_time should not be called")
        ):
            r.run()

        self.assertEqual(log, [(1, 0, "x")])
        self.assertEqual(on_pause_calls, [])

    def test_breakpoints_before_offset_are_ignored(self):
        # Breakpoint at cycle 2 should be skipped because cycle_offset=5.
        actions = [_make_action(7, 0, "x")]
        log: list = []
        on_pause_calls: list = []

        r = _StubRunner(
            actions=actions,
            settings={},
            is_paused=lambda: False,
            cycle_offset=5,
            breakpoints=[(2, 0)],
            on_pause=lambda c, t: on_pause_calls.append((c, t)),
            performed_log=log,
            gt_sequence=[],
        )
        with patch(
            "src.axis.axis_runner.get_game_time", side_effect=AssertionError("get_game_time should not be called")
        ):
            r.run()

        # action 7 → biased to cycle 2, breakpoint at cycle 2 (un-biased) is
        # before offset → skipped
        self.assertEqual(log, [(2, 0, "x")])
        self.assertEqual(on_pause_calls, [])

    def test_stop_event_during_breakpoint_poll_aborts(self):
        actions = [_make_action(5, 0, "x")]
        log: list = []

        stop_event = threading.Event()
        # gt_sequence: first poll triggers stop on the *next* check
        gt_seq = [(0, 0), (0, 5)]

        def _check():
            # set stop on the second call so the first poll runs, second aborts
            res = stop_event.is_set()
            stop_event.set()
            return res

        r = _StubRunner(
            actions=actions,
            settings={},
            is_paused=_check,
            cycle_offset=0,
            breakpoints=[(3, 0)],
            stop_event=stop_event,
            performed_log=log,
            gt_sequence=gt_seq,
        )

        with patch(
            "src.axis.axis_runner.get_game_time", side_effect=_patched_get_game_time(iter(gt_seq))
        ):
            r.run()

        self.assertEqual(log, [])  # aborted before action could execute


class RunnerStateSeedTests(unittest.TestCase):
    """initial_state seeding + skipped-action state registration.

    These guard the resume-after-pause flow: operators deployed in an earlier
    (paused) segment must remain in ``deployed`` so a later RETREAT — during
    playback or in a recording resumed from this state — can be matched.
    """

    def setUp(self):
        GameTime.set_tick_max(30)

    def _runner(self, **kwargs) -> AxisRunner:
        return AxisRunner(actions=[], settings={}, is_paused=lambda: False, **kwargs)

    def test_initial_state_seeds_deployed(self):
        r = self._runner(initial_state={"deployed": {"极境": (4, 1), "桃金娘": [2, 7]}})
        deployed = r.get_state()["deployed"]
        self.assertEqual(deployed["极境"], (4, 1))
        self.assertEqual(deployed["桃金娘"], (2, 7))  # list coerced to tuple

    def test_no_initial_state_is_empty(self):
        self.assertEqual(self._runner().get_state()["deployed"], {})

    def test_initial_state_ignores_malformed_entries(self):
        r = self._runner(initial_state={"deployed": {"a": (1,), "b": "xx", "c": (3, 4)}})
        self.assertEqual(r.get_state()["deployed"], {"c": (3, 4)})

    def test_skipped_deploy_registers_into_state(self):
        r = self._runner()
        a = Action(
            cycle=0, tick=5, action_type=RunnerActionType.DEPLOY,
            oper="斑点", pos="C3", direction=RunnerDirectionType.UP,
        )
        r._register_skipped_action(a, map_height=7, map_width=11)
        # C3 under height 7 → tile_pos (col=2, row=4); deployed stores (row, col).
        self.assertEqual(r.get_state()["deployed"]["斑点"], (4, 2))

    def test_skipped_retreat_removes_from_state(self):
        r = self._runner(initial_state={"deployed": {"斑点": (4, 2)}})
        a = Action(cycle=1, tick=0, action_type=RunnerActionType.RETREAT, oper="斑点")
        r._register_skipped_action(a, map_height=7, map_width=11)
        self.assertNotIn("斑点", r.get_state()["deployed"])

    def test_skipped_skill_leaves_state_untouched(self):
        r = self._runner(initial_state={"deployed": {"斑点": (4, 2)}})
        a = Action(cycle=1, tick=0, action_type=RunnerActionType.SKILL, oper="斑点")
        r._register_skipped_action(a, map_height=7, map_width=11)
        self.assertEqual(r.get_state()["deployed"], {"斑点": (4, 2)})


if __name__ == "__main__":
    unittest.main()
