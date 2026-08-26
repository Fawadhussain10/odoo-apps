/** @odoo-module **/

import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { getColor, hexToRGBA } from "@web/core/colors/colors";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillStart, useEffect, useRef } from "@odoo/owl";

export class PbHmsGraphField extends Component {
    static template = "pb_hms.PbHmsGraphField";
    static props = {
        ...standardFieldProps,
        xlabel: String,
        ylabel: String,
    };

    setup() {
        this.chart = null;
        this.canvasRef = useRef("canvas");
        this.data = this.parseValue(this.props.value);

        onWillStart(() => loadJS("/web/static/lib/Chart/Chart.js"));

        useEffect(() => {
            this.renderChart();
            return () => {
                if (this.chart) {
                    this.chart.destroy();
                }
            };
        });
    }

    /**
     * Safely parses the field's JSON value, falling back to an empty
     * dataset when the field has no value yet (e.g. a patient with no
     * evaluation history).
     */
    parseValue(value) {
        if (!value) {
            return [];
        }
        try {
            return JSON.parse(value);
        } catch {
            return [];
        }
    }

    /**
     * Instantiates a Chart (Chart.js lib) to render the graph according to
     * the current config.
     */
    renderChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
        if (!this.data.length || !this.data[0] || !this.data[0].values || !this.data[0].values.length) {
            return;
        }
        const config = this.getLineChartConfig();
        this.chart = new Chart(this.canvasRef.el, config);
    }
    getLineChartConfig() {
        const labels = this.data[0].values.map(function (pt) {
            return pt.x;
        });
        const borderColor = this.data[0].is_sample_data ? hexToRGBA(getColor(10), 0.1) : getColor(10);
        const backgroundColor = this.data[0].is_sample_data ? hexToRGBA(getColor(10), 0.05) : hexToRGBA(getColor(10), 0.2);
        let line_data;
        line_data = [
            {
                backgroundColor,
                borderColor: this.data[0].color,
                data: this.data[0].values,
                fill: "start",
                label: this.data[0].key,
                borderWidth: 2,
            },
        ]

        if (this.data.length>=2) {
            line_data = [
                {
                    backgroundColor,
                    borderColor: this.data[0].color,
                    data: this.data[0].values,
                    fill: "start",
                    label: this.data[0].key,
                    borderWidth: 2,
                },
                {
                    backgroundColor,
                    borderColor: this.data[1].color,
                    data: this.data[1].values,
                    fill: "start",
                    label: this.data[1].key,
                    borderWidth: 2,
                },
            ]

        }

        return {
            type: "line",
            data: {
                labels,
                datasets: line_data,
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        intersect: false,
                        position: "nearest",
                    },
                },
                scales: {
                    y: {
                        display: true,
                        title: {
                            display: true,
                            text: this.props.ylabel,
                            font: { size: 14 },
                        },
                    },
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: this.props.xlabel,
                            font: { size: 14 },
                        },
                    },
                },
                maintainAspectRatio: false,
                elements: {
                    line: {
                        tension: 0.000001,
                    },
                },
            },
        };
    }
}

export const pbHmsGraphField = {
    component: PbHmsGraphField,
    supportedTypes: ["text"],
    extractProps: ({ attrs }) => ({
        xlabel: attrs.xlabel,
        ylabel: attrs.ylabel,
    }),
};

registry.category("fields").add("PbHmsGraph", pbHmsGraphField);
