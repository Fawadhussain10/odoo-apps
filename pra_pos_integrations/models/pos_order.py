import base64
import json
import logging
import re
import traceback
from datetime import timedelta
from io import BytesIO

import qrcode
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PRA_SANDBOX_URL = "https://ims.pral.com.pk/ims/sandbox/api/Live/PostData"
PRA_PRODUCTION_URL = "https://ims.pral.com.pk/ims/production/api/Live/PostData"
PRA_SANDBOX_TOKEN = "24d8fab3-f2e9-398f-ae17-b387125ec4a2"
PRA_SYNC_TIMEOUT = 20


class PosOrder(models.Model):
    _inherit = 'pos.order'

    pra_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('synced', 'Synced'),
        ('failed', 'Failed'),
    ], string="PRA Status", default='not_synced', copy=False)
    pra_invoice_number = fields.Char(string="PRA Invoice Number", copy=False)
    pra_request = fields.Text(string="PRA Request", copy=False)
    pra_response = fields.Text(string="PRA Response", copy=False)
    pra_synced_date = fields.Datetime(string="PRA Synced On", copy=False)
    pra_qr_image = fields.Binary(string="PRA QR Code", copy=False, attachment=False)

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        return fields + ['pra_status', 'pra_invoice_number', 'pra_qr_image']

    @api.model
    def _process_order(self, order, existing_order):
        order_id = super()._process_order(order, existing_order)
        pos_order = self.browse(order_id)
        if (
            pos_order.state in ('paid', 'done', 'invoiced')
            and pos_order.pra_status != 'synced'
            and pos_order.config_id.pra_enabled
        ):
            pos_order._pra_submit_invoice()
        return order_id

    def action_pra_resync(self):
        self.filtered(
            lambda o: o.state in ('paid', 'done', 'invoiced')
            and o.pra_status != 'synced'
            and o.config_id.pra_enabled
        )._pra_submit_invoice()

    def _pra_submit_invoice(self):
        for order in self:
            try:
                order._pra_send()
            except Exception:
                _logger.exception("PRA: failed to sync POS order %s", order.name)
                order.write({
                    'pra_status': 'failed',
                    'pra_response': traceback.format_exc(),
                })

    @api.model
    def _cron_pra_sync_pending_orders(self, days=7, batch_size=200):
        domain = [
            ('pra_status', 'in', ('not_synced', 'failed')),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('config_id.pra_enabled', '=', True),
            ('date_order', '>=', fields.Datetime.now() - timedelta(days=days)),
        ]
        orders = self.search(domain, limit=batch_size)
        orders._pra_submit_invoice()

    def _pra_get_usin(self):
        self.ensure_one()
        return self.pos_reference or self.name

    def _pra_get_payment_mode(self):
        self.ensure_one()
        modes = {payment.payment_method_id._get_pra_payment_mode() for payment in self.payment_ids}
        modes.discard(False)
        if not modes:
            return 1
        if len(modes) > 1:
            return 5
        return int(modes.pop())

    def _pra_build_payload(self):
        self.ensure_one()
        refund_order = self.refunded_order_id
        invoice_type = 3 if refund_order else 1
        ref_usin = refund_order._pra_get_usin() if refund_order else None
        local_dt = self.date_order + timedelta(hours=5)

        items = []
        for line in self.lines:
            if line.product_id.type == 'combo':
                continue
            pct_code = re.sub(r'\D', '', line.product_id.pra_hs_code or '')
            if not pct_code:
                raise UserError(_(
                    "Please set the PRA HS/PCT Code on product '%s' before syncing this order to PRA."
                ) % line.product_id.display_name)

            qty = abs(line.qty)
            sale_value = round(abs(line.price_subtotal), 2)
            total_amount = round(abs(line.price_subtotal_incl), 2)
            tax_charged = round(total_amount - sale_value, 2)
            gross_value = round(abs(line.price_unit) * qty, 2)
            discount_amount = round(gross_value - sale_value, 2) if line.discount and gross_value > sale_value else 0.0
            percent_taxes = line.tax_ids.filtered(lambda t: t.amount_type == 'percent')
            tax_rate = round(sum(percent_taxes.mapped('amount')), 2) if percent_taxes else 0.0

            items.append({
                "ItemCode": line.product_id.default_code or str(line.product_id.id),
                "ItemName": line.full_product_name or line.product_id.display_name,
                "PCTCode": pct_code,
                "Quantity": qty,
                "TaxRate": tax_rate,
                "SaleValue": sale_value,
                "Discount": discount_amount,
                "FurtherTax": 0.0,
                "TaxCharged": tax_charged,
                "TotalAmount": total_amount,
                "InvoiceType": invoice_type,
                "RefUSIN": ref_usin,
            })

        partner = self.partner_id

        return {
            "InvoiceNumber": "",
            "POSID": int(self.config_id.pra_pos_id),
            "USIN": self._pra_get_usin(),
            "RefUSIN": ref_usin,
            "DateTime": local_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "BuyerName": partner.name or "",
            "BuyerPNTN": partner.vat or "",
            "BuyerCNIC": partner.cnic or "",
            "BuyerPhoneNumber": partner.phone or "",
            "TotalQuantity": round(sum(item['Quantity'] for item in items), 4),
            "TotalSaleValue": round(sum(item['SaleValue'] for item in items), 2),
            "TotalTaxCharged": round(sum(item['TaxCharged'] for item in items), 2),
            "Discount": round(sum(item['Discount'] for item in items), 2),
            "FurtherTax": 0.0,
            "TotalBillAmount": round(abs(self.amount_total), 2),
            "PaymentMode": self._pra_get_payment_mode(),
            "InvoiceType": invoice_type,
            "Items": items,
        }

    def _pra_send(self):
        self.ensure_one()
        config = self.config_id
        if not config.pra_pos_id:
            raise UserError(_("PRA POS ID is not configured for Point of Sale '%s'.") % config.name)
        if config.pra_mode == 'production' and not config.pra_token:
            raise UserError(_("PRA Token is not configured for Point of Sale '%s'.") % config.name)

        payload = self._pra_build_payload()
        url = PRA_SANDBOX_URL if config.pra_mode == 'sandbox' else PRA_PRODUCTION_URL
        token = config.pra_token if config.pra_mode == 'production' else (config.pra_token or PRA_SANDBOX_TOKEN)
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % token,
        }

        self.pra_request = json.dumps(payload, indent=2, default=str)

        response = requests.post(url, headers=headers, data=json.dumps(payload, default=str), timeout=PRA_SYNC_TIMEOUT)
        try:
            result = response.json()
        except ValueError:
            response.raise_for_status()
            raise

        self.pra_response = json.dumps(result, indent=2, default=str)

        invoice_number = result.get('InvoiceNumber')
        if invoice_number and str(result.get('Code')) == '100':
            self.write({
                'pra_invoice_number': invoice_number,
                'pra_status': 'synced',
                'pra_synced_date': fields.Datetime.now(),
            })
            self._pra_generate_qr()
        else:
            self.pra_status = 'failed'

    def _pra_generate_qr(self):
        for order in self:
            qr_text = "\n".join(filter(None, [
                order.company_id.name,
                _("PRA Invoice No: %s") % order.pra_invoice_number,
                _("USIN: %s") % order._pra_get_usin(),
                _("Date: %s") % order.date_order,
                _("Total: %s %s") % (order.currency_id.name, order.amount_total),
            ]))
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=6,
                border=2,
            )
            qr.add_data(qr_text)
            qr.make(fit=True)
            stream = BytesIO()
            qr.make_image().save(stream, format="PNG")
            order.pra_qr_image = base64.b64encode(stream.getvalue())
