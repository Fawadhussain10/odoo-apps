import secrets

from odoo import api, fields, models


class LiService(models.Model):
    _name = 'li.service'
    _description = 'LinkedIn Sales Service'
    _order = 'sequence, name'

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    description = fields.Text(required=True, help='Short pitch the AI uses when writing messages.')
    value_points = fields.Text(help='Proof points / case studies for the AI.')
    crm_team_id = fields.Many2one('crm.team', 'Default sales team')
    crm_tag_ids = fields.Many2many('crm.tag', string='CRM tags')
    active = fields.Boolean(default=True)
    contact_phone = fields.Char('Phone number to give', help='Given to a prospect who asks for our phone number '
                                                           '(or how to call us). Never offered unasked.')
    contact_email = fields.Char('Email address to give', help='Given to a prospect who asks for our email address.')
    # Portfolio: LinkedIn messages sent by the engine are text only, so it goes out as a link
    portfolio_file = fields.Binary('Portfolio file', attachment=True,
                                   help='PDF or presentation. Odoo gives it a private link that Claude puts in a '
                                        'message when the prospect asks for a portfolio, examples or past work.')
    portfolio_filename = fields.Char()
    portfolio_url = fields.Char('Portfolio link',
                                help='Optional: your own link (website, Drive, Behance…). Used instead of the file.')
    portfolio_token = fields.Char(copy=False, readonly=True)
    portfolio_link = fields.Char('Link sent to prospects', compute='_compute_portfolio_link')

    @api.depends('portfolio_file', 'portfolio_url', 'portfolio_token', 'portfolio_filename')
    def _compute_portfolio_link(self):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        for service in self:
            if (service.portfolio_url or '').strip():
                service.portfolio_link = service.portfolio_url.strip()
            elif service.portfolio_file and service.portfolio_token:
                service.portfolio_link = '%s/li_sales/portfolio/%s' % (base, service.portfolio_token)
            else:
                service.portfolio_link = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('portfolio_file'):
                vals['portfolio_token'] = secrets.token_urlsafe(24)
        return super().create(vals_list)

    def write(self, vals):
        if 'portfolio_file' in vals:            # a new file gets a new link; removing it ends the old one
            vals = dict(vals, portfolio_token=secrets.token_urlsafe(24) if vals['portfolio_file'] else False)
        return super().write(vals)


class LiWeekday(models.Model):
    _name = 'li.weekday'
    _description = 'Working day'
    _order = 'code'

    name = fields.Char(required=True, translate=True)
    code = fields.Integer(required=True, help='0 = Monday … 6 = Sunday (Python weekday()).')

    _sql_constraints = [('code_uniq', 'unique(code)', 'Each weekday exists once.')]


class LiTargetTag(models.Model):
    _name = 'li.target.tag'
    _description = 'Persona targeting tag'
    _order = 'kind, name'

    name = fields.Char(required=True)
    kind = fields.Selection([
        ('seniority', 'Seniority'),
        ('industry', 'Industry'),
        ('location', 'Location'),
    ], required=True)
    color = fields.Integer()

    _sql_constraints = [('name_kind_uniq', 'unique(name, kind)', 'This tag already exists.')]


class LiCompanySize(models.Model):
    _name = 'li.company.size'
    _description = 'Company size range'
    _order = 'sequence'

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)


class LiMessageTemplate(models.Model):
    _name = 'li.message.template'
    _description = 'Reusable questionnaire step'
    _order = 'name'

    name = fields.Char(required=True)
    objective = fields.Text()
    template = fields.Text(help='Placeholders: {first_name}, {company}, {service}')
    trigger = fields.Selection([('after_accept', 'After accept'), ('after_reply', 'After reply')],
                               default='after_reply')
    is_question = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
