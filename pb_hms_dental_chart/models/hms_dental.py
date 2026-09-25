# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_
from odoo.exceptions import UserError


class PbHmsTooth(models.Model):
    _inherit="pb.hms.tooth"

    image = fields.Binary(string="Image")


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:   