# -*- coding: utf-8 -*-

from odoo import http, fields, _
from odoo.http import request
from odoo import fields as odoo_fields, http, tools, _, SUPERUSER_ID
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo.exceptions import AccessError, MissingError
import json


class PBDentalChart(http.Controller):

    def pb_procedures_data(self, patient, post={}):
        upper_teeths = request.env['pb.hms.tooth'].search([], limit=16, offset=0)
        lower_teeths = request.env['pb.hms.tooth'].search([], limit=16, offset=16)
        lower_teeths = request.env['pb.hms.tooth'].search([('id','in',lower_teeths.ids)], order="id desc")
        surfaces =  request.env['pb.tooth.surface'].search([])
        procedures =  request.env['product.product'].search([('hospital_product_type','=','dental_procedure')])
        treatment = post.get('treatment_id')
        if not treatment:
            treatments = patient.treatment_ids.filtered(lambda t: t.department_id.department_type=='dental' and t.state=='running')
            if treatments:
                treatment = treatments[0].id
        patient_procedure_ids = patient.patient_procedure_ids.filtered(lambda t: (t.department_id.department_type=='dental' or t.tooth_id) and (t.state in ['scheduled','running'] or not t.invoice_id))
        patient_procedure_done_ids = patient.patient_procedure_ids.filtered(lambda t: (t.department_id.department_type=='dental' or t.tooth_id) and t.state in ['done'])
        data = {
            'error_message': post.get('error_message',''),
            'sucess_message': post.get('sucess_message',''),
            'treatment_id': treatment, 
            'appointment_id': post.get('appointment_id'),
            'pb_header_invisible': True, 
            'pb_footer_invisible': True, 
            'lower_teeths': lower_teeths,
            'upper_teeths': upper_teeths,
            'surfaces': surfaces,
            'procedures': procedures,
            'patient': patient,
            'pb_teeth_json_data': json.loads(patient.pb_teeth_json_data),
            'patient_procedure_ids': patient_procedure_ids,
            'patient_procedure_done_ids': patient_procedure_done_ids,
            'currency_id': request.env.user.sudo().company_id.currency_id,
        }
        return data

    @http.route(['/pb/dental/<int:patient_id>'], type='http', auth="user", website=True, sitemap=False)
    def patient_dental_procedure(self, patient_id=None, access_token=None, **kw):
        patient = request.env['hms.patient'].search([('id','=',patient_id)])
        if not patient:
            return request.render("pb_hms_dental_chart.pb_no_details")
        data = self.pb_procedures_data(patient, kw)
        return request.render("pb_hms_dental_chart.pb_dental_procedure", data)

    @http.route(['/pb/create/dental/procedure'], type='http', auth='user', website=True, sitemap=False)
    def pb_create_procedure(self, redirect=None, **post):
        user = request.env.user.sudo()
        patient = request.env['hms.patient'].sudo().search([('id','=',post.get('patient_id'))])
        data = self.pb_procedures_data(patient)

        error_message = self.validate_pb_procedure_details(post)
        if error_message:
            data.update({'error_message': error_message})
            return request.redirect("/pb/dental/%s?error_message=%s"  % (patient.id, error_message))

        selected_surfaces = []
        for rec in post:
            vals = rec.split('surface_')
            if len(vals)==2:
                selected_surfaces.append(int(vals[1]))

        department = request.env['hr.department'].search([('department_type','=','dental')], limit=1)
        if department:
            department = department.id

        product_id = request.env['product.product'].sudo().search([('id','=',post.get('product_id'))])
        procedure_data = {
            'patient_id': patient.id,
            'treatment_id': post.get('treatment_id'),
            'product_id': product_id.id,
            'tooth_id': post.get('tooth_id'),
            'tooth_surface_ids': [(6,0,selected_surfaces)],
            'physician_id': user.physician_ids and user.physician_ids[0].id or False,
            'department_id': department,
            'price_unit': product_id.list_price,
        }
        if post.get('appointment_id'):
            procedure_data.update({
                'appointment_ids': [(6,0,[post.get('appointment_id', False)])]
            })

        # Create Procedure
        procedure_id = request.env['pb.patient.procedure'].sudo().create(procedure_data)
        sucess_message = _('Created new Procedure %s.') % (procedure_id.name)
        return request.redirect("/pb/dental/%s?sucess_message=%s"  % (patient.id, sucess_message))

    def validate_pb_procedure_details(self, data):
        error_message = ''
        if not data.get('tooth_id'):
            error_message += '\n' + _('Please Select Tooth and other data Properly.')
        if not data.get('product_id'):
            error_message += '\n' + _('Please Select Procedure and other data Properly.')
        return error_message


    @http.route(['/pb/update/procedure/<int:procedure_id>'], type='http', auth="user", website=True, sitemap=False)
    def pb_delete_procedure(self, procedure_id=None, access_token=None, **kw):
        procedure_id = request.env['pb.patient.procedure'].search([('id','=',procedure_id)])
        patient = procedure_id.patient_id
        if procedure_id:
            if kw.get('action')=='createinvoice' and not procedure_id.invoice_id:
                procedure_id.action_create_invoice()
            if kw.get('action')=='delete' and procedure_id.state=='scheduled':
                procedure_id.unlink()
            elif kw.get('action')=='inprogress' and procedure_id.state=='scheduled':
                procedure_id.action_running()
            elif kw.get('action')=='done' and procedure_id.state=='running':
                procedure_id.action_done()
        return request.redirect("/pb/dental/%s"  % (patient.id))    

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: