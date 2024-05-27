from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import datetime, time


class OkrForm(models.Model):
    _name = 'okr.time'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Time Period"

    quarter = fields.Selection([
        ('q1', "Q1"),
        ('q2', "Q2"),
        ('q3', "Q3"),
        ('q4', "Q4"),
    ], string='Quarter', required=True)
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    year = fields.Char(string='Year', default=lambda self: str(datetime.now().year))

    @api.constrains('quarter', 'start_date', 'end_date')
    def _check_quarter_dates(self):
        for record in self:
            if record.quarter == 'q1':
                if not (datetime(int(record.year), 1, 1) <= datetime.combine(record.start_date,
                                                                             datetime.min.time()) <= datetime(
                    int(record.year), 3, 31)) or not (
                        datetime(int(record.year), 1, 1) <= datetime.combine(record.end_date,
                                                                             datetime.min.time()) <= datetime(
                    int(record.year), 3, 31)):
                    raise ValidationError("Quarter 1 months range is from January to March.")
            elif record.quarter == 'q2':
                if not (datetime(int(record.year), 4, 1) <= datetime.combine(record.start_date,
                                                                             datetime.min.time()) <= datetime(
                    int(record.year), 6, 30)) or not (
                        datetime(int(record.year), 4, 1) <= datetime.combine(record.end_date,
                                                                             datetime.min.time()) <= datetime(
                    int(record.year), 6, 30)):
                    raise ValidationError("Quarter 2 months range is from April to June.")
            elif record.quarter == 'q3':
                if not (datetime(int(record.year), 7, 1) <= datetime.combine(record.start_date,
                                                                             datetime.min.time()) <= datetime(
                    int(record.year), 9, 30)) or not (
                        datetime(int(record.year), 7, 1) <= datetime.combine(record.end_date,
                                                                             datetime.min.time()) <= datetime(
                    int(record.year), 9, 30)):
                    raise ValidationError("Quarter 3 months range is from July to September.")
            elif record.quarter == 'q4':
                if not (datetime(int(record.year), 10, 1) <= datetime.combine(record.start_date,
                                                                              datetime.min.time()) <= datetime(
                    int(record.year), 12, 31)) or not (
                        datetime(int(record.year), 10, 1) <= datetime.combine(record.end_date,
                                                                              datetime.min.time()) <= datetime(
                    int(record.year), 12, 31)):
                    raise ValidationError("Quarter 4 months range is from October to December.")
