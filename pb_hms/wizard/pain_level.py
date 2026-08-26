# coding: utf-8

from odoo import models, api, fields

class PbPainLevel(models.TransientModel):
    _name = 'pb.pain.level'
    _description = "Pain Level Diagram"

    name = fields.Char()