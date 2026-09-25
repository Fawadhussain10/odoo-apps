# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import requests
import json


class ResCompany(models.Model):
    _inherit = 'res.company'

    whatsapp_meta_url = fields.Char(string='WhatsApp Meta API URL', default='https://graph.facebook.com/v14.0')
    whatsapp_meta_phone_number_id = fields.Char(string='Phone Number ID')
    whatsapp_meta_token = fields.Char(string='Meta Token')
    whatsapp_business_acccountid = fields.Char("Whatsapp Business Account ID")

    def get_whatsapp_templates(self):
        messageTemplate = self.env['pb.whatsapp.template']
        resLang = self.env['res.lang']
        for rec in self:
            URL =  "%s/%s/message_templates?access_token=%s" % (rec.whatsapp_meta_url,rec.whatsapp_business_acccountid, rec.whatsapp_meta_token)
            reply = requests.get(URL)
            if reply.status_code==200:
                reply_data = json.loads(reply.content)
                for template_data in reply_data['data']:
                    template_name = template_data['name']
                    existing_template = messageTemplate.search([('name','=',template_name)])
                    language_id = resLang.search([('code','=',template_data['language'])])
                    if not existing_template:
                        data = {
                            'name': template_name,
                            'whatsapp_data': template_data,
                            'language_id': language_id and language_id.id or False,
                            'state': template_data['status'],
                            'whasaap_id': template_data['id'],
                            'category': template_data['category'],
                        }
                        for component_data in template_data['components']:
                            if component_data.get('type')=='HEADER' and component_data.get('format') in ['TEXT','IMAGE','DOCUMENT']:
                                data.update({
                                    'header_message_type': component_data.get('format'),
                                    'header_message': component_data.get('text')
                                })
                            elif component_data.get('type')=='BODY' and component_data.get('format') in ['TEXT','IMAGE','DOCUMENT']:
                                data.update({
                                    'body_message_type': component_data.get('format','TEXT'),
                                    'body_message': component_data.get('text')
                                })
                            elif component_data.get('type')=='FOOTER' and component_data.get('format') in ['TEXT','IMAGE','DOCUMENT']:
                                data.update({
                                    'body_message_type': component_data.get('format','TEXT'),
                                    'body_message': component_data.get('text')
                                })
                        messageTemplate.create(data)
            else:
                raise UserError(_("Something went wrong."))


 # vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: