# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class PbHmsPatientMap(http.Controller):

    @http.route('/pb_hms/patient_map_data', type='jsonrpc', auth='user')
    def patient_map_data(self, limit=2000):
        # Uses the caller's own (non-sudo) env, so a patient only shows up
        # here if the logged-in user can actually read it - same ACL as
        # every other patient screen.
        Patient = request.env['hms.patient']
        patients = Patient.search([
            ('partner_latitude', '!=', 0.0), ('partner_longitude', '!=', 0.0),
        ], limit=limit)

        points = []
        for patient in patients:
            address_parts = [
                patient.street, patient.street2, patient.city,
                patient.state_id.name, patient.zip, patient.country_id.name,
            ]
            points.append({
                'id': patient.id,
                'name': patient.name,
                'code': patient.code,
                'lat': patient.partner_latitude,
                'lng': patient.partner_longitude,
                'address': ', '.join(p for p in address_parts if p),
                'phone': patient.phone or '',
            })

        total_patients = Patient.search_count([])
        return {
            'points': points,
            'total_patients': total_patients,
            'located_count': len(points),
        }
