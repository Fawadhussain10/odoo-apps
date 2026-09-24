import { Component, onMounted, onWillDestroy, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const REFRESH_MS = 10000;
const MAX_FILE_BYTES = 16 * 1024 * 1024;
const EMOJIS = (
    "😀 😃 😄 😁 😆 😅 😂 🤣 😊 🙂 😉 😍 🥰 😘 😋 😎 🤩 🥳 😇 🤗 🤔 😐 🙄 😏 😴 😢 😭 😡 😱 🙏 " +
    "👍 👎 👌 ✌️ 🤝 👏 🙌 💪 👋 🤞 ❤️ 💛 💚 💙 🔥 ⭐ ✨ 🎉 🎁 💯 ✅ ❌ ⚠️ ❓ ❗ 📞 📦 🚚 💰 🧾 📅 🕐"
).split(" ");

const AVATAR_COLORS = ["#128c7e", "#5b6cff", "#e8590c", "#c2255c", "#7048e8", "#1098ad", "#d9480f", "#2f9e44"];

function toLocal(sqlDate) {
    try {
        return sqlDate ? deserializeDateTime(sqlDate) : null;
    } catch {
        return null;
    }
}

export class WhatsappInbox extends Component {
    static template = "whatsapp_qr_connect.Inbox";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            chats: [],
            hasLinked: true,
            search: "",
            filter: "all",
            atBottom: true,
            activeId: this.props.action.context?.active_chat_id || false,
            active: false,
            messages: [],
            draft: "",
            files: [],
            showEmoji: false,
            sending: false,
            checking: false,
            loaded: false,
        });
        this.onNew = () => this.refresh();
        onWillStart(() => this.loadChats());
        onMounted(async () => {
            if (this.state.activeId) {
                await this.openChat(this.state.activeId);
            }
            window.addEventListener("whatsapp-new-messages", this.onNew);
            this.timer = setInterval(() => this.refresh(), REFRESH_MS);
        });
        onWillDestroy(() => {
            window.removeEventListener("whatsapp-new-messages", this.onNew);
            clearInterval(this.timer);
        });
    }

    get unreadTotal() {
        return this.state.chats.reduce((sum, c) => sum + c.unread, 0);
    }

    setFilter(filter) {
        this.state.filter = filter;
    }

    onThreadScroll(ev) {
        const el = ev.target;
        this.state.atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        this.stick = this.state.atBottom;
    }

    jumpDown() {
        const el = document.querySelector(".o_wa_thread");
        if (el) {
            el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
        }
    }

    avatarColor(name) {
        let hash = 0;
        for (const ch of name || "") {
            hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
        }
        return AVATAR_COLORS[hash % AVATAR_COLORS.length];
    }

    initial(name) {
        return ((name || "#").replace("+", "")[0] || "#").toUpperCase();
    }

    /** "14:05" today, "Yesterday", otherwise "24/09/2026" (list rows). */
    shortWhen(sqlDate) {
        const dt = toLocal(sqlDate);
        if (!dt) {
            return "";
        }
        const now = new Date();
        const days = Math.round(
            (new Date(now.getFullYear(), now.getMonth(), now.getDate()) -
                new Date(dt.year, dt.month - 1, dt.day)) /
                86400000
        );
        if (days === 0) {
            return dt.toFormat("HH:mm");
        }
        return days === 1 ? _t("Yesterday") : dt.toFormat("dd/MM/yyyy");
    }

    clock(sqlDate) {
        return toLocal(sqlDate)?.toFormat("HH:mm") || "";
    }

    /** Thread rows: a day separator before the first message of each day. */
    get threadItems() {
        const items = [];
        let lastDay = null;
        let prev = null;
        for (const msg of this.state.messages) {
            const dt = toLocal(msg.date);
            const day = dt ? dt.toFormat("yyyy-MM-dd") : "";
            if (day !== lastDay) {
                lastDay = day;
                prev = null;
                items.push({ id: "day-" + day, day: true, label: this.dayLabel(msg.date) });
            }
            // consecutive messages of one side within 5 minutes form a visual group
            const first =
                !prev ||
                prev.msg.direction !== msg.direction ||
                (dt && prev.dt && dt.toMillis() - prev.dt.toMillis() > 5 * 60 * 1000);
            const item = { id: msg.id, day: false, msg, first, last: true, dt };
            if (prev && !first) {
                prev.item.last = false;
            }
            prev = { msg, dt, item };
            items.push(item);
        }
        return items;
    }

    dayLabel(sqlDate) {
        const when = this.shortWhen(sqlDate);
        return when.includes(":") ? _t("Today") : when || "";
    }

    isImage(file) {
        return file?.mimetype?.startsWith("image/");
    }

    isPdf(file) {
        return file?.mimetype === "application/pdf";
    }

    get emojis() {
        return EMOJIS;
    }

    get canSend() {
        return !this.state.sending && (this.state.draft.trim() || this.state.files.length);
    }

    get filteredChats() {
        const term = this.state.search.trim().toLowerCase();
        let chats = this.state.chats;
        if (this.state.filter === "unread") {
            chats = chats.filter((c) => c.unread);
        }
        return term
            ? chats.filter((c) => c.name.toLowerCase().includes(term) || c.phone.includes(term))
            : chats;
    }

    async loadChats() {
        const data = await this.orm.call("whatsapp.chat", "get_chats", []);
        this.state.chats = data.chats;
        this.state.hasLinked = data.has_linked;
        this.state.loaded = true;
    }

    async refresh() {
        try {
            await this.loadChats();
            if (this.state.activeId) {
                const data = await this.orm.call("whatsapp.chat", "get_messages", [
                    [this.state.activeId],
                ]);
                if (data.messages.length !== this.state.messages.length) {
                    this.state.messages = data.messages;
                    if (this.state.atBottom) {
                        this.scrollDown();
                    }
                    await this.loadChats();
                }
            }
        } catch {
            // ignore transient errors
        }
    }

    async openChat(chatId) {
        this.state.activeId = chatId;
        const data = await this.orm.call("whatsapp.chat", "get_messages", [[chatId]]);
        this.state.active = data.chat;
        this.state.messages = data.messages;
        await this.loadChats();
        this.scrollDown();
    }

    /** Show the newest messages: re-applied while pictures load and change the height. */
    scrollDown() {
        this.stick = true;
        this.state.atBottom = true;
        const go = () => {
            const el = document.querySelector(".o_wa_thread");
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        };
        requestAnimationFrame(() => {
            go();
            requestAnimationFrame(go);
        });
        setTimeout(go, 150);
        setTimeout(go, 500);
    }

    onMediaLoad() {
        if (this.stick) {
            const el = document.querySelector(".o_wa_thread");
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    addEmoji(emoji) {
        const input = document.querySelector(".o_wa_input");
        const start = input ? input.selectionStart : this.state.draft.length;
        const end = input ? input.selectionEnd : start;
        this.state.draft = this.state.draft.slice(0, start) + emoji + this.state.draft.slice(end);
        if (input) {
            input.value = this.state.draft;
            input.focus();
            const pos = start + emoji.length;
            input.setSelectionRange(pos, pos);
        }
    }

    toggleEmoji() {
        this.state.showEmoji = !this.state.showEmoji;
    }

    pickFiles() {
        document.querySelector(".o_wa_file_input")?.click();
    }

    async onFilesPicked(ev) {
        await this.addFiles([...ev.target.files]);
        ev.target.value = "";
    }

    onPaste(ev) {
        const files = [...(ev.clipboardData?.files || [])];
        if (files.length) {
            ev.preventDefault();
            this.addFiles(files);
        }
    }

    onDrop(ev) {
        ev.preventDefault();
        this.addFiles([...(ev.dataTransfer?.files || [])]);
    }

    async addFiles(files) {
        for (const file of files) {
            if (file.size > MAX_FILE_BYTES) {
                this.notification.add(_t("'%s' is larger than 16 MB.", file.name), {
                    type: "danger",
                });
                continue;
            }
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(",")[1] || "");
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            const isImage = file.type.startsWith("image/");
            this.state.files.push({
                name: file.name || "file",
                mimetype: file.type || "application/octet-stream",
                data,
                preview: isImage ? `data:${file.type};base64,${data}` : false,
            });
        }
    }

    removeFile(index) {
        this.state.files.splice(index, 1);
    }

    async send() {
        if (!this.canSend || !this.state.activeId) {
            return;
        }
        const text = this.state.draft.trim();
        const attachments = this.state.files.map((f) => ({
            name: f.name,
            mimetype: f.mimetype,
            data: f.data,
        }));
        this.state.sending = true;
        try {
            const data = await this.orm.call("whatsapp.chat", "send_reply", [
                [this.state.activeId],
                text,
                attachments,
            ]);
            this.state.draft = "";
            this.state.files = [];
            this.state.showEmoji = false;
            const input = document.querySelector(".o_wa_input");
            if (input) {
                input.value = "";
            }
            this.state.messages = data.messages;
            await this.loadChats();
            this.scrollDown();
        } finally {
            this.state.sending = false;
        }
    }

    async checkNow() {
        this.state.checking = true;
        try {
            const res = await this.orm.call("whatsapp.chat", "refresh_inbox", []);
            this.notification.add(
                res.received
                    ? _t("%s new message(s) received.", res.received)
                    : _t("No new messages."),
                { type: res.received ? "success" : "info" }
            );
            await this.refresh();
        } finally {
            this.state.checking = false;
        }
    }
}

registry.category("actions").add("whatsapp_qr_connect.inbox", WhatsappInbox);
