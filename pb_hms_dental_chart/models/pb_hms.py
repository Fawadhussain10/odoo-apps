#-*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from markupsafe import escape
import json


class HmsPatient(models.Model):
    _inherit = 'hms.patient'

    def _pb_get_teeth_data(self):
        data = {}
        procedures = self.patient_procedure_ids.filtered(lambda t: t.tooth_id and t.state=='done')
        for procedure in procedures:
            tooth_is_removed = True if procedure.product_id.dental_procedure_type=='tooth_removal' else False
            procedure_label = '<li>%s [%s]</li>' % (escape(procedure.product_id.name or ''), escape(procedure.name or ''))
            if procedure.tooth_id.id not in data:
                data[procedure.tooth_id.id] = {
                    'procedure_details': procedure_label,
                    'tooth_is_removed': tooth_is_removed,
                    'show_procedure_image': procedure.product_id.id if procedure.product_id.show_image_in_chart else False
                }
            else:
                data[procedure.tooth_id.id]['procedure_details'] += procedure_label
                if tooth_is_removed:
                    data[procedure.tooth_id.id]['tooth_is_removed'] = True
                if procedure.product_id.show_image_in_chart:
                    data[procedure.tooth_id.id]['show_procedure_image'] = procedure.product_id.id

        for m_data in data:
            data[m_data]['procedure_details'] = '<b>Performed Procedures</b>&#13;<ul>' + data[m_data]['procedure_details'] + '</ul>'

        self.pb_teeth_json_data = json.dumps(data)

    pb_teeth_json_data = fields.Text(string="Teeth Data", compute="_pb_get_teeth_data")

    def pb_hms_dental_chart(self, param=''):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': '/pb/dental/%s%s' % (self.id, param),
        }


class HmsTreatment(models.Model):
    _inherit = 'hms.treatment'

    def pb_hms_dental_chart(self):
        self.ensure_one()
        param = '?treatment_id=%s' % (self.id)
        return self.patient_id.pb_hms_dental_chart(param=param)


class HmsPatientProcedure(models.Model):
    _inherit = 'pb.patient.procedure'

    def pb_hms_dental_chart(self):
        self.ensure_one()
        return self.patient_id.pb_hms_dental_chart()


class HmsAppointment(models.Model):
    _inherit = 'hms.appointment'

    def pb_hms_dental_chart(self):
        self.ensure_one()
        param = '?appointment_id=%s' % (self.id)
        return self.patient_id.pb_hms_dental_chart(param=param)


class PBProduct(models.Model):
    _inherit = 'product.template'

    dental_procedure_type = fields.Selection([('tooth_removal','Remove Tooth'),('Other','Other')])
    show_image_in_chart = fields.Boolean('Show Product Image in Chart', help="Image to show in chart instead of tooth when perfomed this procedure.")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: