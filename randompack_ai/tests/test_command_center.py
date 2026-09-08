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

	@patch(f"{_B}.client")
	@patch(f"{_B}.frappe")
	def test_completed_maps_with_progress_and_note(self, mock_frappe, mock_client):
		mock_frappe.db.get_value.return_value = "RP-100"
		bridge.on_task_transition(
			self._task(result={"status": "success", "summary": "done well"}), "Completed"
		)
		mock_client.update_task_progress.assert_called_once_with(
			"RP-100:strategy", status="completed", progress=100
		)
		note = mock_client.post_project_note.call_args.kwargs["note"]
		self.assertIn("done well", note)

	@patch(f"{_B}.client")
	@patch(f"{_B}.frappe")
	def test_gate_prep_completion_requests_gate_open(self, mock_frappe, mock_client):
		mock_frappe.db.get_value.return_value = "RP-100"
		bridge.on_task_transition(self._task(phase="gate1_prep"), "Completed")
		mock_client.request_gate_open.assert_called_once()
		self.assertEqual(mock_client.request_gate_open.call_args.kwargs["gate"], "gate1")

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
	@patch(f"{_S}._remember")
	@patch(f"{_S}._warroom")
	@patch(f"{_S}.frappe")
	def test_gate_decided_completes_milestone_once(self, mock_frappe, mock_war, mock_rem):
		mock_frappe.db.get_value.side_effect = ["PRJ-1", "TASK-G1"]
		gate_task = MagicMock()
		gate_task.workflow_state = "Pending"
		mock_frappe.get_doc.return_value = gate_task
		randompack.handle_gate_decided(
			{"project_id": "RP-100", "gate": "gate1", "decision": "Midnight Roast"}, MagicMock()
		)
		self.assertEqual(gate_task.workflow_state, "Completed")
		gate_task.save.assert_called_once()

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
