from odoo import api, fields, models


class ConstructionWbsEvm(models.Model):
    """Earned Value Management fields (FDD S12), added via _inherit rather than editing
    models/wbs.py directly (that file is owned elsewhere in this build).

    Store status is deliberate, not an oversight:
    - bac/pv/ev have a genuine dependency chain through real relational fields
      (boq_line_ids.revised_amount, progress_schedule, progress_physical) so store=True is safe
      and performant.
    - ac and everything derived from it (cv, sv, cpi, spi, eac, etc, vac, rag_status) ultimately
      source cost data from account.analytic.line, which has no relational path back to
      construction.wbs/project.project. A store=True compute here would silently cache a stale
      number forever (the exact bug class the build brief warns about), so these are left
      non-stored and always recompute live on read - see also models/wip/wip_period.py for the
      same reasoning applied to current_additions/completion_pct.
    """

    _inherit = "construction.wbs"

    bac = fields.Monetary(string="BAC (Budget at Completion)", compute="_compute_bac", store=True,
                           currency_field="currency_id",
                           help="Sum of revised_amount across this WBS's BOQ lines (revised budget baseline).")
    pv = fields.Monetary(string="PV (Planned Value)", compute="_compute_pv", store=True, currency_field="currency_id",
                          help="Simplified time-phasing: progress_schedule% x BAC. A true S-curve "
                               "time-phased budget is out of scope for this build - documented simplification.")
    ev = fields.Monetary(string="EV (Earned Value)", compute="_compute_ev", store=True, currency_field="currency_id",
                          help="progress_physical% x BAC.")
    ac = fields.Monetary(string="AC (Actual Cost)", compute="_compute_ac", currency_field="currency_id",
                          help="Actual eligible cost for this WBS. account.analytic.line does not carry WBS "
                               "granularity, so this is the project's total actual cost (from analytic lines "
                               "against the project's analytic account) allocated to this WBS proportionally by "
                               "its BAC share of total project BAC - documented simplification per the build brief.")

    cv = fields.Monetary(string="CV (Cost Variance)", compute="_compute_variances", currency_field="currency_id")
    sv = fields.Monetary(string="SV (Schedule Variance)", compute="_compute_variances", currency_field="currency_id")
    cpi = fields.Float(string="CPI (Cost Performance Index)", compute="_compute_indices",
                        help="EV / AC. Zero-guarded: if AC is 0, CPI reports 1.0 (assume on-budget until cost is "
                             "actually incurred, rather than reporting an undefined/zero index) - documented choice.")
    spi = fields.Float(string="SPI (Schedule Performance Index)", compute="_compute_indices",
                        help="EV / PV. Zero-guarded: if PV is 0 (e.g. no schedule dates set yet), SPI reports 1.0.")
    eac = fields.Monetary(string="EAC (Estimate at Completion)", compute="_compute_forecast", currency_field="currency_id",
                           help="BAC / CPI. Zero-guarded: if CPI is 0, EAC falls back to BAC.")
    etc = fields.Monetary(string="ETC (Estimate to Complete)", compute="_compute_forecast", currency_field="currency_id",
                           help="EAC - AC.")
    vac = fields.Monetary(string="VAC (Variance at Completion)", compute="_compute_forecast", currency_field="currency_id",
                           help="BAC - EAC.")
    rag_status = fields.Selection(
        [("green", "Green"), ("amber", "Amber"), ("red", "Red")],
        string="RAG Status", compute="_compute_rag_status",
        help="Based on the lower of CPI/SPI against company thresholds "
             "(construction_rag_green_threshold / construction_rag_amber_threshold).",
    )

    @api.depends("boq_line_ids.revised_amount", "boq_line_ids.display_type")
    def _compute_bac(self):
        for rec in self:
            lines = rec.boq_line_ids.filtered(lambda l: not l.display_type)
            rec.bac = sum(lines.mapped("revised_amount"))

    @api.depends("progress_schedule", "bac")
    def _compute_pv(self):
        for rec in self:
            rec.pv = (rec.progress_schedule or 0.0) / 100.0 * rec.bac

    @api.depends("progress_physical", "bac")
    def _compute_ev(self):
        for rec in self:
            rec.ev = (rec.progress_physical or 0.0) / 100.0 * rec.bac

    def _get_project_actual_cost(self, project):
        """Sum of account.analytic.line cost postings (amount < 0) against the project's analytic
        account - the same source used by models/wip/wip_period.py. Not cached on self; called
        once per project encountered in _compute_ac below."""
        if not project or not project.account_id:
            return 0.0
        lines = self.env["account.analytic.line"].search([
            ("account_id", "=", project.account_id.id), ("amount", "<", 0.0),
        ])
        return -sum(lines.mapped("amount"))

    @api.depends("bac", "project_id")
    def _compute_ac(self):
        project_actual_cost_cache = {}
        project_bac_cache = {}
        for rec in self:
            project = rec.project_id
            if not project:
                rec.ac = 0.0
                continue
            if project.id not in project_actual_cost_cache:
                project_actual_cost_cache[project.id] = self._get_project_actual_cost(project)
                project_bac_cache[project.id] = sum(project.wbs_ids.mapped("bac"))
            project_actual_cost = project_actual_cost_cache[project.id]
            project_bac = project_bac_cache[project.id]
            share = (rec.bac / project_bac) if project_bac else 0.0
            rec.ac = project_actual_cost * share

    @api.depends("ev", "ac", "pv")
    def _compute_variances(self):
        for rec in self:
            rec.cv = rec.ev - rec.ac
            rec.sv = rec.ev - rec.pv

    @api.depends("ev", "ac", "pv")
    def _compute_indices(self):
        for rec in self:
            rec.cpi = (rec.ev / rec.ac) if rec.ac else 1.0
            rec.spi = (rec.ev / rec.pv) if rec.pv else 1.0

    @api.depends("bac", "ac", "cpi")
    def _compute_forecast(self):
        for rec in self:
            rec.eac = (rec.bac / rec.cpi) if rec.cpi else rec.bac
            rec.etc = rec.eac - rec.ac
            rec.vac = rec.bac - rec.eac

    @api.depends("cpi", "spi")
    def _compute_rag_status(self):
        for rec in self:
            green = rec.env.company.construction_rag_green_threshold or 0.95
            amber = rec.env.company.construction_rag_amber_threshold or 0.85
            worst = min(rec.cpi, rec.spi)
            if worst >= green:
                rec.rag_status = "green"
            elif worst >= amber:
                rec.rag_status = "amber"
            else:
                rec.rag_status = "red"

    # -- Financial/Billing progress (FDD 4): progress_financial was a plain, uncomputed Float on
    # construction.wbs; progress_billing likewise. Both are turned into computes here (same
    # override-a-plain-field-via-_inherit pattern already used for boq.line.consumed_qty/
    # certified_qty elsewhere in this build) since neither was claimed by another stage.
    progress_financial = fields.Float(compute="_compute_progress_financial",
                                       help="Actual eligible cost incurred (AC) / latest estimated total eligible "
                                            "cost (EAC, falling back to BAC when AC is 0).")
    progress_billing = fields.Float(compute="_compute_progress_billing",
                                     help="This WBS's certified value (via BOQ lines' certified_qty x rate) / BAC.")

    @api.depends("ac", "eac")
    def _compute_progress_financial(self):
        for rec in self:
            rec.progress_financial = round(100.0 * rec.ac / rec.eac, 2) if rec.eac else 0.0

    @api.depends("boq_line_ids.certified_qty", "boq_line_ids.customer_rate", "boq_line_ids.revised_net_qty", "boq_line_ids.display_type")
    def _compute_progress_billing(self):
        # Billing progress compares against the customer contract value (customer_rate), not the
        # cost budget (bac uses budget rate) - a different denominator on purpose.
        for rec in self:
            lines = rec.boq_line_ids.filtered(lambda l: not l.display_type)
            revised_contract_value = sum(line.revised_net_qty * line.customer_rate for line in lines)
            certified_value = sum(line.certified_qty * line.customer_rate for line in lines)
            rec.progress_billing = round(100.0 * certified_value / revised_contract_value, 2) if revised_contract_value else 0.0


class ProjectProjectEvm(models.Model):
    """Project-level EVM rollups (sum of active WBS-level figures); low-effort addition per the
    build brief ("consider adding project-level rollups... if it's low-effort")."""

    _inherit = "project.project"

    evm_bac = fields.Monetary(string="BAC", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_pv = fields.Monetary(string="PV", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_ev = fields.Monetary(string="EV", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_ac = fields.Monetary(string="AC", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_cv = fields.Monetary(string="CV", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_sv = fields.Monetary(string="SV", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_cpi = fields.Float(string="CPI", compute="_compute_evm_rollup")
    evm_spi = fields.Float(string="SPI", compute="_compute_evm_rollup")
    evm_eac = fields.Monetary(string="EAC", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_etc = fields.Monetary(string="ETC", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_vac = fields.Monetary(string="VAC", compute="_compute_evm_rollup", currency_field="currency_id")
    evm_rag_status = fields.Selection(
        [("green", "Green"), ("amber", "Amber"), ("red", "Red")],
        string="RAG Status", compute="_compute_evm_rollup",
    )

    @api.depends("wbs_ids.bac", "wbs_ids.pv", "wbs_ids.ev", "wbs_ids.ac")
    def _compute_evm_rollup(self):
        for rec in self:
            wbs = rec.wbs_ids
            rec.evm_bac = sum(wbs.mapped("bac"))
            rec.evm_pv = sum(wbs.mapped("pv"))
            rec.evm_ev = sum(wbs.mapped("ev"))
            rec.evm_ac = sum(wbs.mapped("ac"))
            rec.evm_cv = rec.evm_ev - rec.evm_ac
            rec.evm_sv = rec.evm_ev - rec.evm_pv
            rec.evm_cpi = (rec.evm_ev / rec.evm_ac) if rec.evm_ac else 1.0
            rec.evm_spi = (rec.evm_ev / rec.evm_pv) if rec.evm_pv else 1.0
            rec.evm_eac = (rec.evm_bac / rec.evm_cpi) if rec.evm_cpi else rec.evm_bac
            rec.evm_etc = rec.evm_eac - rec.evm_ac
            rec.evm_vac = rec.evm_bac - rec.evm_eac
            green = rec.company_id.construction_rag_green_threshold if rec.company_id else 0.95
            amber = rec.company_id.construction_rag_amber_threshold if rec.company_id else 0.85
            worst = min(rec.evm_cpi, rec.evm_spi)
            if worst >= (green or 0.95):
                rec.evm_rag_status = "green"
            elif worst >= (amber or 0.85):
                rec.evm_rag_status = "amber"
            else:
                rec.evm_rag_status = "red"
