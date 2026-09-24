from unittest.mock import MagicMock, patch

from odoo.addons.point_of_sale.tests.test_generic_localization import TestGenericLocalization
from odoo.tests import tagged

REQUESTS_POST = 'odoo.addons.pra_pos_integrations.models.pos_order.requests.post'


@tagged('post_install', '-at_install')
class TestPraPosTour(TestGenericLocalization):
    """Runs Odoo's own POS tour (open register, sell, pay, receipt) in a real browser
    with PRA enabled: the POS must load with this module, sync the order to PRA and
    render the receipt, which now carries the PRA block."""

    def test_generic_localization(self):
        self.main_pos_config.write({'pra_enabled': True, 'pra_pos_id': '999999', 'pra_mode': 'sandbox'})
        (self.whiteboard_pen | self.wall_shelf).sudo().write({'pra_hs_code': '1234.5678'})
        with patch(REQUESTS_POST) as post:
            post.return_value = MagicMock(**{'json.return_value': {'Code': '100', 'InvoiceNumber': 'PRA-TOUR-0001'}})
            order, html = super().test_generic_localization()
            self.assertTrue(post.called, "the order paid in the POS screen was not reported to PRA")
        self.assertEqual(order.pra_status, 'synced')
        self.assertEqual(order.pra_invoice_number, 'PRA-TOUR-0001')
        self.assertIn('PRA Invoice No: PRA-TOUR-0001', html)
