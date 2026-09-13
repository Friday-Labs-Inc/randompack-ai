# Copyright (c) 2026, Friday Labs and contributors
# For license information, please see license.txt

"""
The RandomPack domain surface — connector #1's event handlers (Design 81b).

PLAIN ENGLISH
=============
RandomPack (the ops backend) POSTs signed events to the back-compat URL
`receive_event` below, which simply delegates to the GENERIC connector spine
(`connectors.core`): that verifies the HMAC signature, persists a Connector
Event row, acks 200, and queues processing on the `friday` queue. The seam is
generic core; what lives HERE is purely the RandomPack *meaning* — the HANDLERS
registry + handler functions that turn each event into a Friday action (brief
ingestion, pipeline start, gate transitions, etc.). `connectors.core.process_event`
imports this module and dispatches through `HANDLERS`.

CONTRACT NOTES (agreed with the randompack side, design 60):
  - comment.added never echoes Friday's own notes back — no self-dedupe here.
  - `Pending Review` (not "failed") is the needs-human signal on write-back.
"""

from __future__ import annotations

import json

import re

import frappe

from randompack_ai import branding

from frappe.friday_core.connectors import core as connector_core

# This connector's registry id (the Connector row created by the 81b migration).
CONNECTOR_NAME = "randompack-system"


# ---------------------------------------------------------------------------
# The endpoint (thin wrapper — generic intake lives in connectors.core)
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive_event():
	"""POST /api/method/randompack_ai.surfaces.randompack.receive_event

	Back-compat URL for the RandomPack backend. Delegates to the generic
	signed-event intake (Design 81): the `randompack-system` Connector row
	carries the HMAC secret + tolerance, and the HANDLERS registry at the bottom
	of this module is what `connectors.core.process_event` dispatches through.
	Guest-reachable by design: the HMAC signature IS the authentication.
	"""
	return connector_core.receive_event(CONNECTOR_NAME)


# ---------------------------------------------------------------------------
# Handlers (the RandomPack event meaning — stays in domain:randompack)
# ---------------------------------------------------------------------------

# Their brief field → our Brand Brief field. Unknown keys fall through to
# `notes` so nothing in the frozen snapshot is ever silently lost.
_BRIEF_FIELD_MAP = {
	# The older wire vocabulary, kept so recorded events still replay.
	"company": "business_name",
	"industry": "industry",
	"audience": "target_audience",
	"differentiator": "what_they_do",
	"personality_attributes": "brand_personality",  # list → comma-joined
	"references": "inspirations",
	"brands_admired": "color_preferences",  # admired/avoid both land in prefs
	"brands_avoid": "competitors",
	# RandomPack's snapshot is its Onboarding Brief as a dict, so the keys are
	# that doctype's own fieldnames. Without these every Brand Brief the CD saw
	# was titled "RandomPack RP-BRIEF-…" with the company in the unmapped notes.
	"company_name": "business_name",
	"category": "industry",
	"what_you_do": "what_they_do",
	"target_audience": "target_audience",
	"personality": "brand_personality",
	"competitors": "competitors",
	"color_preferences": "color_preferences",
}


def _ingest_brief(rp_brief: str, snapshot: dict) -> str:
	"""Create a Brand Brief from a frozen brief_snapshot (idempotent by rp_brief).
	Returns the brief name (existing or newly created). Shared by both handlers —
	whichever event arrives carrying the snapshot creates the brief. Correlation
	key is the RandomPack Onboarding Brief docname (`brief`)."""
	existing = frappe.db.get_value("Brand Brief", {"rp_brief": rp_brief}, "name") if rp_brief else None
	if existing:
		return existing

	# RandomPack's brief_snapshot is a JSON field → arrives as a JSON string.
	if isinstance(snapshot, str):
		try:
			snapshot = json.loads(snapshot)
		except (ValueError, TypeError):
			snapshot = {}

	doc_fields: dict = {"doctype": "Brand Brief", "status": "Ready", "rp_brief": rp_brief}
	leftovers: dict = {}
	for key, value in (snapshot or {}).items():
		target = _BRIEF_FIELD_MAP.get(key)
		if not target:
			leftovers[key] = value
			continue
		if isinstance(value, list):
			value = ", ".join(
				(v.get("url") or v.get("note") or v.get("file") or "") if isinstance(v, dict) else str(v)
				for v in value
			).strip(", ")
		if doc_fields.get(target):
			doc_fields[target] = (
				f"{doc_fields[target]}\nAvoid: {value}"
				if key == "brands_avoid"
				else f"{doc_fields[target]}\n{value}"
			)
		else:
			doc_fields[target] = value

	notes_parts = [f"[rp:{rp_brief}]"]
	if leftovers:
		notes_parts.append("Unmapped brief fields:\n" + frappe.as_json(leftovers))
	doc_fields["notes"] = "\n".join(notes_parts)
	doc_fields.setdefault("business_name", f"RandomPack {rp_brief}")
	return frappe.get_doc(doc_fields).insert(ignore_permissions=True).name


def handle_payment_received(data: dict, event) -> None:
	"""payment.received → stage the Brand Brief IF a snapshot is present.

	RandomPack's payment.received carries only {brief, sales_order} (no
	snapshot), so this is normally a no-op — the brief is created at
	project.created, which carries the frozen snapshot. Kept for the case where
	a snapshot is delivered early.
	"""
	snapshot = data.get("brief_snapshot") or {}
	rp_brief = str(data.get("brief") or "")
	if snapshot and rp_brief:
		_ingest_brief(rp_brief, snapshot)


def _brief_summary(snapshot: dict, rp_brief: str) -> str:
	"""The brief as a person would read it on a desk — not a JSON dump."""
	if isinstance(snapshot, str):
		try:
			snapshot = json.loads(snapshot)
		except (ValueError, TypeError):
			snapshot = {}
	snapshot = snapshot or {}
	lines = []
	for label, key in (
		("Company", "company_name"), ("Contact", "full_name"), ("What they do", "what_you_do"),
		("Differentiator", "differentiator"), ("Audience", "target_audience"),
		("Stage", "stage"), ("Preferred start", "preferred_start"),
	):
		value = snapshot.get(key)
		if value:
			lines.append(f"{label}: {value}")
	personality = snapshot.get("personality")
	if isinstance(personality, list) and personality:
		lines.append("Personality: " + ", ".join(str(p) for p in personality))
	lines.append(f"[rp:{rp_brief}]")
	return "\n".join(lines)


def _assign_to_cd(task_name: str, summary: str) -> None:
	"""Put the task on every human Creative Director's desk. Best-effort: a
	studio with the role unassigned still gets the task, just unowned."""
	from randompack_ai.domains.randompack_brand import CD_ROLE

	try:
		users = frappe.get_all("Has Role", filters={"role": CD_ROLE, "parenttype": "User"}, pluck="parent")
		users = [u for u in users if u not in ("Administrator", "Guest")]
		if not users:
			return
		from frappe.desk.form import assign_to

		assign_to.add({"assign_to": users, "doctype": "Task", "name": task_name,
					   "description": summary[:140]})
	except Exception:
		frappe.log_error(title="friday.randompack _assign_to_cd failed")


def handle_brief_submitted(data: dict, event) -> None:
	"""brief.submitted → the Creative Director sees the brief when the
	conversation ends, not when money lands.

	Until this handler existed the event was received and recorded and nothing
	happened: the Brand Brief was only built inside payment.received. So a
	studio learned of an enquiry from a list view, and the person responsible
	for judging it learned of it last.

	Three things, all idempotent by the RandomPack brief id:
	  * the Brand Brief, from the snapshot the event now carries (no pipeline
	    is started — that is still payment's job);
	  * the local Friday Project, so the task carries the engagement;
	  * one Task on the CD's desk, human-owned, never dispatched to an agent.
	"""
	rp_brief = str(data.get("brief") or "")
	if not rp_brief:
		return
	snapshot = data.get("brief_snapshot") or {}
	rp_project = str(data.get("project") or "")
	company = str(data.get("company_name") or data.get("company") or "").strip()

	brief = _ingest_brief(rp_brief, snapshot)
	if rp_project and frappe.db.get_value("Brand Brief", brief, "rp_project") != rp_project:
		frappe.db.set_value("Brand Brief", brief, "rp_project", rp_project)

	project = None
	if rp_project:
		project = _ensure_friday_project(rp_project, rp_brief, company or None)
		if project and not frappe.db.get_value("Brand Brief", brief, "project"):
			frappe.db.set_value("Brand Brief", brief, "project", project)

	if frappe.db.exists("Task", {"backend_ref": rp_brief}):
		return  # a replay; the desk already has it

	summary = _brief_summary(snapshot, rp_brief)
	task = frappe.get_doc({
		"doctype": "Task",
		"title": f"Review brief — {company or rp_brief}",
		"description": summary,
		"project": project,
		"backend_ref": rp_brief,
		"workflow_state": "Pending",
		# A person's task. `milestone` is the mode the engine never dispatches.
		"execution_mode": "milestone",
		"dispatchable": 0,
		"priority": "normal",
	}).insert(ignore_permissions=True)
	_assign_to_cd(task.name, summary)
	_warroom(f"New brief from {company or rp_brief} — on the Creative Director's desk.")


# ---------------------------------------------------------------------------
# 60b handlers — the command center reacts to the pipeline's business moments
# ---------------------------------------------------------------------------


def _backend_ref(data: dict, event) -> str:
	return str(data.get("project_id") or data.get("brief_id") or event.event_id)


def _find_brief(backend_ref: str) -> str | None:
	return frappe.db.get_value("Brand Brief", {"notes": ("like", f"%[rp:{backend_ref}]%")}, "name")


def _ensure_friday_project(rp_project: str, rp_brief: str, business_name: str | None) -> str | None:
	"""Design 77: ensure a local Friday Project record exists for this engagement
	and return its docname. Idempotent — keyed by the RandomPack project ref
	stored on Project.backend_ref (unique). Returns None if we can't make one
	(missing both rp_project and rp_brief, etc.); the caller treats that as
	'no local project, brief stays standalone'."""
	if not (rp_project or rp_brief):
		return None
	# Match by backend_ref (the RP project docname). This is the unique key
	# on Project — a replay of project.created finds the existing row.
	existing = _find_project(rp_project) if rp_project else None
	if existing:
		return existing
	name_hint = (business_name or "").strip() or f"RandomPack {rp_project or rp_brief}"
	try:
		doc = frappe.get_doc({
			"doctype": "Project",
			"project_name": f"{name_hint} ({rp_project or rp_brief})",
			"description": f"Brand pipeline for RandomPack project {rp_project!r} (brief {rp_brief!r}).",
			"status": "Open",
			"backend_ref": rp_project or rp_brief,
		})
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		# A duplicate backend_ref race or any other insert failure — log
		# and move on. The brief stays without a local project link rather
		# than blocking the pipeline.
		frappe.log_error(title="friday.randompack _ensure_friday_project failed")
		return _find_project(rp_project) if rp_project else None


def _find_project(backend_ref: str) -> str | None:
	return frappe.db.get_value("Project", {"backend_ref": backend_ref}, "name")


# **[PROJ-0585]** — the war room prefixes a message with the engagement it is
# about, which is the only thing that says where a line belongs.
_PROJECT_PREFIX = re.compile(r"^\*\*\[([^\]]+)\]\*\*")


def _warroom(text: str) -> None:
	"""Best-effort War Room post, on this bench and on the studio's.

	There are two Ravens. This bench has the war room, where Friday narrates
	everything it does; the studio logs into the other one, on the backend. So
	all of this commentary was landing in a room the people doing the work
	cannot open, and the only things crossing were the notes the bridge posts
	deliberately.

	Mirrored, not moved: the war room stays the operator's log with everything
	in it, and the studio gets the same line in the Raven they actually use —
	in the engagement's own room when the message names one.
	"""
	try:
		from frappe.friday_core.warroom.publisher import _get_channel_id, _post_to_raven

		channel = _get_channel_id()
		if channel:
			_post_to_raven(channel, {"text": text, "message_type": "Text", "hide_in_message_history": False})
	except Exception:
		pass

	# Separate try: the studio hearing about it must not depend on this bench's
	# own room being reachable, and neither may break the work being narrated.
	try:
		from randompack_ai.integrations.randompack_client import send

		match = _PROJECT_PREFIX.match(text.strip())
		send("randompack.api.v1.friday_says", {
			"text": text,
			"project": match.group(1) if match else None,
		})
	except Exception:
		pass


def handle_project_created(data: dict, event) -> None:
	"""project.created → start the Brand Brief metadata engine (Design 75).

	Correlate the ingested Brand Brief by the RandomPack brief docname, record
	the RandomPack project ref on it (for write-back), then kick the Design-75
	engine by moving the brief into its initial workflow state. The engine's
	on_update hook dispatches the first phase. Idempotent: a replay that finds
	the brief already started is an observable no-op.
	"""
	from randompack_ai.domains.randompack_brand import INITIAL_STATE

	rp_brief = str(data.get("brief") or "")
	rp_project = str(data.get("project") or "")
	snapshot = data.get("brief_snapshot") or {}
	brief = frappe.db.get_value("Brand Brief", {"rp_brief": rp_brief}, "name") if rp_brief else None
	# payment.received carries no snapshot, so the brief usually doesn't exist
	# yet — create it now from project.created's frozen snapshot.
	if not brief and snapshot and rp_brief:
		brief = _ingest_brief(rp_brief, snapshot)
	if not brief:
		brief = _find_brief(_backend_ref(data, event))
	if not brief:
		raise ValueError(
			f"no Brand Brief for RandomPack brief {rp_brief!r} / project {rp_project!r} and no "
			"snapshot to create one"
		)

	doc = frappe.get_doc("Brand Brief", brief)
	# Persist rp_project NOW (apply_workflow doesn't reliably carry an unsaved
	# field), so the engine + write-back see it from the first phase on.
	if rp_project and doc.rp_project != rp_project:
		doc.db_set("rp_project", rp_project, update_modified=False)
		doc.reload()

	# Design 77 — create a LOCAL Friday Project record per engagement and link
	# the brief to it via the canonical 'project' field. The metadata engine's
	# phase_dispatcher._project_of() reads work_item.get('project'), so this
	# makes every engine Task carry the Project docname — enabling the
	# Project's task rollup, Raven channel routing, and share-deliverables.
	# Idempotent: a replay finds the existing Project (matched by backend_ref)
	# and reuses it rather than creating a duplicate.
	if not doc.project:
		project_docname = _ensure_friday_project(rp_project, rp_brief, doc.business_name)
		if project_docname:
			doc.db_set("project", project_docname, update_modified=False)
			doc.reload()

	# After payment the brief idles at INITIAL_STATE ("Intake") — no agentic phase
	# there, so nothing has run yet. Starting the pipeline = firing the Start
	# Pipeline transition (Intake → Strategy), which lets the engine dispatch the
	# first phase WITH the project ref set. A brief already past Intake is a replay.
	if doc.workflow_state and doc.workflow_state != INITIAL_STATE:
		_warroom(f"**[{rp_project or rp_brief}]** project.created replay — pipeline already running ({doc.workflow_state}); no-op.")
		return

	from frappe.friday_core.engine.governance import acting_as
	from frappe.model.workflow import apply_workflow

	if doc.workflow_state != INITIAL_STATE:
		doc.workflow_state = INITIAL_STATE  # ensure at Intake for the transition
	# The webhook worker runs as Guest; Start Pipeline is a System-Manager-gated
	# SYSTEM transition (not an agent/gate action), so fire it as Administrator.
	with acting_as("Administrator"):
		apply_workflow(doc, "Start Pipeline")  # Intake → Strategy; fires the engine
	_warroom(f"**[{rp_project or rp_brief}]** brand pipeline started (brief {brief} → Strategy).")

	from randompack_ai.integrations.randompack_client import post_project_note

	if rp_project:
		post_project_note(rp_project, note=branding.apply("{assistant} started the brand pipeline (strategy → directions → gates → delivery)."))


def handle_gate_decided(data: dict, event) -> None:
	"""gate.decided → fire the Brand Brief's gate transition as the gateway user.

	The brief's CURRENT workflow_state tells us which gate this is (Gate 1
	Review → Approve Direction; Gate 2 Review → Final Approval), so we don't
	depend on the backend's gate naming. 'Refinement Requested' does NOT advance
	— it's noted for a human. The transition fires as the gateway system user
	(holds only the client-reviewer role) per the Design 75 §3 governance guard;
	the engine then dispatches the next phase.
	"""
	from randompack_ai.domains.randompack_brand import GATEWAY_USER
	from frappe.friday_core.engine.governance import acting_as
	from randompack_ai.integrations.randompack_client import post_project_note
	from frappe.model.workflow import apply_workflow

	rp_project = str(data.get("project") or "")
	brief = (frappe.db.get_value("Brand Brief", {"rp_project": rp_project}, "name") if rp_project else None) or \
		_find_brief(_backend_ref(data, event))
	if not brief:
		raise ValueError(f"no Brand Brief for RandomPack project {rp_project!r}")

	decision = str(data.get("decision") or "")
	chosen = str(data.get("chosen_direction") or "")
	if decision == "Refinement Requested":
		_warroom(f"**[{rp_project}]** refinement requested: {str(data.get('client_comments') or '')}")
		post_project_note(rp_project, note=branding.apply("{assistant} noted the refinement request; awaiting the updated direction."))
		return

	doc = frappe.get_doc("Brand Brief", brief)
	state = doc.workflow_state or ""

	# A chosen direction is recorded whenever the client names one, at whichever
	# gate they name it. It used to be read only at Gate 1, because Gate 1 was
	# by definition the direction gate — a studio that puts the choice at its
	# third gate would have had it dropped.
	if chosen:
		doc.db_set("chosen_direction", chosen, update_modified=False)
		doc.reload()

	if state == "Gate Review":
		# One state, one action, any number of gates. Which decision this was is
		# the proposal's business; the pipeline only needs to know it was made.
		action = "Approve Gate"
	elif "Gate 1" in state:
		action = "Approve Direction"  # legacy two-gate machine
	elif "Gate 2" in state:
		action = "Final Approval"  # legacy two-gate machine
		# That machine has no third slot, so a proposal quoting more than two
		# gates would deliver without ever asking about the rest.
		from randompack_ai.integrations.randompack_bridge import warn_if_gates_remain

		warn_if_gates_remain(rp_project, just_decided=str(data.get("which") or data.get("gate") or ""))
	else:
		_warroom(f"**[{rp_project}]** gate.decided but brief is at {state!r} — no matching gate transition; ignored.")
		return

	with acting_as(GATEWAY_USER):
		apply_workflow(doc, action)

	_remember(
		f"RandomPack project {rp_project}: {state} approved — {chosen or decision or 'approved'}",
		subject=rp_project or brief,
	)
	_warroom(f"**[{rp_project}]** {state} approved ({chosen or decision or 'approved'}) — pipeline advanced.")


def handle_refinement_requested(data: dict, event) -> None:
	"""refinement.requested → an agentic task now; advisory scope-guard at round ≥ 3 (Q6)."""
	ref = _backend_ref(data, event)
	project = _find_project(ref)
	if not project:
		raise ValueError(f"no Friday project for backend ref {ref!r}")
	round_n = int(data.get("round") or 1)
	request = str(data.get("request") or data.get("notes") or "See backend comments.")
	brief = _find_brief(ref) or ""

	frappe.get_doc(
		{
			"doctype": "Task",
			"title": f"Refinement round {round_n}",
			"description": (
				f"Client refinement request (round {round_n}) for Brand Brief {brief}:\n"
				f"{request}\n\nProduce the revised draft(s); reply with a concise summary."
			),
			"project": project,
			"workflow_state": "Pending",
			"execution_mode": "agentic",
			"backend_ref": f"refinement_r{round_n}",
			"required_skills": [{"skill": "get-brand-brief"}],
		}
	).insert(ignore_permissions=True)

	if round_n >= 3:
		_remember(
			f"Backend project {ref} reached refinement round {round_n} (+2 delivery days each).", subject=ref
		)
		_warroom(
			f"⚠️ **[PRJ {ref}]** refinement round {round_n} — scope check: each round adds 2 delivery days."
		)


def handle_kill_switch(data: dict, event) -> None:
	"""project.cancelled / payment.refunded → cancel all open tasks NOW (Q7)."""
	ref = _backend_ref(data, event)
	project = _find_project(ref)
	if not project:
		return  # nothing planned — nothing to kill
	open_tasks = frappe.get_all(
		"Task",
		filters={"project": project, "workflow_state": ("not in", ["Completed", "Cancelled"])},
		pluck="name",
	)
	for name in open_tasks:
		task = frappe.get_doc("Task", name)
		task.workflow_state = "Cancelled"
		task.save(ignore_permissions=True)
	frappe.db.set_value("Project", project, "status", "Cancelled", update_modified=False)
	_warroom(f"🛑 **[PRJ {ref}]** {event.event_type} — {len(open_tasks)} open tasks cancelled.")


def handle_gate_reminder(data: dict, event) -> None:
	ref = _backend_ref(data, event)
	_warroom(f"⏰ **[PRJ {ref}]** gate reminder: {data.get('gate') or 'a gate'} is awaiting the client.")


def handle_comment_added(data: dict, event) -> None:
	"""Relay client/team comments to the War Room (Friday's own notes are
	already filtered out by the backend — locked contract, no self-dedupe)."""
	ref = _backend_ref(data, event)
	comment = str(data.get("comment") or data.get("text") or "")[:500]
	if comment:
		_warroom(f"💬 **[PRJ {ref}]** comment: {comment}")


def handle_project_completed(data: dict, event) -> None:
	ref = _backend_ref(data, event)
	project = _find_project(ref)
	if project:
		frappe.db.set_value("Project", project, "status", "Completed", update_modified=False)
	_remember(f"Backend project {ref} completed and delivered.", subject=ref)
	_warroom(f"✅ **[PRJ {ref}]** project completed.")


def _remember(memory: str, subject: str) -> None:
	"""Direct memory write for event context (no agent turn to attribute)."""
	profile = (
		frappe.db.get_value("Chat Platform", "raven", "default_agent_profile")
		or frappe.db.get_value("Chat Platform", "cli", "default_agent_profile")
		or "Friday"
	)
	if not frappe.db.exists("Agent Profile", profile):
		return
	# Design 73 — scope the memory to its project. The subject is the backend_ref
	# (e.g. FLI-001), so resolve the Project from it; recall in that project's
	# room then sees this fact, and other rooms don't.
	project = frappe.db.get_value("Project", {"backend_ref": subject}, "name") if subject else None
	frappe.get_doc(
		{
			"doctype": "Agent Memory",
			"memory": memory[:490],
			"agent_profile": profile,
			"project": project,
			"subject": subject,
			"source_session": "randompack-events",
			"status": "Active",
		}
	).insert(ignore_permissions=True)


HANDLERS = {
	"brief.submitted": handle_brief_submitted,
	"payment.received": handle_payment_received,
	"project.created": handle_project_created,
	"gate.decided": handle_gate_decided,
	"refinement.requested": handle_refinement_requested,
	"project.cancelled": handle_kill_switch,
	"payment.refunded": handle_kill_switch,
	"gate.reminder": handle_gate_reminder,
	"comment.added": handle_comment_added,
	"project.completed": handle_project_completed,
	# gate.opened / phase.changed / files.delivered: recorded (no action needed
	# v0.1 — the ledger keeps them for audit and later use).
}
