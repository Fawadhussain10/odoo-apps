import { registry } from "@web/core/registry";
import { loadJS, loadCSS } from "@web/core/assets";
import { Layout } from "@web/search/layout";
import { standardViewProps } from "@web/views/standard_view_props";
import { useService } from "@web/core/utils/hooks";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    proxy,
    signal,
    t,
    useOnChange,
    useProps,
} from "@odoo/owl";

// Same lazily-loaded Leaflet bundle as the standalone/dashboard map
// (@pb_hms_base/map/patient_map) - a second loadJS/loadCSS call here just
// resolves the same cached promise if that one already ran.
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

class PatientMapViewRenderer extends Component {
    static template = "pb_hms_base.PatientMapViewRenderer";
    props = useProps({ points: t.array() });

    mapRef = signal.ref();

    setup() {
        this.actionService = useService("action");
        this.leafletMap = null;
        this.markersLayer = null;

        onWillStart(() => loadLeaflet());
        onMounted(() => this.initMap());
        onWillUnmount(() => {
            if (this.leafletMap) {
                this.leafletMap.remove();
                this.leafletMap = null;
            }
        });

        // Redraw markers whenever the record set changes (search/filter/
        // group-by updates flow down as a new points array from the
        // controller) without tearing down and re-creating the map itself.
        useOnChange(
            () => [this.props.points],
            () => {
                if (this.leafletMap) {
                    this.drawMarkers();
                }
            },
            { initialRun: false }
        );
    }

    initMap() {
        const mapEl = this.mapRef();
        if (!mapEl || !window.L) {
            return;
        }
        const L = window.L;
        this.leafletMap = L.map(mapEl, {
            zoomControl: true,
            attributionControl: true,
        }).setView([20, 0], 2);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 18,
            attribution: "&copy; OpenStreetMap contributors",
        }).addTo(this.leafletMap);

        this.markersLayer = L.layerGroup().addTo(this.leafletMap);
        this.drawMarkers();
    }

    drawMarkers() {
        const L = window.L;
        this.markersLayer.clearLayers();

        const pbIcon = L.divIcon({
            className: "pb-map-marker",
            html: '<span class="pb-map-marker-dot"></span>',
            iconSize: [18, 18],
            iconAnchor: [9, 9],
            popupAnchor: [0, -10],
        });

        const markers = [];
        for (const point of this.props.points) {
            const marker = L.marker([point.lat, point.lng], { icon: pbIcon });
            marker.bindPopup(this._popupHtml(point));
            marker.on("popupopen", (ev) => {
                const link = ev.popup.getElement().querySelector(".pb-map-popup-link");
                if (link) {
                    link.addEventListener("click", (clickEv) => {
                        clickEv.preventDefault();
                        this.openPatient(point.id);
                    });
                }
            });
            marker.addTo(this.markersLayer);
            markers.push(marker);
        }

        if (markers.length) {
            const group = L.featureGroup(markers);
            this.leafletMap.fitBounds(group.getBounds().pad(0.2));
        }
    }

    _esc(str) {
        const div = document.createElement("div");
        div.textContent = str || "";
        return div.innerHTML;
    }

    _popupHtml(point) {
        return `
            <div class="pb-map-popup">
                <div class="pb-map-popup-name">${this._esc(point.name)}</div>
                <div class="pb-map-popup-code" t-if="point.code">${this._esc(point.code)}</div>
                ${point.address ? `<div class="pb-map-popup-address"><i class="oi" data-icon="location_on"></i> ${this._esc(point.address)}</div>` : ""}
                ${point.phone ? `<div class="pb-map-popup-phone"><i class="oi" data-icon="phone"></i> ${this._esc(point.phone)}</div>` : ""}
                <a href="#" class="pb-map-popup-link">Open Patient <i class="oi ms-1" data-icon="arrow_forward"></i></a>
            </div>
        `;
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
}

class PatientMapViewController extends Component {
    static template = "pb_hms_base.PatientMapViewController";
    static components = { Layout, PatientMapViewRenderer };
    props = useProps(standardViewProps);

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ loading: true, points: [], locatedCount: 0, totalCount: 0 });

        onWillStart(() => this.loadPoints());
        // search/filter updates come in as new domain/context props
        useOnChange(
            () => [this.props.domain, this.props.context],
            () => this.loadPoints(),
            { initialRun: false }
        );
    }

    display() {
        return { ...this.props.display, controlPanel: {} };
    }

    async loadPoints() {
        this.state.loading = true;
        const result = await this.orm.webSearchRead(this.props.resModel, this.props.domain, {
            specification: {
                name: {},
                code: {},
                phone: {},
                partner_latitude: {},
                partner_longitude: {},
                street: {},
                street2: {},
                city: {},
                zip: {},
                state_id: { fields: { display_name: {} } },
                country_id: { fields: { display_name: {} } },
            },
            limit: 5000,
            context: this.props.context,
        });

        this.state.totalCount = result.length;
        this.state.points = result.records
            .filter((r) => r.partner_latitude && r.partner_longitude)
            .map((r) => ({
                id: r.id,
                name: r.name,
                code: r.code || "",
                phone: r.phone || "",
                lat: r.partner_latitude,
                lng: r.partner_longitude,
                address: [
                    r.street,
                    r.street2,
                    r.city,
                    r.state_id && r.state_id.display_name,
                    r.zip,
                    r.country_id && r.country_id.display_name,
                ]
                    .filter(Boolean)
                    .join(", "),
            }));
        this.state.locatedCount = this.state.points.length;
        this.state.loading = false;
    }
}

// Named "pb_map", not "map": this Odoo install has Enterprise's web_map
// installed, which already owns the "map" view type/registry key - reusing
// that name would collide with its (incompatible) arch schema and its own
// client-side view registration. We don't depend on web_map.
// Also not "pb_patient_map": Odoo's view-switcher gives its per-type button
// the class "o_<type>" (e.g. "o_pb_patient_map"), which collided with the
// standalone map page's own root div class of the same name and leaked its
// control-panel styling onto every other Patients tab.
export const patientMapView = {
    type: "pb_map",
    display_name: "Map",
    icon: "location_on",
    multiRecord: true,
    Controller: PatientMapViewController,
    Renderer: PatientMapViewRenderer,
    searchMenuTypes: ["filter", "groupBy", "favorite"],
    props: (genericProps) => genericProps,
};

registry.category("views").add("pb_map", patientMapView);
