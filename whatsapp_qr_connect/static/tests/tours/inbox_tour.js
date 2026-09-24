import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

registry.category("web_tour.tours").add("whatsapp_qr_connect_inbox_tour", {
    steps: () => [
        {
            content: "Open the WhatsApp app from the home screen",
            trigger: ".o_app[data-menu-xmlid='whatsapp_qr_connect.menu_whatsapp_inbox_app']",
            run: "click",
        },
        {
            content: "The chat exists and shows an unread badge",
            trigger: ".o_wa_chat:contains('Ali') .o_wa_unread:contains('2')",
        },
        { content: "Open the chat", trigger: ".o_wa_chat:contains('Ali')", run: "click" },
        {
            content: "The conversation opens at the newest message",
            trigger: ".o_wa_thread",
            run: async ({ anchor }) => {
                await new Promise((r) => setTimeout(r, 900));
                if (anchor.scrollHeight - anchor.scrollTop - anchor.clientHeight > 5) {
                    throw new Error("thread is not scrolled to the latest message");
                }
            },
        },
        { content: "Incoming bubble", trigger: ".o_wa_bubble.o_wa_in:contains('Reply from customer')" },
        { content: "Image is shown", trigger: ".o_wa_bubble.o_wa_in img.o_wa_media[src^='/web/image/']" },
        { content: "Outgoing bubble", trigger: ".o_wa_bubble.o_wa_out:contains('Hello from Odoo')" },
        { content: "Unread badge is gone", trigger: ".o_wa_chat:contains('Ali'):not(:has(.o_wa_unread))" },
        { content: "Type a reply", trigger: ".o_wa_input", run: "edit Thanks for the reply" },
        { content: "Send", trigger: ".o_wa_send", run: "click" },
        { content: "Reply shown", trigger: ".o_wa_bubble.o_wa_out:contains('Thanks for the reply')" },
    ],
});

registry.category("web_tour.tours").add("whatsapp_qr_connect_popup_tour", {
    steps: () => [
        { content: "Any Odoo screen is open", trigger: ".o_action_manager" },
        {
            content: "A reply arrives from WhatsApp (stored by the server)",
            trigger: "body",
            run: async () => {
                await new Promise((r) => setTimeout(r, 1500)); // let the first poll set its baseline
                const [chat] = await rpc("/web/dataset/call_kw/whatsapp.chat/search_read", {
                    model: "whatsapp.chat", method: "search_read", args: [[], ["id"]], kwargs: { limit: 1 } });
                await rpc("/web/dataset/call_kw/whatsapp.message/create", {
                    model: "whatsapp.message", method: "create", kwargs: {},
                    args: [{ chat_id: chat.id, phone: "923001234567", direction: "in",
                             status: "RECEIVED", is_read: false, body: "ping" }] });
            },
        },
        {
            content: "Pop-up announces the new message",
            trigger: ".o_notification:contains('New WhatsApp message from Ali')",
            timeout: 20000,
        },
        {
            content: "It disappears after about 2 seconds",
            trigger: "body:not(:has(.o_notification:contains('New WhatsApp message')))",
        },
    ],
});
