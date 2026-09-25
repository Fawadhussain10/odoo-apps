# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_
from odoo.exceptions import UserError
from datetime import date, datetime, timedelta
from odoo.fields import Domain
from .procedure_recurrence import DAYS, WEEKS

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    recurring_procedure = fields.Boolean(string="Recurrent")
    repeat_number = fields.Integer(string="Repetitions", default=2)


class ProcedureGroupLine(models.Model):
    _inherit = 'procedure.group.line'

    recurring_procedure = fields.Boolean(string="Recurrent")
    repeat_number = fields.Integer(string="Repetitions", default=2)

    @api.onchange('product_id')
    def onchange_product(self):
        if self.product_id:
            self.recurring_procedure = self.product_id.recurring_procedure
            self.repeat_number = self.product_id.repeat_number


class HmsTreatment(models.Model):
    _inherit = 'hms.treatment'

    def get_line_data(self, line):
        res = super(HmsTreatment, self).get_line_data(line)
        res['recurring_procedure'] = line.recurring_procedure
        #PB: On default recurrace creation to avoid error mark mon tru by default.
        if line.recurring_procedure:
            res['mon'] = True
        res['repeat_number'] = line.repeat_number
        res['repeat_type'] = 'after'
        return res

    def pb_create_recurring_procedures(self):
        self.patient_procedure_ids.mapped('recurrence_id').pb_create_recurring_procedures()


#PB: we can use task insted of procedure to optimize code also.
class PbPatientProcedure(models.Model):
    _inherit = 'pb.patient.procedure'

    STATES = {'cancel': [('readonly', True)], 'done': [('readonly', True)]}

    # recurrence fields Taken reference from project procedure recurrence
    recurring_procedure = fields.Boolean(string="Recurrent")
    recurring_count = fields.Integer(string="Procedures in Recurrence", compute='_compute_recurring_count')
    recurrence_id = fields.Many2one('pb.procedure.recurrence', copy=False)
    recurrence_update = fields.Selection([
        ('this', 'This procedure'),
        ('subsequent', 'This and following procedures'),
        ('all', 'All procedures'),
    ], default='this', store=False)
    recurrence_message = fields.Html(string='Next Recurrencies', compute='_compute_recurrence_message', sanitize=False)

    repeat_interval = fields.Integer(string='Repeat Every', default=1, compute='_compute_repeat', readonly=False)
    process_start_time = fields.Float(string='Start Time', default=10)
    repeat_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years'),
    ], default='week', compute='_compute_repeat_stored', readonly=False, store=True, compute_sudo=False)
    repeat_type = fields.Selection([
        ('forever', 'Forever'),
        ('until', 'End Date'),
        ('after', 'Number of Repetitions'),
    ], default="forever", string="Until", compute='_compute_repeat_stored', readonly=False, store=True, compute_sudo=False)
    repeat_until = fields.Date(string="Recurrence End Date", compute='_compute_repeat', readonly=False)
    repeat_number = fields.Integer(string="Repetitions", default=1, compute='_compute_repeat', readonly=False)

    repeat_on_month = fields.Selection([
        ('date', 'Date of the Month'),
        ('day', 'Day of the Month'),
    ], default='date', compute='_compute_repeat', readonly=False)

    repeat_on_year = fields.Selection([
        ('date', 'Date of the Year'),
        ('day', 'Day of the Year'),
    ], default='date', compute='_compute_repeat', readonly=False)

    mon = fields.Boolean(string="Mon", compute='_compute_repeat', readonly=False)
    tue = fields.Boolean(string="Tue", compute='_compute_repeat', readonly=False)
    wed = fields.Boolean(string="Wed", compute='_compute_repeat', readonly=False)
    thu = fields.Boolean(string="Thu", compute='_compute_repeat', readonly=False)
    fri = fields.Boolean(string="Fri", compute='_compute_repeat', readonly=False)
    sat = fields.Boolean(string="Sat", compute='_compute_repeat', readonly=False)
    sun = fields.Boolean(string="Sun", compute='_compute_repeat', readonly=False)

    repeat_day = fields.Selection([
        (str(i), str(i)) for i in range(1, 32)
    ], compute='_compute_repeat', readonly=False)
    repeat_week = fields.Selection([
        ('first', 'First'),
        ('second', 'Second'),
        ('third', 'Third'),
        ('last', 'Last'),
    ], default='first', compute='_compute_repeat', readonly=False)
    repeat_weekday = fields.Selection([
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
        ('sun', 'Sunday'),
    ], string='Day Of The Week', compute='_compute_repeat', readonly=False)
    repeat_month = fields.Selection([
        ('january', 'January'),
        ('february', 'February'),
        ('march', 'March'),
        ('april', 'April'),
        ('may', 'May'),
        ('june', 'June'),
        ('july', 'July'),
        ('august', 'August'),
        ('september', 'September'),
        ('october', 'October'),
        ('november', 'November'),
        ('december', 'December'),
    ], compute='_compute_repeat', readonly=False)

    repeat_show_dow = fields.Boolean(compute='_compute_repeat_visibility')
    repeat_show_day = fields.Boolean(compute='_compute_repeat_visibility')
    repeat_show_week = fields.Boolean(compute='_compute_repeat_visibility')
    repeat_show_month = fields.Boolean(compute='_compute_repeat_visibility')

    @api.model
    def _get_recurrence_fields(self):
        return ['repeat_interval', 'repeat_unit', 'repeat_type', 'repeat_until', 'repeat_number',
                'repeat_on_month', 'repeat_on_year', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat',
                'sun', 'repeat_day', 'repeat_week', 'repeat_month', 'repeat_weekday']

    @api.depends('recurring_procedure', 'repeat_unit', 'repeat_on_month', 'repeat_on_year')
    def _compute_repeat_visibility(self):
        for procedure in self:
            procedure.repeat_show_day = procedure.recurring_procedure and (procedure.repeat_unit == 'month' and procedure.repeat_on_month == 'date') or (procedure.repeat_unit == 'year' and procedure.repeat_on_year == 'date')
            procedure.repeat_show_week = procedure.recurring_procedure and (procedure.repeat_unit == 'month' and procedure.repeat_on_month == 'day') or (procedure.repeat_unit == 'year' and procedure.repeat_on_year == 'day')
            procedure.repeat_show_dow = procedure.recurring_procedure and procedure.repeat_unit == 'week'
            procedure.repeat_show_month = procedure.recurring_procedure and procedure.repeat_unit == 'year'

    def _compute_repeat_fields(self, rec_fields):
        defaults = self.default_get(rec_fields)
        for procedure in self:
            for f in rec_fields:
                if procedure.recurrence_id:
                    procedure[f] = procedure.recurrence_id[f]
                else:
                    if procedure.recurring_procedure:
                        procedure[f] = defaults.get(f)
                    else:
                        procedure[f] = False

    @api.depends('recurring_procedure')
    def _compute_repeat_stored(self):
        self._compute_repeat_fields(['repeat_unit', 'repeat_type'])

    @api.depends('recurring_procedure')
    def _compute_repeat(self):
        rec_fields = [f for f in self._get_recurrence_fields() if f not in ('repeat_unit', 'repeat_type')]
        self._compute_repeat_fields(rec_fields)

    def _get_weekdays(self, n=1):
        self.ensure_one()
        if self.repeat_unit == 'week':
            return [fn(n) for day, fn in DAYS.items() if self[day]]
        return [DAYS.get(self.repeat_weekday)(n)]

    def _get_recurrence_start_date(self):
        return fields.Date.today()

    @api.depends(
        'recurring_procedure', 'repeat_interval', 'repeat_unit', 'repeat_type', 'repeat_until',
        'repeat_number', 'repeat_on_month', 'repeat_on_year', 'mon', 'tue', 'wed', 'thu', 'fri',
        'sat', 'sun', 'repeat_day', 'repeat_week', 'repeat_month', 'repeat_weekday')
    def _compute_recurrence_message(self):
        self.recurrence_message = False
        for procedure in self.filtered(lambda t: t.recurring_procedure and t._is_recurrence_valid()):
            date = procedure._get_recurrence_start_date()
            number_occurrences = min(5, procedure.repeat_number if procedure.repeat_type == 'after' else 5)
            delta = procedure.repeat_interval if procedure.repeat_unit == 'day' else 1
            recurring_dates = self.env['pb.procedure.recurrence']._get_next_recurring_dates(
                date + timedelta(days=delta),
                procedure.repeat_interval,
                procedure.repeat_unit,
                procedure.repeat_type,
                procedure.repeat_until,
                procedure.repeat_on_month,
                procedure.repeat_on_year,
                procedure._get_weekdays(WEEKS.get(procedure.repeat_week)),
                procedure.repeat_day,
                procedure.repeat_week,
                procedure.repeat_month,
                count=number_occurrences)
            date_format = self.env['res.lang']._lang_get(self.env.user.lang).date_format
            chips = ''.join(
                '<span class="pb_recur_chip">%s</span>' % date.strftime(date_format)
                for date in recurring_dates[:5]
            )
            if procedure.repeat_type == 'after' and procedure.repeat_number > 5 or procedure.repeat_type == 'forever' or len(recurring_dates) > 5:
                chips += '<span class="pb_recur_chip pb_recur_more">…</span>'
            message = '<div class="pb_recur_dates">%s</div>' % chips
            if procedure.repeat_type == 'until':
                message += _('<div class="pb_recur_count">Number of procedures: %(procedures_count)s</div>') % {'procedures_count': len(recurring_dates)}
            procedure.recurrence_message = message

    def _is_recurrence_valid(self):
        self.ensure_one()
        return self.repeat_interval > 0 and\
                (not self.repeat_show_dow or self._get_weekdays()) and\
                (self.repeat_type != 'after' or self.repeat_number) and\
                (self.repeat_type != 'until' or self.repeat_until and self.repeat_until > fields.Date.today())

    @api.depends('recurrence_id')
    def _compute_recurring_count(self):
        self.recurring_count = 0
        recurring_procedures = self.filtered(lambda l: l.recurrence_id)
        count = self.env['pb.patient.procedure'].read_group([('recurrence_id', 'in', recurring_procedures.recurrence_id.ids)], ['id'], 'recurrence_id')
        procedures_count = {c.get('recurrence_id')[0]: c.get('recurrence_id_count') for c in count}
        for procedure in recurring_procedures:
            procedure.recurring_count = procedures_count.get(procedure.recurrence_id.id, 0)

    def copy(self, default=None):
        if default is None:
            default = {}
        if not default.get('name'):
            default['name'] = _("%s (copy)", self.name)
        if self.recurrence_id:
            default['recurrence_id'] = self.recurrence_id.copy().id
        return super(PbPatientProcedure, self).copy(default)

    # ------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------
    @api.model
    def default_get(self, default_fields):
        vals = super(PbPatientProcedure, self).default_get(default_fields)

        days = list(DAYS.keys())
        week_start = fields.Datetime.today().weekday()

        if all(d in default_fields for d in days):
            vals[days[week_start]] = True
        if 'repeat_day' in default_fields:
            vals['repeat_day'] = str(fields.Datetime.today().day)
        if 'repeat_month' in default_fields:
            vals['repeat_month'] = self._fields.get('repeat_month').selection[fields.Datetime.today().month - 1][0]
        if 'repeat_until' in default_fields:
            vals['repeat_until'] = fields.Date.today() + timedelta(days=7)
        if 'repeat_weekday' in default_fields:
            vals['repeat_weekday'] = self._fields.get('repeat_weekday').selection[week_start][0]

        return vals

    @api.model_create_multi
    def create(self, vals_list):
        default_stage = dict()
        for vals in vals_list:
            # recurrence
            rec_fields = vals.keys() & self._get_recurrence_fields()
            if rec_fields and vals.get('recurring_procedure') is True:
                rec_values = {rec_field: vals[rec_field] for rec_field in rec_fields}
                rec_values['next_recurrence_date'] = fields.Datetime.today()
                recurrence = self.env['pb.procedure.recurrence'].create(rec_values)
                vals['recurrence_id'] = recurrence.id
        procedures = super().create(vals_list)
        return procedures

    def write(self, vals):
        # recurrence fields
        rec_fields = vals.keys() & self._get_recurrence_fields()
        if rec_fields:
            rec_values = {rec_field: vals[rec_field] for rec_field in rec_fields}
            for procedure in self:
                if procedure.recurrence_id:
                    procedure.recurrence_id.write(rec_values)
                elif vals.get('recurring_procedure'):
                    rec_values['next_recurrence_date'] = fields.Datetime.today()
                    recurrence = self.env['pb.procedure.recurrence'].create(rec_values)
                    procedure.recurrence_id = recurrence.id

        if 'recurring_procedure' in vals and not vals.get('recurring_procedure'):
            self.recurrence_id.unlink()

        procedures = self
        recurrence_update = vals.pop('recurrence_update', 'this')
        if recurrence_update != 'this':
            recurrence_domain = []
            if recurrence_update == 'subsequent':
                for procedure in self:
                    recurrence_domain = Domain.OR([recurrence_domain, ['&', ('recurrence_id', '=', procedure.recurrence_id.id), ('create_date', '>=', procedure.create_date)]])
            else:
                recurrence_domain = [('recurrence_id', 'in', self.recurrence_id.ids)]
            procedures |= self.env['pb.patient.procedure'].search(recurrence_domain)

        result = super(PbPatientProcedure, procedures).write(vals)
        return result

    def unlink(self): 
        if any(self.mapped('recurrence_id')):
            # TODO: show a dialog to stop the recurrence
            raise UserError(_('You cannot delete recurring Procedure. Please, disable the recurrence first.'))
        return super().unlink()

    def action_recurring_procedures(self):
        return {
            'name': 'Procedures in Recurrence',
            'type': 'ir.actions.act_window',
            'res_model': 'pb.patient.procedure',
            'view_mode': 'list,form',
            'domain': [('recurrence_id', 'in', self.recurrence_id.ids)],
        }

    #===========end recurring code=======#
    @api.onchange('product_id')
    def onchange_product(self):
        res = super(PbPatientProcedure, self).onchange_product()
        if self.product_id:
            self.recurring_procedure = self.product_id.recurring_procedure
            self.repeat_number = self.product_id.repeat_number

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: