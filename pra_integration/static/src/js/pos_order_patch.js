// pos_order_patch.js - Simplified approach
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    export_for_printing(baseUrl, headerData) {
        const result = super.export_for_printing(baseUrl, headerData);

        // Add SRB invoice data
        result.pra_invoice_number = this.pra_invoice_number || 'N/A';
        result.pra_qr_code_available = !!this.pra_qr_code;
        result.id = this.id;

        return result;
    },
});