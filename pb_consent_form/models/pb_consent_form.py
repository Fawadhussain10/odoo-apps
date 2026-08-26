# -*- encoding: utf-8 -*-

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

class PbConsentFormTags(models.Model):
    _name = "pb.consent.form.tag"
    _description = "Document Tags"

    name = fields.Char('Name', required=True, translate=True)
    color = fields.Integer('Color Index')

    _name_uniq = models.Constraint('unique (name)', "Tag name already exists !")


class PbConsentForm(models.Model):
    _name = 'pb.consent.form'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = 'Consent Form'
    _order = "id desc"

    READONLYSTATES = {'tosign': [('readonly', True)], 'signed': [('readonly', True)]}

    name = fields.Char(string='Name', required=True, readonly=True, default='/', copy=False)
    subject = fields.Char(string='Subject', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete="restrict", 
        help="Partner to whome Document asigned")
    user_id = fields.Many2one('res.users', string='User', ondelete="restrict", 
        help="User who provided Document")
    date = fields.Date('Date', default=fields.Date.today)
    consent_form_content = fields.Html('Consent Form Content')
    state = fields.Selection([
        ('draft','Draft'),
        ('tosign','To Sign'),
        ('signed','Signed')
    ], 'Status', default="draft", tracking=1) 
    template_id = fields.Many2one('pb.consent.form.template', string="Template", ondelete="restrict")
    tag_ids = fields.Many2many('pb.consent.form.tag', 'ditial_document_tag_rel', 'consent_form_id', 'tag_id', 
        string='Tags', help="Classify and analyze your Consent Forms")
    print_header_in_report = fields.Boolean(string="Print Header")
    company_id = fields.Many2one('res.company', ondelete='restrict', 
        string='Company', default=lambda self: self.env.company)

    pb_signed_on = fields.Datetime("Signed On", copy=False)
    pb_signature = fields.Binary("Signature", copy=False)
    pb_has_to_be_signed = fields.Boolean("Tobe Signed", default=True, copy=False)
    pb_access_url = fields.Char(compute="ge_pb_access_url", string='Portal Access Link')

    def ge_pb_access_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            if not rec.access_token:
                rec._portal_ensure_token()
            rec.pb_access_url = '%s/my/consentforms/%s?access_token=%s' % (base_url, rec.id, rec.access_token)

    def action_to_sign(self):
        self.name = self.env['ir.sequence'].next_by_code('pb.consent.form')
        self.state = 'tosign'

    def action_signed(self):
        self.state = 'signed'

    #PB: Add option to manage on onchange
    #Currently it is not working for new record
    # @api.onchange('template_id')
    # def onchange_template(self):
    #    rendered = self.env['mail.render.mixin']._render_template(self.template_id.consent_form_content, self._name, [self._origin.id])
    #    self.consent_form_content = rendered[self._origin.id]

    def apply_template(self):
        for rec in self:
            rendered = self.env['mail.render.mixin']._render_template(rec.template_id.consent_form_content, self._name, [rec.id])
            rec.consent_form_content = rendered[rec.id]

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for record in res:
            record._portal_ensure_token()
        return res

    def unlink(self):
        for data in self:
            if data.state!='draft':
                raise UserError(('Record Can be deleted in draft state only.'))
        return super(PbConsentForm, self).unlink()

    def get_portal_sign_url(self):
        return "/my/consentform/%s/sign?access_token=%s" % (self.id, self.access_token)

    def _get_report_base_filename(self):
        self.ensure_one()
        return '%s' % (self.name)

    def preview_consent_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': "/my/consentforms/%s" % (self.id),
        }

    def _get_portal_return_action(self):
        """ Return the action used to display record when returning from customer portal. """
        self.ensure_one()
        return self.env.ref('pb_consent_form.action_pb_consent_form')


class PbConsentFormTemplate(models.Model):
    _name = 'pb.consent.form.template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Consent Form Template'

    name = fields.Char("Template")
    consent_form_content = fields.Html('Consent Form Content')


class Partner(models.Model):
    _inherit = 'res.partner' 

    def action_open_consent_form(self):
        action = self.env["ir.actions.actions"]._for_xml_id("pb_consent_form.action_pb_consent_form")
        action['domain'] = [('partner_id','=',self.id)]
        action['context'] = {'default_partner_id': self.id}
        return action

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: