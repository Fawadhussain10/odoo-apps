# -*- coding: utf-8 -*-

from odoo import api, fields, models, SUPERUSER_ID, _


class ResCompany(models.Model):
    _inherit = "res.company"

    birthday_mail_template_id = fields.Many2one('mail.template', 'Birthday Wishes Template',
        help="This will set the default mail template for birthday wishes.")
    unique_gov_code = fields.Boolean('Unique Government Identity for Patient', help='Set this True if the Givernment Identity in patients should be unique.')

    #Call this method directly in case of dependcy issue like pb_certification (call in pb_hms_certification)
    def pb_create_sequence(self, name, code, prefix, padding=3):
        self.env['ir.sequence'].sudo().create({
            'name': self.name + " : " + name,
            'code': code,
            'padding': padding,
            'number_next': 1,
            'number_increment': 1,
            'prefix': prefix,
            'company_id': self.id,
            'pb_auto_create': False,
        })

    def pb_auto_create_sequences(self):
        sequences = self.env['ir.sequence'].search([('pb_auto_create','=',True)])
        for sequence in sequences:
            self.pb_create_sequence(name=sequence.name, code=sequence.code, prefix=sequence.prefix, padding=sequence.padding)

    #Auto create marked sequences in other HMS modules.
    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for record in res:
            record.pb_auto_create_sequences()
        return res

    @api.model
    def pb_get_blocking_data(self):
        return {"name": ""}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    birthday_mail_template_id = fields.Many2one('mail.template', 
        related='company_id.birthday_mail_template_id',
        string='Birthday Wishes Template',
        help="This will set the default mail template for birthday wishes.", readonly=False)
    unique_gov_code = fields.Boolean('Unique Government Identity for Patient',
         related='company_id.unique_gov_code', readonly=False,
         help='Set this True if the Givernment Identity in patients should be unique.')