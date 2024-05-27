from odoo import api, fields, models, _


class OkrForm(models.Model):
    _name = 'okr.objective'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "OKR Objectives"

    name = fields.Char(string='Name', required=True)
    bench = fields.Char(string='Benchmark', required=True)
    rate = fields.Selection([
        ('one', '1'),
        ('two', '2'),
        ('three', '3'),
        ('four', '4'),
    ], string='Rating', required=True, default=False)
    percentage = fields.Integer(string='Percentage')
    result = fields.Selection([
        ('zero', ' '),
        ('pas', 'Pass'),
        ('fail', 'Fail'),
    ], string='Result', default=False)
    date = fields.Date(string='Date', default=fields.Date.today())
    attach = fields.Binary(string='Attachment')
    note = fields.Text(string='Note')

    @api.onchange('rate')
    def percentage_get(self):
        for rec in self:
            if rec.rate == 'one':
                rec.percentage = 25
            if rec.rate == 'two':
                rec.percentage = 50
            if rec.rate == 'three':
                rec.percentage = 75
            if rec.rate == 'four':
                rec.percentage = 100

            if rec.rate in ['one', 'two']:
                rec.result = 'fail'
            elif not rec.rate:
                rec.result = 'zero'
            else:
                rec.result = 'pas'

