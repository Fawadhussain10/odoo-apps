#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for record in res:
            record.pb_create_sequence(name='PB Video Call', code='pb.video.call', prefix='VC')
        return res


class HmsAppointment(models.Model):
    _inherit = 'hms.appointment'

    video_call_id = fields.Many2one('pb.video.call', string='Video Call')
    video_call_link = fields.Char(related="video_call_id.meeting_link", string="Video Call Link", readonly=True)

    def appointment_confirm(self):
        super(HmsAppointment, self).appointment_confirm()
        if self.is_video_call:
            self.create_video_call()
            template = self.env.ref('pb_hms_video_call.pb_video_call_invitaion')
            template.sudo().send_mail(self.id, raise_exception=False)

    def create_video_call(self):
        video_call = self.env['pb.video.call'].create({
            'user_id': self.env.user.id,
            'partner_ids': [(6,0,[self.patient_id.partner_id.id, self.physician_id.partner_id.id])],
            'subject': _('Video Consultation for Appointment ') + self.name,
            'date': self.date,
            'state': 'planned',
            'password': self.name,
            'appointment_id': self.id,
        })
        self.video_call_id = video_call.id

    def consultation_done(self):
        if self.video_call_id:
            self.video_call_id.action_done()
        return super(HmsAppointment, self).consultation_done()

    def get_partner_ids(self):
        partner_ids = ','.join(map(lambda x: str(x.id), [self.patient_id.partner_id,self.physician_id.partner_id]))
        return partner_ids

    def action_send_invitaion(self):
        '''
        This function opens a window to compose an email, with the template message loaded by default
        '''
        self.ensure_one()
        template_id = self.env['ir.model.data']._xmlid_to_res_id('pb_hms_video_call.pb_video_call_invitaion', raise_if_not_found=False)
        ctx = {
            'default_model': 'hms.appointment',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'force_email': True
        }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

