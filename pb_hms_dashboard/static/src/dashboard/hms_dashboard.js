/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { loadBundle } from "@web/core/assets";
import { Layout } from "@web/search/layout";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { PbPatientMap } from "@pb_hms_base/map/patient_map";
import { Component, useState, useRef, onWillStart, onWillDestroy, useEffect } from "@odoo/owl";

// Same validated palette used on the constructions_management dashboard, so every
// premium screen in this apps directory reads as one visual system.
const PALETTE = {
    blue: "#2a78d6",
    green: "#008300",
    magenta: "#e87ba4",
    yellow: "#eda100",
    aqua: "#1baf7a",
    orange: "#eb6834",
    violet: "#4a3aa7",
    red: "#e34948",
};
const STATE_BADGE = {
    Done: "success",
    Cancelled: "danger",
    Waiting: "warning",
    "In consultation": "info",
    "To Invoice": "primary",
};

// how often the dashboard silently re-fetches in the background (ms)
const AUTO_REFRESH_MS = 60000;

export class HmsDashboard extends Component {
    static template = "pb_hms_dashboard.Dashboard";
    static components = { Layout, PbPatientMap };
    static props = ["*"];

    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            refreshing: false,
            data: null,
            filter: "today",
        });
        this.canvasRefs = {
            appointments: useRef("appointmentChart"),
            patients: useRef("patientChart"),
        };
        this.charts = {};

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            Chart.defaults.color = "#93a1b7";
            Chart.defaults.borderColor = "rgba(255, 255, 255, 0.08)";
            Chart.defaults.font.family =
                '"SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
            await this.fetchData(this.state.filter);
        });

        useEffect(
            () => {
                if (!this.state.loading && this.state.data) {
                    this.renderCharts();
                }
                return () => this.destroyCharts();
            },
            () => [this.state.loading]
        );

        this.refreshTimer = setInterval(() => this.fetchData(this.state.filter, true), AUTO_REFRESH_MS);
        onWillDestroy(() => {
            clearInterval(this.refreshTimer);
            this.destroyCharts();
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async fetchData(filter, silent = false) {
        if (silent) {
            this.state.refreshing = true;
        } else {
            this.state.loading = true;
        }
        const data = await rpc("/pb_hms_dashboard/data", { filter });
        this.state.data = data;
        this.state.filter = data.filter;
        this.state.loading = false;
        this.state.refreshing = false;
    }

    setFilter(filter) {
        if (filter === this.state.filter) {
            return;
        }
        this.fetchData(filter);
    }

    fmtMoney(value) {
        const d = this.state.data;
        if (!d) return "-";
        const n = Math.round(value || 0).toLocaleString();
        return d.currency_position === "after" ? `${n} ${d.currency_symbol}` : `${d.currency_symbol}${n}`;
    }

    badgeClass(state) {
        return STATE_BADGE[state] || "neutral";
    }

    destroyCharts() {
        for (const key of Object.keys(this.charts)) {
            this.charts[key]?.destroy();
        }
        this.charts = {};
    }

    renderCharts() {
        this.destroyCharts();
        const d = this.state.data;
        if (!d) return;

        if (this.canvasRefs.appointments.el && d.appointment_trend) {
            const t = d.appointment_trend;
            this.charts.appointments = new Chart(this.canvasRefs.appointments.el, {
                type: "bar",
                data: {
                    labels: t.labels,
                    datasets: [
                        {
                            label: "Appointments",
                            data: t.values,
                            backgroundColor: (ctx) =>
                                t.types && t.types[ctx.dataIndex] === "future" ? PALETTE.aqua : PALETTE.blue,
                            borderRadius: 6,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false } },
                        y: { grid: { color: "rgba(255,255,255,0.08)" }, ticks: { precision: 0 } },
                    },
                },
            });
        }

        if (this.canvasRefs.patients.el && d.patient_trend) {
            const t = d.patient_trend;
            this.charts.patients = new Chart(this.canvasRefs.patients.el, {
                type: "line",
                data: {
                    labels: t.labels,
                    datasets: [
                        {
                            label: "New Patients",
                            data: t.values,
                            borderColor: PALETTE.violet,
                            backgroundColor: "rgba(74, 58, 167, 0.18)",
                            fill: true,
                            tension: 0.35,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true } },
                        y: { grid: { color: "rgba(255,255,255,0.08)" }, ticks: { precision: 0 } },
                    },
                },
            });
        }
    }

    async openAction(methodName) {
        const action = await this.orm.call("res.users", methodName, [[user.userId]]);
        if (action) {
            this.actionService.doAction(action);
        }
    }
}

registry.category("actions").add("pb_hms_dashboard.dashboard", HmsDashboard);
