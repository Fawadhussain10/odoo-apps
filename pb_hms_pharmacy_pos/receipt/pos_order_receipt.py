import json

from odoo import models


class PosOrderReceipt(models.AbstractModel):
    _inherit = 'pos.order.receipt'

    def _order_receipt_generate_line_data(self):
        line_data = super()._order_receipt_generate_line_data()
        for idx, line in enumerate(self.lines):
            data = line_data[idx]
            data['prescription_order_name'] = line.prescription_order_origin_id.name or False
            try:
                data['pb_kit_lines'] = json.loads(line.pb_kit_details) if line.pb_kit_details else []
            except ValueError:
                data['pb_kit_lines'] = []
        return line_data
