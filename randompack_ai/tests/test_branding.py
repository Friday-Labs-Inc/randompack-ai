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
from unittest.mock import MagicMock, patch

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
		self.assertNotIn(branding.DEFAULT_ASSISTANT_NAME, chat.INTAKE_SYSTEM_PROMPT)

	def test_advisor_prompt_is_templated(self):
		self.assertIn("{assistant}", project_chat.ADVISOR_SYSTEM_PROMPT)
		self.assertNotIn(branding.DEFAULT_ASSISTANT_NAME, project_chat.ADVISOR_SYSTEM_PROMPT)


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


class TestResolvedPerCall(unittest.TestCase):
	"""The invariant the whole design rests on: never cache the name.

	One worker process serves several sites. A functools.cache on
	assistant_name(), or a constant resolved at import, would put one studio's
	brand into another studio's customer conversation.
	"""

	def test_two_sites_in_one_process_get_their_own_name(self):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Luma"}):
			first = branding.apply(chat.INTAKE_SYSTEM_PROMPT)
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Nova"}):
			second = branding.apply(chat.INTAKE_SYSTEM_PROMPT)
		self.assertIn("You are Luma,", first)
		self.assertIn("You are Nova,", second)
		self.assertNotIn("Luma", second)
		self.assertNotIn("Nova", first)


class TestMisconfiguredName(unittest.TestCase):
	"""A non-string in site_config is a mistake; it must be loud, not silently wrong."""

	def test_non_string_falls_back_and_is_logged(self):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": 42}):
			with patch.object(branding.frappe, "log_error") as log_error:
				self.assertEqual(branding.assistant_name(), "Friday")
		log_error.assert_called_once()

	def test_boolean_from_a_config_typo_falls_back(self):
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": True}):
			with patch.object(branding.frappe, "log_error"):
				self.assertEqual(branding.assistant_name(), "Friday")


class TestAdvisorWithProjectState(unittest.TestCase):
	"""The branch customers actually hit in the portal — prompt plus live project state."""

	def test_with_context_is_branded(self):
		context = {
			"project": "PROJ-0001",
			"phase": "Directions",
			"gate": {"label": "Gate 1", "state": "Open"},
		}
		with patch.object(branding.frappe, "conf", {"friday_assistant_name": "Luma"}):
			out = project_chat.build_system_prompt(context)
		self.assertIn("You are Luma,", out)
		self.assertNotIn("{assistant}", out)


class TestProvisionersPersistTheBrandedPrompt(unittest.TestCase):
	"""The lines that write a prompt to disk — the stale-row bug this guards."""

	def _provision(self, module, fn_name, profile_const, ensure_attr, exists):
		fake = MagicMock()
		fake.db.exists.return_value = exists
		stored = MagicMock()
		stored.system_prompt = "You are Friday, the stale one"
		fake.get_doc.return_value = stored
		with patch.object(module, "frappe", fake), \
			patch.object(module, ensure_attr, lambda: {}), \
			patch.object(branding, "frappe", MagicMock(conf={"friday_assistant_name": "Luma"})):
			getattr(module, fn_name)()
		return fake, stored

	def test_existing_intake_profile_is_rebranded_in_place(self):
		_, stored = self._provision(
			chat, "provision_intake_profile", "INTAKE_PROFILE", "ensure_intake_platform", exists=True
		)
		self.assertIn("You are Luma,", stored.system_prompt)
		self.assertNotIn("{assistant}", stored.system_prompt)
		stored.save.assert_called_once()

	def test_existing_advisor_profile_is_rebranded_in_place(self):
		_, stored = self._provision(
			project_chat,
			"provision_advisor_profile",
			"ADVISOR_PROFILE",
			"ensure_project_platform",
			exists=True,
		)
		self.assertIn("You are Luma,", stored.system_prompt)
		self.assertNotIn("{assistant}", stored.system_prompt)
		stored.save.assert_called_once()

	def test_rebrand_does_not_rewrite_an_already_correct_row(self):
		"""Every migrate must not churn a new document version."""
		fake = MagicMock()
		fake.db.exists.return_value = True
		stored = MagicMock()
		with patch.object(branding, "frappe", MagicMock(conf={"friday_assistant_name": "Luma"})):
			stored.system_prompt = branding.apply(chat.INTAKE_SYSTEM_PROMPT)
			fake.get_doc.return_value = stored
			with patch.object(chat, "frappe", fake), patch.object(chat, "ensure_intake_platform", lambda: {}):
				chat.provision_intake_profile()
		stored.save.assert_not_called()

	def test_new_intake_profile_is_inserted_branded(self):
		fake = MagicMock()
		fake.db.exists.return_value = False
		with patch.object(chat, "frappe", fake), \
			patch.object(chat, "ensure_intake_platform", lambda: {}), \
			patch.object(branding, "frappe", MagicMock(conf={"friday_assistant_name": "Luma"})):
			chat.provision_intake_profile()
		payload = fake.get_doc.call_args[0][0]
		self.assertIn("You are Luma,", payload["system_prompt"])
		self.assertNotIn("{assistant}", payload["system_prompt"])
