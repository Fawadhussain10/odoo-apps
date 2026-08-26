# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError, MissingError, UserError
from odoo.fields import Domain


class DocumentDirectory(models.Model):
    _name = "document.directory"
    _description = "Document Directory"

    def _get_attachment_count(self):
        res = {}
        AttachmentObj = self.env['ir.attachment']
        for rec in self.sudo():
            attchement_count = 0
            domain = [('directory_id','=',rec.id)]
            if rec.res_model and rec.res_model.name:
                model_domain = [('res_model', '=', rec.res_model.model)]
                domain = Domain.OR([domain, model_domain])
            rec.attchement_count = AttachmentObj.search_count(domain)

    name = fields.Char(required=True)
    parent_id = fields.Many2one('document.directory',string='Parent Directory', index=True, ondelete='cascade')
    children_ids = fields.One2many('document.directory', 'parent_id', string='Children', copy=True)
    user_ids = fields.Many2many('res.users', 'document_user_rel', 'user_id', 'doc_id', string="Users")
    description = fields.Text(string='Description')
    tag_ids = fields.Many2many('pb.document.tag', 'directory_tag_rel', 'directory_id', 'tag_id', 
        string='Tags', help="Classify and analyze your Document")
    department_id = fields.Many2one('hr.department', string='Department', ondelete='restrict')
    attchement_count = fields.Integer(compute='_get_attachment_count', string="Number of documents attached")
    res_model = fields.Many2one('ir.model', 'Model', ondelete='cascade')

    @api.constrains('res_model')
    def _check_model(self):
        if self.res_model:
            directories = self.search([('id', '!=', self.id),('res_model', '=',self.res_model.id)])
            if directories:
                raise ValidationError(_('You can have only one directory for a model.'))
     
    def action_view_attachments(self):
        self = self.sudo()
        domain = [('directory_id','=',self.id)]
        if self.res_model and self.res_model.name:
            model_domain = [('res_model', '=', self.res_model.model)]
            domain = Domain.OR([domain, model_domain])
        attachments = self.env['ir.attachment'].search(domain)
        action = self.env["ir.actions.actions"]._for_xml_id("base.action_attachment")
        action['domain'] = [('id', 'in', attachments.ids)]
        action['context'] = {
                'default_res_model': self.res_model.model,
                'default_directory_id': self.id,
                'default_is_document': True}
        return action


    display_name = fields.Char(compute='_compute_display_name', recursive=True)

    @api.depends('name', 'parent_id.display_name')
    def _compute_display_name(self):
        def get_names(directory):
            """ Return the list [cat.name, cat.parent_id.name, ...] """
            res = []
            while directory:
                # name reads back as False (not '') when unset - guard so
                # " / ".join() below doesn't choke on a bool in the list.
                res.append(directory.name or '')
                directory = directory.parent_id
            return res
        for directory in self:
            directory.display_name = " / ".join(reversed(get_names(directory)))

    @api.constrains('parent_id')
    def _check_directory_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_('Error ! You cannot create recursive Directory.'))
        return True


class Tag(models.Model):
    _name = "pb.document.tag"
    _description = "Document Tags"

    name = fields.Char('Name', required=True, translate=True)
    color = fields.Integer('Color Index')

    _name_uniq = models.Constraint('unique (name)', "Tag name already exists !")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: