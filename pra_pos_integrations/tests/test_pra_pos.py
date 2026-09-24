from unittest.mock import MagicMock, patch

import odoo
from odoo.addons.point_of_sale.tests.common import TestPoSCommon

REQUESTS_POST = 'odoo.addons.pra_pos_integrations.models.pos_order.requests.post'


@odoo.tests.tagged('post_install', '-at_install')
class TestPraPos(TestPoSCommon):
    """PRA e-IMS reporting: order sync hook, payload, QR and the receipt block."""
    _test_user_groups = None

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.config.write({'pra_enabled': True, 'pra_pos_id': '999999', 'pra_mode': 'sandbox'})
        self.product = self.create_product('PRA Burger', self.categ_basic, 100.0, 40.0)
        self.product.product_tmpl_id.pra_hs_code = '1234.5678'

    def _paid_order(self):
        self.open_new_session()
        data = self.create_ui_order_data([(self.product, 2)])
        with patch(REQUESTS_POST) as post:
            post.return_value = MagicMock(**{'json.return_value': {'Code': '100', 'InvoiceNumber': 'PRA-TEST-0001'}})
            result = self.env['pos.order'].sync_from_ui([data])
            self.assertTrue(post.called, "the paid order must be reported to PRA when it is synced")
        return self.env['pos.order'].browse(result['pos.order'][0]['id']), post

    def test_paid_order_is_reported_and_gets_fiscal_number(self):
        order, post = self._paid_order()
        self.assertEqual(order.pra_status, 'synced')
        self.assertEqual(order.pra_invoice_number, 'PRA-TEST-0001')
        self.assertTrue(order.pra_qr_image, "a verification QR code is generated")
        self.assertTrue(order.pra_synced_date)

    def test_payload(self):
        order, post = self._paid_order()
        payload = order._pra_build_payload()
        item = payload['Items'][0]
        self.assertEqual(item['PCTCode'], '12345678')          # normalised to the bare 8 digits
        self.assertEqual(item['Quantity'], 2)
        self.assertAlmostEqual(item['SaleValue'], round(order.lines.price_subtotal, 2))
        self.assertAlmostEqual(item['TotalAmount'], round(order.lines.price_subtotal_incl, 2))
        self.assertEqual(payload['InvoiceType'] if 'InvoiceType' in payload else item['InvoiceType'], 1)

    def test_missing_hs_code_marks_order_failed_without_blocking(self):
        self.product.product_tmpl_id.pra_hs_code = False
        self.open_new_session()
        data = self.create_ui_order_data([(self.product, 1)])
        with patch(REQUESTS_POST) as post:
            result = self.env['pos.order'].sync_from_ui([data])
            self.assertFalse(post.called)
        order = self.env['pos.order'].browse(result['pos.order'][0]['id'])
        self.assertEqual(order.pra_status, 'failed')
        self.assertIn('HS/PCT Code', order.pra_response)

    def test_pra_disabled_config_is_not_reported(self):
        self.config.pra_enabled = False
        self.open_new_session()
        data = self.create_ui_order_data([(self.product, 1)])
        with patch(REQUESTS_POST) as post:
            result = self.env['pos.order'].sync_from_ui([data])
            self.assertFalse(post.called)
        self.assertEqual(self.env['pos.order'].browse(result['pos.order'][0]['id']).pra_status, 'not_synced')

    def test_payment_mode_inferred_from_method_type(self):
        cash = self.cash_pm1
        self.assertEqual(cash._get_pra_payment_mode(), '1')
        bank = self.bank_pm1
        self.assertEqual(bank._get_pra_payment_mode(), '2')
        bank.pra_payment_mode = '6'
        self.assertEqual(bank._get_pra_payment_mode(), '6')

    def test_receipt_shows_pra_block(self):
        order, post = self._paid_order()
        html = order.order_receipt_generate_html()
        self.assertIn('PRA Invoice No: PRA-TEST-0001', html)
        self.assertIn('POS ID: 999999', html)
        self.assertIn('data:image/png;base64', html)
        self.assertIn('PRA Sahulat', html)

    def test_receipt_without_pra_number_has_no_block(self):
        self.config.pra_enabled = False
        self.open_new_session()
        data = self.create_ui_order_data([(self.product, 1)])
        result = self.env['pos.order'].sync_from_ui([data])
        html = self.env['pos.order'].browse(result['pos.order'][0]['id']).order_receipt_generate_html()
        self.assertNotIn('PRA Invoice No', html)
