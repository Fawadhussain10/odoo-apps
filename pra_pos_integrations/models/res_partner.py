from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    cnic = fields.Char(string="CNIC")
