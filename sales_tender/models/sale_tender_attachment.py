# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleTenderAttachment(models.Model):
    _name = 'sale.tender.attachment'
    _description = 'Tender Attachment'

    tender_id = fields.Many2one(
        'sale.tender', string='Tender', required=True, ondelete='cascade')
    attachment_type = fields.Selection([
        ('tender_document', 'Tender Document'),
        ('bank_guarantee_format', 'Bank Guarantee Format'),
        ('other', 'Other'),
    ], string='Type', required=True, default='other')
    name = fields.Char(string='Description')
    filename = fields.Char(string='Filename')
    datas = fields.Binary(string='File', attachment=True)
