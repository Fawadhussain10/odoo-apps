# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _

class ResCompany(models.Model):
    _inherit = 'res.company'

    sms_user_name = fields.Char(string='User Name')
    sms_sms_user_name_param = fields.Char(string='User Name Parameter', default="uname")
    sms_password = fields.Char(string='Password')
    sms_password_param = fields.Char(string='Password Parameter', default="pass")
    sms_sender_id = fields.Char(string='Sender')
    sms_sender_param = fields.Char(string='Sender Parameter', default="source")
    sms_message_param = fields.Char(string='Message Parameter', default="message")
    sms_receiver_param = fields.Char(string='Receiver Parameter', default="destination")
    sms_extra_param = fields.Char(string='Extra Parameter', default="")
    sms_templateid_param = fields.Char(string='Template Parameter', default="")

    sms_url = fields.Char(string='URL', default='http://www.unicel.in/SendSMS/sendmsg.php?')

    verify_otp_msg_sms_template_id = fields.Many2one("pb.sms.template", "Verify OTP SMS")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: