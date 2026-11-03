from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    hrw_gratuity_days_first = fields.Float('Gratuity Days / Year (first 5 years)', default=21.0)
    hrw_gratuity_days_after = fields.Float('Gratuity Days / Year (after 5 years)', default=30.0)
    hrw_gratuity_min_years = fields.Float('Minimum Service for Gratuity (years)', default=1.0)
    hrw_month_days = fields.Float('Days per Month (daily rate basis)', default=30.0)
    hrw_archive_on_exit = fields.Boolean('Archive Employee When Exit Is Applied')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hrw_gratuity_days_first = fields.Float(related='company_id.hrw_gratuity_days_first', readonly=False)
    hrw_gratuity_days_after = fields.Float(related='company_id.hrw_gratuity_days_after', readonly=False)
    hrw_gratuity_min_years = fields.Float(related='company_id.hrw_gratuity_min_years', readonly=False)
    hrw_month_days = fields.Float(related='company_id.hrw_month_days', readonly=False)
    hrw_archive_on_exit = fields.Boolean(related='company_id.hrw_archive_on_exit', readonly=False)
