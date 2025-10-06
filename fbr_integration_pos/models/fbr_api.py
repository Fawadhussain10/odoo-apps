from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta
import requests
import json
import traceback
import qrcode
import base64
from io import BytesIO


def generate_qr_code(value):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=20,
        border=4)
    qr.add_data(value)
    qr.make(fit=True)
    img = qr.make_image()
    stream = BytesIO()
    img.save(stream, format="PNG")
    qr_img = base64.b64encode(stream.getvalue())
    return qr_img


class AccountMove(models.Model):
    _inherit = 'account.move'

    fbr_request = fields.Text("FBR Request", copy=False)
    fbr_response = fields.Text("FBR Response", copy=False)
    fbr_status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('verified', 'Verified'),
        ('failed', 'Failed')
    ], string="FBR Status", default="draft", copy=False)
    fbr_invoice_number = fields.Char("FBR Invoice Number", copy=False)
    fbr_post_successful = fields.Boolean("FBR Data Posted", copy=False)
    fbr_qr_image = fields.Binary(string="QR Code", compute='_generate_qr_code', copy=False)
    qr_in_report = fields.Boolean(string='Display QRCode in Report?', compute='_qr_in_report', copy=False)

    def _qr_in_report(self):
        for rec in self:
            rec.qr_in_report = rec.fbr_invoice_number

    def _generate_qr_code(self, silent_errors=False):
        for order in self:
            qr_img = False
            try:
                if order.fbr_invoice_number:
                    supplier_name = order.company_id.name or ''
                    date = str(order.invoice_date or '')
                    total = f"{order.currency_id.name or ''}{order.amount_total or 0.0}"
                    invoice_text = (
                        f"Seller name: {supplier_name}\n"
                        f"Date: {date}\n"
                        f"FBR Invoice No: {order.fbr_invoice_number}\n"
                        f"Total with VAT: {total}"
                    )
                    qr_img = generate_qr_code(invoice_text)
            except Exception as e:
                if not silent_errors:
                    raise e
            order.fbr_qr_image = qr_img


class PosOrderExt(models.Model):
    _inherit = 'pos.order'

    @api.model
    def sync_from_ui(self, orders):
        data = super().sync_from_ui(orders)
        config = self.env['ir.config_parameter'].sudo()
        pos_orders = data.get('pos.order', [])
        account_move_id = pos_orders[0].get('account_move')
        if account_move_id:
            move = self.env['account.move'].browse(account_move_id)
            for invoice in move:
                fbr_auth_token = config.get_param('fbr_integration_pos.fbr_token')
                fbr_mode = config.get_param('fbr_integration_pos.fbr_mode')

                if not fbr_auth_token:
                    raise ValidationError(_('FBR Token not configured in settings.'))

                fbr_url = "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb" if fbr_mode == 'sandbox' else "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {fbr_auth_token}",
                }

                items_data = []
                for line in invoice.invoice_line_ids:
                    price_subtotal = abs(line.price_subtotal)
                    price_total = abs(line.price_total)
                    tax_charged = abs(round(float(price_total - price_subtotal), 2))
                    tax_rate = 0.0
                    if line.tax_ids:
                        tax_rate = round(line.tax_ids[0].amount, 2)
                    if line.discount:
                        discount_amount = abs(round((line.price_unit * line.quantity) - line.price_subtotal, 2))
                    else:
                        discount_amount = 0.0
                    if line.product_id.name != "POS Service Fee":
                        items_data.append({
                            "hsCode": line.product_id.pct_code,
                            "productDescription": line.product_id.name or "",
                            "ProductCode": line.product_id.default_code or "",
                            "rate": f"{int(tax_rate)}%",
                            "uoM": line.product_id.uom_id.name or "",
                            "quantity": abs(line.quantity),
                            "totalValues": price_total,
                            "valueSalesExcludingST": price_subtotal,
                            "salesTaxApplicable": tax_charged,
                            "fixedNotifiedValueOrRetailPrice": 0,
                            "salesTaxWithheldAtSource": 0,
                            "extraTax": "",
                            "furtherTax": 0,
                            "sroScheduleNo": line.product_id.sro_schedule or "",
                            "fedPayable": 0,
                            "discount": discount_amount,
                            "saleType": line.product_id.sale_type,
                            "sroItemSerialNo": line.product_id.sro_item or ""
                        })

                fbr_payload = {
                    "invoiceDate": (invoice.invoice_date + timedelta(hours=5)).strftime(
                        "%Y-%m-%d") if invoice.invoice_date else fields.Date.today().strftime("%Y-%m-%d"),
                    "sellerBusinessName": invoice.company_id.name or "",
                    "sellerProvince": invoice.company_id.state_id.name or "",
                    "sellerAddress": invoice.company_id.street or "",
                    "sellerNTNCNIC": invoice.company_id.vat,
                    "buyerNTNCNIC": invoice.partner_id.vat or invoice.partner_id.cnic or "1234567890123",
                    "buyerBusinessName": invoice.partner_id.name or "Retail Customer",
                    "buyerProvince": invoice.partner_id.state_id.name or "Punjab",
                    "buyerAddress": invoice.partner_id.street or "Lahore",
                    "buyerRegistrationType": "Registered" if invoice.partner_id and invoice.partner_id.vat else "Unregistered",
                    "items": items_data
                }

                if invoice.move_type in ['out_refund']:
                    fbr_payload['invoiceRefNo'] = invoice.reversed_entry_id.fbr_invoice_number or ""

                fbr_payload['invoiceType'] = "Debit Note" if invoice.reversed_entry_id else "Sale Invoice"
                if fbr_mode == 'sandbox':
                    fbr_payload['scenarioId'] = "SN026" or ""

                try:
                    invoice.fbr_request = json.dumps(fbr_payload, indent=4)
                    response = requests.post(fbr_url, headers=headers, data=json.dumps(fbr_payload), verify=False,
                                             timeout=20)
                    result = response.json()
                    invoice.fbr_response = json.dumps(result, indent=4)
                    statuses = result.get('validationResponse', {}).get('invoiceStatuses', [])
                    # invoice.fbr_invoice_number = statuses[0].get('invoiceNo', '') if statuses and isinstance(
                    #     statuses[0],
                    #     dict) else ''
                    invoice.fbr_invoice_number = result.get('invoiceNumber')
                    invoice.fbr_status = 'verified' if result.get('invoiceNumber') else 'failed'
                    invoice.fbr_post_successful = bool(result.get('invoiceNumber'))
                except Exception:
                    invoice.fbr_status = 'failed'
                    invoice.fbr_post_successful = False
                    invoice.fbr_response = traceback.format_exc()

        return data
