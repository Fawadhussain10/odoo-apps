import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    export_for_printing(baseUrl, headerData) {
        const result = super.export_for_printing(...arguments);
        if (this.pra_invoice_number) {
            result.pra = {
                invoice_number: this.pra_invoice_number,
                qr_image: this.pra_qr_image || false,
                pos_id: this.config?.pra_pos_id || false,
            };
        }
        return result;
    },
});
