# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date, datetime, timedelta
import werkzeug

class Appointment(models.Model):
    _inherit = 'hms.appointment'

    survey_start_url = fields.Char(string='Survey Start Link', copy=False)
    survey_invite_id = fields.Many2one('survey.user_input', string='Feedback Survey Invite', readonly=True)
    survey_status = fields.Selection(related="survey_invite_id.state", readonly=True, store=True, string="Survey Status")

    def appointment_done(self):
        if self.sudo().company_id.survey_id:
            invite = self.sudo().company_id.survey_id._create_answer(partner=self.patient_id.partner_id, check_attempts=False)
            self.survey_invite_id = invite.id
            self.survey_start_url = werkzeug.urls.url_join(invite.survey_id.get_base_url(), invite.get_start_url())
            template = self.env.ref('pb_hms_survey.pb_hms_survey_email')
            template.sudo().send_mail(self.id, raise_exception=False)
        return super(Appointment, self).appointment_done()

    def survey_get_partner_id(self):
        return self.patient_id.partner_id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: