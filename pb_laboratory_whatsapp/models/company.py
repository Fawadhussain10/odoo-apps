# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    pb_laboratory_request_template_id = fields.Many2one('pb.whatsapp.template', 'Laboratory Request Template')
    pb_laboratory_result_template_id = fields.Many2one('pb.whatsapp.template', 'Laboratory Result Template')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: