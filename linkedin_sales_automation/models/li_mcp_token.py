import hashlib
import secrets
from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError

from .li_common import utc_now

TOKEN_PREFIX = 'lism_'
LAST_USED_RESOLUTION = timedelta(minutes=1)


def _hash(plain):
    return hashlib.sha256((plain or '').encode()).hexdigest()


class LiMcpToken(models.Model):
    """Bearer tokens of the Odoo MCP endpoint.

    Only a SHA-256 hash is stored; the plain value is shown once, when the
    token is generated. These tokens are not passwords nor API keys: they open
    /li_sales/mcp only, never /xmlrpc, /jsonrpc or /web/session.
    """
    _name = 'li.mcp.token'
    _description = 'MCP endpoint token'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, help='Where the token is used, e.g. "Claude – sales account".')
    token_hash = fields.Char(required=True, readonly=True, index=True, copy=False)
    token_hint = fields.Char('Token', readonly=True, copy=False, help='First characters, to recognise the token.')
    active = fields.Boolean(default=True)
    last_used = fields.Datetime(readonly=True, copy=False)
    expiry = fields.Datetime(help='Optional. After this date the token is refused.')

    _sql_constraints = [('token_hash_uniq', 'unique(token_hash)', 'Token collision, generate again.')]

    @api.model
    def _generate(self, name, expiry=False):
        """Create a token and return (record, plain value)."""
        plain = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = self.sudo().create({'name': name, 'token_hash': _hash(plain), 'expiry': expiry,
                                    'token_hint': plain[:len(TOKEN_PREFIX) + 6] + '…'})
        return token, plain

    @api.model
    def _authenticate(self, plain):
        """Return the active, unexpired token matching plain, or an empty recordset."""
        if not plain or not plain.startswith(TOKEN_PREFIX):
            return self.browse()
        token = self.sudo().with_context(active_test=True).search([('token_hash', '=', _hash(plain))], limit=1)
        if not token or (token.expiry and token.expiry < utc_now()):
            return self.browse()
        now = utc_now()
        if not token.last_used or now - token.last_used > LAST_USED_RESOLUTION:
            token.last_used = now
        return token

    @api.model
    def _technical_user(self):
        """The technical user, allowed in every company: one Claude connector
        serves the LinkedIn profiles of all companies of the database."""
        env = self.env(user=SUPERUSER_ID, su=True)  # may be called before the request has a user
        user = env.ref('linkedin_sales_automation.user_li_mcp_agent')
        companies = env['res.company'].search([])
        if companies - user.company_ids:
            user.write({'company_ids': [(6, 0, companies.ids)]})
        return self.env['res.users'].sudo().browse(user.id)


class LiMcpTokenWizard(models.TransientModel):
    _name = 'li.mcp.token.wizard'
    _description = 'Generate an MCP token'

    name = fields.Char(required=True, default='Claude')
    expiry = fields.Datetime()
    plain_token = fields.Char(readonly=True)
    connector_url = fields.Char('Connector URL', readonly=True,
                                help='Paste this URL in Claude (Settings > Connectors > Add custom connector). It '
                                     'holds the token: keep it secret like a password.')
    token_id = fields.Many2one('li.mcp.token', readonly=True)

    def action_generate(self):
        self.ensure_one()
        if self.token_id:
            raise UserError(_('This token was already generated.'))
        token, plain = self.env['li.mcp.token']._generate(self.name, self.expiry)
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        self.write({'token_id': token.id, 'plain_token': plain, 'connector_url': '%s/li_sales/mcp/%s' % (base, plain)})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'name': _('Copy the token now'),
        }

    def action_done(self):
        # never keep the plain value once the dialog is closed
        self.write({'plain_token': False, 'connector_url': False})
        return {'type': 'ir.actions.act_window_close'}
