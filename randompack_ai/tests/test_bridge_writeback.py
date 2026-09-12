# Copyright (c) 2026, Friday Labs and contributors
# License: MIT. See license.txt

"""The write-back bridge, against the tasks RandomPack actually creates.

RandomPack used to schedule from a fixed ten-day template. It now schedules from
the accepted proposal, so its tasks are the product's five invariant steps and
its gates are named by the studio — "Sitemap sign-off", not "Gate 1 — choose
direction" — and there may be three of them.

The bridge matched on the retired template's names. Nothing matched, and because
the bridge never raises, nothing said so: the pipeline ran to completion and the
client's gate never opened. These tests pin the two resolutions that broke.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from randompack_ai.integrations import randompack_bridge as bridge

_B = "randompack_ai.integrations.randompack_bridge"

# A proposal-scheduled engagement: five steps, three named gates.
PROPOSAL_TASKS = [
    {"name": "T-1", "subject": "Brief", "status": "Completed", "is_gate": 0},
    {"name": "T-2", "subject": "Strategy", "status": "Completed", "is_gate": 0},
    {"name": "T-3", "subject": "Sitemap sign-off", "status": "Completed", "is_gate": 1},
    {"name": "T-4", "subject": "Directions", "status": "Working", "is_gate": 0},
    {"name": "T-5", "subject": "Choose a direction", "status": "Open", "is_gate": 1},
    {"name": "T-6", "subject": "Production", "status": "Open", "is_gate": 0},
    {"name": "T-7", "subject": "Build review", "status": "Open", "is_gate": 1},
    {"name": "T-8", "subject": "Delivery", "status": "Open", "is_gate": 0},
]

# The retired template, for a brief still in flight against an old project.
LEGACY_TASKS = [
    {"name": "L-1", "subject": "Strategy & naming", "status": "Completed", "is_gate": 0},
    {"name": "L-2", "subject": "Three directions", "status": "Working", "is_gate": 0},
    {"name": "L-3", "subject": "Gate 1 — choose direction", "status": "Open", "is_gate": 1},
    {"name": "L-4", "subject": "Build system", "status": "Open", "is_gate": 0},
]


class TestPhasesResolveToProposalSteps(unittest.TestCase):
    def _resolve(self, phase, tasks=PROPOSAL_TASKS):
        with patch(f"{_B}.client") as c:
            c.get_project_state.return_value = {"tasks": tasks}
            return bridge._resolve_rp_task("PROJ-1", phase)

    def test_strategy_finds_the_step_the_proposal_created(self):
        self.assertEqual(self._resolve("strategy"), "T-2")

    def test_naming_shares_the_strategy_step(self):
        self.assertEqual(self._resolve("naming"), "T-2")

    def test_directions_production_and_guidelines_all_resolve(self):
        self.assertEqual(self._resolve("directions"), "T-4")
        self.assertEqual(self._resolve("production"), "T-6")
        self.assertEqual(self._resolve("guidelines"), "T-8")

    def test_the_retired_template_still_resolves(self):
        """A brief in flight against an old project must keep writing back."""
        self.assertEqual(self._resolve("strategy", LEGACY_TASKS), "L-1")
        self.assertEqual(self._resolve("buildout", LEGACY_TASKS), "L-4")

    def test_a_gate_is_never_returned_as_a_phase(self):
        """"Sitemap sign-off" is a decision, not a step of work."""
        tasks = [{"name": "G", "subject": "Strategy", "status": "Open", "is_gate": 1}]
        self.assertIsNone(self._resolve("strategy", tasks))

    def test_an_unknown_phase_resolves_to_nothing(self):
        self.assertIsNone(self._resolve("nonesuch"))


class TestTheNextGateIsFoundByPosition(unittest.TestCase):
    def _next(self, tasks):
        with patch(f"{_B}.client") as c:
            c.get_project_state.return_value = {"tasks": tasks}
            return bridge._next_undecided_gate("PROJ-1")

    def test_the_first_undecided_gate_is_next(self):
        """The first gate is decided, so the second is the one to open — and it
        is called what the studio quoted, not "Gate 2"."""
        self.assertEqual(self._next(PROPOSAL_TASKS), {"name": "T-5", "subject": "Choose a direction"})

    def test_a_third_gate_is_reachable(self):
        tasks = [dict(t) for t in PROPOSAL_TASKS]
        tasks[4]["status"] = "Completed"  # Choose a direction, decided
        self.assertEqual(self._next(tasks), {"name": "T-7", "subject": "Build review"})

    def test_every_gate_decided_means_none_is_next(self):
        tasks = [dict(t, status="Completed") if t["is_gate"] else dict(t) for t in PROPOSAL_TASKS]
        self.assertIsNone(self._next(tasks))

    def test_a_project_with_no_gates_has_none(self):
        self.assertIsNone(self._next([{"name": "X", "subject": "Production", "status": "Open", "is_gate": 0}]))

    def test_the_retired_templates_gate_is_still_found(self):
        self.assertEqual(self._next(LEGACY_TASKS), {"name": "L-3", "subject": "Gate 1 — choose direction"})


class TestFinishingAGatePrepOpensTheRealGate(unittest.TestCase):
    """The whole point: the client's gate opens, under its quoted name."""

    def _run(self, phase, tasks=PROPOSAL_TASKS):
        task = MagicMock()
        task.work_item_name = "BB-1"
        task.phase_key = phase
        task.get = lambda k, d=None: {
            "work_item_doctype": "Brand Brief", "work_item_name": "BB-1",
            "phase_key": phase, "title": "Gate prep",
        }.get(k, d)

        with patch(f"{_B}.client") as c, \
             patch(f"{_B}.frappe") as f, \
             patch(f"{_B}._push_gate_presentation"), \
             patch(f"{_B}._result_summary", return_value=""):
            f.db.get_value.return_value = "RP-PROJ-1"
            c.get_project_state.return_value = {"tasks": tasks}
            bridge._engine_writeback(task, "Completed")
            return c

    def test_it_asks_for_the_gate_the_studio_named(self):
        c = self._run("gate1_prep")
        self.assertEqual(c.request_gate_open.call_args.kwargs["gate"], "Choose a direction")

    def test_it_flips_that_gates_own_task_to_working(self):
        """request_gate_open is signal-only; a gate opens when its task moves."""
        c = self._run("gate1_prep")
        self.assertIn(("T-5",), [call.args for call in c.update_task_progress.call_args_list])

    def test_a_later_gate_prep_opens_the_later_gate(self):
        tasks = [dict(t) for t in PROPOSAL_TASKS]
        tasks[4]["status"] = "Completed"
        c = self._run("gate2_prep", tasks)
        self.assertEqual(c.request_gate_open.call_args.kwargs["gate"], "Build review")

    def test_nothing_is_opened_when_no_gate_remains(self):
        tasks = [dict(t, status="Completed") if t["is_gate"] else dict(t) for t in PROPOSAL_TASKS]
        c = self._run("gate1_prep", tasks)
        c.request_gate_open.assert_not_called()

    def test_a_non_gate_phase_opens_nothing(self):
        c = self._run("strategy")
        c.request_gate_open.assert_not_called()
