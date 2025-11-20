import requests
from odoo import models, fields, api
import json
import qrcode
import base64
from io import BytesIO
import certifi
import ssl
import logging

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    pra_invoice_id = fields.Char(string="PRA Invoice Object")
    pra_invoice_number = fields.Char("PRA Invoice Number")
    pra_qr_code = fields.Binary("PRA QR Code")

    # @api.model
    # def _order_fields(self, ui_order):
    #     order_fields = super(PosOrder, self)._order_fields(ui_order)
    #     order_fields['pra_invoice_id'] = ui_order.get('pra_invoice_id')
    #     return order_fields

    @api.model
    def _get_pra_config(self, order):
        """ Retrieve PRA configuration based on the environment (test or production). """
        pra_integration_enabled = order.config_id.pra_integration_enabled
        if not pra_integration_enabled:
            return None

        pra_environment = order.config_id.pra_environment or "test"

        if pra_environment == 'test':
            return {
                'api_url': order.config_id.pra_test_api_url,
                'api_key': order.config_id.pra_test_api_key,
                'pos_id': order.config_id.pra_test_pos_id,
                'access_code': order.config_id.pra_test_access_code,
            }
        else:  # production environment
            return {
                'api_url': order.config_id.pra_production_api_url,
                'api_key': order.config_id.pra_production_api_key,
                'pos_id': order.config_id.pra_production_pos_id,
                'access_code': order.config_id.pra_production_access_code,
            }

    @api.model
    def _sync_with_pra(self, order):
        pra_config = self._get_pra_config(order)
        if not pra_config:
            raise UserError("Please configure the PRA before proceeding.")
        headers = {'Authorization': f'Bearer {pra_config["api_key"]}', 'Content-Type': 'application/json'}
        print(headers)
        if order.payment_ids.payment_method_id.pra_payment_id:

            if order.has_refundable_lines == False and not order.lines:
                invoice_type = 3
                invoice_refusin = self.pra_invoice_number
                lines = self.lines
                pos_order = self

            elif order.refunded_order_id:
                invoice_type = 3
                invoice_refusin = order.refunded_order_id.pra_invoice_number
                lines = order.refunded_order_id.lines
                pos_order = order.refunded_order_id

            else:
                invoice_type = 1
                invoice_refusin = None
                lines = order.lines
                pos_order = order

            data = {
                "InvoiceNumber": "",
                "POSID": pra_config["pos_id"],
                "USIN": "USIN0",
                "DateTime": order.date_order.strftime("%Y-%m-%d %H:%M:%S"),
                # "BuyerPNTN": order.partner_id.vat or "",  # Assuming the VAT is used as BuyerPNTN
                # "BuyerCNIC": "",  # You should have a field for CNIC
                # "BuyerName": order.partner_id.name,
                # "BuyerPhoneNumber": order.partner_id.phone or "",
                "BuyerPNTN": "1234567-8",
                "BuyerCNIC": "12345-1234567-8",
                "BuyerName": "Buyer Name",
                "BuyerPhoneNumber": "0000-0000000",
                "TotalBillAmount": abs(pos_order.amount_total),
                "TotalQuantity": abs(sum(line.qty for line in pos_order.lines)),
                "TotalSaleValue": abs(pos_order.amount_total),
                "TotalTaxCharged": abs(pos_order.amount_tax),
                # "Discount": self.get_custom_discount(pos_order),  # You might need to implement a discount field
                "Discount": 0.0,  # You might need to implement a discount field
                "FurtherTax": 0.0,  # Implement as necessary
                "PaymentMode": pos_order.online_payment_method_id.id or 1,
                # Define how you want to handle payment modes
                "RefUSIN": invoice_refusin,
                "InvoiceType": invoice_type,
                "Items": []
            }

            # Populate the Items list
            for line in lines:
                if line.price_unit >= 0 and line.product_id.is_discount_product != True:  # Assuming is_discount_product is a field in product
                    item = {
                        "ItemCode": line.product_id.default_code or "UNKNOWN",
                        "ItemName": line.product_id.name,
                        "Quantity": abs(line.qty),
                        "PCTCode": "00000000",  # Set the appropriate PCT code
                        "TaxRate": abs(line.tax_ids.amount or 0.0),
                        "SaleValue": abs(line.price_subtotal),
                        "TotalAmount": abs(line.price_subtotal_incl),
                        "TaxCharged": abs(line.price_subtotal_incl - line.price_subtotal or 0.0),
                        "Discount": abs(line.discount or 0.0),
                        "FurtherTax": 0.0,  # Handle if necessary
                        "InvoiceType": invoice_type,
                        "RefUSIN": invoice_refusin
                    }
                    data["Items"].append(item)
            # Log the data being sent to PRA log history
            if order:
                # Check if log already exists for this order
                existing_log = self.env['pos.order.log.history'].search([('pos_order_id', '=', pos_order.id)], limit=1)

                if existing_log:
                    # Update existing log
                    existing_log.write({
                        'pos_order_reference': pos_order.pos_reference,
                        'pos_order_id': pos_order.id,
                        'order_send_data': json.dumps(data, indent=4),
                    })
                    pra_log_history = existing_log
                else:
                    # Create new log history record
                    pra_log_history = self.env['pos.order.log.history'].create({
                        'pos_order_reference': pos_order.pos_reference,
                        'pos_order_id': pos_order.id,
                        'order_send_data': json.dumps(data, indent=4),
                    })

            try:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                logging.basicConfig(level=logging.DEBUG)
                logging.getLogger("urllib3").setLevel(logging.DEBUG)
                response = requests.post(pra_config['api_url'], headers=headers, json=data, verify=certifi.where())
                response_data = response.json()
                print(response_data)
                print(response_data['Code'])
                print(response_data['InvoiceNumber'])
                print(response_data['Response'])
                if response_data['Code'] == '100':
                    # Save the PRA invoice number and QR code
                    print("In Success Response")
                    pos_order.pra_invoice_number = response_data['InvoiceNumber']
                    qr_url = "https://reg.pra.punjab.gov.pk/IMSFiscalReport/SearchPOSInvoice_Report.aspx?PRAInvNo="
                    qr = qrcode.QRCode(
                        version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=1,
                    )
                    data = qr_url + response_data['InvoiceNumber']
                    qr.add_data(data)
                    qr.make(fit=True)
                    img = qr.make_image()
                    temp = BytesIO()
                    img.save(temp, format="PNG")
                    qr_image = base64.b64encode(temp.getvalue())
                    pos_order.pra_qr_code = qr_image
                    if response_data:
                        pra_log_history.write({
                            'pra_response': json.dumps(response_data, indent=4),
                            'pra_invoice_number': response_data['InvoiceNumber'],
                            'pra_qr_code': qr_image,
                            'pra_response_success': True,
                        })
                    print("Invoice Number Added Successfully to Odoo with PRA invoice number :",
                          response_data['InvoiceNumber'])
                else:
                    # Handle error
                    raise Exception(f"Error from PRA: {response_data.get('Response')}")
            except Exception as e:
                raise Exception(f"Error connecting to PRA: {str(e)}")
        elif order.id == self.id or self.id == True:
            if order.has_refundable_lines == False and not order.lines:
                invoice_type = 3
                invoice_refusin = self.pra_invoice_number
                lines = self.lines
                pos_order = self

            elif order.refunded_order_id:
                invoice_type = 3
                invoice_refusin = order.refunded_order_id.pra_invoice_number
                lines = order.refunded_order_id.lines
                pos_order = order.refunded_order_id

            else:
                invoice_type = 1
                invoice_refusin = None
                lines = order.lines
                pos_order = order

            data = {
                "InvoiceNumber": "",
                "POSID": pra_config["pos_id"],
                "USIN": "USIN0",
                "DateTime": order.date_order.strftime("%Y-%m-%d %H:%M:%S"),
                # "BuyerPNTN": order.partner_id.vat or "",  # Assuming the VAT is used as BuyerPNTN
                # "BuyerCNIC": "",  # You should have a field for CNIC
                # "BuyerName": order.partner_id.name,
                # "BuyerPhoneNumber": order.partner_id.phone or "",
                "BuyerPNTN": "1234567-8",
                "BuyerCNIC": "12345-1234567-8",
                "BuyerName": "Buyer Name",
                "BuyerPhoneNumber": "0000-0000000",
                "TotalBillAmount": abs(pos_order.amount_total),
                "TotalQuantity": abs(sum(line.qty for line in pos_order.lines)),
                "TotalSaleValue": abs(pos_order.amount_total),
                "TotalTaxCharged": abs(pos_order.amount_tax),
                "Discount": 0.0,  # You might need to implement a discount field
                # "Discount": self.get_custom_discount(pos_order),  # You might need to implement a discount field
                "FurtherTax": 0.0,  # Implement as necessary
                "PaymentMode": pos_order.online_payment_method_id.id or 1,
                # Define how you want to handle payment modes
                "RefUSIN": invoice_refusin,
                "InvoiceType": invoice_type,
                "Items": []
            }

            # Populate the Items list
            for line in lines:
                if line.price_unit >= 0 and line.product_id.is_discount_product != True:  # Assuming is_discount_product is a field in product
                    item = {
                        "ItemCode": line.product_id.default_code or "UNKNOWN",
                        "ItemName": line.product_id.name,
                        "Quantity": abs(line.qty),
                        "PCTCode": "00000000",  # Set the appropriate PCT code
                        "TaxRate": abs(line.tax_ids.amount or 0.0),
                        "SaleValue": abs(line.price_subtotal),
                        "TotalAmount": abs(line.price_subtotal_incl),
                        "TaxCharged": abs(line.price_subtotal_incl - line.price_subtotal or 0.0),
                        "Discount": abs(line.discount or 0.0),
                        "FurtherTax": 0.0,  # Handle if necessary
                        "InvoiceType": invoice_type,
                        "RefUSIN": invoice_refusin
                    }
                    data["Items"].append(item)
            # Log the data being sent to PRA log history
            if order:
                # Check if log already exists for this order
                existing_log = self.env['pos.order.log.history'].search([('pos_order_id', '=', pos_order.id)], limit=1)

                if existing_log:
                    # Update existing log
                    existing_log.write({
                        'pos_order_reference': pos_order.pos_reference,
                        'pos_order_id': pos_order.id,
                        'order_send_data': json.dumps(data, indent=4),
                    })
                    pra_log_history = existing_log
                else:
                    # Create new log history record
                    pra_log_history = self.env['pos.order.log.history'].create({
                        'pos_order_reference': pos_order.pos_reference,
                        'pos_order_id': pos_order.id,
                        'order_send_data': json.dumps(data, indent=4),
                    })

            try:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
                logging.basicConfig(level=logging.DEBUG)
                logging.getLogger("urllib3").setLevel(logging.DEBUG)
                response = requests.post(pra_config['api_url'], headers=headers, json=data, verify=certifi.where())
                response_data = response.json()
                print(response_data)
                print(response_data['Code'])
                print(response_data['InvoiceNumber'])
                print(response_data['Response'])
                if response_data['Code'] == '100':
                    # Save the PRA invoice number and QR code
                    print("In Success Response")
                    pos_order.pra_invoice_number = response_data['InvoiceNumber']
                    qr_url = "https://reg.pra.punjab.gov.pk/IMSFiscalReport/SearchPOSInvoice_Report.aspx?PRAInvNo="
                    qr = qrcode.QRCode(
                        version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=1,
                    )
                    data = qr_url + response_data['InvoiceNumber']
                    qr.add_data(data)
                    qr.make(fit=True)
                    img = qr.make_image()
                    temp = BytesIO()
                    img.save(temp, format="PNG")
                    qr_image = base64.b64encode(temp.getvalue())
                    pos_order.pra_qr_code = qr_image
                    if response_data:
                        pra_log_history.write({
                            'pra_response': json.dumps(response_data, indent=4),
                            'pra_invoice_number': response_data['InvoiceNumber'],
                            'pra_qr_code': qr_image,
                            'pra_response_success': True,
                        })
                    print("Invoice Number Added Successfully to Odoo with PRA invoice number :",
                          response_data['InvoiceNumber'])
                else:
                    # Handle error
                    raise Exception(f"Error from PRA: {response_data.get('Response')}")
            except Exception as e:
                raise Exception(f"Error connecting to PRA: {str(e)}")

    # def action_pos_order_paid(self):
    #     # Ensure that we sync with PRA before the order is fully validated
    #     if not self.pra_invoice_number:
    #         try:
    #             self._sync_with_pra(self)
    #         except Exception as e:
    #             _logger.error(f"Failed to sync order {self.id} with PRA: {str(e)}")

    def pra_sync_pos_orders(self):
        orders = self.search([('state', '=', 'paid'), ('pra_invoice_number', '=', False)])
        for order in orders:
            pra_environment = order.config_id.pra_sync_enabled
            if pra_environment:
                try:
                    self._sync_with_pra(order)
                except Exception as e:
                    _logger.error(f"Failed to sync order {order.id} with PRA: {str(e)}")

    # def get_custom_discount(self, order):
    #     """
    #     Custom method to calculate discount.
    #     This is a placeholder and should be replaced with actual logic.
    #     """
    #     for line in order.lines:
    #         discount_records = self.env['loyalty.program'].search([('product_id', '=', line.product_id.id)])
    #         if discount_records:
    #             return abs(line.price_subtotal_incl)
    #     return 0.0

    def action_pra_order(self):
        for order in self:
            if not order.pra_invoice_number:
                try:
                    self._sync_with_pra(order)
                    order.message_post(body="Order sent to PRA successfully.")
                except Exception as e:
                    raise UserError(f"Failed to send order to PRA: {str(e)}")

    # def refund(self):
    #     res = super().refund()
    #     for order in res:
    #         if order.pra_invoice_number:
    #             try:
    #                 self._sync_with_pra(order)
    #             except Exception as e:
    #                 _logger.error(f"Failed to sync refunded order {order.id} with PRA: {str(e)}")

    @api.model_create_multi
    def create(self, vals_list):
        order = super().create(vals_list)
        if order.config_id.pra_integration_enabled:
            try:
                self._sync_with_pra(order)
            except Exception as e:
                _logger.error(f"Failed to sync new order {order.id} with PRA: {str(e)}")
                raise UserError(f"Failed to send order to PRA: {str(e)}")
        return order
