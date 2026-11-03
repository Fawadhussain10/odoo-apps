/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { HrwSelect } from "./hrw_select";

const TYPE_COLORS = {
    new_hire: { main: "#10b981", soft: "#d1fae5", grad: ["#34d399", "#059669"] },
    resignation: { main: "#f59e0b", soft: "#fef3c7", grad: ["#fbbf24", "#d97706"] },
    termination: { main: "#f43f5e", soft: "#ffe4e6", grad: ["#fb7185", "#e11d48"] },
    change: { main: "#3b82f6", soft: "#dbeafe", grad: ["#60a5fa", "#2563eb"] },
};
const STATE_COLORS = {
    draft: "#94a3b8", in_approval: "#3b82f6", approved: "#0ea5e9", done: "#10b981", rejected: "#f43f5e", cancel: "#cbd5e1",
};
const TYPE_ICONS = { new_hire: "fa-user-plus", resignation: "fa-sign-out", termination: "fa-user-times", change: "fa-exchange" };

function pad(n) {
    return String(n).padStart(2, "0");
}
function iso(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Smoothly animates a number when its value changes. */
export class AnimatedNumber extends Component {
    static template = "hr_process_workflow.AnimatedNumber";
    static props = { value: Number, fmt: { type: String, optional: true }, currency: { type: Object, optional: true } };

    setup() {
        this.state = useState({ display: 0 });
        this.frame = null;
        onMounted(() => this.animate(0, this.props.value));
        onWillUpdateProps((next) => this.animate(this.state.display, next.value));
        onWillUnmount(() => cancelAnimationFrame(this.frame));
    }
    animate(from, to) {
        cancelAnimationFrame(this.frame);
        const start = performance.now();
        const duration = 900;
        const step = (now) => {
            const t = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - t, 4);
            this.state.display = from + (to - from) * eased;
            if (t < 1) {
                this.frame = requestAnimationFrame(step);
            }
        };
        this.frame = requestAnimationFrame(step);
    }
    get text() {
        const v = this.state.display;
        if (this.props.fmt === "money") {
            return formatMoney(v, this.props.currency);
        }
        if (this.props.fmt === "days") {
            return `${v.toFixed(1)}`;
        }
        return Math.round(v).toLocaleString();
    }
}

export function formatMoney(value, currency) {
    let sym = (currency && currency.symbol) || "";
    if (/[^\x00-\x7F€£¥₹₨]/.test(sym) && currency.name) {
        sym = currency.name; // e.g. AED instead of a right-to-left symbol
    }
    const abs = Math.abs(value);
    let txt;
    if (abs >= 1e6) {
        txt = (abs / 1e6).toFixed(2) + "M";
    } else if (abs >= 1e4) {
        txt = (abs / 1e3).toFixed(1) + "k";
    } else {
        txt = abs.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    const sign = value < 0 ? "−" : value > 0 ? "+" : "";
    return currency && currency.position === "after" ? `${sign}${txt} ${sym}` : `${sign}${sym} ${txt}`;
}

export class HrwDirectorDashboard extends Component {
    static template = "hr_process_workflow.HrwDirectorDashboard";
    static components = { AnimatedNumber, HrwSelect };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.typeColors = TYPE_COLORS;
        this.typeIcons = TYPE_ICONS;
        this.stateColors = STATE_COLORS;
        this.presets = [
            { key: "30d", label: "Last 30 days" },
            { key: "qtd", label: "This quarter" },
            { key: "ytd", label: "This year" },
            { key: "12m", label: "Last 12 months" },
            { key: "custom", label: "Pick dates" },
        ];
        this.state = useState({
            loading: true,
            ready: false,
            data: null,
            hoverIdx: null,
            hiddenSeries: {},
            preset: "12m",
            filters: {
                company_ids: [],
                business_unit_id: "",
                department_id: "",
                approver_id: "",
                request_type: "",
                ...this.rangeFor("12m"),
            },
        });
        onWillStart(() => this.load());
        onMounted(() => {
            this.readyTimer = setTimeout(() => (this.state.ready = true), 60);
        });
        onWillUnmount(() => clearTimeout(this.readyTimer));
    }

    // ------------------------------------------------------------------ data
    async load() {
        this.state.loading = true;
        const f = this.state.filters;
        const payload = {
            company_ids: f.company_ids,
            business_unit_id: f.business_unit_id || false,
            department_id: f.department_id || false,
            approver_id: f.approver_id || false,
            request_type: f.request_type || false,
            date_from: f.date_from,
            date_to: f.date_to,
        };
        const data = await this.orm.call("hr.workflow.request", "get_hrw_dashboard_data", [payload]);
        this.state.data = data;
        this.state.loading = false;
    }

    rangeFor(key) {
        const now = new Date();
        let from;
        if (key === "30d") {
            from = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29);
        } else if (key === "qtd") {
            from = new Date(now.getFullYear(), Math.floor(now.getMonth() / 3) * 3, 1);
        } else if (key === "ytd") {
            from = new Date(now.getFullYear(), 0, 1);
        } else {
            from = new Date(now.getFullYear(), now.getMonth() - 11, 1);
        }
        return { date_from: iso(from), date_to: iso(now) };
    }

    setPreset(key) {
        this.state.preset = key;
        if (key !== "custom") {
            Object.assign(this.state.filters, this.rangeFor(key));
            this.load();
        }
    }
    onFilter(name, ev) {
        this.state.filters[name] = ev.target.value;
        if (name === "date_from" || name === "date_to") {
            this.state.preset = "custom";
        }
        this.load();
    }
    onCompany(ev) {
        const v = ev.target.value;
        this.state.filters.company_ids = v ? [parseInt(v)] : [];
        this.load();
    }
    setFilter(name, value) {
        this.state.filters[name] = value === "" ? "" : String(value);
        this.load();
    }
    setCompany(value) {
        this.state.filters.company_ids = value ? [parseInt(value)] : [];
        this.load();
    }
    get typeOptions() {
        return (this.state.data?.options.types || []).map((t) => ({
            ...t, color: TYPE_COLORS[t.id]?.main, soft: TYPE_COLORS[t.id]?.soft, icon: TYPE_ICONS[t.id],
        }));
    }
    get approverOptions() {
        return this.state.data?.options.approvers || [];
    }
    resetFilters() {
        Object.assign(this.state.filters, {
            company_ids: [],
            business_unit_id: "",
            department_id: "",
            approver_id: "",
            request_type: "",
            ...this.rangeFor("12m"),
        });
        this.state.preset = "12m";
        this.load();
    }
    get activeFilterCount() {
        const f = this.state.filters;
        return ["business_unit_id", "department_id", "approver_id", "request_type"].filter((k) => f[k]).length +
            (f.company_ids.length ? 1 : 0);
    }

    // ------------------------------------------------------------------ navigation
    openDomain(name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "hr.workflow.request",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain,
            target: "current",
        });
    }
    openRecord(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.workflow.request",
            views: [[false, "form"]],
            res_id: id,
            target: "current",
        });
    }
    newRequest(type) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "New Request",
            res_model: "hr.workflow.request",
            views: [[false, "form"]],
            context: { default_request_type: type },
            target: "current",
        });
    }

    // ------------------------------------------------------------------ helpers
    money(v) {
        return formatMoney(v || 0, this.state.data && this.state.data.currency);
    }
    avatar(id) {
        return `/web/image/res.users/${id}/avatar_128`;
    }
    initials(name) {
        return (name || "?").split(" ").filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
    }
    fmtDate(s) {
        if (!s) {
            return "";
        }
        const d = new Date(s + "T00:00:00");
        return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
    }
    dateParts(s) {
        const d = new Date(s + "T00:00:00");
        return { day: pad(d.getDate()), month: d.toLocaleDateString(undefined, { month: "short" }) };
    }
    get greeting() {
        const h = new Date().getHours();
        return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
    }
    get firstName() {
        return ((this.state.data && this.state.data.user_name) || "").split(" ")[0];
    }
    get periodLabel() {
        const d = this.state.data;
        if (!d) {
            return "";
        }
        const o = { day: "numeric", month: "short", year: "numeric" };
        return `${new Date(d.date_from + "T00:00:00").toLocaleDateString(undefined, o)} → ${new Date(
            d.date_to + "T00:00:00"
        ).toLocaleDateString(undefined, o)}`;
    }

    // ------------------------------------------------------------------ trend chart
    get chart() {
        const W = 720, H = 330, P = { l: 36, r: 16, t: 18, b: 30 };
        const d = this.state.data;
        const months = d.months;
        const series = d.trend.filter((s) => !this.state.hiddenSeries[s.key]);
        const n = Math.max(months.length, 1);
        const max = Math.max(1, ...series.flatMap((s) => s.values));
        const niceMax = Math.ceil(max / 4) * 4 || 4;
        const x = (i) => P.l + (n === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (n - 1));
        const y = (v) => H - P.b - (v / niceMax) * (H - P.t - P.b);
        // monotone cubic interpolation (Fritsch-Carlson): smooth, never overshoots the data
        const smooth = (pts) => {
            const n = pts.length;
            if (n < 2) {
                return n ? `M${pts[0][0]},${pts[0][1]}` : "";
            }
            const dx = [], m = [], t = new Array(n);
            for (let i = 0; i < n - 1; i++) {
                dx.push(pts[i + 1][0] - pts[i][0]);
                m.push((pts[i + 1][1] - pts[i][1]) / dx[i]);
            }
            t[0] = m[0];
            t[n - 1] = m[n - 2];
            for (let i = 1; i < n - 1; i++) {
                t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
            }
            for (let i = 0; i < n - 1; i++) {
                if (m[i] === 0) {
                    t[i] = t[i + 1] = 0;
                    continue;
                }
                const a = t[i] / m[i], b = t[i + 1] / m[i], h = a * a + b * b;
                if (h > 9) {
                    const k = 3 / Math.sqrt(h);
                    t[i] = k * a * m[i];
                    t[i + 1] = k * b * m[i];
                }
            }
            let path = `M${pts[0][0]},${pts[0][1]}`;
            for (let i = 0; i < n - 1; i++) {
                const d = dx[i] / 3;
                path += ` C${pts[i][0] + d},${pts[i][1] + t[i] * d} ${pts[i + 1][0] - d},${pts[i + 1][1] - t[i + 1] * d} ${pts[i + 1][0]},${pts[i + 1][1]}`;
            }
            return path;
        };
        const lines = series.map((s) => {
            const pts = s.values.map((v, i) => [x(i), y(v)]);
            const line = smooth(pts);
            const area = pts.length ? `${line} L${x(pts.length - 1)},${H - P.b} L${x(0)},${H - P.b} Z` : "";
            return { ...s, line, area, pts, color: TYPE_COLORS[s.key].main };
        });
        const grid = [0, 1, 2, 3, 4].map((k) => ({ y: y((niceMax * k) / 4), label: Math.round((niceMax * k) / 4) }));
        const labelEvery = Math.ceil(n / 8);
        const xLabels = months.map((m, i) => ({ x: x(i), label: m, show: i % labelEvery === 0 || i === n - 1 }));
        const slots = months.map((m, i) => {
            const half = n === 1 ? (W - P.l - P.r) / 2 : (W - P.l - P.r) / (n - 1) / 2;
            return { i, x: x(i) - half, w: half * 2, cx: x(i) };
        });
        return { W, H, P, lines, grid, xLabels, slots };
    }
    get tooltip() {
        const i = this.state.hoverIdx;
        if (i === null || !this.state.data) {
            return null;
        }
        const c = this.chart;
        const rows = this.state.data.trend
            .filter((s) => !this.state.hiddenSeries[s.key])
            .map((s) => ({ key: s.key, label: s.label, value: s.values[i], color: TYPE_COLORS[s.key].main }));
        const total = rows.reduce((a, r) => a + r.value, 0);
        const left = (c.slots[i].cx / c.W) * 100;
        return { month: this.state.data.months[i], rows, total, left, flip: left > 70 };
    }
    toggleSeries(key) {
        this.state.hiddenSeries[key] = !this.state.hiddenSeries[key];
    }

    // ------------------------------------------------------------------ donut
    get donut() {
        const mix = this.state.data.mix;
        const total = mix.reduce((a, m) => a + m.value, 0);
        const R = 70, C = 2 * Math.PI * R;
        let offset = 0;
        const arcs = mix.map((m) => {
            const len = total ? (m.value / total) * C : 0;
            const arc = {
                ...m,
                color: TYPE_COLORS[m.key].main,
                dash: this.state.ready ? `${Math.max(len - 3, 0)} ${C}` : `0 ${C}`,
                offset: -offset,
                pct: total ? Math.round((m.value / total) * 100) : 0,
            };
            offset += len;
            return arc;
        });
        return { R, C, arcs, total };
    }

    // ------------------------------------------------------------------ funnel & bars
    get funnel() {
        const rows = this.state.data.funnel.filter((f) => f.key !== "cancel");
        const max = Math.max(1, ...rows.map((r) => r.value));
        return rows.map((r) => ({ ...r, pct: this.state.ready ? (r.value / max) * 100 : 0, color: STATE_COLORS[r.key] }));
    }
    get cycleBars() {
        const rows = this.state.data.cycle_by_type;
        const max = Math.max(1, ...rows.map((r) => r.value));
        return rows.map((r) => ({ ...r, pct: this.state.ready ? (r.value / max) * 100 : 0, color: TYPE_COLORS[r.key] }));
    }
    get costBars() {
        const rows = this.state.data.cost_by_type;
        const max = Math.max(1, ...rows.map((r) => Math.abs(r.value)));
        return rows.map((r) => ({
            ...r,
            pct: this.state.ready ? (Math.abs(r.value) / max) * 50 : 0,
            negative: r.value < 0,
            color: TYPE_COLORS[r.key],
        }));
    }
    get deptBars() {
        const rows = this.state.data.departments;
        const max = Math.max(1, ...rows.map((r) => r.value));
        return rows.map((r, i) => ({ ...r, pct: this.state.ready ? (r.value / max) * 100 : 0, rank: i + 1 }));
    }
    get approverMax() {
        return Math.max(1, ...this.state.data.approvers.map((a) => a.pending + a.decided));
    }
    approverPct(a, key) {
        return this.state.ready ? (a[key] / this.approverMax) * 100 : 0;
    }
    daysLeftLabel(days) {
        if (days === 0) {
            return "Today";
        }
        if (days === 1) {
            return "Tomorrow";
        }
        return `in ${days} days`;
    }
}

registry.category("actions").add("hrw_director_dashboard", HrwDirectorDashboard);
