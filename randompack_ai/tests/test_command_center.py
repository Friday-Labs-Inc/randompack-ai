# Copyright (c) 2026, Friday Labs and contributors
# License: MIT. See license.txt

"""
Unit tests for the studio domain's write-back and event handling (design 60b).

Mock-based — no DB, no model. Pins:
  - the write-back bridge (Q5): state map, gate-prep -> request_gate_open,
    Pending Review shape, no-backend-ref no-op, never raises
  - event handlers: gate.decided advances the pipeline, refinement round >= 3
    flags scope, the kill switch cancels queued work

The kernel-side halves of the original file (dispatcher gating, the agentic
runner, the Project command skills) stayed in the kernel as
frappe/friday_core/tests/test_command_center.py.
"""

import unittest
from unittest.mock import MagicMock, patch

from randompack_ai.integrations import randompack_bridge as bridge
from randompack_ai.surfaces import randompack

_B = "randompack_ai.integrations.randompack_bridge"
_S = "randompack_ai.surfaces.randompack"


class TestBridge(unittest.TestCase):
	def _task(self, phase="strategy", project="PRJ-1", result=None):
		task = MagicMock()
		task.title = "Strategy draft"
		task.project = project
		values = {"backend_ref": phase, "project": project, "result": result}
		task.get.side_effect = values.get
		return task

	@patch(f"{_B}.client")
	@patch(f"{_B}.frappe")
	def test_no_backend_ref_is_a_noop(self, mock_frappe, mock_client):
		bridge.on_task_transition(self._task(phase=None), "Completed")
		mock_client.update_task_progress.assert_not_called()

	@staticmethod
	def _backend(mock_client, tasks):
		"""What the backend answers when the bridge asks for the engagement.

		The bridge resolves a real Task docname before it writes anything, so a
		test that leaves this a bare MagicMock is testing nothing: every lookup
		"succeeds" and returns another mock.
		"""
		mock_client.get_project_state.return_value = {"tasks": tasks}

	@patch(f"{_B}.client")
	@patch(f"{_B}.frappe")
	def test_completed_maps_with_progress_and_note(self, mock_frappe, mock_client):
		"""The legacy path, which a task carrying backend_ref still takes: it
		composes the reference from the project and the phase rather than
		resolving a real Task docname. The engine path does the resolving, and
		test_bridge_writeback covers that one.

		"completed" became "Completed" here, because RandomPack's
		update_task_progress validates the status against an exact set and
		rejects anything else — lowercase was silently a no-op.
		"""
		mock_frappe.db.get_value.return_value = "RP-100"
		bridge.on_task_transition(
			self._task(result={"status": "success", "summary": "done well"}), "Completed"
		)
		mock_client.update_task_progress.assert_called_once_with(
			"RP-100:strategy", status="Completed", progress=100
		)
		note = mock_client.post_project_note.call_args.kwargs["note"]
		self.assertIn("done well", note)

	@patch(f"{_B}.client")
	@patch(f"{_B}.frappe")
	def test_gate_prep_completion_requests_the_gate_the_studio_named(self, mock_frappe, mock_client):
		"""Not "gate1". The studio names its gates on the proposal, and the
		bridge asks for the next undecided one by position in the chain."""
		mock_frappe.db.get_value.return_value = "RP-100"
		self._backend(mock_client, [
			{"name": "TASK-PREP", "subject": "Directions", "is_gate": 0},
			{"name": "TASK-G1", "subject": "Choose a direction", "is_gate": 1, "status": "Open"},
		])

		bridge.on_task_transition(self._task(phase="gate1_prep"), "Completed")

		mock_client.request_gate_open.assert_called_once()
		self.assertEqual(
			mock_client.request_gate_open.call_args.kwargs["gate"], "Choose a direction")

	@patch(f"{_B}.client")
	@patch(f"{_B}.frappe")
	def test_blocked_signals_pending_review(self, mock_frappe, mock_client):
		mock_frappe.db.get_value.return_value = "RP-100"
		bridge.on_task_transition(self._task(), "Blocked")
		mock_client.signal_pending_review.assert_called_once()

	@patch(f"{_B}.client")
	@patch(f"{_B}.frappe")
	def test_bridge_never_raises(self, mock_frappe, mock_client):
		mock_frappe.db.get_value.side_effect = RuntimeError("db down")
		bridge.on_task_transition(self._task(), "Completed")  # must not raise
		mock_frappe.log_error.assert_called_once()


class TestEventHandlers(unittest.TestCase):
	"""A decided gate advances the brief's own workflow.

	This used to assert that a milestone task was flipped to Completed and
	saved. That is not what happens any more and has not been since the engine
	arrived: the handler fires a workflow transition on the Brand Brief, and
	which transition it fires is read from the brief's CURRENT state, not from
	the gate's name — which is the whole reason the studio can name its gates
	whatever it likes.
	"""

	def _decide(self, state, mock_frappe, payload=None):
		brief = MagicMock()
		brief.workflow_state = state
		mock_frappe.db.get_value.return_value = "BB-0005"
		mock_frappe.get_doc.return_value = brief
		with patch("frappe.model.workflow.apply_workflow") as apply, \
				patch("frappe.friday_core.engine.governance.acting_as"), \
				patch(f"{_S}.post_project_note", create=True):
			randompack.handle_gate_decided(
				payload or {"project": "PRJ-1", "decision": "Approved"}, MagicMock())
		return brief, apply

	@patch(f"{_S}._remember")
	@patch(f"{_S}._warroom")
	@patch(f"{_S}.frappe")
	def test_the_first_gate_approves_the_direction(self, mock_frappe, mock_war, mock_rem):
		_, apply = self._decide("Gate 1 Review", mock_frappe)
		self.assertEqual(apply.call_args[0][1], "Approve Direction")

	@patch(f"{_S}._remember")
	@patch(f"{_S}._warroom")
	@patch(f"{_S}.frappe")
	def test_the_chosen_direction_is_recorded(self, mock_frappe, mock_war, mock_rem):
		brief, _ = self._decide("Gate 1 Review", mock_frappe, {
			"project": "PRJ-1", "decision": "Approved", "chosen_direction": "Midnight Roast"})
		brief.db_set.assert_called_once_with(
			"chosen_direction", "Midnight Roast", update_modified=False)

	@patch(f"{_S}._remember")
	@patch(f"{_S}._warroom")
	@patch(f"{_S}.frappe")
	def test_the_last_gate_is_the_final_approval(self, mock_frappe, mock_war, mock_rem):
		_, apply = self._decide("Gate 2 Review", mock_frappe)
		self.assertEqual(apply.call_args[0][1], "Final Approval")

	@patch(f"{_S}._remember")
	@patch(f"{_S}._warroom")
	@patch(f"{_S}.frappe")
	def test_a_refinement_does_not_advance_anything(self, mock_frappe, mock_war, mock_rem):
		_, apply = self._decide("Gate 1 Review", mock_frappe, {
			"project": "PRJ-1", "decision": "Refinement Requested",
			"client_comments": "warmer"})
		apply.assert_not_called()

	@patch(f"{_S}._remember")
	@patch(f"{_S}._warroom")
	@patch(f"{_S}._find_brief", return_value="BB-0005")
	@patch(f"{_S}._find_project", return_value="PRJ-1")
	@patch(f"{_S}.frappe")
	def test_refinement_round_three_flags_scope(self, mock_frappe, _p, _b, mock_war, mock_rem):
		randompack.handle_refinement_requested(
			{"project_id": "RP-100", "round": 3, "request": "less navy"}, MagicMock()
		)
		payload = mock_frappe.get_doc.call_args[0][0]
		self.assertEqual(payload["execution_mode"], "agentic")
		self.assertIn("round 3", payload["title"].lower())
		mock_rem.assert_called_once()  # scope memory
		self.assertIn("scope", mock_war.call_args[0][0].lower())

	@patch(f"{_S}._warroom")
	@patch(f"{_S}._find_project", return_value="PRJ-1")
	@patch(f"{_S}.frappe")
	def test_kill_switch_cancels_open_tasks(self, mock_frappe, _p, mock_war):
		mock_frappe.get_all.return_value = ["T-1", "T-2"]
		open_task = MagicMock()
		mock_frappe.get_doc.return_value = open_task
		event = MagicMock()
		event.event_type = "project.cancelled"
		randompack.handle_kill_switch({"project_id": "RP-100"}, event)
		self.assertEqual(open_task.workflow_state, "Cancelled")
		self.assertEqual(mock_frappe.get_doc.call_count, 2)
		mock_frappe.db.set_value.assert_called_once()  # project → Cancelled


if __name__ == "__main__":
	unittest.main()
