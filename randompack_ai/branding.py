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
	"""The configured assistant name for the current site, else the default.

	Every fallback here is a site silently showing the WRONG brand, so the only
	swallowed case is the one that is genuinely expected — no site bound. A
	non-string value is a misconfiguration and gets logged rather than hidden.
	"""
	try:
		raw = frappe.conf.get("friday_assistant_name")
	except (AttributeError, RuntimeError):
		# No site bound (import-time use, some CLI paths) — fall back, don't raise.
		return DEFAULT_ASSISTANT_NAME
	if raw is None:
		return DEFAULT_ASSISTANT_NAME
	if not isinstance(raw, str):
		frappe.log_error(
			title="branding: friday_assistant_name is not a string",
			message=f"got {type(raw).__name__}: {raw!r} — falling back to {DEFAULT_ASSISTANT_NAME}",
		)
		return DEFAULT_ASSISTANT_NAME
	return raw.strip() or DEFAULT_ASSISTANT_NAME


def apply(text: str) -> str:
	"""Resolve the placeholder in a prompt.

	A plain replace, not str.format, so a stray brace in prompt copy can never
	raise KeyError in the middle of a customer conversation.
	"""
	return text.replace(PLACEHOLDER, assistant_name())
