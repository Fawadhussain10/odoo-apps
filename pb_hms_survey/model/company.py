# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta
from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    survey_id = fields.Many2one("survey.survey", related='company_id.survey_id', string='Patient Feedback Survey', readonly=False)


class ResCompany(models.Model):
    _inherit = "res.company"

    survey_id = fields.Many2one("survey.survey", "Patient Feedback Survey")