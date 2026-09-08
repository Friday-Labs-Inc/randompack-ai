"""randompack_ai — the design-studio domain on the Friday agent kernel.

Everything here reaches the kernel through published seams; no kernel file is
patched. See README.md for the map.
"""

app_name = "randompack_ai"
app_title = "RandomPack AI"
app_publisher = "Friday Labs"
app_description = "RandomPack AI — the studio-side domain bundle for Friday: personas, pipeline-manifest handler, brand skills and intake surfaces."
app_email = "hello@fridaylabs.in"
app_license = "gpl-3.0"

required_apps = ["frappe"]

# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------
# The generic Design-75 engine already watches every DocType and wakes only for
# work-items an active Domain Bundle governs — it needs no registration here.
# These two are domain reactions layered on top of that.
doc_events = {
	"Brand Brief": {
		"on_update": [
			# When the brief reaches Delivered, push the customer package back
			# to the studio's ops backend.
			"randompack_ai.integrations.randompack_bridge.on_brief_state_change",
			# Feed the Creative Director apprenticeship loop (design 95).
			"randompack_ai.domains.randompack_study.on_brief_study_signal",
		],
	},
}

# ---------------------------------------------------------------------------
# Friday kernel seams
# ---------------------------------------------------------------------------

# Modules whose import registers skill handlers.
friday_skill_handlers = [
	"randompack_ai.skills.handlers_brand",
]

# Skill-definition refreshers run on every migrate, so a deployed skill never
# drifts from what this repo says it is.
friday_skill_definitions = [
	"randompack_ai.skills.bootstrap_brand.ensure_definitions",
]

# Called as fn(doc, state) after every Friday Task transition.
friday_task_transition_hooks = [
	"randompack_ai.integrations.randompack_bridge.on_task_transition",
]

# @-reference prefixes this domain contributes (e.g. @BB-0001).
friday_reference_registry = [
	"randompack_ai.domains.randompack_brand.REFERENCE_REGISTRY",
]

# ---------------------------------------------------------------------------
# Provisioning — the pipeline is DATA, re-applied idempotently on every migrate
# ---------------------------------------------------------------------------
after_migrate = [
	# The bundle itself: work-item, workflow, per-phase transition meta, agent
	# personas, roles, gateway account, connector stub.
	"randompack_ai.domains.randompack_brand.after_migrate",
	# Apprenticeship graduation flags (design 95).
	"randompack_ai.domains.randompack_study.ensure_graduation_flags",
	# Chat surfaces: the public intake wizard and the authenticated project chat.
	"randompack_ai.surfaces.randompack_chat.ensure_intake_platform",
	"randompack_ai.surfaces.randompack_project_chat.ensure_project_platform",
]

# Which phase outputs the client receives (kernel seam: deliverables.materialize).
friday_customer_title_map = ["randompack_ai.deliverables.CUSTOMER_TITLE_MAP"]
