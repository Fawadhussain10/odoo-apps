import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import UserError, ValidationError

from .li_common import linkedin_username, normalize_connector, utc_now


class LiProfile(models.Model):
    _name = 'li.profile'
    _description = 'LinkedIn Profile'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    linkedin_url = fields.Char('LinkedIn URL', required=True, tracking=True)
    owner_id = fields.Many2one('res.users', 'Owner', required=True, default=lambda self: self.env.user,
                               tracking=True)
    account_key = fields.Char(required=True, tracking=True,
                              help='Short key, e.g. "taha" or "rep1". Names this account in work items and '
                                   'in the engine folder.')
    my_display_name = fields.Char('My display name',
                                  help='Name shown on LinkedIn for this account; used to tell our '
                                       'messages from the prospect\'s when reading a thread.')
    connection_state = fields.Selection([
        ('not_connected', 'Not connected'),
        ('connected', 'Connected'),
        ('reconnect_needed', 'Reconnect needed'),
        ('restricted', 'Restricted'),
    ], default='not_connected', required=True, readonly=True, tracking=True, copy=False)
    account_type = fields.Selection([
        ('free', 'Free'),
        ('premium', 'Premium'),
        ('sales_navigator', 'Sales Navigator'),
    ], required=True, default='free')
    home_timezone = fields.Selection(_tz_get, 'Home time zone',
                                     help='Account owner\'s time zone, display only. Sending times '
                                          'come from each persona\'s target time zone.')
    signature = fields.Text(help='Optional sign-off appended to messages.')
    persona_ids = fields.One2many('li.persona', 'linkedin_profile_id', 'Personas')
    persona_count = fields.Integer(compute='_compute_persona_count')
    active_persona_count = fields.Integer('Active personas', compute='_compute_persona_count')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True,
                                 default=lambda self: self.env.company)

    # technical
    last_send_at = fields.Datetime(readonly=True, copy=False)
    send_gap_seconds = fields.Integer(readonly=True, copy=False,
                                      help='Random gap drawn at the last send.')
    last_test_date = fields.Datetime(readonly=True, copy=False)
    last_test_result = fields.Text(readonly=True, copy=False)

    _sql_constraints = [
        ('linkedin_url_uniq', 'unique(linkedin_url)', 'This LinkedIn URL is already registered.'),
        ('account_key_uniq', 'unique(account_key)', 'The account key must be unique.'),
    ]

    @api.depends('persona_ids', 'persona_ids.state')
    def _compute_persona_count(self):
        for profile in self:
            profile.persona_count = len(profile.persona_ids)
            profile.active_persona_count = len(profile.persona_ids.filtered(lambda p: p.state == 'active'))

    @api.constrains('account_key')
    def _check_account_key(self):
        for profile in self:
            key = profile.account_key or ''
            if not key.replace('-', '').replace('_', '').isalnum() or key.lower() != key:
                raise ValidationError(_('The account key may only contain lowercase letters, digits, "-" and "_".'))

    @api.onchange('name')
    def _onchange_name_account_key(self):
        if self.name and not self.account_key:
            self.account_key = re.sub(r'[^a-z0-9]+', '-', self.name.lower()).strip('-')[:40] or False

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def _notify(self, title, message, kind):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': kind, 'sticky': kind != 'success',
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    def action_pause_agents(self):
        for profile in self:
            profile.persona_ids._pause_all_agents(reason=_('LinkedIn profile %s paused', profile.name))
        return True

    def action_open_personas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Personas'),
            'res_model': 'li.persona',
            'view_mode': 'list,form',
            'domain': [('linkedin_profile_id', '=', self.id)],
            'context': {'default_linkedin_profile_id': self.id},
        }

    # ------------------------------------------------------------------
    # Helpers used by the MCP tools
    # ------------------------------------------------------------------
    @api.model
    def _find_by_account(self, account):
        """The profile named by its account key (or name), as used in work items."""
        wanted = normalize_connector(account)
        if not wanted:
            return self.browse()
        if wanted.isdigit():                    # the profile's number works too
            by_id = self.search([('id', '=', int(wanted))])
            if by_id:
                return by_id
        return self.search([]).filtered(
            lambda p: wanted in (normalize_connector(p.account_key), normalize_connector(p.name)))[:1]

    def _account_matches(self, account):
        self.ensure_one()
        return normalize_connector(account) in (normalize_connector(self.account_key), normalize_connector(self.name))

    def _set_reconnect_needed(self, error):
        """Session expired on LinkedIn: flag the profile, pause its agents, notify the owner."""
        for profile in self:
            if profile.connection_state == 'reconnect_needed':
                continue
            profile.connection_state = 'reconnect_needed'
            profile.persona_ids._pause_all_agents(reason=_('LinkedIn session expired on %s', profile.name))
            self.env['li.work.item'].sudo()._cancel_open([('linkedin_profile_id', '=', profile.id),
                                                          ('state', '=', 'released')],
                                                         reason=_('LinkedIn session expired'))
            profile.message_post(body=_('LinkedIn session expired. %(how)s Detail: %(error)s',
                                        how=profile._reconnect_hint(), error=error))
            profile.activity_schedule(
                'mail.mail_activity_data_todo', user_id=profile.owner_id.id,
                summary=_('Reconnect LinkedIn account %s', profile.account_key),
                note=_('The LinkedIn session of %(name)s expired. %(how)s Then run the agents again.',
                       name=profile.name, how=profile._reconnect_hint()))

    def _reconnect_hint(self):
        self.ensure_one()
        if self.execution_mode == 'chrome':
            return _('Log in to LinkedIn in Chrome as this account; Claude checks the account at the start of '
                     'its next run.')
        return _('Open the profile and press Reconnect LinkedIn.')

    def _set_restricted(self, error):
        """LinkedIn restricted the account: stop everything on it and tell the owner.
        No login can lift a restriction; the owner resolves it on linkedin.com."""
        for profile in self:
            if profile.connection_state == 'restricted':
                continue
            profile.connection_state = 'restricted'
            profile.persona_ids._pause_all_agents(reason=_('LinkedIn restricted %s', profile.name))
            self.env['li.work.item'].sudo()._cancel_open([('linkedin_profile_id', '=', profile.id)],
                                                         reason=_('LinkedIn restricted the account'))
            profile.message_post(body=_('LinkedIn restricted this account. Nothing more is done on it. Detail: %s',
                                        error))
            profile.activity_schedule(
                'mail.mail_activity_data_todo', user_id=profile.owner_id.id,
                summary=_('LinkedIn restricted %s', profile.account_key),
                note=_('LinkedIn restricted the account %(name)s and asks for identity verification. Resolve it '
                       'on linkedin.com in your own browser. %(how)s',
                       name=profile.name, how=profile._reconnect_hint()))
