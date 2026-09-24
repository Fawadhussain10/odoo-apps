import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSalesTender(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        group_user = cls.env.ref('sales_tender.sale_tender_group_user')
        group_approver = cls.env.ref('sales_tender.sale_tender_group_approver')
        internal = cls.env.ref('base.group_user')
        sales = cls.env.ref('sales_team.group_sale_salesman')
        cls.user_a = Users.create({'name': 'Tender A', 'login': 'tender_a',
                                   'group_ids': [(6, 0, [internal.id, sales.id, group_user.id])]})
        cls.user_b = Users.create({'name': 'Tender B', 'login': 'tender_b',
                                   'group_ids': [(6, 0, [internal.id, sales.id, group_user.id])]})
        cls.approver = Users.create({'name': 'Approver', 'login': 'tender_approver',
                                     'group_ids': [(6, 0, [internal.id, sales.id, group_approver.id])]})
        cls.partner = cls.env['res.partner'].create({'name': 'Govt Department'})
        if not cls.env.company.chart_template:
            # a bare database has no accounting: load a chart so taxes (and tax groups) exist
            cls.env['account.chart.template'].try_loading('generic_coa', cls.env.company)
        cls.tax = cls.env['account.tax'].create({'name': 'GST 18%', 'amount': 18, 'amount_type': 'percent',
                                                 'type_tax_use': 'sale'})
        cls.product = cls.env['product.product'].create({'name': 'Tender Item', 'list_price': 1000.0})

    def _tender(self, user=None, **extra):
        vals = {
            'partner_id': self.partner.id, 'purpose': 'bid_earnest_money', 'tender_number': 'T-100',
            'order_line_ids': [(0, 0, {'product_id': self.product.id, 'name': 'Tender Item',
                                       'product_uom_qty': 2, 'price_unit': 1000.0,
                                       'tax_id': [(6, 0, self.tax.ids)]})],
        }
        vals.update(extra)
        return self.env['sale.tender'].with_user(user or self.user_a).create(vals)

    # ---------------------------------------------------------------- amounts / numbering
    def test_sequence_and_amounts(self):
        tender = self._tender()
        self.assertTrue(tender.name.startswith('T') or tender.name != 'New')
        self.assertNotEqual(tender.name, 'New')
        self.assertAlmostEqual(tender.amount_untaxed, 2000.0)
        self.assertAlmostEqual(tender.amount_total, 2360.0)
        self.assertAlmostEqual(tender.amount_tax, 360.0)

    # ---------------------------------------------------------------- access (ir.access in Odoo 20)
    def test_user_sees_only_own_tenders(self):
        mine = self._tender(self.user_a)
        other = self._tender(self.user_b)
        visible = self.env['sale.tender'].with_user(self.user_a).search([])
        self.assertIn(mine, visible)
        self.assertNotIn(other, visible)
        with self.assertRaises(AccessError):
            other.with_user(self.user_a).read(['name'])

    def test_approver_sees_all_tenders(self):
        a = self._tender(self.user_a)
        b = self._tender(self.user_b)
        visible = self.env['sale.tender'].with_user(self.approver).search([])
        self.assertTrue(a in visible and b in visible)

    def test_user_cannot_delete_but_approver_can(self):
        tender = self._tender(self.user_a)
        with self.assertRaises(AccessError):
            tender.with_user(self.user_a).unlink()
        tender.with_user(self.approver).unlink()
        self.assertFalse(tender.exists())

    def test_line_and_attachment_access_for_user(self):
        tender = self._tender(self.user_a)
        line = tender.order_line_ids.with_user(self.user_a)
        line.write({'product_uom_qty': 3})
        att = self.env['sale.tender.attachment'].with_user(self.user_a).create(
            {'tender_id': tender.id, 'attachment_type': 'other', 'name': 'doc', 'filename': 'a.txt',
             'datas': base64.b64encode(b'hello').decode()})
        self.assertTrue(att.exists())

    # ---------------------------------------------------------------- workflow
    def test_only_approver_can_accept_or_reject(self):
        tender = self._tender(self.user_a)
        tender.with_user(self.user_a).action_submit_for_approval()
        self.assertEqual(tender.state, 'to_approve')
        with self.assertRaises(AccessError):
            tender.with_user(self.user_a).action_accept()
        tender.with_user(self.approver).action_accept()
        self.assertEqual(tender.state, 'accepted')

    def test_reject_flow_and_reset(self):
        tender = self._tender(self.user_a)
        tender.action_submit_for_approval()
        tender.with_user(self.approver).action_reject()
        self.assertEqual(tender.state, 'rejected')
        tender.action_reset_to_draft()
        self.assertEqual(tender.state, 'draft')

    def test_not_editable_outside_draft(self):
        tender = self._tender(self.user_a)
        tender.action_submit_for_approval()
        with self.assertRaises(UserError):
            tender.write({'tender_number': 'changed'})

    def test_convert_accepted_tender_to_quotation(self):
        tender = self._tender(self.user_a)
        self.env['sale.tender.attachment'].create({
            'tender_id': tender.id, 'attachment_type': 'tender_document', 'name': 'Tender doc',
            'filename': 'tender.txt', 'datas': base64.b64encode(b'tender content').decode()})
        with self.assertRaises(UserError):
            tender.action_convert_to_quotation()          # not accepted yet
        tender.action_submit_for_approval()
        tender.with_user(self.approver).action_accept()
        action = tender.with_user(self.user_a).action_convert_to_quotation()
        order = self.env['sale.order'].browse(action['res_id'])
        self.assertEqual(tender.state, 'converted')
        self.assertEqual(tender.sale_order_id, order)
        self.assertEqual(order.tender_id, tender)
        self.assertEqual(order.partner_id, self.partner)
        self.assertEqual(order.client_order_ref, 'T-100')
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_uom_qty, 2)
        self.assertEqual(order.order_line.price_unit, 1000.0)
        self.assertEqual(order.order_line.tax_ids, self.tax)
        carried = self.env['ir.attachment'].search([('res_model', '=', 'sale.order'), ('res_id', '=', order.id)])
        self.assertEqual(carried.raw.content, b'tender content')
        with self.assertRaises(UserError):
            tender.action_convert_to_quotation()          # already converted
        with self.assertRaises(UserError):
            tender.action_reset_to_draft()

    def test_deleting_the_quotation_reopens_the_tender(self):
        tender = self._tender(self.user_a)
        tender.action_submit_for_approval()
        tender.with_user(self.approver).action_accept()
        order = self.env['sale.order'].browse(tender.action_convert_to_quotation()['res_id'])
        order.unlink()
        self.assertEqual(tender.state, 'accepted')
        self.assertFalse(tender.sale_order_id)

    def test_line_onchange_fills_product_details(self):
        tender = self._tender(self.user_a)
        line = self.env['sale.tender.line'].new({'tender_id': tender.id, 'product_id': self.product.id})
        line._onchange_product_id()
        self.assertEqual(line.price_unit, 1000.0)
        self.assertIn('Tender Item', line.name)
