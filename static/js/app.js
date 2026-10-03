/**
 * static/js/app.js - Real-time Municipal GIS Encroachment Surveillance Client.
 * Integrated with Google Maps (Satellite, Hybrid, Streets, Terrain) & Sentinel-2 Earth Observations.
 */

// Application State
const appState = {
    map: null,
    baseMaps: {},
    layers: {
        cadastre: null,
        structures: null,
        encroachments: null,
        buffer: null,
        drawItems: null,
    },
    drawControl: null,
    cadastreData: null,
    structuresData: null,
    encroachmentsData: null,
    statsData: null,
    selectedFlag: null,
    activePolygonLayer: null,
};

// Colors by Land Use
const LAND_USE_COLORS = {
    RESIDENTIAL: { color: "#3B82F6", fillColor: "#3B82F6", fillOpacity: 0.25 },
    COMMERCIAL: { color: "#8B5CF6", fillColor: "#8B5CF6", fillOpacity: 0.30 },
    INDUSTRIAL: { color: "#D946EF", fillColor: "#D946EF", fillOpacity: 0.35 },
    AGRICULTURAL: { color: "#84CC16", fillColor: "#84CC16", fillOpacity: 0.25 },
    PUBLIC_UTILITY_ROAD: { color: "#94A3B8", fillColor: "#64748B", fillOpacity: 0.50 },
    PUBLIC_PARK: { color: "#10B981", fillColor: "#10B981", fillOpacity: 0.30 },
    GOVERNMENT_RESERVE: { color: "#F59E0B", fillColor: "#F59E0B", fillOpacity: 0.25 },
    WATER_BODY: { color: "#06B6D4", fillColor: "#06B6D4", fillOpacity: 0.45 },
    CONSERVATION_BUFFER: { color: "#10B981", fillColor: "#10B981", fillOpacity: 0.15 },
};

// Satellite & Sensor Telemetry Labels
const SENSOR_LABELS = {
    google_hybrid: "Google Maps Hybrid (Maxar/Airbus Optical + Road Network)",
    google_satellite: "Google Maps Satellite (Sub-Meter Ortho Imagery)",
    google_streets: "Google Maps Vector Cartography",
    google_terrain: "Google Maps Terrain & Elevation Contours",
    sentinel2: "Copernicus Sentinel-2 Cloudless (ESA 10m Multi-Spectral)",
    satellite: "ESRI World Imagery (High-Resolution Satellite)",
    dark: "Carto Dark Matter (Surveillance Night Mode)",
    osm: "OpenStreetMap Global Cadastre",
};

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initEventListeners();
    fetchDataset();
    initSpectralSimulator();
});

/**
 * Initialize Leaflet Map with Google Maps, Sentinel-2 & Satellite Basemaps
 */
function initMap() {
    // Sector 7 center (lat: 12.9252, lon: 77.5915)
    appState.map = L.map("gis-map", {
        center: [12.9252, 77.5915],
        zoom: 17,
        zoomControl: false,
    });

    L.control.zoom({ position: "bottomright" }).addTo(appState.map);

    // 1. Google Maps Hybrid (Satellite + High-Resolution Labels & Roads)
    appState.baseMaps.google_hybrid = L.tileLayer("https://{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", {
        maxZoom: 21,
        subdomains: ["mt0", "mt1", "mt2", "mt3"],
        attribution: '&copy; Google Maps &bull; Satellite + Road Network',
    });

    // 2. Google Maps Pure Satellite (Sub-Meter Ortho Photogrammetry)
    appState.baseMaps.google_satellite = L.tileLayer("https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", {
        maxZoom: 21,
        subdomains: ["mt0", "mt1", "mt2", "mt3"],
        attribution: '&copy; Google Maps &bull; Maxar &bull; Airbus Satellite Imagery',
    });

    // 3. Google Maps Standard Streets
    appState.baseMaps.google_streets = L.tileLayer("https://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", {
        maxZoom: 21,
        subdomains: ["mt0", "mt1", "mt2", "mt3"],
        attribution: '&copy; Google Maps Cartography',
    });

    // 4. Google Maps Terrain & Elevation
    appState.baseMaps.google_terrain = L.tileLayer("https://{s}.google.com/vt/lyrs=p&x={x}&y={y}&z={z}", {
        maxZoom: 21,
        subdomains: ["mt0", "mt1", "mt2", "mt3"],
        attribution: '&copy; Google Maps Terrain & Relief',
    });

    // 5. European Space Agency Copernicus Sentinel-2 Cloudless Feed
    appState.baseMaps.sentinel2 = L.tileLayer("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/GoogleMapsCompatible/{z}/{x}/{y}.jpg", {
        maxZoom: 18,
        attribution: '&copy; Sentinel-2 Cloudless &bull; European Space Agency (ESA) &bull; EOX',
    });

    // 6. ESRI World Satellite Imagery
    appState.baseMaps.satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        attribution: '&copy; Esri &bull; Earthstar Geographics &bull; Maxar',
        maxZoom: 19,
    });

    // 7. Carto Dark Matter
    appState.baseMaps.dark = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; CartoDB &copy; OpenStreetMap',
        maxZoom: 20,
    });

    // 8. OpenStreetMap Standard
    appState.baseMaps.osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
    });

    // Default to Google Maps Hybrid for instant high-detail satellite context
    appState.baseMaps.google_hybrid.addTo(appState.map);

    // Feature Layers
    appState.layers.cadastre = L.geoJSON(null, {
        style: styleCadastreFeature,
        onEachFeature: onEachCadastreFeature,
    }).addTo(appState.map);

    appState.layers.structures = L.geoJSON(null, {
        style: () => ({
            color: "#38BDF8",
            weight: 2,
            opacity: 0.95,
            fillColor: "#0284C7",
            fillOpacity: 0.35,
            dashArray: "4, 4",
        }),
        onEachFeature: onEachStructureFeature,
    }).addTo(appState.map);

    appState.layers.encroachments = L.geoJSON(null, {
        style: styleEncroachmentFeature,
        onEachFeature: onEachEncroachmentFeature,
    }).addTo(appState.map);

    // Leaflet Draw Feature Group for Surveyor Interaction
    appState.layers.drawItems = new L.FeatureGroup().addTo(appState.map);
    const drawOptions = {
        position: "topright",
        draw: {
            polygon: {
                allowIntersection: false,
                drawError: { color: "#e1e100", message: "Polygon edges cannot cross!" },
                shapeOptions: { color: "#F59E0B", weight: 3, fillOpacity: 0.3 },
            },
            polyline: false,
            circle: false,
            rectangle: {
                shapeOptions: { color: "#F59E0B", weight: 3, fillOpacity: 0.3 },
            },
            circlemarker: false,
            marker: false,
        },
        edit: {
            featureGroup: appState.layers.drawItems,
            remove: true,
        },
    };
    appState.drawControl = new L.Control.Draw(drawOptions);
    appState.map.addControl(appState.drawControl);

    // Map Drawing Event Handlers
    appState.map.on(L.Draw.Event.CREATED, (e) => {
        const layer = e.layer;
        appState.layers.drawItems.clearLayers();
        appState.layers.drawItems.addLayer(layer);

        // Extract coordinates in [lon, lat] format
        const latlngs = layer.getLatLngs()[0];
        const coords = latlngs.map((pt) => [pt.lng, pt.lat]);
        coords.push(coords[0]); // Close ring

        analyzeDrawnPolygon(coords);
    });

    // Real-Time GPS Cursor Telemetry
    appState.map.on("mousemove", (e) => {
        const latElem = document.getElementById("lbl-cursor-lat");
        const lonElem = document.getElementById("lbl-cursor-lon");
        if (latElem) latElem.innerText = e.latlng.lat.toFixed(6);
        if (lonElem) lonElem.innerText = e.latlng.lng.toFixed(6);
    });

    appState.map.on("zoomend", () => {
        const zoomElem = document.getElementById("lbl-map-zoom");
        if (zoomElem) zoomElem.innerText = `${appState.map.getZoom()}x`;
    });
}

/**
 * Fetch All GIS Layers & Populate UI
 */
async function fetchDataset() {
    try {
        const [cadastreRes, structuresRes, encroachmentsRes, statsRes] = await Promise.all([
            fetch("/api/cadastre").then((r) => r.json()),
            fetch("/api/structures").then((r) => r.json()),
            fetch("/api/encroachments").then((r) => r.json()),
            fetch("/api/stats").then((r) => r.json()),
        ]);

        appState.cadastreData = cadastreRes;
        appState.structuresData = structuresRes;
        appState.encroachmentsData = encroachmentsRes;
        appState.statsData = statsRes;

        // Render GeoJSON to Map
        appState.layers.cadastre.clearLayers().addData(appState.cadastreData);
        appState.layers.structures.clearLayers().addData(appState.structuresData);
        appState.layers.encroachments.clearLayers().addData(appState.encroachmentsData);

        // Render UI
        updateKpiRibbon(appState.statsData);
        renderViolationsQueue(appState.encroachmentsData.features);
        renderCadastreRegistry(appState.cadastreData.features);
        fetchClassifierDiagnostics();

        // Fit Bounds
        if (appState.cadastreData.features.length > 0) {
            appState.map.fitBounds(appState.layers.cadastre.getBounds(), { padding: [30, 30] });
        }
    } catch (err) {
        console.error("Error loading GIS data:", err);
    }
}

/**
 * Cadastral Styling & Popups with Direct Google Maps Link
 */
function styleCadastreFeature(feature) {
    const landUse = feature.properties.registered_land_use;
    const styleConf = LAND_USE_COLORS[landUse] || { color: "#64748B", fillColor: "#64748B", fillOpacity: 0.2 };
    return {
        color: styleConf.color,
        weight: 2,
        opacity: 0.9,
        fillColor: styleConf.fillColor,
        fillOpacity: styleConf.fillOpacity,
    };
}

function onEachCadastreFeature(feature, layer) {
    const p = feature.properties;
    const owner = p.ownership;
    const centroid = layer.getBounds().getCenter();
    const gmapsUrl = `https://www.google.com/maps/search/?api=1&query=${centroid.lat.toFixed(6)},${centroid.lng.toFixed(6)}`;
    const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${centroid.lat.toFixed(6)},${centroid.lng.toFixed(6)}`;

    const popupContent = `
        <div style="font-family: 'Inter', sans-serif; font-size: 12px; color: #111;">
            <strong style="color: #1E3A8A; font-size: 13px;">${p.survey_number}</strong> &bull; ${p.parcel_id}<br/>
            <strong>Owner:</strong> ${owner.full_name} (${owner.owner_type})<br/>
            <strong>Registered Use:</strong> <span style="font-weight:600;">${p.registered_land_use}</span><br/>
            <strong>Area:</strong> ${p.area_sqm.toLocaleString()} m²<br/>
            <strong>Setback:</strong> ${p.setback_meters} m &bull; Max Coverage: ${p.max_coverage_ratio * 100}%
            <div style="margin-top: 8px; border-top: 1px solid #ddd; padding-top: 4px;">
                <a href="${gmapsUrl}" target="_blank" class="popup-gmaps-link"><i class="fa-brands fa-google"></i> Google Maps</a>
                <a href="${streetViewUrl}" target="_blank" class="popup-gmaps-link" style="color: #EA4335;"><i class="fa-solid fa-street-view"></i> Street View</a>
            </div>
        </div>
    `;
    layer.bindPopup(popupContent);
}

/**
 * Satellite Structure Styling with Google Ground Truth
 */
function onEachStructureFeature(feature, layer) {
    const p = feature.properties;
    const centroid = layer.getBounds().getCenter();
    const gmapsUrl = `https://www.google.com/maps/search/?api=1&query=${centroid.lat.toFixed(6)},${centroid.lng.toFixed(6)}`;
    const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${centroid.lat.toFixed(6)},${centroid.lng.toFixed(6)}`;

    const popupContent = `
        <div style="font-family: 'Inter', sans-serif; font-size: 12px; color: #111;">
            <strong style="color: #0284C7;"><i class="fa-solid fa-satellite"></i> SAT DETECTED FOOTPRINT</strong><br/>
            <strong>ID:</strong> ${p.structure_id}<br/>
            <strong>Classified Land Cover:</strong> ${p.classified_land_use}<br/>
            <strong>Footprint Area:</strong> ${p.area_sqm} m²<br/>
            <strong>Confidence:</strong> ${(p.confidence * 100).toFixed(1)}%
            <div style="margin-top: 8px; border-top: 1px solid #ddd; padding-top: 4px;">
                <a href="${gmapsUrl}" target="_blank" class="popup-gmaps-link"><i class="fa-brands fa-google"></i> Google Maps</a>
                <a href="${streetViewUrl}" target="_blank" class="popup-gmaps-link" style="color: #EA4335;"><i class="fa-solid fa-street-view"></i> Street View</a>
            </div>
        </div>
    `;
    layer.bindPopup(popupContent);
}

/**
 * Encroachment Styling & Events
 */
function styleEncroachmentFeature(feature) {
    const sev = feature.properties.severity;
    let color = "#EF4444";
    if (sev === "HIGH") color = "#F97316";
    if (sev === "MEDIUM") color = "#F59E0B";
    if (sev === "LOW") color = "#10B981";

    return {
        color: color,
        weight: 3,
        opacity: 1.0,
        fillColor: color,
        fillOpacity: 0.65,
        className: "pulsing-polygon",
    };
}

function onEachEncroachmentFeature(feature, layer) {
    layer.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        selectEncroachmentFlag(feature.properties, layer);
    });

    const p = feature.properties;
    const centroid = layer.getBounds().getCenter();
    const gmapsUrl = `https://www.google.com/maps/search/?api=1&query=${centroid.lat.toFixed(6)},${centroid.lng.toFixed(6)}`;
    const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${centroid.lat.toFixed(6)},${centroid.lng.toFixed(6)}`;

    const popupContent = `
        <div style="font-family: 'Inter', sans-serif; font-size: 12px; color: #111;">
            <strong style="color: #DC2626; font-size: 13px;"><i class="fa-solid fa-triangle-exclamation"></i> ENCROACHMENT: ${p.flag_id}</strong><br/>
            <strong>Severity:</strong> <span style="font-weight:700; color:#DC2626;">${p.severity}</span><br/>
            <strong>Type:</strong> ${formatEncroachmentType(p.encroachment_type)}<br/>
            <strong>Invaded Area:</strong> ${p.encroached_area_sqm} m²<br/>
            <strong>Violator:</strong> ${p.violator_owner_name}<br/>
            <strong>Affected:</strong> ${p.affected_owner_name}<br/>
            <div style="margin-top: 8px; border-top: 1px solid #ddd; padding-top: 4px;">
                <a href="${gmapsUrl}" target="_blank" class="popup-gmaps-link"><i class="fa-brands fa-google"></i> Google Maps</a>
                <a href="${streetViewUrl}" target="_blank" class="popup-gmaps-link" style="color: #EA4335;"><i class="fa-solid fa-street-view"></i> Street View</a>
            </div>
        </div>
    `;
    layer.bindPopup(popupContent);
    layer.bindTooltip(`<strong>${p.flag_id}</strong>: ${p.encroached_area_sqm} m² (${p.severity})`, {
        sticky: true,
        direction: "top",
    });
}

/**
 * Select & Inspect an Encroachment Flag
 */
function selectEncroachmentFlag(props, layer = null) {
    appState.selectedFlag = props;

    // Switch to Inspector Tab
    switchTab("tab-inspector");

    // Populate Inspector UI
    document.getElementById("inspector-empty").style.display = "none";
    document.getElementById("inspector-content").style.display = "flex";

    document.getElementById("insp-flag-id").innerText = props.flag_id;
    const sevElem = document.getElementById("insp-severity");
    sevElem.innerText = props.severity;
    sevElem.className = `badge-severity sev-${props.severity.toLowerCase()}`;

    document.getElementById("insp-type-title").innerText = formatEncroachmentType(props.encroachment_type);
    document.getElementById("insp-violator-name").innerText = props.violator_owner_name;
    document.getElementById("insp-violator-parcel").innerText = props.suspected_violator_parcel_id || "Unregistered / Squatter";
    document.getElementById("insp-affected-name").innerText = props.affected_owner_name;
    document.getElementById("insp-affected-parcel").innerText = props.affected_parcel_id;

    document.getElementById("insp-area").innerText = `${props.encroached_area_sqm} m²`;
    document.getElementById("insp-confidence").innerText = `${(props.confidence * 100).toFixed(1)}%`;
    document.getElementById("insp-zoning").innerText = props.affected_land_use;
    document.getElementById("insp-penalty").innerText = `₹${props.estimated_penalty.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

    document.getElementById("insp-recommendation").innerText = props.recommended_action;
    document.getElementById("insp-status-select").value = props.status;

    // Determine Centroid for Google Maps Links
    let centroidLat = 12.9252;
    let centroidLng = 77.5915;
    if (layer) {
        const c = layer.getBounds().getCenter();
        centroidLat = c.lat;
        centroidLng = c.lng;
    } else {
        appState.layers.encroachments.eachLayer((l) => {
            if (l.feature.properties.flag_id === props.flag_id) {
                const c = l.getBounds().getCenter();
                centroidLat = c.lat;
                centroidLng = c.lng;
            }
        });
    }

    // Set Google Maps and Google Street View URLs
    const gmapsBtn = document.getElementById("btn-open-gmaps");
    if (gmapsBtn) {
        gmapsBtn.href = `https://www.google.com/maps/search/?api=1&query=${centroidLat.toFixed(6)},${centroidLng.toFixed(6)}`;
    }
    const streetViewBtn = document.getElementById("btn-open-streetview");
    if (streetViewBtn) {
        streetViewBtn.href = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${centroidLat.toFixed(6)},${centroidLng.toFixed(6)}`;
    }

    // Highlight violation card in list
    document.querySelectorAll(".violation-card").forEach((card) => {
        card.classList.toggle("active", card.dataset.flagId === props.flag_id);
    });

    // Zoom to layer
    if (layer) {
        appState.map.flyToBounds(layer.getBounds(), { padding: [50, 50], maxZoom: 19 });
    } else {
        appState.layers.encroachments.eachLayer((l) => {
            if (l.feature.properties.flag_id === props.flag_id) {
                appState.map.flyToBounds(l.getBounds(), { padding: [50, 50], maxZoom: 19 });
            }
        });
    }
}

/**
 * Update KPI Ribbon Cards
 */
function updateKpiRibbon(stats) {
    document.getElementById("val-parcels").innerText = stats.total_parcels;
    document.getElementById("val-flags").innerText = stats.total_encroachment_flags;
    document.getElementById("val-area").innerText = `${stats.total_encroached_area_sqm.toLocaleString()} m²`;

    const critCount = (stats.severity_breakdown.CRITICAL || 0) + (stats.severity_breakdown.HIGH || 0);
    document.getElementById("val-critical").innerText = critCount;

    document.getElementById("val-penalties").innerText = `₹${stats.total_potential_penalties.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
    document.getElementById("tab-count-violations").innerText = stats.total_encroachment_flags;
}

/**
 * Render Violations Queue Cards
 */
function renderViolationsQueue(features) {
    const container = document.getElementById("violations-container");
    container.innerHTML = "";

    const filterSev = document.getElementById("filter-severity").value;
    const filterType = document.getElementById("filter-type").value;

    const filtered = features.filter((f) => {
        const p = f.properties;
        const matchSev = filterSev === "ALL" || p.severity === filterSev;
        const matchType = filterType === "ALL" || p.encroachment_type === filterType;
        return matchSev && matchType;
    });

    if (filtered.length === 0) {
        container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-check-double"></i><p>No active violations match current filters.</p></div>`;
        return;
    }

    filtered.forEach((f) => {
        const p = f.properties;
        const card = document.createElement("div");
        card.className = "violation-card";
        card.dataset.flagId = p.flag_id;

        card.innerHTML = `
            <div class="card-top">
                <span class="flag-badge">${p.flag_id}</span>
                <span class="badge-severity sev-${p.severity.toLowerCase()}">${p.severity}</span>
            </div>
            <div class="card-title">${formatEncroachmentType(p.encroachment_type)}</div>
            <div class="card-details">
                <span><i class="fa-solid fa-ruler-combined"></i> ${p.encroached_area_sqm} m²</span>
                <span><i class="fa-solid fa-indian-rupee-sign"></i> ₹${p.estimated_penalty.toLocaleString()}</span>
            </div>
        `;

        card.addEventListener("click", () => {
            selectEncroachmentFlag(p);
        });

        container.appendChild(card);
    });
}

/**
 * Render Cadastral Registry
 */
function renderCadastreRegistry(parcels) {
    const container = document.getElementById("parcels-table-container");
    container.innerHTML = "";

    parcels.forEach((f) => {
        const p = f.properties;
        const owner = p.ownership;
        const card = document.createElement("div");
        card.className = "parcel-list-card";
        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; margin-bottom: 2px;">
                <strong>${p.survey_number}</strong>
                <span style="font-size:0.7rem; color:#9CA3AF;">${p.parcel_id}</span>
            </div>
            <div style="color:#D1D5DB; font-size:0.75rem;">${owner.full_name} &bull; ${owner.owner_type}</div>
            <div style="color:#9CA3AF; font-size:0.7rem; display:flex; justify-content:space-between; margin-top:4px;">
                <span>Use: ${p.registered_land_use}</span>
                <span>${p.area_sqm} m²</span>
            </div>
        `;

        card.addEventListener("click", () => {
            appState.layers.cadastre.eachLayer((l) => {
                if (l.feature.properties.parcel_id === p.parcel_id) {
                    appState.map.flyToBounds(l.getBounds(), { padding: [50, 50], maxZoom: 18 });
                    l.openPopup();
                }
            });
        });

        container.appendChild(card);
    });
}

/**
 * Real-Time Scan Execution
 */
async function triggerRealTimeScan() {
    const btn = document.getElementById("btn-scan");
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning GIS Layers...`;
    btn.disabled = true;

    try {
        const res = await fetch("/api/scan", { method: "POST" });
        const data = await res.json();

        appState.encroachmentsData = data.encroachments;
        appState.statsData = data.stats;

        appState.layers.encroachments.clearLayers().addData(appState.encroachmentsData);
        updateKpiRibbon(appState.statsData);
        renderViolationsQueue(appState.encroachmentsData.features);

        alert(`Spatial Scan Complete!\nIdentified ${data.flags_detected} active boundary & regulatory discrepancies.`);
    } catch (err) {
        console.error("Scan failed:", err);
        alert("Scan failed. Check server console.");
    } finally {
        btn.innerHTML = `<i class="fa-solid fa-satellite-dish"></i> Run Real-Time Scan`;
        btn.disabled = false;
    }
}

/**
 * Analyze Arbitrary Polygon Drawn by Surveyor
 */
async function analyzeDrawnPolygon(coords) {
    try {
        const res = await fetch("/api/analyze-custom-polygon", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ coordinates: coords }),
        });
        const data = await res.json();
        const analysis = data.analysis;

        const body = document.getElementById("survey-result-body");
        let html = `
            <div style="font-size: 0.9rem; line-height: 1.6;">
                <p><strong>Total Drawn Area:</strong> ${analysis.drawn_area_sqm} m²</p>
                <p><strong>Intersected Parcels/Right-of-Ways:</strong> ${analysis.intersects_count}</p>
                <hr style="border: 0; border-top: 1px solid #374151; margin: 12px 0;">
                <h5 style="margin-bottom: 8px;">Spatial Intersections Breakdown:</h5>
        `;

        if (analysis.intersections.length === 0) {
            html += `<p style="color: #10B981;">No intersection with any registered municipal cadastre. Lies entirely in un-surveyed territory.</p>`;
        } else {
            html += `<ul style="padding-left: 20px;">`;
            analysis.intersections.forEach((item) => {
                html += `
                    <li style="margin-bottom: 6px;">
                        <strong>${item.survey_number}</strong> (${item.owner_name}) &bull; ${item.land_use}<br/>
                        Overlap: <strong>${item.overlap_sqm} m²</strong> (${item.percentage_of_drawn}% of drawn footprint)
                        ${item.is_public_asset ? '<span style="color:#EF4444; font-weight:bold;"> [MUNICIPAL/GOVT LAND]</span>' : ''}
                    </li>
                `;
            });
            html += `</ul>`;
        }

        html += `</div>`;
        body.innerHTML = html;
        document.getElementById("modal-survey-result").style.display = "flex";
    } catch (err) {
        console.error("Polygon analysis failed:", err);
    }
}

/**
 * Statutory Legal Notice Generation
 */
async function openStatutoryNoticeModal() {
    if (!appState.selectedFlag) return;

    try {
        const res = await fetch(`/api/notice/${appState.selectedFlag.flag_id}`);
        const data = await res.json();
        const n = data.notice;

        document.getElementById("not-ref").innerText = n.notice_reference;
        document.getElementById("not-date").innerText = n.issue_date;

        document.getElementById("not-violator-name").innerText = n.addressee.name;
        document.getElementById("not-violator-parcel").innerText = `Holding Parcel: ${n.addressee.parcel_id} (Survey #${n.addressee.survey_number})`;
        document.getElementById("not-zone").innerText = n.addressee.zone;

        document.getElementById("not-statutory-order").innerText = n.statutory_order;

        document.getElementById("not-type").innerText = n.infringement_details.encroachment_type;
        document.getElementById("not-area").innerText = `${n.infringement_details.encroached_area_sqm} m²`;
        document.getElementById("not-affected").innerText = n.infringement_details.affected_property;
        document.getElementById("not-coords").innerText = n.infringement_details.gps_centroid;
        document.getElementById("not-penalty").innerText = `₹${n.estimated_penalty_inr.toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
        document.getElementById("not-deadline").innerText = `${n.compliance_deadline_days} Days from service`;

        document.getElementById("modal-notice").style.display = "flex";
    } catch (err) {
        console.error("Notice generation failed:", err);
    }
}

/**
 * Multi-Spectral Simulator
 */
function initSpectralSimulator() {
    const sliders = ["r", "g", "b", "nir", "swir"];
    sliders.forEach((s) => {
        const input = document.getElementById(`rng-${s}`);
        const label = document.getElementById(`val-${s}`);
        input.addEventListener("input", () => {
            label.innerText = parseFloat(input.value).toFixed(2);
            updateSpectralCalculation();
        });
    });
}

let spectralDebounceTimer = null;
function updateSpectralCalculation() {
    clearTimeout(spectralDebounceTimer);
    spectralDebounceTimer = setTimeout(async () => {
        const r = parseFloat(document.getElementById("rng-r").value);
        const g = parseFloat(document.getElementById("rng-g").value);
        const b = parseFloat(document.getElementById("rng-b").value);
        const nir = parseFloat(document.getElementById("rng-nir").value);
        const swir = parseFloat(document.getElementById("rng-swir").value);

        try {
            const res = await fetch("/api/classify-spectral-sample", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ red: r, green: g, blue: b, nir: nir, swir: swir }),
            });
            const data = await res.json();
            const rData = data.result;

            document.getElementById("idx-ndvi").innerText = rData.indices.ndvi;
            document.getElementById("idx-ndbi").innerText = rData.indices.ndbi;
            document.getElementById("idx-ndwi").innerText = rData.indices.ndwi;
            document.getElementById("idx-bsi").innerText = rData.indices.bsi;

            document.getElementById("ml-predicted-class").innerText = `${rData.predicted_land_cover} (${rData.corresponding_land_use})`;
            const confPct = (rData.confidence * 100).toFixed(1);
            document.getElementById("ml-confidence-val").innerText = `${confPct}%`;
            document.getElementById("ml-confidence-bar").style.width = `${confPct}%`;
        } catch (err) {
            console.error("Spectral simulation failed:", err);
        }
    }, 200);
}

async function fetchClassifierDiagnostics() {
    try {
        const res = await fetch("/api/classifier-diagnostics");
        const data = await res.json();
        document.getElementById("ml-acc").innerText = `${(data.accuracy * 100).toFixed(1)}%`;
    } catch (err) {
        console.error("Diagnostics load failed:", err);
    }
}

/**
 * Event Listeners & Location Search
 */
function initEventListeners() {
    // Top Action Buttons
    document.getElementById("btn-scan").addEventListener("click", triggerRealTimeScan);
    document.getElementById("btn-draw-mode").addEventListener("click", () => {
        new L.Draw.Polygon(appState.map, appState.drawControl.options.draw.polygon).enable();
    });

    document.getElementById("btn-export-audit").addEventListener("click", async () => {
        const res = await fetch("/api/audit-report");
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `Municipal_Cadastral_Audit_Dossier_${Date.now()}.json`;
        a.click();
    });

    document.getElementById("btn-reset").addEventListener("click", async () => {
        if (confirm("Reset municipal cadastre to baseline simulated state?")) {
            await fetch("/api/reset", { method: "POST" });
            fetchDataset();
        }
    });

    // Location Search via Nominatim or Lat/Lon Coordinates
    const searchInput = document.getElementById("input-map-search");
    const searchBtn = document.getElementById("btn-map-search");

    const performLocationSearch = async () => {
        const query = searchInput.value.trim();
        if (!query) return;

        // Check if query is in lat, lon format (e.g. 12.9252, 77.5915)
        const coordMatch = query.match(/^([+-]?\d+(\.\d+)?)\s*,\s*([+-]?\d+(\.\d+)?)$/);
        if (coordMatch) {
            const lat = parseFloat(coordMatch[1]);
            const lon = parseFloat(coordMatch[3]);
            appState.map.flyTo([lat, lon], 18, { duration: 1.5 });
            return;
        }

        // Global Geocoding via OpenStreetMap Nominatim
        searchBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
        try {
            const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`);
            const results = await res.json();
            if (results && results.length > 0) {
                const lat = parseFloat(results[0].lat);
                const lon = parseFloat(results[0].lon);
                appState.map.flyTo([lat, lon], 17, { duration: 2.0 });
            } else {
                alert(`Location "${query}" not found. Try entering city name, address, or coordinates.`);
            }
        } catch (err) {
            console.error("Geocoding failed:", err);
        } finally {
            searchBtn.innerHTML = `<i class="fa-solid fa-location-arrow"></i>`;
        }
    };

    if (searchBtn && searchInput) {
        searchBtn.addEventListener("click", performLocationSearch);
        searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") performLocationSearch();
        });
    }

    // Layer Checkbox Toggles
    document.getElementById("chk-cadastre").addEventListener("change", (e) => {
        if (e.target.checked) appState.map.addLayer(appState.layers.cadastre);
        else appState.map.removeLayer(appState.layers.cadastre);
    });
    document.getElementById("chk-structures").addEventListener("change", (e) => {
        if (e.target.checked) appState.map.addLayer(appState.layers.structures);
        else appState.map.removeLayer(appState.layers.structures);
    });
    document.getElementById("chk-encroachments").addEventListener("change", (e) => {
        if (e.target.checked) appState.map.addLayer(appState.layers.encroachments);
        else appState.map.removeLayer(appState.layers.encroachments);
    });

    // Basemap Switcher with Google Maps & Telemetry Updates
    document.getElementById("sel-basemap").addEventListener("change", (e) => {
        const val = e.target.value;
        Object.values(appState.baseMaps).forEach((m) => appState.map.removeLayer(m));
        if (appState.baseMaps[val]) {
            appState.baseMaps[val].addTo(appState.map);
        }
        const sensorElem = document.getElementById("lbl-active-sensor");
        if (sensorElem && SENSOR_LABELS[val]) {
            sensorElem.innerText = SENSOR_LABELS[val];
        }
    });

    // Filters
    document.getElementById("filter-severity").addEventListener("change", () => {
        if (appState.encroachmentsData) renderViolationsQueue(appState.encroachmentsData.features);
    });
    document.getElementById("filter-type").addEventListener("change", () => {
        if (appState.encroachmentsData) renderViolationsQueue(appState.encroachmentsData.features);
    });

    // Search Parcels
    document.getElementById("input-search-parcel").addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase();
        if (!appState.cadastreData) return;
        const filtered = appState.cadastreData.features.filter((f) => {
            const p = f.properties;
            return (
                p.survey_number.toLowerCase().includes(query) ||
                p.parcel_id.toLowerCase().includes(query) ||
                p.ownership.full_name.toLowerCase().includes(query)
            );
        });
        renderCadastreRegistry(filtered);
    });

    // Tab Navigation
    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const target = btn.dataset.tab;
            switchTab(target);
        });
    });

    // Statutory Notice Modal Actions
    document.getElementById("btn-generate-notice").addEventListener("click", openStatutoryNoticeModal);
    document.getElementById("btn-close-notice").addEventListener("click", () => {
        document.getElementById("modal-notice").style.display = "none";
    });
    document.getElementById("btn-dismiss-notice").addEventListener("click", () => {
        document.getElementById("modal-notice").style.display = "none";
    });
    document.getElementById("btn-print-notice").addEventListener("click", () => {
        window.print();
    });

    // Survey Result Modal Actions
    document.getElementById("btn-close-survey-result").addEventListener("click", () => {
        document.getElementById("modal-survey-result").style.display = "none";
    });
    document.getElementById("btn-done-survey-result").addEventListener("click", () => {
        document.getElementById("modal-survey-result").style.display = "none";
    });

    // Status Update
    document.getElementById("btn-save-status").addEventListener("click", async () => {
        if (!appState.selectedFlag) return;
        const newStatus = document.getElementById("insp-status-select").value;
        const res = await fetch("/api/update-flag-status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ flag_id: appState.selectedFlag.flag_id, status: newStatus }),
        });
        const data = await res.json();
        if (data.status === "success") {
            appState.selectedFlag.status = newStatus;
            alert(`Enforcement Status updated to ${newStatus}`);
        }
    });
}

function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach((b) => {
        b.classList.toggle("active", b.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-pane").forEach((p) => {
        p.classList.toggle("active", p.id === tabId);
    });
}

function formatEncroachmentType(typeStr) {
    const map = {
        GOVERNMENT_LAND_TRESPASS: "Municipal / Public Road Trespass",
        BOUNDARY_SPILLOVER: "Private Neighbor Boundary Spillover",
        WATERBODY_BUFFER_VIOLATION: "Eco-Sensitive Waterbody Buffer Violation",
        UNAUTHORIZED_LAND_USE: "Unauthorized Land Use Conversion",
        SETBACK_EXCESS: "Mandatory Setback Fringe Excess",
    };
    return map[typeStr] || typeStr.replace(/_/g, " ");
}
