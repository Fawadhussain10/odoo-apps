/** @odoo-module **/

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    get_prescription_order() {
        if (this.prescription_order_origin_id) {
            let details = false;
            try {
                details = this.pb_kit_details ? JSON.parse(this.pb_kit_details) : false;
            } catch {
                details = false;
            }
            return {
                name: this.prescription_order_origin_id.name,
                details,
                is_kit_product: this.prescription_order_line_id?.is_kit_product || false,
                kit_product_name: this.prescription_order_line_id?.kit_product_name || false,
                kit_product_qty: this.prescription_order_line_id?.kit_product_qty || false,
            };
        }
        return false;
    },
    /**
     * Set quantity based on the given prescription order line.
     * @param {'prescription.line'} prescriptionOrderLine
     */
    setQuantityFromSOL(prescriptionOrderLine) {
        if (this.product_id.type === "service") {
            this.setQuantity(prescriptionOrderLine.qty_to_invoice);
        } else {
            this.setQuantity(
                prescriptionOrderLine.product_uom_qty -
                    Math.max(prescriptionOrderLine.qty_delivered, prescriptionOrderLine.qty_invoiced)
            );
        }
    },
});
