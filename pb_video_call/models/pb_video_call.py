# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import math
import random
import uuid


class PbVideoCall(models.Model):
    _name = 'pb.video.call'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Video Call'
    _order = 'id desc'

    READONLY_STATES = {'done': [('readonly', True)], 'cancel': [('readonly', True)]}

    def _get_meeting_code(self):
        return str(uuid.uuid4()).replace('-','')

    def _get_meeting_password(self):
        string = '0123456789' #abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
        password = "" 
        length = len(string) 
        for i in range(4) : 
            password += string[math.floor(random.random() * length)] 
        return password

    def _get_meeting_link(self):
        """ NOTE: Update code from relavent module. """
        for rec in self:
            rec.meeting_link = ""

    name = fields.Char(string="Name")
    user_id = fields.Many2one('res.users', string='User', required=True, default=lambda self: self.env.user.id)
    partner_ids = fields.Many2many('res.partner', string='Participants')
    meeting_link = fields.Char(string='Meeting Link', compute="_get_meeting_link")
    meeting_code = fields.Char(string='Meeting Code', default=_get_meeting_code)
    subject = fields.Char(string='Subject', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('planned', 'Planned'),
        ('done', 'Done'),
        ('cancel', 'Canceled'),
    ], string='Meeting Status', index=True, default='draft')
    description = fields.Text("Description")
    date = fields.Datetime("Date", default=fields.Datetime.now)
    password = fields.Char(string='Meeting Password', default=_get_meeting_password)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('pb.video.call') or ''
        return super().create(vals_list)

    def unlink(self):
        for data in self:
            if data.state in ['done']:
                raise UserError(_('You can not delete record in done state'))
        return super(PbVideoCall, self).unlink()

    def create_call(self):
        pass

    def action_draft(self):
        self.state = 'draft'

    def action_plan(self):
        self.state = 'planned'

    def action_done(self):
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancel'

    def open_record(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_video_call.action_pb_video_call")
        action['views'] = [(self.env.ref('pb_video_call.pb_video_call_form').id, 'form')]
        action['domain'] = [('id', '=', self.id)]
        action['flags'] = {'initial_mode': 'edit'}
        return action

    def get_partner_ids(self):
        partner_ids = ','.join(map(lambda x: str(x.id), self.partner_ids))
        return partner_ids

    def action_send_invitaion(self):
        '''
        This function opens a window to compose an email, with the template message loaded by default
        '''
        self.ensure_one()
        template_id = self.env['ir.model.data']._xmlid_to_res_id('pb_video_call.pb_video_call_invitation', raise_if_not_found=False)
        try:
            compose_form_id = self.env['ir.model.data']._xmlid_to_res_id('mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = {
            'default_model': 'pb.video.call',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'force_email': True
        }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    video_call_id = fields.Many2one('pb.video.call', string='Video Call')
    video_call_link = fields.Char(related="video_call_id.meeting_link", string="Video Call Link")

    def create_video_call(self):
        video_call = self.env['pb.video.call'].create({
            'user_id': self.user_id and self.user_id.id or self.env.user.id,
            'partner_ids': [(6,0,self.partner_ids.ids)],
            'subject': self.name,
            'date': self.start,
            'state': 'planned',
        })
        self.video_call_id = video_call.id

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: