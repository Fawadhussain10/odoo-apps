# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from calendar import monthrange
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, timedelta
from dateutil.rrule import rrule, rruleset, DAILY, WEEKLY, MONTHLY, YEARLY, MO, TU, WE, TH, FR, SA, SU
from pytz import timezone as TIMEZONE

MONTHS = {
    'january': 31,
    'february': 28,
    'march': 31,
    'april': 30,
    'may': 31,
    'june': 30,
    'july': 31,
    'august': 31,
    'september': 30,
    'october': 31,
    'november': 30,
    'december': 31,
}

DAYS = {
    'mon': MO,
    'tue': TU,
    'wed': WE,
    'thu': TH,
    'fri': FR,
    'sat': SA,
    'sun': SU,
}

WEEKS = {
    'first': 1,
    'second': 2,
    'third': 3,
    'last': 4,
}

class PbProcedureRecurrence(models.Model):
    _name = 'pb.procedure.recurrence'
    _description = 'Procedure Recurrence'

    procedure_ids = fields.One2many('pb.patient.procedure', 'recurrence_id')
    next_recurrence_date = fields.Date()
    recurrence_left = fields.Integer(string="Number of procedures left to create")

    repeat_interval = fields.Integer(string='Repeat Every', default=1)
    repeat_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years'),
    ], default='week')
    repeat_type = fields.Selection([
        ('forever', 'Forever'),
        ('until', 'End Date'),
        ('after', 'Number of Repetitions'),
    ], default="forever", string="Until")
    repeat_until = fields.Date(string="End Date")
    repeat_number = fields.Integer(string="Repetitions")

    repeat_on_month = fields.Selection([
        ('date', 'Date of the Month'),
        ('day', 'Day of the Month'),
    ])

    repeat_on_year = fields.Selection([
        ('date', 'Date of the Year'),
        ('day', 'Day of the Year'),
    ])

    mon = fields.Boolean(string="Mon")
    tue = fields.Boolean(string="Tue")
    wed = fields.Boolean(string="Wed")
    thu = fields.Boolean(string="Thu")
    fri = fields.Boolean(string="Fri")
    sat = fields.Boolean(string="Sat")
    sun = fields.Boolean(string="Sun")

    repeat_day = fields.Selection([
        (str(i), str(i)) for i in range(1, 32)
    ])
    repeat_week = fields.Selection([
        ('first', 'First'),
        ('second', 'Second'),
        ('third', 'Third'),
        ('last', 'Last'),
    ])
    repeat_weekday = fields.Selection([
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
        ('sun', 'Sunday'),
    ], string='Day Of The Week', readonly=False)
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
    ])

    @api.constrains('repeat_unit', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
    def _check_recurrence_days(self):
        for procedure in self.filtered(lambda p: p.repeat_unit == 'week'):
            if not any([procedure.mon, procedure.tue, procedure.wed, procedure.thu, procedure.fri, procedure.sat, procedure.sun]):
                raise ValidationError('You should select a least one day')

    @api.constrains('repeat_interval')
    def _check_repeat_interval(self):
        if self.filtered(lambda t: t.repeat_interval <= 0):
            raise ValidationError('The interval should be greater than 0')

    @api.constrains('repeat_number', 'repeat_type')
    def _check_repeat_number(self):
        if self.filtered(lambda t: t.repeat_type == 'after' and t.repeat_number <= 0):
            raise ValidationError('Should repeat at least once')

    @api.constrains('repeat_type', 'repeat_until')
    def _check_repeat_until_date(self):
        today = fields.Date.today()
        if self.filtered(lambda t: t.repeat_type == 'until' and t.repeat_until < today):
            raise ValidationError('The end date should be in the future')

    @api.constrains('repeat_unit', 'repeat_on_month', 'repeat_day', 'repeat_type', 'repeat_until')
    def _check_repeat_until_month(self):
        if self.filtered(lambda r: r.repeat_type == 'until' and r.repeat_unit == 'month' and r.repeat_until and r.repeat_on_month == 'date' and int(r.repeat_day) > r.repeat_until.day):
            raise ValidationError('The end date should be after the day of the month')

    @api.model
    def _get_recurring_fields(self): 
        return ['company_id', 'description', 'patient_id', 'product_id', 'recurrence_id',
                'price_unit', 'physician_id', 'diseas_id', 'treatment_id', 'department_id',
                'name', 'recurring_procedure', 'consumable_line_ids']

    def _get_weekdays(self, n=1):
        self.ensure_one()
        if self.repeat_unit == 'week':
            return [fn(n) for day, fn in DAYS.items() if self[day]]
        return [DAYS.get(self.repeat_weekday)(n)]

    @api.model
    def _get_next_recurring_dates(self, date_start, repeat_interval, repeat_unit, repeat_type, repeat_until, repeat_on_month, repeat_on_year, weekdays, repeat_day, repeat_week, repeat_month, **kwargs):
        count = kwargs.get('count', 1)
        rrule_kwargs = {'interval': repeat_interval or 1, 'dtstart': date_start}
        repeat_day = int(repeat_day)
        start = False
        dates = []
        if repeat_type == 'until':
            rrule_kwargs['until'] = repeat_until if repeat_until else fields.Date.today()
        else:
            rrule_kwargs['count'] = count

        if repeat_unit == 'week'\
            or (repeat_unit == 'month' and repeat_on_month == 'day')\
            or (repeat_unit == 'year' and repeat_on_year == 'day'):
            rrule_kwargs['byweekday'] = weekdays

        if repeat_unit == 'day':
            rrule_kwargs['freq'] = DAILY
        elif repeat_unit == 'month':
            rrule_kwargs['freq'] = MONTHLY
            if repeat_on_month == 'date':
                start = date_start - relativedelta(days=1)
                if repeat_type == 'until' and repeat_until > date_start:
                    delta = relativedelta(repeat_until, date_start)
                    count = delta.years * 12 + delta.months
                for i in range(count):
                    start = start.replace(day=min(repeat_day, monthrange(start.year, start.month)[1]))
                    if i == 0 and start < date_start:
                        # Ensure the next recurrence is in the future
                        start += relativedelta(months=repeat_interval)
                    dates.append(start)
                    start += relativedelta(months=repeat_interval)
                return dates
        elif repeat_unit == 'year':
            rrule_kwargs['freq'] = YEARLY
            month = list(MONTHS.keys()).index(repeat_month) + 1
            rrule_kwargs['bymonth'] = month
            if repeat_on_year == 'date':
                rrule_kwargs['bymonthday'] = min(repeat_day, MONTHS.get(repeat_month))
                rrule_kwargs['bymonth'] = month
        else:
            rrule_kwargs['freq'] = WEEKLY

        rules = rrule(**rrule_kwargs)
        return list(rules) if rules else []

    #PB: Get hour and minutes from float
    def pb_get_hour_minutes(self, value):
        str_value = str(value)
        hours = str_value.split('.')[0]
        minutes = ("%2d" % int(str(float("0." + str_value.split('.')[1]) * 60).split('.')[0])).replace(' ', '0')
        return (int(hours), int(minutes))

    def _new_procedure_values(self, procedure):
        self.ensure_one()
        fields_to_copy = self._get_recurring_fields()
        procedure_values = procedure.read(fields_to_copy).pop()
        create_values = {
            field: value[0] if isinstance(value, tuple) else value for field, value in procedure_values.items()
        }
        #create_values['stage_id'] = procedure.project_id.type_ids[0].id if procedure.project_id.type_ids else procedure.stage_id.id
        #create_values['user_id'] = False
        return create_values

    def _create_next_procedure(self):
        timezone = self.env.context.get('tz') or self.env.user.partner_id.tz or 'UTC'
        utcnow = TIMEZONE('utc').localize(datetime.utcnow()) # generic time
        utc = utcnow.astimezone(TIMEZONE('utc')).replace(tzinfo=None)
        user_time = utcnow.astimezone(TIMEZONE(timezone)).replace(tzinfo=None)
        offset = relativedelta(user_time, utc)
        offset_hours = offset.hours
        offset_minutes = offset.minutes

        for recurrence in self:
            procedure = recurrence.sudo().procedure_ids[-1]
            create_values = recurrence._new_procedure_values(procedure)

            hours, minutes = self.pb_get_hour_minutes(procedure.process_start_time)

            next_recurrence_date_time = datetime.combine(recurrence.next_recurrence_date, datetime.min.time())
            new_date = next_recurrence_date_time.replace(hour=hours, minute=minutes, second=0) - timedelta(hours=offset_hours, minutes=offset_minutes)
            create_values['date'] = new_date
            new_procedure = self.env['pb.patient.procedure'].sudo().create(create_values)
            new_procedure.onchange_date_and_product()

    def _set_next_recurrence_date(self, next_recurrence_date=False):
        if next_recurrence_date:
            today = next_recurrence_date
        else:
            today = fields.Date.today()
        tomorrow = today + relativedelta(days=1)
        for recurrence in self.filtered(
            lambda r:
            r.repeat_type == 'after' and r.recurrence_left >= 0
            or r.repeat_type == 'until' and r.repeat_until >= today
            or r.repeat_type == 'forever'
        ):
            if recurrence.repeat_type == 'after' and recurrence.recurrence_left == 0:
                recurrence.next_recurrence_date = False
            else:
                next_date = self._get_next_recurring_dates(tomorrow, recurrence.repeat_interval, recurrence.repeat_unit, recurrence.repeat_type, recurrence.repeat_until, recurrence.repeat_on_month, recurrence.repeat_on_year, recurrence._get_weekdays(), recurrence.repeat_day, recurrence.repeat_week, recurrence.repeat_month, count=1)
                recurrence.next_recurrence_date = next_date[0] if next_date else False

    @api.model
    def _cron_create_recurring_procedures(self):
        if not self.env.user.has_group('pb_hms_recurring_procedure.group_recurring_procedures'):
            return
        today = fields.Date.today()
        recurring_today = self.search([('next_recurrence_date', '<=', today)])
        recurring_today._create_next_procedure()
        for recurrence in recurring_today.filtered(lambda r: r.repeat_type == 'after'):
            recurrence.recurrence_left -= 1
        recurring_today._set_next_recurrence_date()

    @api.model_create_multi
    def create(self, vals_list):
        default_stage = dict()
        for vals in vals_list:
            if vals.get('repeat_number'):
                vals['recurrence_left'] = vals.get('repeat_number')
        res = super().create(vals_list)
        res._set_next_recurrence_date()
        return res

    def write(self, vals):
        if vals.get('repeat_number'):
            vals['recurrence_left'] = vals.get('repeat_number')

        res = super(PbProcedureRecurrence, self).write(vals)

        if 'next_recurrence_date' not in vals and not self.env.context.get('avoid_next_recurrence_date_update'):
            self._set_next_recurrence_date()
        return res

    def pb_create_recurring_procedures(self):
        # recurrence_left only means anything for repeat_type == 'after' (same
        # rule the cron uses); for 'forever'/'until' it's never populated, so
        # gating the loop on it there stopped the batch after a single
        # occurrence. Those two modes have no natural stopping point for a
        # synchronous button click, so cap the batch like the on-form preview
        # already does (see _compute_recurrence_message's min(5, ...)).
        MAX_BATCH = 5
        for rec in self:
            rec._set_next_recurrence_date()
            created = 0
            while (rec.next_recurrence_date
                   and (rec.repeat_type != 'after' or rec.recurrence_left >= 0)
                   and created < MAX_BATCH):
                rec._create_next_procedure()
                if rec.repeat_type == 'after':
                    rec.with_context(avoid_next_recurrence_date_update=True).recurrence_left -= 1
                rec._set_next_recurrence_date(rec.next_recurrence_date)
                created += 1
