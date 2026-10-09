from odoo import fields, models


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
