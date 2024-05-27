from odoo import api, fields, models, _


class OkrForm(models.Model):
    _name = 'okr.type'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "OKR Type"

    name = fields.Char(string='Name', required=True)