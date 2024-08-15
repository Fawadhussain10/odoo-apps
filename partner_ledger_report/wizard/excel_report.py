# -*- coding: utf-8 -*-

from odoo import fields, models


class ExcelReport(models.TransientModel):
    _name = "excel.report"
    _description="Excel Report"

    excel_file = fields.Binary('Excel Report')
    file_name = fields.Char('Excel File', size=64)

