from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

from .hrw_approval_step import REQUEST_TYPES


class HrWorkflowRequestDashboard(models.Model):
    _inherit = 'hr.workflow.request'

    @api.model
    def _hrw_dashboard_base_domain(self, flt):
        domain = []
        if flt.get('company_ids'):
            domain.append(('company_id', 'in', [int(c) for c in flt['company_ids']]))
        if flt.get('business_unit_id'):
            bu = int(flt['business_unit_id'])
            domain += ['|', ('business_unit_id', '=', bu), ('new_business_unit_id', '=', bu)]
        if flt.get('department_id'):
            dep = int(flt['department_id'])
            domain += ['|', ('department_id', '=', dep), ('new_department_id', '=', dep)]
        if flt.get('request_type'):
            domain.append(('request_type', '=', flt['request_type']))
        if flt.get('approver_id'):
            domain.append(('approval_ids.approver_ids', 'in', [int(flt['approver_id'])]))
        return domain

    @api.model
    def get_hrw_dashboard_data(self, flt=None):
        flt = flt or {}
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(flt.get('date_from')) or today.replace(day=1) - relativedelta(months=11)
        date_to = fields.Date.to_date(flt.get('date_to')) or today
        base = self._hrw_dashboard_base_domain(flt)
        in_range = [('request_date', '>=', date_from), ('request_date', '<=', date_to)]
        eff_range = [('effective_date', '>=', date_from), ('effective_date', '<=', date_to)]
        horizon = today + timedelta(days=30)
        Req = self

        def count(domain):
            return Req.search_count(base + domain)

        def kpi(key, label, value, domain, icon, tone, hint, fmt='int'):
            return {'key': key, 'label': label, 'value': value, 'domain': base + domain, 'icon': icon,
                    'tone': tone, 'hint': hint, 'fmt': fmt}

        open_dom = [('state', 'in', ('draft', 'in_approval', 'approved'))]
        overdue_dom = [('state', '=', 'in_approval'), ('current_deadline', '<', today)]
        legal_dom = [('state', '=', 'in_approval'), ('current_step_category', '=', 'legal')]
        upcoming_dom = [('state', 'in', ('in_approval', 'approved')), ('effective_date', '>=', today),
                        ('effective_date', '<=', horizon)]
        joiners_dom = [('request_type', '=', 'new_hire'), ('state', 'in', ('approved', 'done'))] + eff_range
        exits_dom = [('request_type', 'in', ('resignation', 'termination')),
                     ('state', 'in', ('approved', 'done'))] + eff_range
        cost_dom = [('request_type', '=', 'change'), ('state', 'in', ('approved', 'done'))] + eff_range
        cycle_dom = [('state', 'in', ('approved', 'done')), ('approved_date', '!=', False)] + in_range

        cost_change = sum(r.total_difference for r in Req.search(base + cost_dom))
        net_impact = sum(r.cost_impact for r in Req.search(
            base + [('state', 'in', ('approved', 'done'))] + eff_range))
        cycles = Req.search(base + cycle_dom).mapped('cycle_days')
        avg_cycle = round(sum(cycles) / len(cycles), 1) if cycles else 0.0

        kpis = [
            kpi('open', _('Open Requests'), count(open_dom), open_dom, 'fa-inbox', 'indigo',
                _('Requests not finished yet')),
            kpi('overdue', _('Late Approvals'), count(overdue_dom), overdue_dom, 'fa-clock-o', 'rose',
                _('Waiting longer than allowed')),
            kpi('legal', _('Waiting for Legal'), count(legal_dom), legal_dom, 'fa-balance-scale', 'amber',
                _('Terminations with the legal team')),
            kpi('upcoming', _('Coming Up (30 days)'), count(upcoming_dom), upcoming_dom, 'fa-calendar-check-o',
                'sky', _('Changes that start soon')),
            kpi('joiners', _('New Joiners'), count(joiners_dom), joiners_dom, 'fa-user-plus', 'emerald',
                _('People joining in this period')),
            kpi('exits', _('Leavers'), count(exits_dom), exits_dom, 'fa-sign-out', 'orange',
                _('People leaving in this period')),
            kpi('cost', _('Salary Increase / Month'), cost_change, cost_dom, 'fa-line-chart', 'violet',
                _('Extra monthly cost of approved raises'), 'money'),
            kpi('cycle', _('Average Approval Time'), avg_cycle, cycle_dom, 'fa-tachometer', 'teal',
                _('Days from submit to final approval'), 'days'),
        ]

        # ---------------------------------------------------------------- monthly trend by type
        months = []
        cursor = date_from.replace(day=1)
        while cursor <= date_to and len(months) < 24:
            months.append(cursor)
            cursor += relativedelta(months=1)
        trend_rows = Req._read_group(base + in_range, ['request_date:month', 'request_type'], ['__count'])
        trend = {t: [0] * len(months) for t, _l in REQUEST_TYPES}
        month_index = {(m.year, m.month): i for i, m in enumerate(months)}
        for month, rtype, cnt in trend_rows:
            if month and (month.year, month.month) in month_index:
                trend[rtype][month_index[(month.year, month.month)]] += cnt
        type_labels = dict(REQUEST_TYPES)
        trend_series = [{'key': t, 'label': type_labels[t], 'values': trend[t]} for t, _l in REQUEST_TYPES]

        # ---------------------------------------------------------------- mix, status, cycle by type
        mix = [{'key': t, 'label': type_labels[t], 'value': cnt,
                'domain': base + in_range + [('request_type', '=', t)]}
               for t, cnt in Req._read_group(base + in_range, ['request_type'], ['__count'])]
        state_labels = dict(self._fields['state'].selection)
        status = {s: 0 for s in state_labels}
        for s, cnt in Req._read_group(base + in_range, ['state'], ['__count']):
            status[s] = cnt
        funnel = [{'key': s, 'label': state_labels[s], 'value': status[s],
                   'domain': base + in_range + [('state', '=', s)]} for s in state_labels]
        cycle_by_type = []
        for t, avg in Req._read_group(base + cycle_dom, ['request_type'], ['cycle_days:avg']):
            cycle_by_type.append({'key': t, 'label': type_labels[t], 'value': round(avg or 0.0, 1)})
        cost_by_type = []
        for t, total in Req._read_group(base + [('state', 'in', ('approved', 'done'))] + eff_range,
                                        ['request_type'], ['cost_impact:sum']):
            cost_by_type.append({'key': t, 'label': type_labels[t], 'value': total or 0.0})

        # ---------------------------------------------------------------- approver workload
        Approval = self.env['hr.workflow.approval']
        visible_requests = Req.search(base)
        pending_lines = Approval.search([('request_id', 'in', visible_requests.ids), ('state', '=', 'pending'),
                                         ('request_id.state', '=', 'in_approval')])
        pending_lines = pending_lines.filtered(lambda l: l == l.request_id.current_approval_id)
        decided = Approval.search([('request_id', 'in', visible_requests.ids), ('state', 'in', ('approved', 'rejected')),
                                   ('decided_date', '>=', fields.Datetime.to_datetime(date_from))])
        approvers = {}
        for line in pending_lines:
            for user in line.approver_ids:
                a = approvers.setdefault(user.id, {'id': user.id, 'name': user.name, 'pending': 0, 'overdue': 0,
                                                   'decided': 0, 'hours': []})
                a['pending'] += 1
                if line.deadline and line.deadline < today:
                    a['overdue'] += 1
        for line in decided:
            user = line.decided_by
            if not user:
                continue
            a = approvers.setdefault(user.id, {'id': user.id, 'name': user.name, 'pending': 0, 'overdue': 0,
                                               'decided': 0, 'hours': []})
            a['decided'] += 1
            if line.response_hours:
                a['hours'].append(line.response_hours)
        approver_rows = []
        for a in approvers.values():
            hrs = a.pop('hours')
            a['avg_hours'] = round(sum(hrs) / len(hrs), 1) if hrs else 0.0
            a['domain'] = base + [('state', '=', 'in_approval'), ('current_approver_ids', 'in', [a['id']])]
            approver_rows.append(a)
        approver_rows.sort(key=lambda a: (-a['overdue'], -a['pending'], -a['decided']))

        # ---------------------------------------------------------------- lists
        def row(r):
            return {
                'id': r.id, 'name': r.name, 'type': r.request_type, 'type_label': type_labels[r.request_type],
                'employee': r.employee_id.sudo().name or r.new_employee_name or '',
                'employee_id': r.employee_id.id or False,
                'department': (r.new_department_id if r.request_type == 'new_hire' else r.department_id).display_name or '',
                'effective_date': fields.Date.to_string(r.effective_date) if r.effective_date else False,
                'days_left': (r.effective_date - today).days if r.effective_date else None,
                'step': r.current_step_name or state_labels[r.state],
                'state': r.state, 'state_label': state_labels[r.state],
                'deadline': fields.Date.to_string(r.current_deadline) if r.current_deadline else False,
                'days_overdue': (today - r.current_deadline).days if r.current_deadline else 0,
                'approvers': [{'id': u.id, 'name': u.name} for u in r.current_approver_ids[:4]],
                'cost_impact': r.cost_impact,
            }

        upcoming = [row(r) for r in Req.search(base + upcoming_dom, order='effective_date asc', limit=8)]
        overdue = [row(r) for r in Req.search(base + overdue_dom, order='current_deadline asc', limit=8)]
        recent = [row(r) for r in Req.search(base, order='write_date desc', limit=8)]

        # ---------------------------------------------------------------- departments heat
        dept_rows = []
        for dep, cnt in Req._read_group(base + open_dom + [('department_id', '!=', False)],
                                        ['department_id'], ['__count'], order='__count desc', limit=6):
            dept_rows.append({'id': dep.id, 'name': dep.display_name, 'value': cnt,
                              'domain': base + open_dom + [('department_id', '=', dep.id)]})

        # ---------------------------------------------------------------- filter options
        companies = self.env.user.company_ids
        options = {
            'companies': [{'id': c.id, 'name': c.name} for c in companies],
            'business_units': [{'id': b.id, 'name': b.display_name}
                               for b in self.env['hr.business.unit'].search([])],
            'departments': [{'id': d.id, 'name': d.display_name}
                            for d in self.env['hr.department'].search([('company_id', 'in', companies.ids + [False])])],
            'approvers': [{'id': u.id, 'name': u.name}
                          for u in Approval.search([('request_id', 'in', visible_requests.ids)]).approver_ids.sorted('name')],
            'types': [{'id': t, 'name': l} for t, l in REQUEST_TYPES],
        }
        return {
            'user_name': self.env.user.name,
            'today': fields.Date.to_string(today),
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'currency': {'symbol': self.env.company.currency_id.symbol, 'name': self.env.company.currency_id.name,
                         'position': self.env.company.currency_id.position},
            'kpis': kpis,
            'months': [m.strftime('%b %y') for m in months],
            'trend': trend_series,
            'mix': mix,
            'funnel': funnel,
            'cycle_by_type': cycle_by_type,
            'cost_by_type': cost_by_type,
            'net_impact': net_impact,
            'approvers': approver_rows[:8],
            'upcoming': upcoming,
            'overdue': overdue,
            'recent': recent,
            'departments': dept_rows,
            'options': options,
            'total_in_range': count(in_range),
        }
