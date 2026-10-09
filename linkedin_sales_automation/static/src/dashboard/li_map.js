/** @odoo-module **/
import { Component, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { WORLD_HEIGHT, WORLD_PATHS, WORLD_SCALE, WORLD_WIDTH, WORLD_XMAX, WORLD_YMAX } from "./li_world";

const MAX_ZOOM = 12;
const TONES = [
    ["hot", _t("Warm lead / meeting")],
    ["engaged", _t("Accepted / talking")],
    ["pipeline", _t("Queued / invited")],
    ["closed", _t("Closed")],
];

/** Natural Earth projection, the same as the pre-projected world outline. */
export function project(lat, lng) {
    const l = (lng * Math.PI) / 180;
    const p = (lat * Math.PI) / 180;
    const p2 = p * p;
    const p4 = p2 * p2;
    const x = l * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)));
    const y = p * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)));
    return [(x + WORLD_XMAX) * WORLD_SCALE, (WORLD_YMAX - y) * WORLD_SCALE];
}

function graticule() {
    const lines = [];
    const line = (points) => "M" + points.map(([lat, lng]) => project(lat, lng).map((v) => v.toFixed(1)).join(",")).join("L");
    for (let lng = -180; lng <= 180; lng += 30) {
        const pts = [];
        for (let lat = -60; lat <= 85; lat += 5) {
            pts.push([lat, lng]);
        }
        lines.push(line(pts));
    }
    for (let lat = -60; lat <= 80; lat += 20) {
        const pts = [];
        for (let lng = -180; lng <= 180; lng += 5) {
            pts.push([lat, lng]);
        }
        lines.push(line(pts));
    }
    return lines;
}
const GRATICULE = graticule();

export class LiProspectMap extends Component {
    static template = "linkedin_sales_automation.ProspectMap";
    static props = { map: Object, filters: Object };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.box = useRef("box");
        this.paths = WORLD_PATHS;
        this.graticule = GRATICULE;
        this.tones = TONES;
        this.width = WORLD_WIDTH;
        this.height = WORLD_HEIGHT;
        this.state = useState({ zoom: 1, cx: WORLD_WIDTH / 2, cy: WORLD_HEIGHT / 2, popup: null, hover: null });
        this.drag = null;
    }

    // ---------------------------------------------------------------- view
    get view() {
        const w = this.width / this.state.zoom;
        const h = this.height / this.state.zoom;
        const cx = Math.min(Math.max(this.state.cx, w / 2), this.width - w / 2);
        const cy = Math.min(Math.max(this.state.cy, h / 2), this.height - h / 2);
        return { x: cx - w / 2, y: cy - h / 2, w, h };
    }
    get viewBox() {
        const v = this.view;
        return `${v.x} ${v.y} ${v.w} ${v.h}`;
    }
    get dots() {
        const places = this.props.map.places;
        const max = Math.max(1, ...places.map((p) => p.count));
        const k = 1 / Math.pow(this.state.zoom, 0.85);
        return places
            .map((p, i) => {
                const [x, y] = project(p.lat, p.lng);
                const r = (2.6 + 7 * Math.sqrt(p.count / max)) * k;
                return { ...p, key: `${p.lat},${p.lng}`, x, y, r, delay: `${(i % 12) * 0.2}s` };
            })
            .sort((a, b) => b.count - a.count);
    }
    get strokeWidth() {
        return 0.6 / this.state.zoom;
    }
    zoomTo(zoom, cx = this.state.cx, cy = this.state.cy) {
        this.state.zoom = Math.min(MAX_ZOOM, Math.max(1, zoom));
        this.state.cx = cx;
        this.state.cy = cy;
    }
    zoomIn() {
        this.zoomTo(this.state.zoom * 1.6);
    }
    zoomOut() {
        this.zoomTo(this.state.zoom / 1.6);
    }
    reset() {
        this.state.popup = null;
        this.zoomTo(1, this.width / 2, this.height / 2);
    }
    toMap(ev) {
        const rect = this.box.el.getBoundingClientRect();
        const v = this.view;
        return [v.x + ((ev.clientX - rect.left) / rect.width) * v.w, v.y + ((ev.clientY - rect.top) / rect.height) * v.h];
    }
    onWheel(ev) {
        ev.preventDefault();
        const [mx, my] = this.toMap(ev);
        const factor = ev.deltaY < 0 ? 1.25 : 0.8;
        const zoom = Math.min(MAX_ZOOM, Math.max(1, this.state.zoom * factor));
        const v = this.view;
        // keep the point under the cursor in place
        const w = this.width / zoom;
        const h = this.height / zoom;
        const fx = (mx - v.x) / v.w;
        const fy = (my - v.y) / v.h;
        this.zoomTo(zoom, mx - (fx - 0.5) * w, my - (fy - 0.5) * h);
    }
    onPointerDown(ev) {
        if (ev.button !== 0 || ev.target.closest(".o_li_map_popup, .o_li_map_tools")) {
            return;
        }
        const v = this.view;
        this.drag = { x: ev.clientX, y: ev.clientY, cx: v.x + v.w / 2, cy: v.y + v.h / 2, moved: false };
    }
    onPointerMove(ev) {
        if (!this.drag) {
            return;
        }
        const dx = ev.clientX - this.drag.x;
        const dy = ev.clientY - this.drag.y;
        if (!this.drag.moved && Math.hypot(dx, dy) < 4) {
            return;
        }
        this.drag.moved = true;
        const rect = this.box.el.getBoundingClientRect();
        const v = this.view;
        this.state.cx = this.drag.cx - (dx / rect.width) * v.w;
        this.state.cy = this.drag.cy - (dy / rect.height) * v.h;
    }
    onPointerUp() {
        this.wasDragged = Boolean(this.drag && this.drag.moved);
        this.drag = null;
    }

    // ---------------------------------------------------------------- popup
    async openPlace(dot, ev) {
        ev.stopPropagation();
        if (this.wasDragged) {
            this.wasDragged = false;
            return;
        }
        const rect = this.box.el.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        this.state.popup = {
            dot,
            left: Math.min(Math.max(x, 170), rect.width - 170),
            top: y,
            above: y > rect.height * 0.55,
            loading: true,
            data: null,
        };
        const data = await this.orm.call("li.dashboard", "get_map_place", [dot.lat, dot.lng, this.props.filters]);
        if (this.state.popup && this.state.popup.dot.key === dot.key) {
            this.state.popup.data = data;
            this.state.popup.loading = false;
        }
    }
    closePopup() {
        if (this.wasDragged) {
            this.wasDragged = false;
            return;
        }
        this.state.popup = null;
    }
    closeNow() {
        this.state.popup = null;
    }
    keep(ev) {
        ev.stopPropagation();
    }
    openProspect(prospect) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "li.prospect",
            res_id: prospect.id,
            views: [[false, "form"]],
        });
    }
    async openAll(dot) {
        const action = await this.orm.call("li.dashboard", "get_map_action", [dot.lat, dot.lng, this.props.filters]);
        action.name = dot.place;
        this.action.doAction(action);
    }
    initials(name) {
        return (name || "?")
            .split(/\s+/)
            .filter((w) => w)
            .slice(0, 2)
            .map((w) => w[0].toUpperCase())
            .join("");
    }
    stageTone(stage) {
        if (["warm", "meeting"].includes(stage)) {
            return "hot";
        }
        if (["accepted", "messaged", "replied"].includes(stage)) {
            return "engaged";
        }
        if (["queued", "invited"].includes(stage)) {
            return "pipeline";
        }
        return "closed";
    }
    setHover(dot) {
        this.state.hover = dot;
    }
}
