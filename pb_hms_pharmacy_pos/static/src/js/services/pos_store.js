/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async onClickPrescriptionOrder(clickedOrderId) {
        const prescription_order = await this._getPrescriptionOrder(clickedOrderId);
        await this._processPrescriptionOrder(prescription_order);
    },
    async _getPrescriptionOrder(id) {
        const result = await this.data.callRelated(
            "prescription.order",
            "load_prescription_order_from_pos",
            [id, this.config.id]
        );
        return result["prescription.order"][0];
    },
    async _processPrescriptionOrder(prescription_order) {
        if (prescription_order.partner_id) {
            this.getOrder().setPartner(prescription_order.partner_id);
        }

        // Fiscal position should be set after the partner is set
        // to ensure that the fiscal position is correctly computed
        // based on the prescription order.
        const orderFiscalPos = prescription_order.fiscal_position_id;
        this.getOrder().update({
            fiscal_position_id: orderFiscalPos,
        });

        const selectedOption = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("What do you want to do?"),
            list: [{ id: "0", label: _t("Settle the order"), item: "settle" }],
        });
        if (!selectedOption) {
            return;
        }
        await this.settlePrescriptionOrder(prescription_order, orderFiscalPos);
        this.selectOrderLine(this.getOrder(), this.getOrder().lines.at(-1));
    },
    async settlePrescriptionOrder(prescription_order, orderFiscalPos) {
        if (prescription_order.pricelist_id) {
            this.getOrder().setPricelist(prescription_order.pricelist_id);
        }

        const lines = prescription_order.prescription_line_ids;
        const productToAddInPos = lines
            .filter((line) => line.product_id && !this.models["product.product"].get(line.product_id.id))
            .map((line) => line.product_id.id);
        if (productToAddInPos.length) {
            const confirmed = await ask(this.dialog, {
                title: _t("Products not available in POS"),
                body: _t(
                    "Some of the products in your Prescription Order are not available in POS, do you want to import them?"
                ),
            });
            if (confirmed) {
                await this.data.searchRead("product.product", [["id", "in", productToAddInPos]], []);
            }
        }

        const converted_lines = await this.data.call("prescription.line", "read_converted", [
            lines.map((l) => l.id),
        ]);

        /**
         * This variable will have 3 values, `undefined | false | true`.
         * Initially, it is `undefined`. When looping thru each prescription.line,
         * when a line comes with lots (`.lot_names`), we use these lot names
         * as the pack lot of the generated pos.order.line. We ask the user
         * if they want to use the lots that come with the prescription.lines to
         * be used on the corresponding pos.order.line only once. So, once the
         * `useLoadedLots` becomes true, it will be true for the succeeding lines,
         * and vice versa.
         */
        let useLoadedLots;

        for (const line of lines) {
            if (!line.product_id || !this.models["product.product"].get(line.product_id.id)) {
                continue;
            }
            const converted_line = converted_lines.find((l) => l.id === line.id);
            if (!converted_line) {
                continue;
            }

            const product = this.models["product.product"].get(line.product_id.id);
            const taxes = orderFiscalPos
                ? orderFiscalPos.getTaxesAfterFiscalPosition(converted_line.tax_ids)
                : converted_line.tax_ids;

            const newLine = await this.addLineToCurrentOrder(
                {
                    product_id: product,
                    product_tmpl_id: product.product_tmpl_id,
                    qty: converted_line.product_uom_qty,
                    price_unit: converted_line.price_unit,
                    price_type: "manual",
                    tax_ids: taxes.map((tax) => ["link", tax]),
                    prescription_order_origin_id: prescription_order,
                    prescription_order_line_id: line,
                    customer_note: converted_line.customer_note,
                    description: converted_line.name,
                    order_id: this.getOrder(),
                },
                {},
                false
            );

            if (
                newLine.getProduct().tracking !== "none" &&
                (this.pickingType.use_create_lots || this.pickingType.use_existing_lots) &&
                (converted_line.lot_names || []).length > 0
            ) {
                // Ask once when `useLoadedLots` is undefined, then reuse its value on the succeeding lines.
                if (useLoadedLots === undefined) {
                    useLoadedLots = await ask(this.dialog, {
                        title: _t("SN/Lots Loading"),
                        body: _t("Do you want to load the SN/Lots linked to the Prescriptions Order?"),
                    });
                }
                if (useLoadedLots) {
                    newLine.setPackLotLines({
                        modifiedPackLotLines: [],
                        newPackLotLines: (converted_line.lot_names || []).map((name) => ({
                            lot_name: name,
                        })),
                    });
                }
            }
            newLine.setQuantityFromSOL(converted_line);
            newLine.setUnitPrice(converted_line.price_unit);
            newLine.setDiscount(converted_line.discount);
        }
    },
});
