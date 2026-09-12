# Copyright (c) 2026, Friday Labs and contributors
# License: MIT. See license.txt

"""What the studio sees of Friday, from the studio's own console.

Friday runs on its own site. The studio works on RandomPack's. Without this,
knowing what the agent did overnight means opening a second system — so the
console asks, over the same signed request path Luma's chat already uses, and
the reply is rendered beside the studio's own work.

This surface is READ ONLY and says so. It reports what happened and what is
waiting; approving is a decision, and a decision crossing a signed machine seam
is a different question with a different answer. The console links out for that
until it has been designed properly.

Guest-reachable by the same rule as every other RandomPack-facing surface here:
the HMAC signature IS the authentication, verified before anything is read.
"""

import frappe

from frappe.friday_core.surfaces import chat_spine

CONNECTOR_NAME = "randompack-system"

# What an unsigned caller gets. Never a reason — an error that distinguishes
# "bad signature" from "no such module" is a probe worth answering with silence.
DENIED = {"available": False, "reason": "unauthorised", "activity": [], "approvals": []}

MAX_LIMIT = 100


def _verify() -> bool:
	return chat_spine.verify_rp_signature(frappe.request.get_data() or b"", CONNECTOR_NAME)


def _actions(limit: int) -> list[dict]:
	"""What the agent wrote, newest first.

	The Agent Write Log is append-only and stamps every write with who acted, so
	it is the honest record of unattended work — not a summary the agent chose
	to emit about itself.
	"""
	rows = frappe.get_all(
		"Agent Write Log",
		filters={"actor_kind": ["!=", "human"]},
		fields=["name", "ref_doctype", "ref_name", "action", "actor", "actor_kind", "creation"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return [
		{
			"id": r.name,
			"what": f"{r.action} {r.ref_doctype}",
			"reference": r.ref_name,
			"doctype": r.ref_doctype,
			"actor": r.actor,
			"actor_kind": r.actor_kind,
			"at": str(r.creation),
		}
		for r in rows
	]


def _failures(limit: int) -> list[dict]:
	"""Skill runs that did not succeed.

	Surfaced beside the successes deliberately: a console that shows only what
	worked teaches a studio to trust an agent more than the evidence supports.
	"""
	rows = frappe.get_all(
		"Execution Log",
		filters={"status": ["not in", ["Success", "success"]]},
		fields=["name", "agent_profile", "skill", "status", "task", "creation"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return [
		{
			"id": r.name,
			"agent": r.agent_profile,
			"skill": r.skill,
			"status": r.status,
			"task": r.task,
			"at": str(r.creation),
		}
		for r in rows
	]


def _approvals() -> list[dict]:
	"""What the agent is holding, waiting on a human.

	This is the only part of the payload that is about the future rather than
	the past, and the reason the studio needs the console at all: work stopped
	on somebody's desk is invisible until someone goes looking.
	"""
	rows = frappe.get_all(
		"Workflow Request",
		filters={"status": ["in", ["Pending", "pending", "Requested"]]},
		fields=["name", "agent_profile", "skill", "risk_level", "requested_at"],
		order_by="requested_at asc",
		limit_page_length=MAX_LIMIT,
	)
	return [
		{
			"id": r.name,
			"agent": r.agent_profile,
			"skill": r.skill,
			"risk": r.risk_level,
			"since": str(r.requested_at or ""),
			# The console links out rather than approving across the seam.
			"url": frappe.utils.get_url(f"/app/workflow-request/{r.name}"),
		}
		for r in rows
	]


@frappe.whitelist(allow_guest=True, methods=["POST"])
def overview():
	"""One round trip: what the agent did, what failed, what it is waiting on."""
	if not _verify():
		return DENIED

	payload = frappe.request.get_json(silent=True) or {}
	try:
		limit = min(MAX_LIMIT, max(1, int(payload.get("limit") or 20)))
	except (TypeError, ValueError):
		limit = 20

	return {
		"available": True,
		"read_only": True,
		"site": frappe.local.site,
		"activity": _actions(limit),
		"failures": _failures(min(limit, 10)),
		"approvals": _approvals(),
	}
