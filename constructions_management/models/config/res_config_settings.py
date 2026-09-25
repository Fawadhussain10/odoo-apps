from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    construction_rag_green_threshold = fields.Float(
        default=0.95, string="RAG Green Threshold (>=)",
        help="Variance / performance index at or above this value shows Green on dashboards.",
    )
    construction_rag_amber_threshold = fields.Float(
        default=0.85, string="RAG Amber Threshold (>=)",
        help="Below Green and at or above this value shows Amber; below this shows Red.",
    )
    construction_wip_material_account_id = fields.Many2one("account.account", string="Default Contract WIP Account")
    construction_wip_cost_account_id = fields.Many2one("account.account", string="Default Contract Cost Account")
    construction_wip_revenue_account_id = fields.Many2one("account.account", string="Default Contract Revenue Account")
    construction_progress_billing_account_id = fields.Many2one("account.account", string="Default Progress Billing (Contract Liability) Account")
    construction_retention_account_id = fields.Many2one("account.account", string="Default Retention Payable/Receivable Account")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    construction_rag_green_threshold = fields.Float(related="company_id.construction_rag_green_threshold", readonly=False)
    construction_rag_amber_threshold = fields.Float(related="company_id.construction_rag_amber_threshold", readonly=False)
    construction_wip_material_account_id = fields.Many2one(related="company_id.construction_wip_material_account_id", readonly=False)
    construction_wip_cost_account_id = fields.Many2one(related="company_id.construction_wip_cost_account_id", readonly=False)
    construction_wip_revenue_account_id = fields.Many2one(related="company_id.construction_wip_revenue_account_id", readonly=False)
    construction_progress_billing_account_id = fields.Many2one(related="company_id.construction_progress_billing_account_id", readonly=False)
    construction_retention_account_id = fields.Many2one(related="company_id.construction_retention_account_id", readonly=False)
