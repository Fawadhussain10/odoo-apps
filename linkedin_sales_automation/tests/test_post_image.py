import base64
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import LiCommon
from .test_writing import PNG


@tagged('post_install', '-at_install', 'linkedin_sales_automation')
class TestPostImageLink(HttpCase, LiCommon):
    """Claude in Chrome gets a private 6-hour link to the post image, no Odoo login."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_li()
        cls.profile.write({'execution_mode': 'chrome', 'chrome_verified_at': '2099-01-01 00:00:00'})
        cls.post = cls.env['li.post'].create({'name': 'With image', 'linkedin_profile_id': cls.profile.id,
                                              'text': 'Hello LinkedIn', 'state': 'approved', 'image': PNG})
        cls.base = cls.env['ir.config_parameter'].sudo().get_param('web.base.url').rstrip('/')

    def test_portfolio_link_serves_the_file_without_login(self):
        service = self.env['li.service'].create({'name': 'Advisory', 'description': 'Advice.',
                                                 'portfolio_file': PNG, 'portfolio_filename': 'our-work.png'})
        response = self._get(service.portfolio_link)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, base64.b64decode(PNG))
        self.assertIn('our-work.png', response.headers['Content-Disposition'])
        self.assertEqual((response.headers['Content-Type'], response.headers['Content-Disposition'][:6]),
                         ('image/png', 'inline'))
        page = base64.b64encode(b'<html><script>alert(1)</script></html>')
        service.write({'portfolio_file': page, 'portfolio_filename': 'portfolio.html'})
        response = self._get(service.portfolio_link)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/octet-stream')    # never a page of ours
        self.assertTrue(response.headers['Content-Disposition'].startswith('attachment'))
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self._get(self.base + '/li_sales/portfolio/' + 'x' * 32).status_code, 404)
        service.portfolio_file = False
        self.assertEqual(self._get(self.base + '/li_sales/portfolio/' + 'y' * 32).status_code, 404)

    def _item(self):
        items = self.env['li.mcp.tools'].call_tool('li_get_work', {'linkedin_profile': 'taha'})['items']
        return [i for i in items if i['type'] == 'publish_post'][0]

    def _get(self, url):
        return self.url_open(url.replace(self.base, ''), allow_redirects=False)

    def test_signed_link(self):
        item = self._item()
        url = item['image_url']
        self.assertRegex(url, r'/li_sales/post_image/%s/[A-Za-z0-9_-]{40,}$' % self.post.id)
        self.assertNotIn('/web/image', url)
        self.assertIn('valid for 6 hours', item['instructions'])
        resp = self._get(url)                                 # no session cookie: not logged in
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers['Content-Type'], 'image/png')
        self.assertEqual(resp.content, base64.b64decode(PNG))
        self.assertIn('no-store', resp.headers['Cache-Control'])
        # only the stored hash, never the token itself
        self.assertNotIn(url.rsplit('/', 1)[1], str(self.post.sudo().read()[0]))

    def test_wrong_expired_or_other_post(self):
        url = self._item()['image_url']
        token = url.rsplit('/', 1)[1]
        self.assertEqual(self._get(url[:-3] + 'abc').status_code, 404)
        other = self.env['li.post'].create({'name': 'Other', 'linkedin_profile_id': self.profile.id,
                                            'text': 'x', 'image': PNG})
        self.assertEqual(self._get('/li_sales/post_image/%s/%s' % (other.id, token)).status_code, 404)
        later = fields.Datetime.now() + timedelta(hours=6, minutes=1)
        with patch('odoo.addons.linkedin_sales_automation.models.li_post.utc_now', return_value=later):
            self.assertEqual(self._get(url).status_code, 404)
        # a new item gives a new link and the old one stops working
        self.env['li.work.item'].search([('post_id', '=', self.post.id)])._close('cancelled')
        new_url = self._item()['image_url']
        self.assertNotEqual(new_url, url)
        self.assertEqual(self._get(url).status_code, 404)
        self.assertEqual(self._get(new_url).status_code, 200)

    def test_post_without_image_has_no_link(self):
        self.post.sudo().image = False
        self.assertEqual(self._item()['image_url'], '')
