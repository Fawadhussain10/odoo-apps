# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.whatsapp_qr_connect.models.whatsapp_account import WhatsappAccount
from odoo.addons.whatsapp_qr_connect.models.whatsapp_document import DOCUMENTS


@tagged('post_install', '-at_install')
class TestWhatsappDocuments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['whatsapp.account']
        cls.acc_a = Account.create({'name': 'A', 'state': 'connected', 'phone': '923001111111', 'is_default': True})
        cls.partner = cls.env['res.partner'].create({'name': 'Al-Noor Traders', 'phone': '0300 1234567'})

    def _has(self, model):
        return model in self.env.registry

    def _need_accounting(self):
        if 'account.move.line' not in self.env.registry:
            self.skipTest('accounting not installed')

    # -------------------------------------------------------------- buttons
    def test_button_installed_only_for_installed_apps(self):
        for doc in DOCUMENTS:
            view = self.env.ref('whatsapp_qr_connect.wa_view_%s' % doc['model'].replace('.', '_'),
                                raise_if_not_found=False)
            form_exists = (self._has(doc['model']) and self.env.ref(doc['view'], raise_if_not_found=False)
                           and all(self._has(m) for m in doc.get('requires', [])))
            self.assertEqual(bool(view), bool(form_exists), doc['model'])
            if view:
                arch = self.env[doc['model']].get_view(view_type='form')['arch']
                self.assertIn('fa-whatsapp', arch, doc['model'])

    def test_button_click_runs_as_plain_internal_user(self):
        """The button is a server action: a normal user must be able to run it."""
        self._need_accounting()
        user = self.env['res.users'].create({
            'name': 'Seller', 'login': 'seller_wa',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('account.group_account_invoice').id])],
        })
        action = self.env.ref('whatsapp_qr_connect.wa_action_res_partner')
        res = action.with_user(user).with_context(
            active_model='res.partner', active_id=self.partner.id,
            active_ids=[self.partner.id]).run()
        self.assertEqual(res['res_model'], 'whatsapp.send.wizard')

    # --------------------------------------------------------------- dialog
    def test_dialog_prefills_phone_message_and_pdf(self):
        self._need_accounting()
        action = self.env['whatsapp.document'].wa_open_dialog('res.partner', self.partner.id)
        ctx = action['context']
        self.assertEqual(ctx['default_phone'], '0300 1234567')
        self.assertIn('Al-Noor Traders', ctx['default_message'])
        self.assertEqual(ctx['default_report_xmlid'], 'whatsapp_qr_connect.action_report_partner_ledger')
        self.assertEqual(ctx['default_pdf_filename'], 'Ledger_Al-Noor_Traders.pdf')
        self.assertEqual(ctx['default_account_id'], self.acc_a.id)

    def test_dialog_needs_a_linked_number(self):
        self.acc_a.state = 'draft'
        with self.assertRaises(UserError):
            self.env['whatsapp.document'].wa_open_dialog('res.partner', self.partner.id)

    def test_dialog_refuses_unsupported_model(self):
        with self.assertRaises(UserError):
            self.env['whatsapp.document'].wa_open_dialog('res.users', 1)

    def test_dialog_respects_read_access(self):
        portal = self.env['res.users'].create({
            'name': 'Portal', 'login': 'portal_doc',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])]})
        with self.assertRaises(AccessError):
            self.env['whatsapp.document'].with_user(portal).wa_open_dialog('res.partner', self.partner.id)

    def test_sale_order_message_and_phone(self):
        if not self._has('sale.order'):
            self.skipTest('sale not installed')
        product = self.env['product.product'].create({'name': 'Rice', 'list_price': 100})
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 2})]})
        ctx = self.env['whatsapp.document'].wa_open_dialog('sale.order', order.id)['context']
        self.assertEqual(ctx['default_phone'], '0300 1234567')
        self.assertIn(order.name, ctx['default_message'])
        self.assertIn('quotation', ctx['default_message'])
        self.assertEqual(ctx['default_report_xmlid'], 'sale.action_report_saleorder')

    def test_invoice_and_bill_wording(self):
        self._need_accounting()
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {'name': 'Service', 'quantity': 1, 'price_unit': 500})]})
        invoice.action_post()
        ctx = self.env['whatsapp.document'].wa_open_dialog('account.move', invoice.id)['context']
        self.assertIn('invoice', ctx['default_message'])
        self.assertIn(invoice.name, ctx['default_message'])
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.partner.id, 'invoice_date': '2026-01-01',
            'invoice_line_ids': [(0, 0, {'name': 'Goods', 'quantity': 1, 'price_unit': 70})]})
        bill.action_post()
        self.assertIn('bill', self.env['whatsapp.document'].wa_open_dialog(
            'account.move', bill.id)['context']['default_message'])

    def test_purchase_order_message(self):
        if not self._has('purchase.order'):
            self.skipTest('purchase not installed')
        order = self.env['purchase.order'].create({'partner_id': self.partner.id})
        ctx = self.env['whatsapp.document'].wa_open_dialog('purchase.order', order.id)['context']
        self.assertIn('request for quotation', ctx['default_message'])

    def test_delivery_message(self):
        if not self._has('stock.picking'):
            self.skipTest('stock not installed')
        picking_type = self.env['stock.picking.type'].search([('code', '=', 'outgoing')], limit=1)
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id, 'partner_id': self.partner.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id})
        ctx = self.env['whatsapp.document'].wa_open_dialog('stock.picking', picking.id)['context']
        self.assertIn('delivery', ctx['default_message'])
        self.assertEqual(ctx['default_report_xmlid'], 'stock.action_report_delivery')

    # --------------------------------------------------------------- ledger
    def test_ledger_lines_and_report_render(self):
        self._need_accounting()
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {'name': 'Service', 'quantity': 1, 'price_unit': 500})]})
        invoice.action_post()
        lines, balance = self.env['report.whatsapp_qr_connect.report_partner_ledger']._ledger_lines(self.partner)
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(balance, invoice.amount_total)
        self.assertEqual(lines[0]['move'], invoice.name)
        html = self.env['ir.actions.report']._render_qweb_html(
            'whatsapp_qr_connect.action_report_partner_ledger', [self.partner.id])[0]
        self.assertIn(b'Account Statement', html)
        self.assertIn(invoice.name.encode(), html)
        self.assertIn('%s' % '{:,.2f}'.format(invoice.amount_total), html.decode().replace('\xa0', ' '))

    # ----------------------------------------------------------- attachment
    def test_wizard_attaches_pdf_and_cleans_up(self):
        seen = {}

        def fake(account, mode, payload=None, timeout=90, **extra):
            att = payload['messages'][0]['attachment']
            seen['exists'] = os.path.exists(att['path'])
            seen['data'] = open(att['path'], 'rb').read()
            seen['att'] = att
            seen['timeout'] = timeout
            return {'ok': True, 'results': [{'status': 'SENT', 'message_id': 'X1'}]}

        wizard = self.env['whatsapp.send.wizard'].create({
            'account_id': self.acc_a.id, 'phone': '923001234567', 'message': 'Hi',
            'res_model': 'res.partner', 'res_id': self.partner.id,
            'report_xmlid': 'whatsapp_qr_connect.action_report_partner_ledger',
            'pdf_filename': 'Ledger_Al-Noor.pdf'})
        with patch.object(WhatsappAccount, '_run_worker', fake), \
                patch('odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf',
                      return_value=(b'%PDF-1.4 fake', 'pdf')):
            action = wizard.action_send()
        self.assertEqual(action['params']['type'], 'success')
        self.assertTrue(seen['exists'])
        self.assertEqual(seen['data'], b'%PDF-1.4 fake')
        self.assertEqual(seen['att']['filename'], 'Ledger_Al-Noor.pdf')
        self.assertEqual(seen['att']['mimetype'], 'application/pdf')
        self.assertFalse(os.path.exists(seen['att']['path']))          # temp file removed
        log = self.env['whatsapp.message'].search([], order='id desc', limit=1)
        self.assertEqual(log.attachment_name, 'Ledger_Al-Noor.pdf')
        self.assertGreater(seen['timeout'], 60)                        # room to upload the file

    def test_wizard_without_pdf_sends_text_only(self):
        seen = {}

        def fake(account, mode, payload=None, timeout=90, **extra):
            seen['msg'] = payload['messages'][0]
            return {'ok': True, 'results': [{'status': 'SENT'}]}

        wizard = self.env['whatsapp.send.wizard'].create({
            'account_id': self.acc_a.id, 'phone': '923001234567', 'message': 'Hi',
            'res_model': 'res.partner', 'res_id': self.partner.id,
            'report_xmlid': 'whatsapp_qr_connect.action_report_partner_ledger',
            'pdf_filename': 'x.pdf', 'attach_pdf': False})
        with patch.object(WhatsappAccount, '_run_worker', fake):
            wizard.action_send()
        self.assertNotIn('attachment', seen['msg'])

    def test_pdf_failure_gives_a_clear_error(self):
        wizard = self.env['whatsapp.send.wizard'].create({
            'account_id': self.acc_a.id, 'phone': '923001234567', 'message': 'Hi',
            'res_model': 'res.partner', 'res_id': self.partner.id,
            'report_xmlid': 'whatsapp_qr_connect.action_report_partner_ledger'})
        with patch('odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf',
                   side_effect=RuntimeError('wkhtmltopdf missing')):
            with self.assertRaisesRegex(UserError, "Attach PDF"):
                wizard.action_send()
