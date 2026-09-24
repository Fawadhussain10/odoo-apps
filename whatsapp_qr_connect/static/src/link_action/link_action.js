import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const POLL_MS = 2000;

export class WhatsappLinkAction extends Component {
    static template = "whatsapp_qr_connect.LinkAction";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.accountId = this.props.action.params.account_id;
        this.state = useState({
            status: "linking",
            qr: false,
            error: false,
            phone: false,
            waited: 0,
        });
        this.timer = null;
        onWillStart(() => this.poll());
        onWillUnmount(() => this.stopPolling());
        this.startPolling();
    }

    startPolling() {
        this.stopPolling();
        this.timer = setInterval(() => this.poll(), POLL_MS);
    }

    stopPolling() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    async poll() {
        let data;
        try {
            data = await this.orm.call("whatsapp.account", "get_link_status", [[this.accountId]]);
        } catch (error) {
            this.state.error = error.data?.message || _t("Could not read the linking status.");
            return;
        }
        this.state.status = data.state;
        this.state.qr = data.qr_image;
        this.state.phone = data.phone;
        this.state.error = data.error;
        this.state.waited += POLL_MS / 1000;
        if (data.state === "connected") {
            this.stopPolling();
            this.notification.add(
                _t("WhatsApp number %s linked successfully.", data.phone || ""),
                { type: "success" }
            );
            this.openAccount();
        } else if (data.state !== "linking") {
            this.stopPolling();
        }
    }

    get isStarting() {
        return this.state.status === "linking" && !this.state.qr;
    }

    async retry() {
        this.state.error = false;
        this.state.qr = false;
        this.state.status = "linking";
        this.state.waited = 0;
        await this.orm.call("whatsapp.account", "action_link", [[this.accountId]]);
        this.startPolling();
    }

    async cancel() {
        this.stopPolling();
        await this.orm.call("whatsapp.account", "action_cancel_link", [[this.accountId]]);
        this.openAccount();
    }

    openAccount() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "whatsapp.account",
            res_id: this.accountId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("whatsapp_qr_connect.link_action", WhatsappLinkAction);
