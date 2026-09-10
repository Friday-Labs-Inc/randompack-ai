"""What the client-facing assistant calls itself, per deployment.

A studio runs RandomPack under its own brand, so the assistant's name is
per-site configuration rather than a constant baked into a prompt. Prompts
carry the `{assistant}` placeholder and `apply()` resolves it at call time —
never at import, because one worker process serves several sites.

	bench --site luma.knc.studio set-config friday_assistant_name Luma
"""

import frappe

PLACEHOLDER = "{assistant}"
DEFAULT_ASSISTANT_NAME = "Friday"


def assistant_name() -> str:
	"""The configured assistant name for the current site, else the default."""
	try:
		configured = (frappe.conf.get("friday_assistant_name") or "").strip()
	except Exception:
		# No site bound (import-time use, some CLI paths) — fall back rather than raise.
		configured = ""
	return configured or DEFAULT_ASSISTANT_NAME


def apply(text: str) -> str:
	"""Resolve the placeholder in a prompt.

	A plain replace, not str.format, so a stray brace in prompt copy can never
	raise KeyError in the middle of a customer conversation.
	"""
	return text.replace(PLACEHOLDER, assistant_name())
