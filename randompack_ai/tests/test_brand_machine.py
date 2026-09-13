# Copyright (c) 2026, Friday Labs and contributors
# License: MIT. See license.txt

"""The Design 95 brand-pipeline machine SHAPE (domains/randompack_brand.py data).

DB-free: these pin the STATES/TRANSITIONS/PHASES data — the corrected flow where the
HUMAN Creative Director creates the identity and the AI produces around it, gated by
his internal gate. The role-gating *enforcement* (who can actually fire what) is the
DB-backed test_engine_governance suite; this suite catches a mis-edit of the machine
data itself before it ever provisions.
"""

from __future__ import annotations

import unittest

from randompack_ai.domains import randompack_brand as bundle

_STATES = dict(bundle.STATES)
_TRANSITIONS = {(f, a): (n, r) for f, a, n, r in bundle.TRANSITIONS}
_PHASES = {p["phase_key"]: p for p in bundle.PHASES}


class TestDesign95MachineShape(unittest.TestCase):
	def test_human_cd_states_exist_with_the_cd_role(self):
		self.assertEqual(_STATES["CD Creative"], bundle.CD_ROLE)
		self.assertEqual(_STATES["CD Internal Gate"], bundle.CD_ROLE)
		self.assertEqual(_STATES["AI Production"], "Creative Director")

	def test_flow_routes_through_the_human_cd(self):
		# Naming hands off to the HUMAN's creative stage (not the old AI Directions).
		self.assertEqual(_TRANSITIONS[("Naming", "Complete Naming")][0], "CD Creative")
		# The human signals readiness; the client presentation is prepped from HIS files.
		self.assertEqual(_TRANSITIONS[("CD Creative", "Creative Ready")], ("Gate Prep", bundle.CD_ROLE))
		# A decided gate enters AI Production (not the old Buildout).
		self.assertEqual(_TRANSITIONS[("Gate Review", "Approve Gate")][0], "AI Production")
		# Production must pass the human CD before the client track.
		self.assertEqual(
			_TRANSITIONS[("AI Production", "Complete Production")][0], "CD Internal Gate"
		)

	def test_internal_gate_has_approve_and_refine_loop(self):
		# Approval goes back to Gate Prep, not on to a second numbered gate: how
		# many times an engagement goes in front of the client is the proposal's
		# business, not this machine's.
		self.assertEqual(
			_TRANSITIONS[("CD Internal Gate", "Approve Production")], ("Gate Prep", bundle.CD_ROLE)
		)
		self.assertEqual(
			_TRANSITIONS[("CD Internal Gate", "Request Refinement")], ("AI Production", bundle.CD_ROLE)
		)

	def test_no_agent_role_owns_a_human_cd_transition(self):
		# The CD role is not any agent's discriminator_role — an agent can never
		# hold it, so it can never skip the human stage or self-approve production.
		self.assertNotIn(bundle.CD_ROLE, bundle.AGENT_ROLES)
		for (frm, _action), (_nxt, role) in _TRANSITIONS.items():
			if frm in ("CD Creative", "CD Internal Gate"):
				self.assertEqual(role, bundle.CD_ROLE)

	def test_human_states_have_no_agentic_phase(self):
		phase_states = {p["from_state"] for p in bundle.PHASES}
		self.assertNotIn("CD Creative", phase_states)
		self.assertNotIn("CD Internal Gate", phase_states)

	def test_production_phase_applies_the_humans_system(self):
		prod = _PHASES["production"]
		self.assertEqual(prod["from_state"], "AI Production")
		self.assertEqual(prod["agent_role"], "Creative Director")
		self.assertIn("get-project-file", prod["skills"])
		for anchor in ("design system", "EXACTLY", "never invent", "refinement"):
			self.assertIn(anchor, prod["prompt"])

	def test_gate1_prep_reads_the_humans_files(self):
		prep = _PHASES["gate1_prep"]
		self.assertIn("get-project-file", prep["skills"])
		self.assertIn("never invent", prep["prompt"])

	def test_legacy_states_kept_for_inflight_briefs(self):
		# In-flight briefs at the old states must stay valid and able to finish.
		for state in ("Directions", "Buildout"):
			self.assertIn(state, _STATES)
		self.assertEqual(_TRANSITIONS[("Directions", "Complete Directions")][0], "Gate Prep")
		self.assertEqual(_TRANSITIONS[("Buildout", "Complete Buildout")][0], "Gate Prep")
		self.assertIn("directions", _PHASES)
		self.assertIn("buildout", _PHASES)

		# The two-gate machine's own states, kept for the same reason: a brief
		# sitting at Gate 1 Review when this shipped must still be able to finish.
		for state in ("Gate 1 Prep", "Gate 1 Review", "Gate 2 Prep", "Gate 2 Review"):
			self.assertIn(state, _STATES)
		self.assertEqual(_TRANSITIONS[("Gate 1 Review", "Approve Direction")][0], "AI Production")
		self.assertEqual(_TRANSITIONS[("Gate 2 Review", "Final Approval")][0], "Guidelines")
		self.assertIn("gate1_prep", _PHASES)
		self.assertIn("gate2_prep", _PHASES)

	def test_sequential_only_invariant_holds(self):
		# Design 75 §8: at most ONE agentic transition per state (the engine takes
		# the first and logs otherwise). Human states may have several (CD Internal
		# Gate has 2) — only AGENTIC ones are constrained.
		agentic_from = [p["from_state"] for p in bundle.PHASES]
		self.assertEqual(len(agentic_from), len(set(agentic_from)))

	def test_cd_agent_profile_is_the_apprentice(self):
		cd = next(p for p in bundle.PROFILES if p["profile_name"] == "Creative Director")
		for anchor in ("production designer", "apprentice", "never originate"):
			self.assertIn(anchor, cd["system_prompt"])
		self.assertIn("get-project-file", cd["skills"])


if __name__ == "__main__":
	unittest.main()


class TestTheGateCycleTakesAnyNumberOfGates(unittest.TestCase):
	"""There used to be two client gates, because the ten-day package had two
	client decisions. A studio names its own gates now and may quote one or
	five, so the gate is a cycle the pipeline re-enters, not a pair of
	stations it passes through once each."""

	def test_there_is_one_gate_prep_and_one_gate_review(self):
		self.assertIn("Gate Prep", _STATES)
		self.assertIn("Gate Review", _STATES)

	def test_the_cycle_closes(self):
		"""Prep → Review → production → the CD → prep again. Without the last
		edge the pipeline could only ever put one decision to the client."""
		self.assertEqual(_TRANSITIONS[("Gate Prep", "Complete Gate Prep")][0], "Gate Review")
		self.assertEqual(_TRANSITIONS[("Gate Review", "Approve Gate")][0], "AI Production")
		self.assertEqual(_TRANSITIONS[("AI Production", "Complete Production")][0], "CD Internal Gate")
		self.assertEqual(_TRANSITIONS[("CD Internal Gate", "Approve Production")][0], "Gate Prep")

	def test_the_cycle_has_an_exit_from_both_of_its_states(self):
		"""The bridge fires this when the backend reports no undecided gate
		left. Whether the engine's auto-advance has already carried the brief
		from Gate Prep to Gate Review by then is a race, so an exit that worked
		from only one of them would strand the engagement half the time."""
		self.assertEqual(_TRANSITIONS[("Gate Prep", "No Gate Remaining")][0], "Guidelines")
		self.assertEqual(_TRANSITIONS[("Gate Review", "No Gate Remaining")][0], "Guidelines")

	def test_one_prep_phase_serves_every_gate(self):
		self.assertIn("gate_prep", _PHASES)
		self.assertEqual(_PHASES["gate_prep"]["from_state"], "Gate Prep")
		self.assertEqual(_PHASES["gate_prep"]["action"], "Complete Gate Prep")

	def test_no_new_brief_can_reach_a_numbered_gate(self):
		"""The old states survive for briefs in flight, but nothing leads into
		them any more — that is what makes them legacy rather than alive."""
		reachable = {nxt for (_frm, _a), (nxt, _r) in _TRANSITIONS.items()}
		for dead in ("Gate 1 Prep", "Gate 2 Prep"):
			self.assertNotIn(dead, reachable, f"{dead} is still reachable")
