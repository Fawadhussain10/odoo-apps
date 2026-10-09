/** @odoo-module **/
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { LiProspectMap } from "./li_map";

const PRESETS = [
    ["today", _t("Today")],
    ["last_7", _t("Last 7 days")],
    ["last_30", _t("Last 30 days")],
    ["this_month", _t("This month")],
    ["since_active", _t("Since active")],
    ["custom", _t("Custom")],
];

const TILES = [
    { key: "connections_sent", label: _t("Connections sent"), icon: "fa-paper-plane", tone: "blue" },
    { key: "connections_per_day", label: _t("Connections per day"), icon: "fa-calendar-check-o", tone: "blue" },
    { key: "messages_sent", label: _t("Messages sent"), icon: "fa-comments", tone: "violet" },
    { key: "acceptance_rate", label: _t("Acceptance rate"), pct: true, icon: "fa-handshake-o", tone: "aqua" },
    { key: "reply_rate", label: _t("Reply rate"), pct: true, icon: "fa-reply", tone: "aqua" },
    { key: "warm_lead_rate", label: _t("Warm lead rate"), pct: true, icon: "fa-fire", tone: "orange" },
    { key: "meeting_rate", label: _t("Meeting rate"), pct: true, icon: "fa-video-camera", tone: "orange" },
    { key: "meetings_booked", label: _t("Meetings booked"), icon: "fa-calendar", tone: "violet" },
    { key: "followups_sent", label: _t("Follow-ups sent"), icon: "fa-bell", tone: "blue" },
    { key: "followup_reply_rate", label: _t("Follow-up reply rate"), pct: true, icon: "fa-refresh", tone: "aqua" },
];
const OVERDUE_TILE = { key: "overdue_replies", label: _t("Overdue replies"), live: true };

const COLUMNS = [
    { key: "name", label: _t("Persona") },
    { key: "profile", label: _t("Profile") },
    { key: "service", label: _t("Service") },
    { key: "invite_sent", label: _t("Sent"), num: true },
    { key: "acceptance_rate", label: _t("Accept"), num: true, pct: true },
    { key: "reply_rate", label: _t("Reply"), num: true, pct: true },
    { key: "warm_lead", label: _t("Warm"), num: true },
    { key: "meeting_booked", label: _t("Meet"), num: true },
];

// background work changes the numbers: refresh while the dashboard is open
const REFRESH_MS = 60000;

const CHART = { width: 640, height: 220, top: 12, right: 8, bottom: 26, left: 36 };

export class LiSalesDashboard extends Component {
    static template = "linkedin_sales_automation.Dashboard";
    static components = { LiProspectMap };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.presets = PRESETS;
        this.tiles = TILES;
        this.overdueTile = OVERDUE_TILE;
        this.columns = COLUMNS;
        this.chart = CHART;
        this.state = useState({
            filters: {
                date_preset: "since_active",
                date_from: "",
                date_to: "",
                profile_ids: [],
                persona_ids: [],
                service_ids: [],
                agent: "both",
                execution_mode: "all",
            },
            data: null,
            loading: true,
            openMenu: null,
            sort: { key: "invite_sent", asc: false },
            hover: null,
        });
        onWillStart(() => this.load());
        onMounted(() => {
            this.timer = setInterval(() => this.refresh(), REFRESH_MS);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("li.dashboard", "get_data", [this.state.filters]);
        this.state.loading = false;
    }

    async refresh() {
        // quiet reload: no spinner, skipped while hidden, loading or a filter menu is open
        const f = this.state.filters;
        if (document.hidden || this.state.loading || this.state.openMenu
            || (f.date_preset === "custom" && !(f.date_from && f.date_to))) {
            return;
        }
        const filters = JSON.stringify(f);
        const data = await this.orm.silent.call("li.dashboard", "get_data", [f]);
        if (filters === JSON.stringify(this.state.filters) && !this.state.loading) {
            this.state.data = data;
        }
    }

    // ---------------------------------------------------------------- filters
    setPreset(ev) {
        this.state.filters.date_preset = ev.target.value;
        if (ev.target.value !== "custom") {
            this.load();
        }
    }
    setDate(field, ev) {
        this.state.filters[field] = ev.target.value;
        if (this.state.filters.date_from && this.state.filters.date_to) {
            this.load();
        }
    }
    setAgent(agent) {
        this.state.filters.agent = agent;
        this.load();
    }
    setMode(mode) {
        this.state.filters.execution_mode = mode;
        this.load();
    }

    // ---------------------------------------------------------------- operations
    get opsTiles() {
        const q = this.state.data.queue;
        const p = this.state.data.posts;
        return [
            { key: "writing_waiting", label: _t("Waiting for Claude"), value: q.writing_waiting, icon: "fa-pencil",
              tone: "violet", hint: _t("%(a)s prospects, %(b)s post ideas", { a: q.writing_prospects, b: q.post_ideas }) },
            { key: "approved_waiting", label: _t("Approved texts to send"), value: q.approved_waiting, icon: "fa-clock-o",
              tone: "blue", hint: q.approved_waiting ? (q.next_window === "now" ? _t("sending now")
                  : _t("next window %s", q.next_window)) : _t("queue empty") },
            { key: "sent_today", label: _t("Sent today"), value: q.sent_today, icon: "fa-paper-plane", tone: "aqua",
              hint: _t("invites, messages, follow-ups") },
            { key: "stale_today", label: _t("Discarded (stale) today"), value: q.stale_today, icon: "fa-recycle",
              tone: "orange", hint: _t("conversation changed before sending") },
            { key: "posts_published", label: _t("Posts published"), value: p.published, icon: "fa-bullhorn",
              tone: "blue", hint: _t("%(r)s reactions · %(c)s comments", { r: p.reactions, c: p.comments }) },
            { key: "posts_to_approve", label: _t("Posts to approve"), value: p.to_approve, icon: "fa-check-square-o",
              tone: "violet", hint: _t("drafts written by Claude") },
        ];
    }
    async openOps(tile) {
        const action = await this.orm.call("li.dashboard", "get_action", [tile.key, this.state.filters]);
        action.name = tile.label;
        this.action.doAction(action);
    }
    openProfile(entry) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "li.profile", res_id: entry.id,
                               views: [[false, "form"]] });
    }
    shortDate(value) {
        return value ? value.slice(0, 16).replace("T", " ") + " UTC" : _t("never");
    }
    closeMenus() {
        if (this.state.openMenu) {
            this.state.openMenu = null;
        }
    }
    keepOpen() {}
    toggleMenu(name) {
        this.state.openMenu = this.state.openMenu === name ? null : name;
    }
    toggleId(field, id) {
        const ids = this.state.filters[field];
        const index = ids.indexOf(id);
        if (index >= 0) {
            ids.splice(index, 1);
        } else {
            ids.push(id);
        }
        this.load();
    }
    clearIds(field) {
        this.state.filters[field] = [];
        this.load();
    }
    menuLabel(field, options, allLabel) {
        const ids = this.state.filters[field];
        if (!ids.length) {
            return allLabel;
        }
        if (ids.length === 1) {
            const found = options.find((o) => o.id === ids[0]);
            return found ? found.name : allLabel;
        }
        return _t("%s selected", ids.length);
    }
    get personaOptions() {
        const options = this.state.data ? this.state.data.options.personas : [];
        const profiles = this.state.filters.profile_ids;
        return profiles.length ? options.filter((p) => profiles.includes(p.profile_id)) : options;
    }

    // ---------------------------------------------------------------- tiles
    formatTile(tile) {
        const value = this.state.data.kpis[tile.key];
        return tile.pct ? `${value}%` : `${value}`;
    }
    tileHint(tile) {
        const d = this.state.data.details;
        switch (tile.key) {
            case "acceptance_rate":
                return d.already_connected
                    ? _t("%(a)s of %(b)s invited accepted · %(c)s already connected", {
                          a: d.accepted_of_invited,
                          b: d.invited_prospects,
                          c: d.already_connected,
                      })
                    : _t("%(a)s of %(b)s invited accepted", { a: d.accepted_of_invited, b: d.invited_prospects });
            case "reply_rate":
                return _t("%(a)s of %(b)s messaged replied", { a: d.replied_of_messaged, b: d.messaged_prospects });
            case "followup_reply_rate":
                return _t("%(a)s of %(b)s followed up replied", {
                    a: d.replied_after_followup,
                    b: d.followed_up_prospects,
                });
            case "connections_per_day":
                return _t("over %s day(s) with invites", d.invite_days);
            case "warm_lead_rate":
                return _t("%(a)s warm of %(b)s connected", { a: d.warm_leads, b: d.connected });
            case "overdue_replies":
                return _t("live, not date-filtered");
            default:
                return "";
        }
    }
    async openTile(tile) {
        const action = await this.orm.call("li.dashboard", "get_action", [tile.key, this.state.filters]);
        action.name = tile.label;
        this.action.doAction(action);
    }

    // ---------------------------------------------------------------- daily chart
    get daily() {
        const rows = this.state.data.daily.rows;
        const c = CHART;
        const plotW = c.width - c.left - c.right;
        const plotH = c.height - c.top - c.bottom;
        const max = Math.max(1, ...rows.map((r) => Math.max(r.sent, r.accepted)));
        const step = this.niceStep(max);
        const top = Math.ceil(max / step) * step;
        const slot = rows.length ? plotW / rows.length : plotW;
        const barW = Math.max(2, Math.min(14, (slot - 4) / 2 - 1));
        const y = (v) => c.top + plotH - (v / top) * plotH;
        const ticks = [];
        for (let v = 0; v <= top; v += step) {
            ticks.push({ value: v, y: y(v) });
        }
        const labelEvery = Math.max(1, Math.ceil(rows.length / 8));
        const bars = rows.map((r, i) => {
            const x0 = c.left + i * slot + slot / 2 - barW - 1;
            return {
                ...r,
                index: i,
                sentX: x0,
                accX: x0 + barW + 2,
                sentY: y(r.sent),
                accY: y(r.accepted),
                sentH: Math.max(0, c.top + plotH - y(r.sent)),
                accH: Math.max(0, c.top + plotH - y(r.accepted)),
                slotX: c.left + i * slot,
                slotW: slot,
                centerX: c.left + i * slot + slot / 2,
                label: i % labelEvery === 0 ? r.date.slice(5) : "",
            };
        });
        return { bars, ticks, barW, baseline: c.top + plotH, plotRight: c.width - c.right };
    }
    niceStep(max) {
        const raw = max / 4;
        const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
        const n = raw / mag;
        return Math.max(1, (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag);
    }
    hoverBar(bar) {
        this.state.hover = bar;
    }

    // ---------------------------------------------------------------- funnel
    get funnel() {
        const rows = this.state.data.funnel;
        const max = Math.max(1, ...rows.map((r) => r.value));
        return rows.map((r, i) => {
            const prev = i ? rows[i - 1].value : 0;
            return {
                ...r,
                width: `${Math.max(r.value ? 2 : 0, (100 * r.value) / max)}%`,
                conversion: i && prev ? `${Math.round((1000 * r.value) / prev) / 10}%` : "",
            };
        });
    }

    // ---------------------------------------------------------------- header
    get rangeLabel() {
        const range = this.state.data.range;
        const fmt = (s) => (s ? s.slice(0, 10) : "");
        const preset = PRESETS.find((p) => p[0] === this.state.filters.date_preset);
        const start = range.start ? fmt(range.start) : _t("the first event");
        return `${preset ? preset[1] : ""} · ${start} → ${fmt(range.end)} · ${range.tz}`;
    }
    ratePct(tile) {
        return tile.pct ? `${Math.min(100, this.state.data.kpis[tile.key])}%` : "";
    }
    initials(name) {
        return (name || "?")
            .split(/\s+/)
            .filter((w) => /[A-Za-z0-9]/.test(w[0] || ""))
            .slice(0, 2)
            .map((w) => w[0].toUpperCase())
            .join("") || "?";
    }

    // ---------------------------------------------------------------- table
    sortBy(key) {
        const sort = this.state.sort;
        sort.asc = sort.key === key ? !sort.asc : false;
        sort.key = key;
    }
    get personaRows() {
        const { key, asc } = this.state.sort;
        const rows = [...this.state.data.personas];
        rows.sort((a, b) => {
            const va = a[key];
            const vb = b[key];
            const cmp = typeof va === "number" ? va - vb : String(va).localeCompare(String(vb));
            return asc ? cmp : -cmp;
        });
        return rows;
    }
    openPersona(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "li.persona",
            res_id: row.id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("li_sales_dashboard", LiSalesDashboard);
