from odoo import fields, models, api, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    strn_or_ntn = fields.Char(string="STRN")
    vat = fields.Char(related='partner_id.vat', string="NTN", readonly=False)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    cnic = fields.Char(string="CNIC")


class ProductTempExt(models.Model):
    _inherit = 'product.template'

    pct_code = fields.Char("PCT/HS Code", required=True, store=True)
    sale_type = fields.Char(string='Sale Type', required=True, store=True)
    sro_schedule = fields.Char(string='SRO Schedule No', store=True)
    sro_item = fields.Char(string='SRO Item No', store=True)
    fed_duty = fields.Many2one('account.tax', string='FED Duty', store=True)
    further_tax = fields.Many2one('account.tax', string='Further Tax', store=True)
    extra_tax = fields.Many2one('account.tax', string='Extra Tax', store=True)
    other_tax = fields.Char(string='Other Type Tax (e.g. Exempt)', store=True)
    withholding_tax = fields.Many2one('account.tax', string='Withholding Tax', store=True)


class ProductProductExt(models.Model):
    _inherit = 'product.product'

    pct_code = fields.Char("PCT/HS Code", required=True, store=True)
    sale_type = fields.Char(string='Sale Type', required=True, store=True)
    sro_schedule = fields.Char(string='SRO Schedule No', store=True)
    sro_item = fields.Char(string='SRO Item No', store=True)
    fed_duty = fields.Many2one('account.tax', string='FED Duty', store=True)
    further_tax = fields.Many2one('account.tax', string='Further Tax', store=True)
    extra_tax = fields.Many2one('account.tax', string='Extra Tax', store=True)
    other_tax = fields.Char(string='Other Type Tax (e.g. Exempt)', store=True)
    withholding_tax = fields.Many2one('account.tax', string='Withholding Tax', store=True)
