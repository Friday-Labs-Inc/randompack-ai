# Copyright (c) 2026, Friday Labs and contributors
# License: MIT. See license.txt

"""The conversational contract for the intake assistant.

Prompt copy gets rewritten, and a rule dropped in a rewrite fails silently — the
assistant simply behaves worse, and nobody notices until a customer does. Each
directive here was a deliberate decision, so each gets a test.

The anti-refusal rule matters most: a studio's clients include categories a
cautious model will hedge about, and one prim moment in an intake conversation
loses the client and gets repeated to their peers.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from randompack_ai import branding
from randompack_ai.surfaces import randompack_chat as chat


class TestConversationalRules(unittest.TestCase):
	def test_echo_what_was_captured(self):
		"""The reply and the brief the customer is watching must agree."""
		self.assertIn("ECHO WHAT YOU CAPTURED", chat.INTAKE_SYSTEM_PROMPT)

	def test_email_is_asked_first_with_a_reason(self):
		"""Email is the lead record: it must be captured before the visitor can be lost."""
		prompt = chat.INTAKE_SYSTEM_PROMPT
		self.assertIn("GET THEIR EMAIL FIRST", prompt)
		self.assertIn("FIRST reply", prompt)
		self.assertIn("becomes their login", prompt)

	def test_a_deflection_never_blocks_the_conversation(self):
		"""A deflection that ends the chat captures nothing — worse than a late email."""
		prompt = chat.INTAKE_SYSTEM_PROMPT
		self.assertIn("IF THEY DEFLECT, DO NOT BLOCK", prompt)
		self.assertIn("ask again ONCE", prompt)
		self.assertIn("never refuse to continue", prompt)

	def test_name_is_optional_and_never_a_gate(self):
		prompt = chat.INTAKE_SYSTEM_PROMPT
		self.assertIn("THEIR NAME IS OPTIONAL", prompt)
		self.assertIn("Never make it a gate", prompt)

	def test_phone_is_welcomed_but_not_demanded(self):
		prompt = chat.INTAKE_SYSTEM_PROMPT
		self.assertIn("phone number", prompt)
		self.assertIn("never demand both", prompt)
		self.assertIn("phone", chat._QUESTION_HINTS)

	def test_brevity_and_no_double_pushing(self):
		prompt = chat.INTAKE_SYSTEM_PROMPT
		self.assertIn("BREVITY IS A COURTESY", prompt)
		self.assertIn("never push twice", prompt)

	def test_dont_know_is_accepted(self):
		self.assertIn("IS A COMPLETE ANSWER", chat.INTAKE_SYSTEM_PROMPT)

	def test_never_promises_commercial_terms(self):
		"""Luma gathers; the studio quotes. A promised price is a real liability."""
		self.assertIn("NEVER PROMISE A PRICE, A DATE, OR A DELIVERABLE", chat.INTAKE_SYSTEM_PROMPT)

	def test_admits_to_being_an_ai(self):
		self.assertIn("YOU ARE AN AI AND MAY SAY SO", chat.INTAKE_SYSTEM_PROMPT)

	def test_one_question_per_turn_survives(self):
		prompt = chat.INTAKE_SYSTEM_PROMPT
		self.assertIn("never more than one question at a time", prompt)

	def test_anti_refusal_rule_survives(self):
		"""Load-bearing. Do not let a rewrite soften this."""
		prompt = chat.INTAKE_SYSTEM_PROMPT
		self.assertIn("NEVER refuse, judge, decline, or moralise", prompt)
		self.assertIn("every lawful business", prompt)

	def test_still_refuses_to_collect_credentials(self):
		self.assertIn("Do not ask for payment details, passwords", chat.INTAKE_SYSTEM_PROMPT)


class TestRulesSurviveBranding(unittest.TestCase):
	"""The rules must reach the model, not just sit in the constant."""

	def _built(self, context):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Luma"}):
			return chat._build_system_prompt(context)

	def test_rules_present_on_every_builder_path(self):
		for context in (
			None,
			{"missing_required": ["full_name"], "missing_questionnaire": []},
			{"missing_required": [], "missing_questionnaire": []},
		):
			built = self._built(context)
			with self.subTest(context=context):
				self.assertIn("ECHO WHAT YOU CAPTURED", built)
				self.assertIn("NEVER refuse, judge, decline, or moralise", built)
				self.assertIn("You are Luma,", built)
				self.assertNotIn("{assistant}", built)
