/** @odoo-module **/

import { patch } from '@web/core/utils/patch';

import { PaymentForm } from '@payment/interactions/payment_form';

patch(PaymentForm.prototype, {

    /**
     * Add `pb_appointment_id` to the transaction route params if it is provided.
     *
     * @override method from payment.payment_form
     * @private
     * @return {object} The extended transaction route params
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = super._prepareTransactionRouteParams(...arguments);
        return {
            ...transactionRouteParams,
            'pb_appointment_id': this.paymentContext.pbAppointmentId
                ? parseInt(this.paymentContext.pbAppointmentId) : undefined,
        };
    },

});
