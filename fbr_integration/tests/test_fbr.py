import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

REQUESTS_POST = 'odoo.addons.fbr_integration.models.fbr_api.requests.post'
SALE_TYPE = 'Goods at Standard Rate (default)'


@tagged('post_install', '-at_install')
class TestFbrIntegration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        if not company.chart_template:
            cls.env['account.chart.template'].try_loading('generic_coa', company)
        company.write({'vat': '1234567-8', 'street': 'Main Boulevard'})
        cls.tax = cls.env['account.tax'].create({
            'name': 'GST 18% FBR', 'amount': 18, 'amount_type': 'percent', 'type_tax_use': 'sale'})
        cls.product = cls.env['product.product'].create({
            'name': 'FBR Widget', 'list_price': 100.0, 'default_code': 'W1',
            'pct_code': '8471.3010', 'sale_type': SALE_TYPE, 'taxes_id': [(6, 0, cls.tax.ids)]})
        cls.partner = cls.env['res.partner'].create({'name': 'FBR Buyer', 'vat': '7654321-0'})
        cls.icp = cls.env['ir.config_parameter'].sudo()
        cls.icp.set_str('fbr_integration.fbr_token', 'test-token')
        cls.icp.set_str('fbr_integration.fbr_mode', 'sandbox')

    def _invoice(self, post=True):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id, 'invoice_date': '2026-09-01',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id, 'quantity': 2, 'price_unit': 100.0,
                'pct_code': '8471.3010', 'sale_type': SALE_TYPE, 'tax_ids': [(6, 0, self.tax.ids)]})],
        })
        if post:
            invoice.action_post()
        return invoice

    def _fbr_reply(self, number='FBR-INV-0001'):
        reply = MagicMock()
        reply.json.return_value = {'invoiceNumber': number,
                                   'validationResponse': {'invoiceStatuses': [{'invoiceNo': '1'}]}}
        return reply

    # ------------------------------------------------------------------ settings
    def test_settings_round_trip_uses_typed_parameters(self):
        settings = self.env['res.config.settings'].create({
            'fbr_mode': 'production', 'fbr_token': 'tok-123', 'fbr_bpos_id': '07',
            'fbr_enable_service': True, 'fbr_service_fee': 5.5})
        settings.set_values()
        icp = self.env['ir.config_parameter'].sudo()
        self.assertEqual(icp.get_str('fbr_integration.fbr_mode'), 'production')
        self.assertEqual(icp.get_str('fbr_integration.fbr_token'), 'tok-123')
        self.assertEqual(icp.get_str('fbr_integration.fbr_bpos_id'), '07')
        self.assertTrue(icp.get_bool('fbr_integration.fbr_enable_service'))
        self.assertAlmostEqual(icp.get_float('fbr_integration.fbr_service_fee'), 5.5)
        values = self.env['res.config.settings'].default_get(
            ['fbr_mode', 'fbr_token', 'fbr_bpos_id', 'fbr_enable_service', 'fbr_service_fee'])
        self.assertEqual(values['fbr_mode'], 'production')
        self.assertEqual(values['fbr_token'], 'tok-123')
        self.assertTrue(values['fbr_enable_service'])
        self.assertAlmostEqual(values['fbr_service_fee'], 5.5)

    # ------------------------------------------------------------------ invoice / line fields
    def test_line_takes_hs_code_from_product_and_keeps_taxes(self):
        invoice = self._invoice(post=False)
        line = invoice.invoice_line_ids
        self.assertEqual(line.pct_code, '8471.3010')
        self.assertEqual(line.tax_ids, self.tax)

    def test_display_scenario_only_in_sandbox(self):
        invoice = self._invoice(post=False)
        self.assertTrue(invoice.display_scenario)
        self.icp.set_str('fbr_integration.fbr_mode', 'production')
        invoice.invalidate_recordset(['display_scenario'])
        self.assertFalse(invoice.display_scenario)

    # ------------------------------------------------------------------ posting to FBR
    def test_posting_sends_payload_and_stores_result(self):
        invoice = self._invoice()
        invoice.scenario_id = 'SN001'
        with patch(REQUESTS_POST, return_value=self._fbr_reply()) as post:
            invoice.action_post_data_to_fbr()
        self.assertTrue(post.called)
        sent = json.loads(invoice.fbr_request)
        self.assertEqual(sent['sellerNTNCNIC'], '1234567-8')
        self.assertEqual(sent['buyerNTNCNIC'], '7654321-0')
        self.assertEqual(sent['buyerRegistrationType'], 'Registered')
        self.assertEqual(sent['scenarioId'], 'SN001')
        self.assertEqual(sent['invoiceType'], 'Sale Invoice')
        item = sent['items'][0]
        self.assertEqual(item['hsCode'], '8471.3010')
        self.assertEqual(item['rate'], '18%')
        self.assertEqual(item['quantity'], 2)
        self.assertAlmostEqual(item['valueSalesExcludingST'], 200.0)
        self.assertAlmostEqual(item['salesTaxApplicable'], 36.0)
        self.assertAlmostEqual(item['totalValues'], 236.0)
        headers = post.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer test-token')
        self.assertIn('postinvoicedata_sb', post.call_args.args[0])       # sandbox gateway
        self.assertEqual(invoice.fbr_invoice_number, 'FBR-INV-0001')
        self.assertEqual(invoice.fbr_status, 'verified')
        self.assertTrue(invoice.fbr_post_successful)

    def test_production_uses_live_gateway(self):
        self.icp.set_str('fbr_integration.fbr_mode', 'production')
        invoice = self._invoice()
        with patch(REQUESTS_POST, return_value=self._fbr_reply()) as post:
            invoice.action_post_data_to_fbr()
        self.assertNotIn('_sb', post.call_args.args[0])
        self.assertNotIn('scenarioId', json.loads(invoice.fbr_request))

    def test_failed_reply_is_recorded_without_raising(self):
        invoice = self._invoice()
        bad = MagicMock()
        bad.json.return_value = {'error': 'invalid'}
        with patch(REQUESTS_POST, return_value=bad):
            invoice.action_post_data_to_fbr()
        self.assertEqual(invoice.fbr_status, 'failed')
        self.assertFalse(invoice.fbr_post_successful)

    def test_token_and_posted_state_are_required(self):
        invoice = self._invoice(post=False)
        with self.assertRaises(ValidationError):
            invoice.action_post_data_to_fbr()                # not posted yet
        invoice.action_post()
        self.icp.set_str('fbr_integration.fbr_token', '')
        with self.assertRaises(ValidationError):
            invoice.action_post_data_to_fbr()                # no token configured

    def test_service_fee_is_added_when_enabled(self):
        fee = self.env.ref('fbr_integration.product_fbr_service_fee')
        with self.assertRaises(ValidationError):                    # module tells the admin what is missing
            self.icp.set_bool('fbr_integration.fbr_enable_service', True)
            self._invoice().action_post_data_to_fbr()
        fee.property_account_income_id = self.env['account.account'].search(
            [('account_type', '=', 'income')], limit=1)
        self.icp.set_bool('fbr_integration.fbr_enable_service', True)
        self.icp.set_float('fbr_integration.fbr_service_fee', 1.0)
        invoice = self._invoice()
        with patch(REQUESTS_POST, return_value=self._fbr_reply()):
            invoice.action_post_data_to_fbr()
        self.assertEqual(invoice.state, 'posted')
        self.assertIn(fee, invoice.invoice_line_ids.product_id)
        # the service line itself is never reported as a goods item
        self.assertEqual(len(json.loads(invoice.fbr_request)['items']), 1)

    # ------------------------------------------------------------------ QR code + report
    def test_qr_code_is_generated_once_fbr_number_exists(self):
        invoice = self._invoice()
        self.assertFalse(invoice.fbr_qr_image)
        with patch(REQUESTS_POST, return_value=self._fbr_reply()):
            invoice.action_post_data_to_fbr()
        invoice.invalidate_recordset(['fbr_qr_image'])
        self.assertTrue(invoice.fbr_qr_image)
        self.assertEqual(bytes(invoice.fbr_qr_image)[:8], b'\x89PNG\r\n\x1a\n')

    def test_report_shows_hs_code_number_and_qr_and_no_tax_column(self):
        invoice = self._invoice()
        with patch(REQUESTS_POST, return_value=self._fbr_reply('FBR-REPORT-7')):
            invoice.action_post_data_to_fbr()
        html = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', invoice.ids)[0].decode()
        self.assertIn('HS Code', html)
        self.assertIn('8471.3010', html)
        self.assertIn('FBR Invoice No#', html)
        self.assertIn('FBR-REPORT-7', html)
        self.assertIn('alt="FBR QR Code"', html)
        self.assertIn('data:image/png;base64', html)
        self.assertNotIn('>Taxes<', html)
