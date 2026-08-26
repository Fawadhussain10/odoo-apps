# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class PbIrAttachment(models.AbstractModel):
    _inherit = "ir.attachment"

    def pb_get_action(self):
        pb_action_id = self.env.ref('base.action_attachment')
        for rec in self:
            rec.pb_action_id = pb_action_id

    pb_action_id = fields.Integer(compute="pb_get_action")

    def get_default_chart_image(self, department=False, company=False):
        chart_image = False
        chart_name = ''
        user_company = self.env.user.sudo().company_id
        if department and department.pb_default_chart_image:
            chart_image = department.pb_default_chart_image
            chart_name = department.pb_default_chart_image_name

        elif company and company.pb_default_chart_image:
            chart_image = company.pb_default_chart_image
            chart_name = company.pb_default_chart_image_name

        elif user_company.pb_default_chart_image:
            chart_image = user_company.pb_default_chart_image
            chart_name = user_company.pb_default_chart_image_name

        if not chart_image:
            raise UserError(_("No defalt Chart Image is configured yet. Please Configure it on relavant Department on General Setting."))

        return chart_image,chart_name

    def pb_hms_image_chart(self, param=''):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': '/my/pb/image/editor/%s%s' % (self.id, param),
        }

    def pb_create_chart_image(self, datas, name, res_model, res_id):
        attachment = self.create({
            'name': name,
            'datas': datas,
            'res_model': res_model,
            'res_id': res_id,
        })
        return attachment

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: