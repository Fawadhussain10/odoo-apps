/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { Record } from "@web/model/relational_model/record";
import { toRaw } from "@odoo/owl";

patch(Record.prototype, {
    /**
     * List the missing required fields by name in the save-blocked
     * notification, instead of just a generic "Missing required fields"
     * message, so the user knows exactly what to fill in.
     *
     * @override
     */
    _displayInvalidFieldNotification() {
        const invalidFields = [...toRaw(this._invalidFields)];
        const labels = invalidFields.map((fieldName) => {
            const activeField = this.activeFields[fieldName];
            const field = this.fields[fieldName];
            return (activeField && activeField.string) || (field && field.string) || fieldName;
        });

        const message = labels.length
            ? _t("Missing required fields: %(fields)s", { fields: labels.join(", ") })
            : _t("Missing required fields");

        return this.model.notification.add(message, { type: "danger" });
    },
});
