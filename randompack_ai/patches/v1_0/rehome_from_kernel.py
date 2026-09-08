# Copyright (c) 2026, Friday Labs and contributors
# For license information, please see license.txt

"""Re-home the design-studio domain out of the Friday kernel into this app.

PLAIN ENGLISH
=============
The brand pipeline used to live inside the kernel (module "Friday Core"). It
now lives here (module "RandomPack AI"). On a site that ran the old layout,
three pointers still say "Friday Core":

  1. the `Brand Brief` / `Brand Direction` DocType rows,
  2. their Custom Field / Property Setter siblings (Frappe stamps a module on
     those too, and an unknown module makes them invisible to export),
  3. the `randompack-system` Connector's `handler_module`, a dotted path to a
     module that has moved.

Fixing (1) BEFORE schema sync matters: `bench migrate` deletes DocTypes whose
module belongs to an app that no longer ships the file, so a Brand Brief left
pointing at "Friday Core" would be swept as an orphan — with its data.

Idempotent, and a no-op on a fresh site (nothing to re-home).
"""

from __future__ import annotations

import frappe

MODULE = "RandomPack AI"
DOCTYPES = ("Brand Brief", "Brand Direction")
PAGES = ("studio",)
HANDLER_MOVES = {
	"frappe.friday_core.surfaces.randompack": "randompack_ai.surfaces.randompack",
}


def execute() -> None:
	if not frappe.db.exists("Module Def", MODULE):
		# install-app creates it; a migrate that runs before the app is
		# installed has nothing to re-home yet.
		return

	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.db.set_value("DocType", doctype, "module", MODULE, update_modified=False)

	for page in PAGES:
		if frappe.db.exists("Page", page):
			frappe.db.set_value("Page", page, "module", MODULE, update_modified=False)

	# Custom Fields / Property Setters the domain's provisioner created. The two
	# DocTypes name their target differently (`dt` vs `doc_type`).
	for doctype, target_column in (("Custom Field", "dt"), ("Property Setter", "doc_type")):
		if not frappe.db.has_column(doctype, "module"):
			continue
		frappe.db.sql(
			f"""UPDATE `tab{doctype}` SET module = %s
			    WHERE module = 'Friday Core' AND `{target_column}` IN %s""",
			(MODULE, DOCTYPES),
		)

	# Connector handler_module now points into this app.
	for old, new in HANDLER_MOVES.items():
		frappe.db.sql(
			"UPDATE `tabConnector` SET handler_module = %s WHERE handler_module = %s",
			(new, old),
		)
