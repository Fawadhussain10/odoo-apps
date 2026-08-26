# -*- coding: utf-8 -*-
import time
from urllib.request import Request, urlopen
import urllib
import json
import requests
import base64
from datetime import datetime
import os

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_datetime, DEFAULT_SERVER_DATETIME_FORMAT as DTF


class PbWhatsAppTemplate(models.Model):
    _inherit = 'pb.whatsapp.template'

    def pb_send_template_for_approval(self):
        for rec in self:
            if rec.header_message_type and rec.header_message_type!='TEXT':
                raise UserError(_("Currently only Message Type template upload is supported."))
            if rec.body_message_type and rec.body_message_type!='TEXT':
                raise UserError(_("Currently only Message Type template upload is supported."))
            if rec.footer_message_type and rec.footer_message_type!='TEXT':
                raise UserError(_("Currently only Message Type template upload is supported."))

            URL = "%s/%s/message_templates" % (rec.company_id.whatsapp_meta_url,rec.company_id.whatsapp_business_acccountid)
            data = {
                "name": rec.name, 
                "language": rec.language_id.code,
                "components": [],
                "access_token": rec.company_id.whatsapp_meta_token
            }
            if rec.header_message_type:
                data['components'].append({
                    'type': 'HEADER',
                    'format': rec.header_message_type,
                    'text': rec.header_message
                })
            if rec.body_message_type:
                data['components'].append({
                    'type': 'BODY',
                    'format': rec.header_message_type,
                    'text': rec.body_message
                })
            if rec.footer_message_type:
                data['components'].append({
                    'type': 'FOOTER',
                    'format': rec.footer_message_type,
                    'text': rec.footer_message
                })

            params = urllib.parse.urlencode(data)
            reply = requests.post(URL + "?" + params)
            print ("reply-------",reply)
            # if reply.status_code==200:
            #     rec.state = 'sent'
            # else:
            #     rec.state = 'error'
            # rec.reply_data = reply.text


class PbWhatsAppMessage(models.Model):
    _inherit = 'pb.whatsapp.message'

    def pb_get_file_type(self):
        for rec in self:
            media_type = 'document'
            if rec.mimetype=='image/png':
                media_type = 'image'
            rec.media_type = media_type

    media_id = fields.Char("Meta Media ID", copy=False)
    media_type = fields.Selection([('image','Image'),
        ('document','Document'),
        ('audio','Audio'),
        ('video','Video')], compute="pb_get_file_type" ,string="PB File Type")

    def pb_get_media_id(self):
        company = self.env.user.sudo().company_id
        file_dir = os.path.dirname(os.path.realpath(__file__))
        if not os.access(file_dir, os.W_OK):
            raise ValidationError(_("Module Location %s does not have Write Access.") % (file_dir))

        doc_file = base64.decodebytes(self.file)
        file_name = self.file_name.replace('/',' ').replace(' ','_')
        file_path = os.path.join(file_dir, file_name)

        fp = open(os.path.join(file_dir, file_name), 'wb')
        fp.write(doc_file)
        fp.close()

        media_headers = {
            'Authorization': 'Bearer %s' % (self.company_id.whatsapp_meta_token)
        }
        Media_URL = "%s/%s/media" % (self.company_id.whatsapp_meta_url,self.company_id.whatsapp_meta_phone_number_id)
        media_data = {
            "messaging_product": "whatsapp"
        }
        
        files = [('file',(file_name,open(file_path,'rb'),self.mimetype))]
        reply = requests.request("POST", Media_URL, headers=media_headers, data=media_data, files=files)
        if reply.status_code==200:
            self.media_id = json.loads(reply.text).get('id')
            os.remove(file_path)
        else:
            self.reply_data = reply.text

    def send_whatsapp_message(self):
        for rec in self:            
            try:
                headers = {
                    'Content-type': 'application/json',
                    'Authorization': 'Bearer %s' % (rec.company_id.whatsapp_meta_token)
                }
                to_number = rec.mobile.replace('+','').replace(' ','')
                if rec.message_type=='message':
                    URL = "%s/%s/messages" % (rec.company_id.whatsapp_meta_url,rec.company_id.whatsapp_meta_phone_number_id)
                    message = {
                            "messaging_product": "whatsapp", 
                            "to": to_number
                        }
                    if rec.template_id:
                        message["type"] = "template"
                        message["template"] = { 
                            "name": rec.template_id.name, 
                            "language": { 
                                "code": rec.template_id.language_id.code or "en_US"
                            } 
                        }

                    else:
                        message["text"] = { 
                            "body": rec.message
                        }

                elif rec.message_type in ['file']:
                    #PB: if no media first create media id.
                    if not rec.media_id:
                        rec.pb_get_media_id()

                    URL = "%s/%s/messages" % (rec.company_id.whatsapp_meta_url,rec.company_id.whatsapp_meta_phone_number_id)
                    message = {
                        "messaging_product": "whatsapp", 
                        "to": to_number,
                        "type": rec.media_type,
                        rec.media_type: {
                            "id" : rec.media_id,
                            "filename": rec.file_name.replace('/',' ').replace(' ','_')
                        }
                    }

                else:
                    rec.state = 'error'
                    rec.error_message = 'This Message Type is not suppoerted.'
                    return

                reply = requests.post(URL, data=json.dumps(message), headers=headers)
                if reply.status_code==200:
                    rec.state = 'sent'
                else:
                    rec.state = 'error'
                rec.reply_data = reply.text

            except Exception as e:
                rec.state = 'error'
                rec.error_message = e


class PBwhatsappMixin(models.AbstractModel):
    _inherit = "pb.whatsapp.mixin"

    def pb_whatsapp_chat_history(self, partner, mobile):
        raise UserError(_("History not supported."))

        return  False

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: