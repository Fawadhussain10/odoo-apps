import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const POLL_MS = 10000;   // safety net only: replies are pushed over the bus websocket
const POPUP_MS = 2000;

/**
 * Runs in every Odoo screen: asks the server for new WhatsApp replies and shows
 * a short "new message" pop-up (2 seconds) - the chat screen is told through a
 * window event so that it can refresh itself.
 */
export const whatsappInboxNotifier = {
    dependencies: ["orm", "notification", "action", "bus_service"],
    start(env, { orm, notification, action, bus_service }) {
        if (!user.isInternalUser) {
            return {};
        }
        // only members of WhatsApp / Chat User take part
        user.hasGroup("whatsapp_qr_connect.group_whatsapp_chat").then((allowed) => {
            if (allowed) {
                init();
            }
        });
        return {};

        function init() {
            let lastId = null;
            let busy = false;

            function showPopup(items) {
                const last = items[items.length - 1];
                const more = items.length - 1;
                notification.add(
                    more
                        ? _t("%(name)s and %(n)s more: new WhatsApp messages", {
                              name: last.name,
                              n: more,
                          })
                        : _t("New WhatsApp message from %(name)s: %(text)s", {
                              name: last.name,
                              text: last.text,
                          }),
                    {
                        type: "success",
                        title: _t("WhatsApp"),
                        autocloseDelay: POPUP_MS,
                        className: "o_whatsapp_popup",
                        buttons: [
                            {
                                name: _t("Open"),
                                primary: true,
                                onClick: () =>
                                    action.doAction({
                                        type: "ir.actions.client",
                                        tag: "whatsapp_qr_connect.inbox",
                                        context: { active_chat_id: last.chat_id },
                                    }),
                            },
                        ],
                    }
                );
            }

            function refreshScreens(detail) {
                window.dispatchEvent(new CustomEvent("whatsapp-new-messages", { detail }));
            }

            // instant path: the server pushes every stored reply over the bus websocket
            bus_service.subscribe("whatsapp_qr_connect.new_message", (payload) => {
                if (lastId === null || payload.id <= lastId) {
                    return;
                }
                lastId = payload.id;
                showPopup([payload]);
                refreshScreens(payload);
            });
            bus_service.start?.();

            async function poll() {
                if (busy || document.hidden) {
                    return;
                }
                busy = true;
                try {
                    const data = await orm.call("whatsapp.chat", "poll", [lastId || 0]);
                    const first = lastId === null;
                    if (!first && data.new.length) {
                        showPopup(data.new);
                    }
                    if (first || data.new.length) {
                        refreshScreens(data);
                    }
                    lastId = Math.max(lastId || 0, data.last_id);
                } catch {
                    // offline / logged out: try again on the next tick
                } finally {
                    busy = false;
                }
            }

            poll();
            setInterval(poll, POLL_MS);
        }
    },
};

registry.category("services").add("whatsapp_inbox_notifier", whatsappInboxNotifier);
