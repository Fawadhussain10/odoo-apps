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


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    pct_code = fields.Char("PCT/HS Code", required=True)
    sale_type = fields.Char(string='Sale Type', required=True)
    sro_schedule = fields.Char(string='SRO Schedule No')
    sro_item = fields.Char(string='SRO Item No')
    fed_duty = fields.Many2one('account.tax', string='FED Duty')
    further_tax = fields.Many2one('account.tax', string='Further Tax')
    extra_tax = fields.Many2one('account.tax', string='Extra Tax')
    other_tax = fields.Char(string='Other Type Tax (e.g. Exempt)')
    withholding_tax = fields.Many2one('account.tax', string='Withholding Tax')

    @api.onchange('product_id')
    def _onchange_product_id_custom_fields(self):
        if self.product_id:
            self.pct_code = self.product_id.pct_code
            self.sale_type = self.product_id.sale_type
            self.sro_schedule = self.product_id.sro_schedule
            self.sro_item = self.product_id.sro_item
            self.fed_duty = self.product_id.fed_duty.id
            self.further_tax = self.product_id.further_tax.id
            self.extra_tax = self.product_id.extra_tax.id
            self.withholding_tax = self.product_id.withholding_tax
            self.other_tax = self.product_id.other_tax

    @api.onchange('fed_duty', 'further_tax', 'extra_tax', 'other_tax', 'product_id', 'withholding_tax')
    def _onchange_custom_taxes(self):
        for line in self:
            new_custom_taxes = self.env['account.tax']
            if line.product_id and line.product_id.taxes_id:
                new_custom_taxes |= line.product_id.taxes_id
            if line.fed_duty:
                new_custom_taxes |= line.fed_duty
            if line.further_tax:
                new_custom_taxes |= line.further_tax
            if line.extra_tax:
                new_custom_taxes |= line.extra_tax
            if line.withholding_tax:
                new_custom_taxes |= line.withholding_tax
            if line.other_tax:
                matched_tax = self.env['account.tax'].search([('name', 'ilike', line.other_tax)], limit=1)
                if matched_tax:
                    new_custom_taxes |= matched_tax
            line.tax_ids = [(6, 0, new_custom_taxes.ids)]

    def _apply_custom_taxes(self):
        for line in self:
            new_custom_taxes = self.env['account.tax']
            if line.product_id and line.product_id.taxes_id:
                new_custom_taxes |= line.product_id.taxes_id
            if line.fed_duty:
                new_custom_taxes |= line.fed_duty
            if line.further_tax:
                new_custom_taxes |= line.further_tax
            if line.extra_tax:
                new_custom_taxes |= line.extra_tax
            if line.withholding_tax:
                new_custom_taxes |= line.withholding_tax
            if line.other_tax:
                matched_tax = self.env['account.tax'].search([('name', 'ilike', line.other_tax)], limit=1)
                if matched_tax:
                    new_custom_taxes |= matched_tax
            line.tax_ids = [(6, 0, new_custom_taxes.ids)]

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in
               ['fed_duty', 'further_tax', 'extra_tax', 'other_tax', 'product_id', 'withholding_tax']):
            self._apply_custom_taxes()
        return res

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._apply_custom_taxes()
        return record


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
    scenario_id = fields.Char(string='Scenario ID')
    fbr_qr_image = fields.Binary(string="QR Code", compute='_generate_qr_code', copy=False)
    qr_in_report = fields.Boolean(string='Display QRCode in Report?', compute='_qr_in_report', copy=False)
    display_scenario = fields.Boolean(string='Display Scenario', compute='_display_scenario_field')

    def _display_scenario_field(self):
        for rec in self:
            config = self.env['ir.config_parameter'].sudo()
            fbr_mode = config.get_param('fbr_integration.fbr_mode')
            rec.display_scenario = fbr_mode == 'sandbox'

    def _qr_in_report(self):
        for rec in self:
            rec.qr_in_report = rec.fbr_invoice_number

    def _generate_qr_code(self, silent_errors=False):
        for order in self:
            order.fbr_qr_image = None
            fbr_invoice_number = order.fbr_invoice_number
            supplier_name = order.company_id.name
            date = str(order.invoice_date)
            total = ''.join([order.currency_id.name, str(order.amount_total)])
            invoice = f"Seller name: {supplier_name}\nDate: {date}\nFBR Invoice No: {fbr_invoice_number}\nTotal with VAT: {total}"
            try:
                qr_img = generate_qr_code(invoice)
                if order.fbr_invoice_number:
                    order.write({'fbr_qr_image': qr_img})
            except Exception as e:
                if not silent_errors:
                    raise e

    def action_post_data_to_fbr(self):
        for invoice in self:
            if invoice.state != 'posted':
                raise ValidationError(_('Please post the invoice first.'))

            config = self.env['ir.config_parameter'].sudo()
            fbr_enable_service = config.get_param('fbr_integration.fbr_enable_service')
            service_fee_product = self.env.ref('fbr_integration.product_fbr_service_fee', raise_if_not_found=False)
            fbr_service_fee = config.get_param('fbr_integration.fbr_service_fee') or 1.0
            fbr_auth_token = config.get_param('fbr_integration.fbr_token')
            fbr_mode = config.get_param('fbr_integration.fbr_mode')

            if fbr_enable_service:
                invoice.button_draft()
                if not service_fee_product:
                    raise ValidationError(_('FBR Service Fee product is not configured properly.'))
                account = service_fee_product.property_account_income_id or service_fee_product.categ_id.property_account_income_categ_id
                if not account:
                    raise ValidationError(_('Please configure an income account for the FBR Service Fee product.'))
                if invoice.invoice_line_ids.filtered(lambda x: x.product_id == service_fee_product):
                    service_line = invoice.invoice_line_ids.filtered(lambda x: x.product_id == service_fee_product)
                    service_line.unlink()
                invoice.write({
                    'invoice_line_ids': [(0, 0, {
                        'product_id': service_fee_product.id,
                        'name': service_fee_product.name,
                        'quantity': 1,
                        'price_unit': float(fbr_service_fee),
                        'account_id': account.id,
                        'tax_ids': [(6, 0, [])],
                    })]
                })
                invoice.action_post()

            if not fbr_auth_token:
                raise ValidationError(_('FBR Token not configured in settings.'))

            fbr_url = "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata_sb" if fbr_mode == 'sandbox' else "https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {fbr_auth_token}",
            }

            items_data = []

            for line in invoice.invoice_line_ids:
                extra_tax_rate = 0.0
                if line.extra_tax:
                    extra_tax_rate = round(line.extra_tax.amount, 2)
                fed_duty_rate = 0.0
                if line.fed_duty:
                    fed_duty_rate = round(line.fed_duty.amount, 2)
                further_tax_rate = 0.0
                if line.further_tax:
                    further_tax_rate = round(line.further_tax.amount, 2)
                tax_rate = 0.0
                if line.tax_ids:
                    tax_rate = round(line.tax_ids[0].amount, 2)
                withholding_rate = 0.0
                if line.withholding_tax:
                    withholding_rate = round(line.withholding_tax.amount, 2)

                price_subtotal = abs(line.price_subtotal)
                price_total = abs(line.price_total)
                tax_charged = abs(round(float(price_total - price_subtotal), 2))
                further_tax_amount = round(price_subtotal * (further_tax_rate / 100), 2)
                fed_duty_amount = round(price_subtotal * (fed_duty_rate / 100), 2)
                withholding_tax_amount = round(price_subtotal * (withholding_rate / 100), 2)
                if line.discount:
                    discount_amount = abs(round((line.price_unit * line.quantity) - line.price_subtotal, 2))
                else:
                    discount_amount = 0.0
                extra_tax_amount = round(price_subtotal * (extra_tax_rate / 100), 2)
                tax_charged = tax_charged - extra_tax_amount - further_tax_amount - fed_duty_amount - withholding_tax_amount

                if line.product_id.id != service_fee_product.id:
                    items_data.append({
                        "hsCode": line.pct_code,
                        "productDescription": line.product_id.name or "",
                        "ProductCode": line.product_id.default_code or "",
                        "rate": f"{int(tax_rate)}%" if tax_rate > 0 else line.other_tax,
                        "uoM": line.product_uom_id.name or "",
                        "quantity": abs(line.quantity),
                        "totalValues": price_total,
                        "valueSalesExcludingST": price_subtotal,
                        "salesTaxApplicable": tax_charged,
                        "fixedNotifiedValueOrRetailPrice": (
                            line.price_subtotal if fbr_mode == 'sandbox' and invoice.scenario_id == "SN008" else 0
                        ),
                        "salesTaxWithheldAtSource": abs(withholding_tax_amount) or 0,
                        "extraTax": f"{extra_tax_amount}" if extra_tax_amount > 0.0 else "",
                        "furtherTax": further_tax_amount,
                        "sroScheduleNo": line.sro_schedule or "",
                        "fedPayable": fed_duty_amount,
                        "discount": discount_amount,
                        "saleType": line.sale_type,
                        "sroItemSerialNo": line.sro_item or ""
                    })

            fbr_payload = {
                "invoiceDate": (invoice.invoice_date + timedelta(hours=5)).strftime(
                    "%Y-%m-%d") if invoice.invoice_date else fields.Date.today().strftime("%Y-%m-%d"),
                "sellerBusinessName": invoice.company_id.name or "",
                "sellerProvince": invoice.company_id.state_id.name or "",
                "sellerAddress": invoice.company_id.street or "",
                "sellerNTNCNIC": invoice.company_id.vat,
                "buyerNTNCNIC": invoice.partner_id.vat or invoice.partner_id.cnic,
                "buyerBusinessName": invoice.partner_id.name or "",
                "buyerProvince": invoice.partner_id.state_id.name or "",
                "buyerAddress": invoice.partner_id.street or "",
                "buyerRegistrationType": "Registered" if invoice.partner_id.vat else "Unregistered",
                "items": items_data
            }

            if invoice.move_type in ['out_refund']:
                fbr_payload['invoiceRefNo'] = invoice.reversed_entry_id.fbr_invoice_number or ""

            if not invoice.reversed_entry_id:
                fbr_payload['invoiceType'] = "Sale Invoice"
            else:
                fbr_payload['invoiceType'] = "Credit Note"

            if fbr_mode == 'sandbox':
                fbr_payload['scenarioId'] = invoice.scenario_id or ""

            try:
                invoice.fbr_request = json.dumps(fbr_payload, indent=4)
                response = requests.post(fbr_url, headers=headers, data=json.dumps(fbr_payload), verify=False,
                                         timeout=20)
                result = response.json()

                invoice.fbr_response = json.dumps(result, indent=4)
                statuses = result.get('validationResponse', {}).get('invoiceStatuses', [])
                if statuses and isinstance(statuses, list) and isinstance(statuses[0], dict):
                    invoice.fbr_invoice_number = statuses[0].get('invoiceNo', '')
                else:
                    invoice.fbr_invoice_number = ''
                invoice.fbr_status = 'verified' if result.get('invoiceNumber') else 'failed'
                invoice.fbr_post_successful = bool(result.get('invoiceNumber'))

            except Exception:
                invoice.fbr_status = 'failed'
                invoice.fbr_post_successful = False
                invoice.fbr_response = traceback.format_exc()
