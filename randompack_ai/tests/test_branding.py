# Copyright (c) 2026, Friday Labs and contributors
# License: MIT. See license.txt

"""Deployment branding (branding.py) and its use in the client-facing prompts.

DB-free: `frappe.conf` is patched directly. The point of these tests is that the
assistant's name is per-site CONFIGURATION — a studio deploying RandomPack under
its own brand must never need a code change, and a site that configures nothing
must keep saying "Friday".
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from randompack_ai import branding
from randompack_ai.surfaces import randompack_chat as chat
from randompack_ai.surfaces import randompack_project_chat as project_chat


class TestAssistantName(unittest.TestCase):
	def test_defaults_to_friday_when_unconfigured(self):
		with patch.object(branding.frappe, "conf", {}):
			self.assertEqual(branding.assistant_name(), "Friday")

	def test_reads_the_site_config_key(self):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Luma"}):
			self.assertEqual(branding.assistant_name(), "Luma")

	def test_blank_and_whitespace_fall_back_to_the_default(self):
		for value in ("", "   ", None):
			with patch.object(branding.frappe, "conf", {"friday_assistant_name": value}):
				self.assertEqual(branding.assistant_name(), "Friday")

	def test_surrounding_whitespace_is_stripped(self):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "  Luma  "}):
			self.assertEqual(branding.assistant_name(), "Luma")

	def test_no_bound_site_falls_back_rather_than_raising(self):
		class Exploding:
			def get(self, *_a, **_k):
				raise RuntimeError("no site bound")

		with patch.object(branding.frappe, "conf", Exploding()):
			self.assertEqual(branding.assistant_name(), "Friday")


class TestApply(unittest.TestCase):
	def test_placeholder_is_replaced(self):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Luma"}):
			self.assertEqual(branding.apply("You are {assistant}, hello"), "You are Luma, hello")

	def test_stray_braces_are_left_alone(self):
		# A plain replace, not str.format — unbalanced copy must never raise mid-conversation.
		with patch.object(branding.frappe, "conf", {}):
			self.assertEqual(branding.apply("use {json} like {this"), "use {json} like {this")


class TestPromptsCarryThePlaceholder(unittest.TestCase):
	"""The constants must stay templates — a literal name here is the bug this prevents."""

	def test_intake_prompt_is_templated(self):
		self.assertIn("{assistant}", chat.INTAKE_SYSTEM_PROMPT)
		self.assertNotIn("You are Friday", chat.INTAKE_SYSTEM_PROMPT)

	def test_advisor_prompt_is_templated(self):
		self.assertIn("{assistant}", project_chat.ADVISOR_SYSTEM_PROMPT)
		self.assertNotIn("You are Friday", project_chat.ADVISOR_SYSTEM_PROMPT)


class TestBuildersResolveBranding(unittest.TestCase):
	"""Every return path of both builders must come out branded."""

	def _intake(self, context):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Luma"}):
			return chat._build_system_prompt(context)

	def test_intake_no_context(self):
		out = self._intake(None)
		self.assertIn("You are Luma,", out)
		self.assertNotIn("{assistant}", out)

	def test_intake_with_outstanding_fields(self):
		out = self._intake({"missing_required": ["full_name"], "missing_questionnaire": []})
		self.assertIn("You are Luma,", out)
		self.assertNotIn("{assistant}", out)

	def test_intake_brief_complete(self):
		out = self._intake({"missing_required": [], "missing_questionnaire": []})
		self.assertIn("You are Luma,", out)
		self.assertNotIn("{assistant}", out)

	def test_advisor_without_context(self):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Luma"}):
			out = project_chat.build_system_prompt(None)
		self.assertIn("You are Luma,", out)
		self.assertNotIn("{assistant}", out)

	def test_unconfigured_site_still_says_friday(self):
		with patch.object(branding.frappe, "conf", {}):
			out = chat._build_system_prompt(None)
		self.assertIn("You are Friday,", out)
		self.assertNotIn("{assistant}", out)
