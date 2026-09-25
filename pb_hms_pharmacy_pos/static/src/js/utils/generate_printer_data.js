import { patch } from "@web/core/utils/patch";
import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";

/**
 * Mirrors PosOrderReceipt._order_receipt_generate_line_data (Python).
 */
patch(GeneratePrinterData.prototype, {
    generateLineData() {
        const data = super.generateLineData(...arguments);
        for (const index in this.order.lines) {
            const line = this.order.lines[index];
            const prescription = line.getPrescriptionOrder();
            data[index].prescription_order_name = prescription?.name || false;
            data[index].pb_kit_lines = prescription?.details || [];
        }
        return data;
    },
});
