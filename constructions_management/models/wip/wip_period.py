import calendar

from odoo import _, api, fields, models
from odoo.exceptions import UserError

WIP_PERIOD_STATE_SELECTION = [
    ("open", "Open"),
    ("frozen", "Cut-off Frozen"),
    ("calculated", "Calculated"),
    ("reviewed", "Project Accountant Reviewed"),
    ("approved", "Finance Approved"),
    ("posted", "Posted"),
    ("locked", "Locked"),
]


class ConstructionWipPeriod(models.Model):
    _name = "construction.wip.period"
    _description = "Construction WIP Period (Cost-to-Cost Revenue Recognition)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, period_month desc"

    name = fields.Char(default="New", copy=False)
    project_id = fields.Many2one("project.project", required=True, ondelete="restrict", index=True, tracking=True)
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True)
    # Design choice (documented in build report): stored as the 1st of the month so a simple
    # Date field can use standard date-range domains against account.analytic.line/other models
    # without a separate parsing step; the UI can format it as "MMMM yyyy".
    period_month = fields.Date(required=True, tracking=True, help="Any date within the accounting month; normalized to the 1st of the month.")
    recognition_method = fields.Selection(related="project_id.billing_policy", string="Recognition Method",
                                           help="Reuses project.project.billing_policy rather than duplicating a similar selection here.")
    state = fields.Selection(WIP_PERIOD_STATE_SELECTION, default="open", tracking=True, copy=False)

    # -- Cost side (WIP ledger) --
    opening_wip = fields.Monetary(currency_field="currency_id", copy=False,
                                   help="Snapshot of the previous period's Closing WIP; set by 'Calculate'.")
    current_additions = fields.Monetary(compute="_compute_current_additions", currency_field="currency_id",
                                         help="Actual eligible cost incurred this period, from account.analytic.line "
                                              "postings against the project's analytic account (the Odoo-standard "
                                              "single source of truth for 'all costs posted against this project'). "
                                              "Deliberately NOT stored: account.analytic.line has no relational path "
                                              "back to this model, so a store=True compute here would silently go "
                                              "stale (exactly the bug class flagged in the build brief) once new "
                                              "costs post after the first computation. Kept always-live instead; "
                                              "'Calculate' reads this live value once and snapshots it into the real "
                                              "stored field recognized_cost, which IS the frozen accounting figure.")
    recognized_cost = fields.Monetary(currency_field="currency_id", copy=False,
                                       help="Cost of work recognized to the P&L this period; set by 'Calculate' "
                                            "(defaults to Current Additions under the cost-to-cost method - see "
                                            "build report for the reasoning) and adjustable by the project "
                                            "accountant before Finance approval.")
    closing_wip = fields.Monetary(compute="_compute_closing_wip", store=True, currency_field="currency_id",
                                   help="Opening WIP + Current Additions - Recognized Cost; carried forward as next period's Opening WIP.")

    # -- Revenue side (contract asset / contract liability) --
    completion_pct = fields.Float(compute="_compute_completion_pct", string="Completion % (Cost-to-Cost)",
                                   help="Cumulative eligible cost incurred to date / latest estimated total eligible "
                                        "cost (EAC, falling back to the current baseline BOQ's revised total). Not "
                                        "stored, same staleness reasoning as current_additions above.")
    recognized_revenue = fields.Monetary(currency_field="currency_id", copy=False,
                                          help="Incremental revenue recognized this period; set by 'Calculate' as "
                                               "(cumulative completion % x revised contract value) minus revenue "
                                               "already recognized in prior periods.")
    billed_revenue = fields.Monetary(currency_field="currency_id", copy=False,
                                      help="Sum of Progress Certificates' Net Certificate dated within this period "
                                           "and Approved/Invoiced; set by 'Calculate'.")
    unbilled_work = fields.Monetary(compute="_compute_billing_positions", store=True, currency_field="currency_id")
    billing_in_excess = fields.Monetary(compute="_compute_billing_positions", store=True, currency_field="currency_id",
                                         help="Contract Liability: billed_revenue - recognized_revenue, floored at 0.")
    contract_asset = fields.Monetary(compute="_compute_billing_positions", store=True, currency_field="currency_id",
                                      help="Contract Asset: recognized_revenue - billed_revenue, floored at 0.")

    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)
    line_ids = fields.One2many("construction.wip.period.line", "wip_period_id", string="WBS Breakdown", copy=False)

    _sql_period_uniq = models.Constraint(
        "unique(project_id, period_month)",
        "Only one WIP period may exist per project per month.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.wip.period") or "New"
            self._normalize_period_month_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - {"state", "move_id", "message_main_attachment_id"} and any(rec.state == "locked" for rec in self):
            raise UserError(_("Locked WIP periods cannot be modified."))
        self._normalize_period_month_vals(vals)
        return super().write(vals)

    def unlink(self):
        if any(rec.state in ("posted", "locked") for rec in self):
            raise UserError(_("Posted or locked WIP periods cannot be deleted."))
        return super().unlink()

    @api.model
    def _normalize_period_month_vals(self, vals):
        if vals.get("period_month"):
            period_month = fields.Date.to_date(vals["period_month"])
            if period_month:
                vals["period_month"] = period_month.replace(day=1)

    def _period_bounds(self, period_month):
        date_from = period_month.replace(day=1)
        last_day = calendar.monthrange(date_from.year, date_from.month)[1]
        date_to = date_from.replace(day=last_day)
        return date_from, date_to

    def _get_previous_periods(self):
        self.ensure_one()
        if not self.project_id or not self.period_month:
            return self.browse()
        return self.search([
            ("project_id", "=", self.project_id.id),
            ("period_month", "<", self.period_month),
            ("id", "!=", self.id),
        ], order="period_month")

    def _get_revised_contract_value(self):
        self.ensure_one()
        if not self.project_id:
            return 0.0
        return (self.project_id.original_contract_value or 0.0) + (self.project_id.total_approved_variation_revenue or 0.0)

    def _get_latest_estimated_total_eligible_cost(self):
        """EAC (sum of construction.wbs EAC, see models/wip/evm.py) if available/non-zero, else the
        current baseline BOQ's revised total for the project. See build report for the fallback rationale."""
        self.ensure_one()
        project = self.project_id
        if not project:
            return 0.0
        wbs_records = project.wbs_ids
        if wbs_records and "eac" in wbs_records._fields:
            eac_total = sum(wbs_records.mapped("eac"))
            if eac_total:
                return eac_total
        boq_lines = self.env["construction.boq.line"].search([
            ("project_id", "=", project.id), ("display_type", "=", False), ("boq_id.is_current", "=", True),
        ])
        return sum(boq_lines.mapped("revised_amount"))

    @api.depends("project_id", "period_month")
    def _compute_current_additions(self):
        AnalyticLine = self.env["account.analytic.line"]
        for rec in self:
            account = rec.project_id.account_id if rec.project_id else False
            if not account or not rec.period_month:
                rec.current_additions = 0.0
                continue
            date_from, date_to = rec._period_bounds(rec.period_month)
            lines = AnalyticLine.search([
                ("account_id", "=", account.id),
                ("amount", "<", 0.0),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ])
            rec.current_additions = -sum(lines.mapped("amount"))

    @api.depends("project_id", "period_month")
    def _compute_completion_pct(self):
        AnalyticLine = self.env["account.analytic.line"]
        for rec in self:
            account = rec.project_id.account_id if rec.project_id else False
            if not account or not rec.period_month:
                rec.completion_pct = 0.0
                continue
            _date_from, date_to = rec._period_bounds(rec.period_month)
            lines = AnalyticLine.search([
                ("account_id", "=", account.id), ("amount", "<", 0.0), ("date", "<=", date_to),
            ])
            cumulative_cost = -sum(lines.mapped("amount"))
            eac = rec._get_latest_estimated_total_eligible_cost()
            rec.completion_pct = round(100.0 * cumulative_cost / eac, 2) if eac else 0.0

    @api.depends("opening_wip", "current_additions", "recognized_cost")
    def _compute_closing_wip(self):
        for rec in self:
            rec.closing_wip = rec.opening_wip + rec.current_additions - rec.recognized_cost

    @api.depends("recognized_revenue", "billed_revenue")
    def _compute_billing_positions(self):
        for rec in self:
            rec.unbilled_work = rec.recognized_revenue - rec.billed_revenue
            rec.billing_in_excess = max(rec.billed_revenue - rec.recognized_revenue, 0.0)
            rec.contract_asset = max(rec.recognized_revenue - rec.billed_revenue, 0.0)

    # -- Workflow --
    def action_freeze(self):
        self.filtered(lambda r: r.state == "open").write({"state": "frozen"})

    def action_calculate(self):
        for rec in self.filtered(lambda r: r.state == "frozen"):
            previous = rec._get_previous_periods()
            last_period = previous[-1:] if previous else previous
            rec.opening_wip = last_period.closing_wip if last_period else 0.0
            # Cost-to-cost method: cost of revenue is recognized as it is incurred (this is what
            # defines the cost-to-cost % complete measure), so recognized_cost defaults to the
            # period's actual cost additions. Left as a plain, project-accountant-editable field
            # (not a live compute) so it can be adjusted for ineligible costs before Finance
            # approval - see build report point 7.
            rec.recognized_cost = rec.current_additions
            prior_recognized_revenue = sum(previous.mapped("recognized_revenue"))
            cumulative_target = (rec.completion_pct / 100.0) * rec._get_revised_contract_value()
            rec.recognized_revenue = cumulative_target - prior_recognized_revenue
            date_from, date_to = rec._period_bounds(rec.period_month)
            certs = self.env["construction.progress.certificate"].search([
                ("project_id", "=", rec.project_id.id),
                ("certificate_date", ">=", date_from),
                ("certificate_date", "<=", date_to),
                ("state", "in", ("approved", "invoiced")),
            ])
            rec.billed_revenue = sum(certs.mapped("net_certificate"))
            rec.state = "calculated"
            rec._recompute_lines()

    def _recompute_lines(self):
        self.ensure_one()
        Line = self.env["construction.wip.period.line"]
        CertLine = self.env["construction.progress.certificate.line"]
        existing = {line.wbs_id.id: line for line in self.line_ids}
        wbs_records = self.project_id.wbs_ids
        project_bac = sum(wbs_records.mapped("bac")) if wbs_records and "bac" in wbs_records._fields else 0.0
        date_from, date_to = self._period_bounds(self.period_month)
        seen_wbs_ids = set()
        for wbs in wbs_records:
            seen_wbs_ids.add(wbs.id)
            share = (wbs.bac / project_bac) if project_bac else 0.0
            billed_lines = CertLine.search([
                ("boq_line_id.wbs_id", "=", wbs.id),
                ("certificate_id.certificate_date", ">=", date_from),
                ("certificate_id.certificate_date", "<=", date_to),
                ("certificate_id.state", "in", ("approved", "invoiced")),
            ])
            vals = {
                "wip_period_id": self.id,
                "wbs_id": wbs.id,
                "opening_wip": self.opening_wip * share,
                "current_additions": self.current_additions * share,
                "recognized_cost": self.recognized_cost * share,
                "recognized_revenue": self.recognized_revenue * share,
                "billed_revenue": sum(billed_lines.mapped("amount")),
            }
            if wbs.id in existing:
                existing[wbs.id].write(vals)
            else:
                Line.create(vals)
        stale = self.line_ids.filtered(lambda l: l.wbs_id.id not in seen_wbs_ids)
        stale.unlink()

    def action_review(self):
        self.filtered(lambda r: r.state == "calculated").write({"state": "reviewed"})

    def action_approve(self):
        # Finance-only conceptually: gate the button in the view with
        # groups="constructions_management.group_construction_finance" (no new security group built).
        self.filtered(lambda r: r.state == "reviewed").write({"state": "approved"})

    def action_post(self):
        for rec in self.filtered(lambda r: r.state == "approved"):
            company = rec.project_id.company_id or rec.env.company
            cost_account = company.construction_wip_cost_account_id
            wip_account = company.construction_wip_material_account_id
            revenue_account = company.construction_wip_revenue_account_id
            billing_account = company.construction_progress_billing_account_id
            if not (cost_account and wip_account and revenue_account and billing_account):
                raise UserError(_(
                    "Configure the Contract WIP, Contract Cost, Contract Revenue and Progress "
                    "Billing accounts in Construction Settings before posting a WIP period."
                ))
            journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", company.id)], limit=1
            )
            if not journal:
                raise UserError(_("No General journal found for company %s.", company.name))
            analytic_account = rec.project_id.account_id
            analytic_distribution = {str(analytic_account.id): 100.0} if analytic_account else False
            move_lines = []
            if rec.recognized_cost:
                move_lines += [
                    (0, 0, {
                        "name": _("%(name)s - Contract Cost Recognized", name=rec.name),
                        "account_id": cost_account.id, "debit": rec.recognized_cost, "credit": 0.0,
                        "analytic_distribution": analytic_distribution,
                    }),
                    (0, 0, {
                        "name": _("%(name)s - Contract WIP Relief", name=rec.name),
                        "account_id": wip_account.id, "debit": 0.0, "credit": rec.recognized_cost,
                        "analytic_distribution": analytic_distribution,
                    }),
                ]
            if rec.recognized_revenue:
                # Dr/Cr the same Progress Billing (contract liability/asset) control account used by
                # construction.progress.certificate's customer invoice, so this entry nets against
                # actual billings instead of double-recognizing revenue - see build report point 7.
                move_lines += [
                    (0, 0, {
                        "name": _("%(name)s - Progress Billing / Contract Asset Movement", name=rec.name),
                        "account_id": billing_account.id, "debit": rec.recognized_revenue, "credit": 0.0,
                        "analytic_distribution": analytic_distribution,
                    }),
                    (0, 0, {
                        "name": _("%(name)s - Contract Revenue Recognized", name=rec.name),
                        "account_id": revenue_account.id, "debit": 0.0, "credit": rec.recognized_revenue,
                        "analytic_distribution": analytic_distribution,
                    }),
                ]
            if not move_lines:
                raise UserError(_("Nothing to post: Recognized Cost and Recognized Revenue are both zero."))
            move = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": rec._period_bounds(rec.period_month)[1],
                "ref": rec.name,
                "line_ids": move_lines,
            })
            move.action_post()
            rec.write({"move_id": move.id, "state": "posted"})

    def action_lock(self):
        self.filtered(lambda r: r.state == "posted").write({"state": "locked"})


class ConstructionWipPeriodLine(models.Model):
    _name = "construction.wip.period.line"
    _description = "Construction WIP Period - WBS Breakdown"
    _order = "wbs_id"

    wip_period_id = fields.Many2one("construction.wip.period", required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(related="wip_period_id.project_id", store=True)
    currency_id = fields.Many2one(related="wip_period_id.currency_id", store=True)
    wbs_id = fields.Many2one("construction.wbs", required=True, ondelete="restrict",
                              domain="[('project_id', '=', project_id)]")

    opening_wip = fields.Monetary(currency_field="currency_id")
    current_additions = fields.Monetary(currency_field="currency_id",
                                         help="Allocated from the period's project-level Current Additions by this "
                                              "WBS's share of total project BAC (account.analytic.line does not "
                                              "carry WBS granularity) - documented simplification, see build report.")
    recognized_cost = fields.Monetary(currency_field="currency_id")
    closing_wip = fields.Monetary(compute="_compute_closing_wip", store=True, currency_field="currency_id")

    completion_pct = fields.Float(related="wbs_id.progress_financial")
    recognized_revenue = fields.Monetary(currency_field="currency_id", help="Allocated by BAC share, like Current Additions.")
    billed_revenue = fields.Monetary(currency_field="currency_id",
                                      help="Actual (not allocated) sum of Progress Certificate lines whose BOQ line "
                                           "belongs to this WBS, dated in this period and Approved/Invoiced.")
    unbilled_work = fields.Monetary(compute="_compute_billing_positions", store=True, currency_field="currency_id")
    billing_in_excess = fields.Monetary(compute="_compute_billing_positions", store=True, currency_field="currency_id")
    contract_asset = fields.Monetary(compute="_compute_billing_positions", store=True, currency_field="currency_id")

    _sql_line_uniq = models.Constraint(
        "unique(wip_period_id, wbs_id)",
        "A WIP period can only have one breakdown line per WBS.",
    )

    @api.depends("opening_wip", "current_additions", "recognized_cost")
    def _compute_closing_wip(self):
        for rec in self:
            rec.closing_wip = rec.opening_wip + rec.current_additions - rec.recognized_cost

    @api.depends("recognized_revenue", "billed_revenue")
    def _compute_billing_positions(self):
        for rec in self:
            rec.unbilled_work = rec.recognized_revenue - rec.billed_revenue
            rec.billing_in_excess = max(rec.billed_revenue - rec.recognized_revenue, 0.0)
            rec.contract_asset = max(rec.recognized_revenue - rec.billed_revenue, 0.0)
