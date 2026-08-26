# -*- encoding: utf-8 -*-

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError


class CertificateTag(models.Model):
    _name = "certificate.tag"
    _description = "Certificate Tags"

    name = fields.Char('Name', required=True, translate=True)
    color = fields.Integer('Color Index')

    _name_uniq = models.Constraint('unique (name)', "Tag name already exists !")

class CertificateManagement(models.Model):
    _name = 'certificate.management'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Certificate Management'
    _order = "id desc"

    READONLYSTATES = {'done': [('readonly', True)]}

    name = fields.Char(string='Name', required=True, readonly=True, default='/', copy=False)
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete="restrict", 
        help="Partner to whome certificate asigned")
    user_id = fields.Many2one('res.users', string='User', ondelete="restrict", 
        help="User who provided certificate")
    date = fields.Datetime('Date', default=fields.Datetime.now)
    certificate_content = fields.Html('Certificate Content')
    state = fields.Selection([
        ('draft','Draft'),
        ('cancel','Cancel'),
        ('done','Done')
    ], 'Status', default="draft", tracking=1) 
    template_id = fields.Many2one('certificate.template', string="Certificate Template", ondelete="restrict")
    tag_ids = fields.Many2many('certificate.tag', 'certificate_tag_rel', 'certificate_id', 'tag_id', 
        string='Tags', help="Classify and analyze your Certificates")
    print_header_in_report = fields.Boolean(string="Print Header", default=False)
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Company', default=lambda self: self.env.company)

    def action_done(self):
        self.name = self.env['ir.sequence'].next_by_code('certificate.management')
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancel'

    def action_reset_to_draft(self):
        self.state = 'draft'

    #PB: Add option to manage on onchange
    #Currently it is not working for new record
    # @api.onchange('template_id')
    # def onchange_template(self):
    #    rendered = self.env['mail.render.mixin']._render_template(self.template_id.certificate_content, 'certificate.management', [self._origin.id])
    #    self.certificate_content = rendered[self._origin.id]

    def apply_template(self):
        for rec in self:
            rendered = self.env['mail.render.mixin']._render_template(rec.template_id.certificate_content, 'certificate.management', [rec.id])
            rec.certificate_content = rendered[rec.id]

    def unlink(self):
        for data in self:
            if data.state in ['done']:
                raise UserError(('You can only delete in draft'))
        return super(CertificateManagement, self).unlink()


class CertificateTemplate(models.Model):
    _name = 'certificate.template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Certificate Template'

    name = fields.Char("Template")
    certificate_content = fields.Html('Certificate Content')


class Partner(models.Model):
    _inherit = 'res.partner' 

    def action_open_certificate(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_certification.action_certificate_management")
        action['domain'] = [('partner_id','=',self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: