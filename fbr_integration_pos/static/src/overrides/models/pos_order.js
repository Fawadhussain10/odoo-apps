import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    setup() {
        super.setup(...arguments);
        if(this.config.auto_invoice_on_payment && !this.uiState.locked){
            this.update({ to_invoice: this.config.auto_invoice_on_payment});
        }
    },
});
