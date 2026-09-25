import { Component, usePlugin, useProps, xml } from "@odoo/owl";
import { BarcodePlugin } from "@barcodes/barcode_plugin";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Invisible field widget forwarding scanned barcodes to the record, which
 * triggers the server-side onchange of pb.hms.barcode.scan.mixin.
 */
export class PbHmsBarcodeHandlerField extends Component {
    static template = xml``;
    props = useProps(standardFieldProps);

    setup() {
        const barcode = usePlugin(BarcodePlugin);
        useBus(barcode.bus, "barcode_scanned", (ev) => {
            this.props.record.update({ [this.props.name]: ev.detail.barcode });
        });
    }
}

registry.category("fields").add("pb_hms_barcode_handler", { component: PbHmsBarcodeHandlerField });
