# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class Attachment(models.Model):
    _inherit = "ir.attachment"

    is_document = fields.Boolean("Is Document")
    directory_id = fields.Many2one('document.directory', string='Directory', ondelete='restrict')
    description = fields.Text(string='Description')
    tag_ids = fields.Many2many('pb.document.tag', 'pb_attachment_document_tag_rel', 'document_id', 'tag_id', 
        string='Tags', help="Classify and analyze your Document")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: