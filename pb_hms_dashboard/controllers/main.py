# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class PbHmsDashboardController(http.Controller):

    @http.route('/pb_hms_dashboard/data', type='jsonrpc', auth='user')
    def get_dashboard_data(self, filter='today'):
        user = request.env.user
        if filter not in ('today', 'week', 'month', 'year', 'all'):
            filter = 'today'
        if user.dashboard_data_filter != filter:
            user.sudo().dashboard_data_filter = filter

        can_receptionist = user.has_group('pb_hms.group_hms_receptionist')
        can_manager = user.has_group('pb_hms_base.group_hms_manager')
        can_invoice = user.has_group('account.group_account_invoice')
        is_physician = user.is_physician

        company = user.company_id
        data = {
            'user_name': user.name,
            'filter': filter,
            'is_physician': is_physician,
            'is_manager': can_manager,
            'can_receptionist': can_receptionist,
            'can_invoice': can_invoice,
            'currency_symbol': company.currency_id.symbol,
            'currency_position': company.currency_id.position,
        }

        if is_physician:
            data['mine'] = {
                'total_patients': user.my_total_patients,
                'total_appointments': user.my_total_appointments,
                'total_treatments': user.my_total_treatments,
                'total_running_treatments': user.my_total_running_treatments,
                'avg_wait_time': user.my_avg_wait_time,
                'avg_cons_time': user.my_avg_cons_time,
            }

        if can_receptionist and (not is_physician or can_manager):
            data['overview'] = {
                'total_patients': user.total_patients,
                'total_appointments': user.total_appointments,
                'total_treatments': user.total_treatments,
                'total_running_treatments': user.total_running_treatments,
                'total_shedules': user.total_shedules,
                'avg_wait_time': user.avg_wait_time,
                'avg_cons_time': user.avg_cons_time,
                'birthday_patients': user.birthday_patients,
                'birthday_employee': user.birthday_employee,
            }
            data['appointments'] = self._get_appointment_rows(user.appointment_data)
            data['appointment_trend'] = self._chartify_bar(user.appointment_bar_graph)
            data['patient_trend'] = self._chartify_line(user.patient_line_graph)

        if can_manager:
            data['physicians'] = {
                'total_physicians': user.total_physicians,
                'total_referring_physicians': user.total_referring_physicians,
            }

        if can_invoice:
            data['invoices'] = {
                'total_open_invoice': user.total_open_invoice,
                'total_open_invoice_amount': user.total_open_invoice_amount,
            }

        return data

    def _get_appointment_rows(self, appointment_data_json):
        import json
        try:
            return json.loads(appointment_data_json or '[]')
        except ValueError:
            return []

    def _chartify_bar(self, graph_json):
        import json
        try:
            payload = json.loads(graph_json or '[]')
        except ValueError:
            return {'labels': [], 'values': []}
        if not payload:
            return {'labels': [], 'values': []}
        values = payload[0].get('values', [])
        return {
            'labels': [v.get('label') for v in values],
            'values': [v.get('value') for v in values],
            'types': [v.get('type') for v in values],
        }

    def _chartify_line(self, graph_json):
        import json
        try:
            payload = json.loads(graph_json or '[]')
        except ValueError:
            return {'labels': [], 'values': []}
        if not payload:
            return {'labels': [], 'values': []}
        values = payload[0].get('values', [])
        return {
            'labels': [v.get('x') for v in values],
            'values': [v.get('y') for v in values],
        }
