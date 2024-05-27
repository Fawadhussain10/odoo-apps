from odoo import api, fields, models, _


class OkrForm(models.Model):
    _name = 'okr.comp'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "OKR Competencies"

    name = fields.Char(string='Name')
    bench1 = fields.Char(string='Benchmark')
    rate1 = fields.Selection([
        ('one', '1'),
        ('two', '2'),
        ('three', '3'),
        ('four', '4'),
    ], string='Rating', default=False)
    percentage1 = fields.Integer(string='Percentage')
    result1 = fields.Selection([
        ('zero', ' '),
        ('pas', 'Pass'),
        ('fail', 'Fail'),
    ], string='Result', default=False)
    date1 = fields.Date(string='Date', default=fields.Date.today())
    attach1 = fields.Binary(string='Attachment')
    note1 = fields.Text(string='Note')

    @api.onchange('rate1')
    def percentage_get(self):
        for rec in self:
            if rec.rate1 == 'one':
                rec.percentage1 = 25
            if rec.rate1 == 'two':
                rec.percentage1 = 50
            if rec.rate1 == 'three':
                rec.percentage1 = 75
            if rec.rate1 == 'four':
                rec.percentage1 = 100

            if rec.rate1 in ['one', 'two']:
                rec.result1 = 'fail'
            elif not rec.rate1:
                rec.result1 = 'zero'
            else:
                rec.result1 = 'pas'
