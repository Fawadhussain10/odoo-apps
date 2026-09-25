import { registry } from "@web/core/registry";
import { formatFloatTime } from "@web/views/fields/formatters";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillDestroy, proxy, t, useOnChange, useProps } from "@odoo/owl";

export class PbTimer extends Component {
    static template = "pb_web_timer_widget.PbTimeCounter";
    props = useProps({
        ...standardFieldProps,
        pb_timer_start_field: t.string(),
        pb_timer_stop_field: t.string(),
        duration_field: t.string(),
    });

    setup() {
        this.state = proxy({ duration: 0 });
        // (Re)start the timer whenever the timer state or the saved duration
        // changes; the cleanup stops it as soon as it is no longer running.
        useOnChange(
            () => [this.isOngoing(), this.props.record.data[this.props.duration_field]],
            (ongoing, duration) => {
                this.state.duration = duration || 0;
                if (!ongoing) {
                    return;
                }
                this._runTimer();
                return () => clearTimeout(this.timer);
            }
        );
        onWillDestroy(() => clearTimeout(this.timer));
    }

    isOngoing() {
        const data = this.props.record.data;
        return Boolean(data[this.props.pb_timer_start_field] && !data[this.props.pb_timer_stop_field]);
    }

    formattedDuration() {
        // formatFloatTime except 1,5 =  1h30min but in this case 1,5 = 1min30
        return formatFloatTime(this.state.duration / 60, { displaySeconds: true });
    }

    _runTimer() {
        this.timer = setTimeout(() => {
            this.state.duration += 1 / 60;
            this._runTimer();
        }, 1000);
    }
}

export const pbTimer = {
    component: PbTimer,
    supportedTypes: ["float"],
    extractProps: ({ options }) => ({
        pb_timer_start_field: options.widget_start_field,
        pb_timer_stop_field: options.widget_stop_field,
        duration_field: options.duration_field,
    }),
};

registry.category("fields").add("PbTimer", pbTimer);
