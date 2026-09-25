import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DOCUMENT_STATE_SELECTION = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("superseded", "Superseded"),
]

# Fields that remain writable even after a document has been superseded by a later revision -
# mirrors the shape of construction.boq.line's LIVE_TRACKING_FIELDS / _check_baseline_editable
# immutability guard in models/boq/boq.py, adapted to this model's much simpler needs.
IMMUTABLE_EXEMPT_FIELDS = {"is_superseded", "state"}


class ConstructionDocument(models.Model):
    _name = "construction.document"
    _description = "Construction Document Register"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False)
    document_type_id = fields.Many2one("construction.document.type", required=True, tracking=True)
    project_id = fields.Many2one("project.project", required=True, ondelete="cascade", index=True, tracking=True)
    wbs_id = fields.Many2one("construction.wbs", string="WBS / Phase", domain="[('project_id', '=', project_id)]")
    boq_line_id = fields.Many2one(
        "construction.boq.line", string="BOQ Line",
        domain="[('project_id', '=', project_id), ('display_type', '=', False)]",
    )
    partner_id = fields.Many2one("res.partner", string="Vendor / Customer")
    responsible_id = fields.Many2one("res.users", string="Responsible", default=lambda self: self.env.user)
    revision = fields.Char(default="Rev 0")
    is_superseded = fields.Boolean(default=False, copy=False)
    previous_revision_id = fields.Many2one("construction.document", string="Previous Revision", readonly=True, copy=False)
    state = fields.Selection(DOCUMENT_STATE_SELECTION, default="draft", tracking=True, copy=False)
    date_issued = fields.Date()
    date_response_due = fields.Date()
    date_effective = fields.Date()
    company_id = fields.Many2one(related="project_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                sequence = False
                if vals.get("document_type_id"):
                    doc_type = self.env["construction.document.type"].browse(vals["document_type_id"])
                    sequence = doc_type.sequence_id
                if sequence:
                    vals["name"] = sequence.next_by_id() or "New"
                else:
                    vals["name"] = self.env["ir.sequence"].next_by_code("construction.document") or "New"
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - IMMUTABLE_EXEMPT_FIELDS:
            for rec in self:
                if rec.is_superseded:
                    raise UserError(_(
                        "Document '%(name)s' has been superseded by a later revision and can no longer be edited.",
                        name=rec.name,
                    ))
        return super().write(vals)

    def action_submit(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "submitted"})

    def action_approve(self):
        for rec in self.filtered(lambda r: r.state == "submitted"):
            vals = {"state": "approved"}
            if not rec.date_effective:
                vals["date_effective"] = fields.Date.context_today(rec)
            rec.write(vals)

    def action_reject(self):
        self.filtered(lambda r: r.state == "submitted").write({"state": "rejected"})

    def action_create_revision(self):
        """Clones the record onto a new revision, marking self superseded/read-only - mirrors
        construction.boq.action_create_revision's copy() pattern in models/boq/boq.py, without
        the baseline-approval-locking complexity since a document register entry only needs the
        supersede flag."""
        self.ensure_one()
        if self.is_superseded:
            raise UserError(_("This document is already superseded; create the next revision from its latest version instead."))
        new_doc = self.copy({
            "name": "New",
            "revision": self._get_next_revision_label(),
            "previous_revision_id": self.id,
            "state": "draft",
            "is_superseded": False,
            "date_issued": False,
            "date_response_due": False,
            "date_effective": False,
        })
        self.write({"is_superseded": True, "state": "superseded"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.document",
            "res_id": new_doc.id,
            "view_mode": "form",
            "target": "current",
        }

    def _get_next_revision_label(self):
        """Best-effort revision bump (e.g. "Rev 0" -> "Rev 1", "Rev A" -> "Rev B"); falls back to
        repeating the same label for the user to edit manually if no trailing number/letter is
        found. Documented simplification - see report item 7."""
        self.ensure_one()
        rev = (self.revision or "").strip()
        match_num = re.match(r"^(.*?)(\d+)$", rev)
        if match_num:
            prefix, num = match_num.groups()
            return f"{prefix}{int(num) + 1}"
        match_letter = re.match(r"^(.*?)([A-Za-z])$", rev)
        if match_letter:
            prefix, letter = match_letter.groups()
            return f"{prefix}{chr(ord(letter.upper()) + 1)}"
        return rev
