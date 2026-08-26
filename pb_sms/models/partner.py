# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import math, random


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner','pb.sms.mixin']

    def _count_sms(self):
        Announcement = self.env['pb.sms.announcement']
        for rec in self:
            rec.sms_count = len(rec.sms_ids.ids)
            rec.announcement_count = Announcement.search_count([('partner_ids','in',rec.id)])

    sms_ids = fields.One2many('pb.sms', 'partner_id', string='SMS')
    sms_count = fields.Integer(compute="_count_sms", string="#SMS Count")
    announcement_count = fields.Integer(compute="_count_sms", string="#SMS Announcement Count")
    pb_otp_sms = fields.Char(string="OTP SMS", copy=False)
    generated_otp_sms = fields.Char(string="Generated OTP SMS")
    verified_mobile_sms = fields.Boolean(string="Verified SMS", help="The mobile number is verified using the SMS message", default=False)

    def action_send_otp_sms(self):
        self.generateotp_sms()

        for rec in self:
            verify_otp_msg_sms_template_id = rec.sudo().company_id.verify_otp_msg_sms_template_id or self.env.user.sudo().company_id.verify_otp_msg_sms_template_id
            if verify_otp_msg_sms_template_id:
                if rec.phone:
                    try:
                        rendered = self.env['mail.render.mixin']._render_template(verify_otp_msg_sms_template_id.message, rec._name, [rec.id])
                        msg = rendered[rec.id]
                    except:
                       raise UserError(_("Configured Message fromat is wrong please contact administrator correct it first."))
                    self.with_context(force_send=True).create_sms(msg, rec.phone, False, res_model='res.partner', res_id=rec.id)
                else:
                    raise UserError(_('Please define Mobile Number in the patient.'))
            else:
                raise UserError(_('Please define Hospital in the patient.'))

    def generateotp_sms(self):
        digits = "0123456789"
        otp = ""
        for i in range(4):
            otp += digits[math.floor(random.random() * 10)]
            self.generated_otp_sms = otp

    def action_verify_otp_sms(self):
        if self.pb_otp_sms:
            pass
        else:
            raise UserError(_('Please enter OTP.'))
            
        if self.generated_otp_sms == self.pb_otp_sms:
            self.verified_mobile_sms = True
        else:
            raise UserError(_('The OTP you entered is invalid. Please enter the correct OTP.'))

    def action_pb_sms(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_sms.action_pb_sms")
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {
            'default_partner_id': self.id,
            'default_mobile': self.phone,
        }
        return action

    def action_pb_sms_announcement(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_sms.action_sms_announcement")
        action['domain'] = [('partner_ids', 'in', self.id)]
        action['context'] = { 'default_partner_ids': [(6, 0, [self.id])] }
        return action

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: