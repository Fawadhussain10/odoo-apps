import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("whatsapp_qr_connect_link_tour", {
    steps: () => [
        {
            content: "The QR screen shows the code",
            trigger: ".o_whatsapp_link .o_whatsapp_qr img[src^='data:image/png;base64,']",
        },
        {
            content: "Instructions are visible",
            trigger: ".o_whatsapp_link .o_whatsapp_steps",
        },
        {
            content: "Cancel linking",
            trigger: ".o_whatsapp_link button:contains('Cancel')",
            run: "click",
        },
        {
            content: "Back on the number form, not linked",
            trigger: ".o_form_view .o_statusbar_status .o_arrow_button_current:contains('Not Linked')",
        },
    ],
});
