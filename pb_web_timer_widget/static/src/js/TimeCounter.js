/** @odoo-module **/

import { registry } from "@web/core/registry";
import { formatFloatTime } from "@web/views/fields/formatters";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillUpdateProps, onWillStart, onWillDestroy } from "@odoo/owl";

export class PbTimer extends Component {
    static template = "pb_web_timer_widget.PbTimeCounter";
    static props = {
        ...standardFieldProps,
        pb_timer_start_field: String,
        pb_timer_stop_field: String,
        duration_field: String,
    };

    setup() {
        super.setup();
        this.state = useState({
            duration:
                this.props.duration !== undefined
                    ? this.props.duration
                    : this.props.record.data[this.props.duration_field],
        });

        const newLocal = this;
        let timer_running;
        timer_running = 0;
        if (this.props.record.data[this.props.pb_timer_start_field]){
            timer_running = 1;
        }
        if (this.props.record.data[this.props.pb_timer_start_field] && this.props.record.data[this.props.pb_timer_stop_field]){
            timer_running = 0;
        }

        this.ongoing =
            this.props.ongoing !== undefined
                ? newLocal.props.ongoing
                : timer_running;

        onWillStart(() => this._runTimer());
        onWillUpdateProps((nextProps) => {
            this.ongoing = nextProps.ongoing;
            this._runTimer();
        });
        onWillDestroy(() => clearTimeout(this.timer));
    }

    get duration() {
        // formatFloatTime except 1,5 =  1h30min but in this case 1,5 = 1min30
        return formatFloatTime(this.state.duration / 60, { displaySeconds: true });
    }

    _runTimer() {
        if (this.ongoing) {
            this.timer = setTimeout(() => {
                this.state.duration += 1 / 60;
                this._runTimer();
            }, 1000);
        }
    }
}

export const pbTimer = {
    component: PbTimer,
    supportedTypes: ["float"],
    extractProps: ({ attrs }) => ({
        pb_timer_start_field: attrs.options.widget_start_field,
        pb_timer_stop_field: attrs.options.widget_stop_field,
        duration_field: attrs.options.duration_field,
    }),
};

registry.category("fields").add("PbTimer", pbTimer);
