# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    pb_waba_verify_otp_template_id = fields.Many2one('pb.whatsapp.template', 'Verify OTP Whatsapp Template')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: