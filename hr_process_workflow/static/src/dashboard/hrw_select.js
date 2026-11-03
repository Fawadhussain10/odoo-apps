/** @odoo-module **/

import { Component, onWillUnmount, useRef, useState } from "@odoo/owl";

/**
 * Premium dropdown used by the HR dashboard filters (replaces native <select>).
 * options: [{id, name, color?, icon?}]; value: id or "" for "all".
 */
export class HrwSelect extends Component {
    static template = "hr_process_workflow.HrwSelect";
    static props = {
        icon: { type: String, optional: true },
        placeholder: String,
        options: Array,
        value: { optional: true },
        onChange: Function,
    };

    setup() {
        this.root = useRef("root");
        this.search = useRef("search");
        this.state = useState({ open: false, query: "", active: -1 });
        this.onDocClick = (ev) => {
            if (this.state.open && this.root.el && !this.root.el.contains(ev.target)) {
                this.close();
            }
        };
        document.addEventListener("mousedown", this.onDocClick, true);
        onWillUnmount(() => document.removeEventListener("mousedown", this.onDocClick, true));
    }

    get selected() {
        const v = this.props.value;
        return v === "" || v === undefined || v === null || v === false
            ? null
            : this.props.options.find((o) => String(o.id) === String(v)) || null;
    }
    get searchable() {
        return this.props.options.length > 6;
    }
    get items() {
        const q = this.state.query.trim().toLowerCase();
        const all = [{ id: "", name: this.props.placeholder, isAll: true }, ...this.props.options];
        return q ? all.filter((o) => !o.isAll && o.name.toLowerCase().includes(q)) : all;
    }
    initials(name) {
        return (name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    }
    isSelected(o) {
        return o.isAll ? !this.selected : this.selected && String(this.selected.id) === String(o.id);
    }

    toggle() {
        if (this.state.open) {
            this.close();
        } else {
            this.state.open = true;
            this.state.query = "";
            this.state.active = -1;
            setTimeout(() => this.search.el && this.search.el.focus(), 30);
        }
    }
    close() {
        this.state.open = false;
    }
    pick(o) {
        this.close();
        this.props.onChange(o.isAll ? "" : o.id);
    }
    onKey(ev) {
        const items = this.items;
        if (ev.key === "ArrowDown") {
            this.state.active = Math.min(items.length - 1, this.state.active + 1);
            ev.preventDefault();
        } else if (ev.key === "ArrowUp") {
            this.state.active = Math.max(0, this.state.active - 1);
            ev.preventDefault();
        } else if (ev.key === "Enter" && items[this.state.active >= 0 ? this.state.active : 0]) {
            this.pick(items[this.state.active >= 0 ? this.state.active : 0]);
            ev.preventDefault();
        } else if (ev.key === "Escape") {
            this.close();
        }
    }
}
