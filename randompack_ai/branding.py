"""What the client-facing assistant calls itself, and who it works for.

A studio runs RandomPack under its own brand, so both the assistant's name and
the studio's name are per-site configuration rather than constants baked into a
prompt. Prompts carry `{assistant}` and `{studio}`; `apply()` resolves them at
call time — never at import, because one worker process serves several sites.

	bench --site luma.knc.studio set-config friday_assistant_name Luma
	bench --site luma.knc.studio set-config friday_studio_name KNC

The studio default is deliberately "the studio" rather than the product's name.
An unset site should say something true and generic, not introduce itself as a
company the customer is not talking to.
"""

import frappe

PLACEHOLDER = "{assistant}"
STUDIO_PLACEHOLDER = "{studio}"
DEFAULT_ASSISTANT_NAME = "Friday"
DEFAULT_STUDIO_NAME = "the studio"


def _configured(key: str, default: str) -> str:
	"""Read one branding key for the current site, else the default.

	Every fallback here is a site silently showing the WRONG brand, so the only
	swallowed case is the one that is genuinely expected — no site bound. A
	non-string value is a misconfiguration and gets logged rather than hidden.
	"""
	try:
		raw = frappe.conf.get(key)
	except (AttributeError, RuntimeError):
		# No site bound (import-time use, some CLI paths) — fall back, don't raise.
		return default
	if raw is None:
		return default
	if not isinstance(raw, str):
		frappe.log_error(
			title=f"branding: {key} is not a string",
			message=f"got {type(raw).__name__}: {raw!r} — falling back to {default}",
		)
		return default
	return raw.strip() or default


def assistant_name() -> str:
	"""What the assistant calls itself on this site."""
	return _configured("friday_assistant_name", DEFAULT_ASSISTANT_NAME)


def studio_name() -> str:
	"""The studio this assistant works for on this site."""
	return _configured("friday_studio_name", DEFAULT_STUDIO_NAME)


def apply(text: str) -> str:
	"""Resolve the placeholders in a prompt.

	A plain replace, not str.format, so a stray brace in prompt copy can never
	raise KeyError in the middle of a customer conversation.
	"""
	return text.replace(PLACEHOLDER, assistant_name()).replace(
		STUDIO_PLACEHOLDER, studio_name()
	)
