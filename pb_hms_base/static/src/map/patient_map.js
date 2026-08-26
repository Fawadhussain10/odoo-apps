/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { loadJS, loadCSS } from "@web/core/assets";
import { Layout } from "@web/search/layout";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onWillStart, onMounted, onWillDestroy } from "@odoo/owl";

let leafletLoadPromise = null;
function loadLeaflet() {
    if (!leafletLoadPromise) {
        leafletLoadPromise = Promise.all([
            loadCSS("/pb_hms_base/static/src/lib/leaflet/leaflet.css"),
            loadJS("/pb_hms_base/static/src/lib/leaflet/leaflet.js"),
        ]);
    }
    return leafletLoadPromise;
}

// A reusable Leaflet-based patient map. Two shapes:
//  - full page (props.compact falsy): tall map, its own header/stats
//  - dashboard card (props.compact true): short map, minimal chrome, meant to
//    sit inside a .pb-card/.hms-dashboard-* wrapper the caller already renders
export class PbPatientMap extends Component {
    static template = "pb_hms_base.PatientMap";
    static components = { Layout };
    // Accepts arbitrary props: mounted both as a plain client action (which the
    // action framework passes its own action/actionId/className props to) and
    // as an embedded <PbPatientMap compact="true"/> inside the dashboard.
    static props = ["*"];
    static defaultProps = { compact: false };

    setup() {
        this.actionService = useService("action");
        this.mapRef = useRef("mapContainer");
        this.state = useState({ loading: true, totalPatients: 0, locatedCount: 0 });
        this.leafletMap = null;

        onWillStart(async () => {
            await loadLeaflet();
        });

        onMounted(async () => {
            await this.renderMap();
        });

        onWillDestroy(() => {
            if (this.leafletMap) {
                this.leafletMap.remove();
                this.leafletMap = null;
            }
        });
    }

    get display() {
        return { controlPanel: {} };
    }

    async renderMap() {
        const data = await rpc("/pb_hms/patient_map_data", {});
        this.state.totalPatients = data.total_patients;
        this.state.locatedCount = data.located_count;
        this.state.loading = false;

        if (!this.mapRef.el) {
            return;
        }

        const L = window.L;
        const map = L.map(this.mapRef.el, {
            zoomControl: !this.props.compact,
            attributionControl: !this.props.compact,
            // In compact/dashboard mode the map is small and sits inline in a
            // scrolling page - leaving scroll-wheel zoom/touch-drag-pan on
            // means scrolling the mouse wheel, or dragging a finger, starting
            // over the card zooms/pans the tiny map instead of scrolling the
            // page. It's a static preview (there's a "Full map" link for
            // actually interacting with it), so trade that off for a card
            // that doesn't fight the page's own scroll.
            scrollWheelZoom: !this.props.compact,
            dragging: !this.props.compact,
        }).setView([20, 0], 2);
        this.leafletMap = map;

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 18,
            attribution: '&copy; OpenStreetMap contributors',
        }).addTo(map);

        const pbIcon = L.divIcon({
            className: "pb-map-marker",
            html: '<span class="pb-map-marker-dot"></span>',
            iconSize: [18, 18],
            iconAnchor: [9, 9],
            popupAnchor: [0, -10],
        });

        const markers = [];
        for (const point of data.points) {
            const marker = L.marker([point.lat, point.lng], { icon: pbIcon }).addTo(map);
            const popupHtml = `
                <div class="pb-map-popup">
                    <div class="pb-map-popup-name">${this._esc(point.name)}</div>
                    <div class="pb-map-popup-code">${this._esc(point.code || "")}</div>
                    <div class="pb-map-popup-address">${this._esc(point.address)}</div>
                    <div class="pb-map-popup-phone">${this._esc(point.phone)}</div>
                    <a href="#" class="pb-map-popup-link" data-patient-id="${point.id}">Open Patient</a>
                </div>`;
            marker.bindPopup(popupHtml);
            marker.on("popupopen", (ev) => {
                const link = ev.popup.getElement().querySelector(".pb-map-popup-link");
                if (link) {
                    link.addEventListener("click", (e) => {
                        e.preventDefault();
                        this.openPatient(point.id);
                    });
                }
            });
            markers.push(marker);
        }

        if (markers.length) {
            const group = L.featureGroup(markers);
            map.fitBounds(group.getBounds().pad(0.2));
        }
    }

    _esc(str) {
        const div = document.createElement("div");
        div.textContent = str || "";
        return div.innerHTML;
    }

    openPatient(patientId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "hms.patient",
            res_id: patientId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openFullMap() {
        this.actionService.doAction("pb_hms_base.action_patient_map");
    }
}

registry.category("actions").add("pb_hms_base.action_patient_map", PbPatientMap);
