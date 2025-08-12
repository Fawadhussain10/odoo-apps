import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { rpc } from "@web/core/network/rpc";

patch(PaymentScreen.prototype, {
    name: "fbr_integration_pos_payment_patch",
    async _finalizeValidation() {
        await super._finalizeValidation();
        const order = this.currentOrder;
        try {
            const orderId = order.id;
            if (!orderId) {
                console.warn("No orderId found for order.");
                return;
            }
            const orderResult = await rpc("/web/dataset/call_kw", {
                model: "pos.order",
                method: "read",
                args: [[orderId], ["account_move"]],
                kwargs: {},
            });
            const accountMoveField = orderResult[0].account_move;
            if (!accountMoveField || !accountMoveField[0]) {
                console.warn("No account_move ID found.");
                return;
            }
            const accountMoveId = accountMoveField[0]; // 169
            const accountMoveResult = await rpc("/web/dataset/call_kw", {
                model: "account.move",
                method: "read",
                args: [[accountMoveId], ["fbr_invoice_number", "fbr_qr_image"]],
                kwargs: {},
            });
            const moveData = accountMoveResult[0];
            if (moveData) {
                order.fbr_invoice_number = moveData.fbr_invoice_number || "";
                order.fbr_qr_image = moveData.fbr_qr_image || "";
            } else {
                console.warn("No account_move found for backend order:", orderId);
            }
        } catch (error) {
            console.error("Error fetching FBR data:", error);
        }
    },
});

patch(PosOrder.prototype, {
  export_for_printing() {
    const result = super.export_for_printing(...arguments);
    result.fbr_invoice_number = this.fbr_invoice_number || "";
    result.fbr_qr_image_uri = this.fbr_qr_image
            ? "data:image/png;base64," + this.fbr_qr_image
            : "";
    return result;
  },
});
