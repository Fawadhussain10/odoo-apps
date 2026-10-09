/** @odoo-module **/
import { Component, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const FRAME_INTERVAL = 250; // ~4 frames per second
const STATE_INTERVAL = 1000;
const TEXT_FLUSH = 120;
const NAMED_KEYS = new Set(["Enter", "Tab", "Backspace", "Delete", "Escape", "ArrowLeft", "ArrowRight",
    "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]);
const ACTIVE = new Set(["starting", "waiting", "two_step", "captcha", "validating"]);

/**
 * Connect LinkedIn: log in here (the sign-in browser streamed from the server),
 * import a session made on your own computer, or paste the li_at cookie.
 * Typed text goes straight to the sign-in browser; it is not kept here.
 */
export class LinkedInConnect extends Component {
    static template = "linkedin_sales_automation.Connect";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        const params = this.props.action.params || {};
        this.profileId = params.profile_id;
        this.profileName = params.profile_name;
        this.xvfb = params.xvfb;
        this.screen = useRef("screen");
        this.fileInput = useRef("file");
        this.state = useState({
            tab: "login", busy: false, token: null, state: "none", message: "", error: "",
            frameUrl: null, seq: -1, liAt: "", displayName: "",
        });
        this.textBuffer = "";
        this.timers = [];
        onWillUnmount(() => this.stopPolling());
    }

    setTab(tab) {
        this.state.tab = tab;
        this.state.error = "";
    }
    get active() {
        return ACTIVE.has(this.state.state);
    }
    get showScreen() {
        return this.state.tab === "login" && this.state.token && this.state.state !== "validating"
            && this.state.state !== "connected" && this.state.state !== "failed";
    }
    url(path) {
        return `/li_sales/connect/${this.profileId}/${path}`;
    }

    // ------------------------------------------------------------ start
    async startLogin() {
        await this.begin(() => rpc(this.url("start"), {}));
    }
    async sendCookie() {
        const value = this.state.liAt;
        this.state.liAt = ""; // never kept in the page
        await this.begin(() => rpc(this.url("cookie"), { li_at: value }));
    }
    async importSession() {
        const file = this.fileInput.el && this.fileInput.el.files[0];
        if (!file) {
            this.state.error = _t("Choose the zip file first.");
            return;
        }
        await this.begin(async () => {
            const form = new FormData();
            form.append("session_file", file);
            form.append("csrf_token", odoo.csrf_token);
            const response = await fetch(this.url("import"), { method: "POST", body: form });
            return response.json();
        });
    }
    async begin(call) {
        this.state.error = "";
        this.state.busy = true;
        try {
            const result = await call();
            if (result.error) {
                this.state.error = result.error;
                return;
            }
            this.state.token = result.token;
            this.applyView(result);
            this.startPolling();
        } finally {
            this.state.busy = false;
        }
    }

    // ------------------------------------------------------------ polling
    startPolling() {
        this.stopPolling();
        this.timers.push(setInterval(() => this.pollState(), STATE_INTERVAL));
        if (this.state.tab === "login") {
            this.timers.push(setInterval(() => this.pollFrame(), FRAME_INTERVAL));
        }
    }
    stopPolling() {
        this.timers.forEach((t) => clearInterval(t));
        this.timers = [];
        if (this.flushTimer) {
            clearTimeout(this.flushTimer);
        }
    }
    applyView(view) {
        this.state.state = view.state;
        this.state.message = view.message;
        this.state.displayName = view.display_name || "";
        if (!ACTIVE.has(view.state)) {
            this.stopPolling();
        }
    }
    async pollState() {
        if (this.polling) {
            return;
        }
        this.polling = true;
        try {
            const view = await rpc(this.url("state"), { token: this.state.token });
            if (view.error) {
                this.state.error = view.error;
                this.stopPolling();
            } else {
                this.applyView(view);
            }
        } finally {
            this.polling = false;
        }
    }
    async pollFrame() {
        if (this.framing || !this.showScreen) {
            return;
        }
        this.framing = true;
        try {
            const response = await fetch(`${this.url("frame")}?after=${this.state.seq}`, {
                headers: { "X-Login-Token": this.state.token },
            });
            if (response.status === 200) {
                const blob = await response.blob();
                const old = this.state.frameUrl;
                this.state.frameUrl = URL.createObjectURL(blob);
                this.state.seq = parseInt(response.headers.get("X-Frame-Seq") || "0");
                if (old) {
                    URL.revokeObjectURL(old);
                }
            }
        } catch {
            // next tick retries
        } finally {
            this.framing = false;
        }
    }

    // ------------------------------------------------------------ input
    send(events) {
        if (!this.active || !this.state.token) {
            return;
        }
        rpc(this.url("input"), { token: this.state.token, events }, { silent: true });
    }
    point(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        return { x: (ev.clientX - rect.left) / rect.width, y: (ev.clientY - rect.top) / rect.height };
    }
    onClick(ev) {
        ev.currentTarget.focus();
        this.flushText();
        this.send([{ type: "click", button: "left", ...this.point(ev) }]);
    }
    onDblClick(ev) {
        this.send([{ type: "dblclick", button: "left", ...this.point(ev) }]);
    }
    onWheel(ev) {
        ev.preventDefault();
        this.send([{ type: "scroll", dx: Math.round(ev.deltaX), dy: Math.round(ev.deltaY) }]);
    }
    onKeyDown(ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "v") {
            return; // paste event follows
        }
        if (ev.ctrlKey || ev.metaKey || ev.altKey) {
            if (/^[a-zA-Z0-9]$/.test(ev.key)) {
                ev.preventDefault();
                this.flushText();
                const mod = ev.ctrlKey ? "Control" : ev.metaKey ? "Meta" : "Alt";
                this.send([{ type: "key", key: `${mod}+${ev.key}` }]);
            }
            return;
        }
        if (NAMED_KEYS.has(ev.key)) {
            ev.preventDefault();
            this.flushText();
            this.send([{ type: "key", key: ev.key }]);
        } else if (ev.key.length === 1) {
            ev.preventDefault();
            this.textBuffer += ev.key;
            if (!this.flushTimer) {
                this.flushTimer = setTimeout(() => this.flushText(), TEXT_FLUSH);
            }
        }
    }
    onPaste(ev) {
        ev.preventDefault();
        const text = (ev.clipboardData && ev.clipboardData.getData("text")) || "";
        if (text) {
            this.flushText();
            this.send([{ type: "text", text: text.slice(0, 512) }]);
        }
    }
    flushText() {
        if (this.flushTimer) {
            clearTimeout(this.flushTimer);
            this.flushTimer = null;
        }
        if (this.textBuffer) {
            const text = this.textBuffer;
            this.textBuffer = "";
            this.send([{ type: "text", text }]);
        }
    }

    // ------------------------------------------------------------ end
    async cancel() {
        if (this.state.token && this.active) {
            const view = await rpc(this.url("cancel"), { token: this.state.token });
            this.applyView(view);
        }
    }
    async close() {
        await this.cancel();
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
    async done() {
        this.stopPolling();
        await this.action.doAction({ type: "ir.actions.act_window_close" });
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "li.profile", res_id: this.profileId,
            views: [[false, "form"]],
        });
    }
    restart() {
        this.stopPolling();
        Object.assign(this.state, { token: null, state: "none", message: "", error: "", seq: -1 });
    }
}

registry.category("actions").add("li_linkedin_connect", LinkedInConnect);
