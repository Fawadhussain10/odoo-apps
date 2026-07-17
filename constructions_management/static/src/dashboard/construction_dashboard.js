import {rpc} from "@web/core/network/rpc";
import {registry} from "@web/core/registry";
import {loadBundle} from "@web/core/assets";
import {Layout} from "@web/search/layout";
import {useService} from "@web/core/utils/hooks";
import {Component, useState, useRef, onWillStart, useEffect} from "@odoo/owl";

// Fixed categorical palette (validated: CVD-safe adjacent pairs, contrast-checked against both
// light and dark surfaces) - reused identically across every chart on this dashboard so color
// always means the same thing everywhere the user looks.
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
const STATUS = {
    good: "#0ca30c",
    warning: "#fab219",
    serious: "#ec835a",
    critical: "#d03b3b",
};
const PROJECT_STATE_COLORS = {
    draft: "#9e9e9e",
    tender: PALETTE.violet,
    mobilization: PALETTE.yellow,
    in_progress: PALETTE.blue,
    on_hold: STATUS.warning,
    practical_completion: PALETTE.aqua,
    defect_liability: PALETTE.orange,
    closed: STATUS.good,
    cancelled: STATUS.critical,
};
const MR_STATE_COLORS = [
    PALETTE.blue, PALETTE.aqua, PALETTE.violet, PALETTE.yellow,
    PALETTE.orange, PALETTE.magenta, STATUS.good, "#9e9e9e", STATUS.critical,
];

function formatMoney(value, symbol, position, compact = true) {
    const n = Math.round(value || 0);
    let display;
    if (compact && Math.abs(n) >= 10000000) {
        display = (n / 10000000).toFixed(2) + "Cr";
    } else if (compact && Math.abs(n) >= 100000) {
        display = (n / 100000).toFixed(2) + "L";
    } else if (compact && Math.abs(n) >= 1000) {
        display = (n / 1000).toFixed(1) + "k";
    } else {
        display = n.toLocaleString();
    }
    return position === "after" ? `${display} ${symbol}` : `${symbol}${display}`;
}

export class ConstructionDashboard extends Component {
    static template = "constructions_management.Dashboard";
    static components = {Layout};
    static props = ["*"];

    setup() {
        this.actionService = useService("action");
        this.state = useState({
            loading: true,
            data: null,
        });
        this.canvasRefs = {
            budget: useRef("budgetChart"),
            status: useRef("statusChart"),
            materialRequests: useRef("mrChart"),
            rag: useRef("ragChart"),
        };
        this.charts = {};

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            // Chart.js draws straight to canvas, so it never picks up our (now dark) CSS -
            // without this, every axis label/legend defaults to near-black text that's
            // unreadable on the dark card background.
            Chart.defaults.color = "#93a1b7";
            Chart.defaults.borderColor = "rgba(255, 255, 255, 0.08)";
            Chart.defaults.font.family =
                '"SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
            await this.fetchData();
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
    }

    get display() {
        return {controlPanel: {}};
    }

    async fetchData() {
        this.state.loading = true;
        const data = await rpc("/constructions_management/dashboard_data", {});
        this.state.data = data;
        this.state.loading = false;
    }

    fmt(value, compact = true) {
        if (!this.state.data) return "-";
        return formatMoney(value, this.state.data.currency_symbol, this.state.data.currency_position, compact);
    }

    fmtPct(value) {
        return `${((value || 0) * 100).toFixed(1)}%`;
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

        // Budget vs Actual vs EAC - horizontal bar, top projects by revised budget
        if (this.canvasRefs.budget.el) {
            const projects = d.projects.slice(0, 8);
            this.charts.budget = new Chart(this.canvasRefs.budget.el, {
                type: "bar",
                data: {
                    labels: projects.map((p) => p.name),
                    datasets: [
                        {
                            label: "Revised Budget",
                            data: projects.map((p) => p.revised_budget),
                            backgroundColor: PALETTE.blue,
                            borderRadius: 4
                        },
                        {
                            label: "Actual Cost",
                            data: projects.map((p) => p.actual_cost),
                            backgroundColor: PALETTE.aqua,
                            borderRadius: 4
                        },
                        {
                            label: "EAC",
                            data: projects.map((p) => p.eac),
                            backgroundColor: PALETTE.violet,
                            borderRadius: 4
                        },
                    ],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {legend: {position: "top", labels: {boxWidth: 10, usePointStyle: true}}},
                    scales: {
                        x: {grid: {display: false}, ticks: {callback: (v) => this.fmt(v)}},
                        y: {grid: {display: false}},
                    },
                },
            });
        }

        // Project status donut
        if (this.canvasRefs.status.el) {
            const rows = d.project_status_breakdown;
            this.charts.status = new Chart(this.canvasRefs.status.el, {
                type: "doughnut",
                data: {
                    labels: rows.map((r) => r.label),
                    datasets: [{
                        data: rows.map((r) => r.value),
                        backgroundColor: rows.map((r, i) => Object.values(PROJECT_STATE_COLORS)[i % 9] || PALETTE.blue),
                        borderWidth: 3,
                        borderColor: "#141b2d",
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "68%",
                    plugins: {
                        legend: {
                            position: "right",
                            labels: {boxWidth: 10, usePointStyle: true, font: {size: 11}}
                        }
                    },
                },
            });
        }

        // Material request pipeline
        if (this.canvasRefs.materialRequests.el) {
            const rows = d.material_request_status;
            this.charts.materialRequests = new Chart(this.canvasRefs.materialRequests.el, {
                type: "bar",
                data: {
                    labels: rows.map((r) => r.label),
                    datasets: [{data: rows.map((r) => r.value), backgroundColor: MR_STATE_COLORS, borderRadius: 6}],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {legend: {display: false}},
                    scales: {
                        x: {grid: {display: false}},
                        y: {grid: {color: "rgba(255,255,255,0.08)"}, ticks: {precision: 0}},
                    },
                },
            });
        }

        // RAG donut
        if (this.canvasRefs.rag.el) {
            const rag = d.rag_counts;
            this.charts.rag = new Chart(this.canvasRefs.rag.el, {
                type: "doughnut",
                data: {
                    labels: ["On Track", "At Risk", "Critical"],
                    datasets: [{
                        data: [rag.green, rag.amber, rag.red],
                        backgroundColor: [STATUS.good, STATUS.warning, STATUS.critical],
                        borderWidth: 3,
                        borderColor: "#141b2d",
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: "68%",
                    plugins: {
                        legend: {
                            position: "right",
                            labels: {boxWidth: 10, usePointStyle: true, font: {size: 11}}
                        }
                    },
                },
            });
        }
    }

    openProject(projectId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "project.project",
            res_id: projectId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("constructions_management.dashboard", ConstructionDashboard);
