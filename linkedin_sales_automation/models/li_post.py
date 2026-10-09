"""LinkedIn posts: idea -> Claude's draft -> a person approves -> published
at the scheduled time (built-in engine: create_post in the background; Claude
in Chrome: a publish_post item). Reactions, comments and reposts are re-read
weekly within the read budget."""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.base.models.res_partner import _tz_get
from odoo.exceptions import UserError

from .li_common import to_local, utc_now

POST_STATES = [
    ('idea', 'Idea'),
    ('draft', 'Draft'),
    ('approved', 'Approved'),
    ('scheduled', 'Scheduled'),
    ('publishing', 'Publishing'),
    ('published', 'Published'),
    ('failed', 'Failed'),
]
POST_MAX_CHARS = 3000
STATS_EVERY = timedelta(days=7)
STATS_FOR = timedelta(days=90)
MAX_PUBLISH_ATTEMPTS = 3
IMAGE_LINK_HOURS = 6

_NUMBER = r'(\d[\d,.]*\s*[KkMm]?)'


def _number(value):
    value = value.replace(',', '').strip()
    factor = 1
    if value[-1:] in 'Kk':
        factor, value = 1000, value[:-1]
    elif value[-1:] in 'Mm':
        factor, value = 1000000, value[:-1]
    try:
        return int(round(float(value.strip()) * factor))
    except ValueError:
        return 0


def parse_post_stats(text):
    """(reactions, comments, reposts) from the text of a post page (English UI)."""
    text = text or ''
    comments = re.search(_NUMBER + r'\s+comments?\b', text, re.I)
    reposts = re.search(_NUMBER + r'\s+reposts?\b', text, re.I)
    reactions = re.search(_NUMBER + r'\s+reactions?\b', text, re.I)
    if reactions:
        reaction_count = _number(reactions.group(1))
    else:
        others = re.search(r'\band\s+' + _NUMBER + r'\s+others?\b', text, re.I)
        reaction_count = _number(others.group(1)) + 1 if others else 0
    return (reaction_count, _number(comments.group(1)) if comments else 0,
            _number(reposts.group(1)) if reposts else 0)


class LiPost(models.Model):
    _name = 'li.post'
    _description = 'LinkedIn post'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'scheduled_at desc, id desc'

    name = fields.Char('Title', required=True, tracking=True, help='Short name of the idea, for lists.')
    linkedin_profile_id = fields.Many2one('li.profile', 'LinkedIn Profile', required=True, index=True,
                                          ondelete='cascade', tracking=True)
    execution_mode = fields.Selection(related='linkedin_profile_id.execution_mode')
    company_id = fields.Many2one(related='linkedin_profile_id.company_id', store=True, index=True)
    service_id = fields.Many2one('li.service', help='Optional: the service the post is about.')
    idea = fields.Text(help='What the post should say: topic, angle, key points, call to action. Claude writes '
                            'the draft from this.')
    text = fields.Text('Post text', tracking=True)
    char_count = fields.Integer(compute='_compute_char_count')
    image = fields.Image(max_width=2048, max_height=2048, attachment=True)
    image_filename = fields.Char()
    scheduled_at = fields.Datetime('Publish at', tracking=True,
                                   help='Empty: published at the first chance after approval.')
    schedule_tz = fields.Selection(_tz_get, 'Time zone', default=lambda self: self.env.user.tz or 'UTC',
                                   help='Time zone the publish time is shown in.')
    scheduled_local = fields.Char('Publish at (local)', compute='_compute_scheduled_local')
    state = fields.Selection(POST_STATES, default='idea', required=True, index=True, tracking=True)
    approved_by = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    post_url = fields.Char('Post URL', readonly=True, tracking=True)
    published_at = fields.Datetime(readonly=True, index=True)
    publish_attempts = fields.Integer(readonly=True)
    publish_started = fields.Datetime(readonly=True)
    reactions = fields.Integer(readonly=True)
    comments = fields.Integer(readonly=True)
    reposts = fields.Integer(readonly=True)
    stats_checked_at = fields.Datetime('Stats read at', readonly=True)
    error = fields.Text(readonly=True)
    image_token_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    image_token_expiry = fields.Datetime(readonly=True, copy=False, groups='base.group_system')

    @api.depends('text')
    def _compute_char_count(self):
        for post in self:
            post.char_count = len(post.text or '')

    @api.depends('scheduled_at', 'schedule_tz')
    def _compute_scheduled_local(self):
        for post in self:
            post.scheduled_local = (to_local(post.scheduled_at, post.schedule_tz).strftime('%a %d %b %Y %H:%M')
                                    + ' (%s)' % (post.schedule_tz or 'UTC')) if post.scheduled_at else False

    # ------------------------------------------------------------------
    # Rights and buttons
    # ------------------------------------------------------------------
    def _check_approver(self):
        user = self.env.user
        for post in self:
            if not (user.has_group('linkedin_sales_automation.group_li_manager')
                    or post.linkedin_profile_id.owner_id == user):
                raise UserError(_('Only the owner of %s or a LinkedIn Sales Manager can approve its posts.',
                                  post.linkedin_profile_id.name))

    def action_approve(self):
        self._check_approver()
        for post in self:
            if post.state not in ('draft', 'failed'):
                raise UserError(_('Only a draft (or a failed post) can be approved.'))
            text = (post.text or '').strip()
            if not text:
                raise UserError(_('Write the post text first.'))
            if len(text) > POST_MAX_CHARS:
                raise UserError(_('LinkedIn posts hold at most %s characters (this one has %s).',
                                  POST_MAX_CHARS, len(text)))
            post.sudo().write({'state': 'scheduled' if post.scheduled_at else 'approved',
                               'approved_by': self.env.user.id, 'approved_at': utc_now(), 'error': False,
                               'publish_attempts': 0})
            prefix = _('Approve post')
            post.activity_ids.filtered(lambda a: a.summary and a.summary.startswith(prefix)).action_feedback(
                feedback=_('Approved by %s', self.env.user.name))
        return True

    def action_back_to_draft(self):
        for post in self:
            if post.state in ('publishing', 'published'):
                raise UserError(_('A published post cannot go back to draft.'))
            post.sudo().write({'state': 'draft' if post.text else 'idea', 'approved_by': False, 'approved_at': False})
        return True

    def action_back_to_idea(self):
        for post in self:
            if post.state in ('publishing', 'published'):
                raise UserError(_('A published post cannot go back to idea.'))
            post.sudo().write({'state': 'idea', 'approved_by': False, 'approved_at': False})
        return True

    def action_open_post(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.post_url, 'target': 'new'}

    def write(self, vals):
        locked = {'text', 'image', 'linkedin_profile_id'} & set(vals)
        if locked and not self.env.su and any(p.state in ('approved', 'scheduled', 'publishing', 'published')
                                              for p in self):
            raise UserError(_('Approved and published posts cannot be changed: set the post back to draft first.'))
        return super().write(vals)

    # ------------------------------------------------------------------
    # Queue helpers (engine and Chrome)
    # ------------------------------------------------------------------
    @api.model
    def _due_domain(self, profile):
        return [('linkedin_profile_id', '=', profile.id), ('state', 'in', ('approved', 'scheduled')),
                '|', ('scheduled_at', '=', False), ('scheduled_at', '<=', utc_now())]

    @api.model
    def _stats_domain(self, profile):
        now = utc_now()
        return [('linkedin_profile_id', '=', profile.id), ('state', '=', 'published'), ('post_url', '!=', False),
                ('published_at', '>', now - STATS_FOR),
                '|', ('stats_checked_at', '=', False), ('stats_checked_at', '<', now - STATS_EVERY)]

    def _mark_published(self, post_url=None, note=None):
        self.ensure_one()
        post = self.sudo()
        post.write({'state': 'published', 'post_url': post_url or False, 'published_at': utc_now(), 'error': note or False})
        post.message_post(body=_('Published on LinkedIn%s', (': %s' % post_url) if post_url else
                                 _(' (LinkedIn showed no link: add the post URL by hand if needed)')))

    def _publish_failed(self, error, retry_safe):
        """retry_safe: nothing reached LinkedIn, the post goes back to the queue
        (at most 3 attempts). Otherwise the outcome is unknown: never retried."""
        self.ensure_one()
        post = self.sudo()
        attempts = post.publish_attempts + 1
        if retry_safe and attempts < MAX_PUBLISH_ATTEMPTS:
            post.write({'state': 'scheduled' if post.scheduled_at else 'approved', 'publish_attempts': attempts,
                        'error': error, 'publish_started': False})
            return False
        post.write({'state': 'failed', 'publish_attempts': attempts, 'publish_started': False,
                    'error': error if retry_safe else _('Outcome unknown — check LinkedIn before posting again. %s',
                                                         error)})
        post.message_post(body=_('Publishing failed: %s', post.error))
        post.activity_schedule('mail.mail_activity_data_todo', user_id=post.linkedin_profile_id.owner_id.id,
                               summary=_('Post not published: %s', post.name), note=post.error)
        return True

    def _set_stats(self, reactions, comments, reposts):
        self.sudo().write({'reactions': reactions, 'comments': comments, 'reposts': reposts,
                           'stats_checked_at': utc_now()})

    @api.model
    def _cron_recover_publishing(self):
        """Publishing still in progress after 15 minutes: Odoo stopped mid-way."""
        for post in self.sudo().search([('state', '=', 'publishing'),
                                        ('publish_started', '<', utc_now() - timedelta(minutes=15))]):
            post._publish_failed(_('Odoo stopped while the post was being published'), retry_safe=False)

    # ------------------------------------------------------------------
    # Signed image link (Claude in Chrome downloads the image without an Odoo login)
    # ------------------------------------------------------------------
    def _signed_image_url(self):
        """A new random link to this post's image only, valid for 6 hours. Odoo
        keeps only its hash; a new link replaces the previous one."""
        self.ensure_one()
        if not self.image:
            return ''
        token = secrets.token_urlsafe(32)
        self.sudo().write({'image_token_hash': hashlib.sha256(token.encode()).hexdigest(),
                           'image_token_expiry': utc_now() + timedelta(hours=IMAGE_LINK_HOURS)})
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        return '%s/li_sales/post_image/%s/%s' % (base, self.id, token)

    def _image_for_token(self, token):
        """The image bytes (base64) when the token is valid, else False."""
        self.ensure_one()
        post = self.sudo()
        if not (token and post.image and post.image_token_hash and post.image_token_expiry):
            return False
        if post.image_token_expiry < utc_now():
            return False
        if not hmac.compare_digest(post.image_token_hash, hashlib.sha256(token.encode()).hexdigest()):
            return False
        return post.image

    def _payload(self):
        self.ensure_one()
        return {'post_id': self.id, 'title': self.name, 'text': self.text or '', 'idea': self.idea or '',
                'service': self.service_id.name or '', 'has_image': bool(self.image),
                'scheduled_at': self.scheduled_local or ''}
