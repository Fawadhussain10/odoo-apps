
// pos_store_patch.js - Corrected version
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    getReceiptHeaderData(order) {
        const result = super.getReceiptHeaderData(order);

        if (order) {
            result.pra_invoice_number = order.pra_invoice_number || 'N/A';
            result.pra_qr_code_available = !!order.pra_qr_code;
            result.id = order.id;
        }

        return result;
    },
});