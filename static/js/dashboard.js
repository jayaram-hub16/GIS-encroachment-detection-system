/**
 * dashboard.js - Full CRUD Management Dashboard for Municipal GIS System
 * Handles: parcels, encroachments, users, stats, modals, toasts, pagination
 */

"use strict";

// ════════════════════════════════════════
// STATE
// ════════════════════════════════════════
const DS = {
    parcelPage: 1, parcelSort: "created_at", parcelDir: "desc",
    encPage: 1,
    auditPage: 1,
    deletePending: null, // { url, onSuccess }
};

// ════════════════════════════════════════
// INIT
// ════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {
    // Sidebar toggle (mobile)
    document.getElementById("menuToggle")?.addEventListener("click", openSidebar);
    document.getElementById("sidebarClose")?.addEventListener("click", closeSidebar);

    // Show overview by default
    showPage("overview", document.querySelector(".nav-item[data-page='overview']"));

    // Hide Users nav item for non-admins (will be shown from API check)
    checkAdminRole();
});

// ════════════════════════════════════════
// SIDEBAR
// ════════════════════════════════════════
function openSidebar() {
    document.getElementById("sidebar").classList.add("open");
    document.getElementById("sidebarOverlay").classList.add("open");
}
function closeSidebar() {
    document.getElementById("sidebar").classList.remove("open");
    document.getElementById("sidebarOverlay").classList.remove("open");
}

// ════════════════════════════════════════
// PAGE NAVIGATION
// ════════════════════════════════════════
const PAGE_CONFIG = {
    overview:      { icon: "fa-gauge-high",          label: "Dashboard" },
    parcels:       { icon: "fa-map-location-dot",    label: "Land Parcels" },
    encroachments: { icon: "fa-triangle-exclamation",label: "Encroachments" },
    users:         { icon: "fa-users-gear",          label: "User Management" },
    auditlogs:     { icon: "fa-scroll",              label: "Audit Logs" },
};

function showPage(pageId, navEl) {
    // Hide all pages
    document.querySelectorAll(".page-section").forEach(s => s.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

    // Show target
    const section = document.getElementById(`page-${pageId}`);
    if (section) section.classList.add("active");
    if (navEl) navEl.classList.add("active");

    // Update breadcrumb
    const cfg = PAGE_CONFIG[pageId] || { icon: "fa-circle", label: pageId };
    document.getElementById("breadcrumbText").innerHTML =
        `<i class="fa-solid ${cfg.icon}"></i> ${cfg.label}`;

    // Close sidebar on mobile
    closeSidebar();

    // Load page data
    switch (pageId) {
        case "overview":      loadOverview(); break;
        case "parcels":       DS.parcelPage = 1; loadParcels(); break;
        case "encroachments": DS.encPage = 1; loadEncroachments(); break;
        case "users":         loadUsers(); break;
        case "auditlogs":     DS.auditPage = 1; loadAuditLogs(); break;
    }
}

function refreshCurrentPage() {
    const active = document.querySelector(".page-section.active");
    if (!active) return;
    const pageId = active.id.replace("page-", "");
    const icon = document.getElementById("refreshIcon");
    if (icon) { icon.classList.add("spinning"); setTimeout(() => icon.classList.remove("spinning"), 800); }
    showPage(pageId, null);
}

// ════════════════════════════════════════
// OVERVIEW / KPI
// ════════════════════════════════════════
async function loadOverview() {
    try {
        const res = await fetch("/api/dashboard-stats");
        if (!res.ok) throw new Error("Stats API error");
        const data = await res.json();
        const db = data.db_stats || {};
        const gis = data.gis_stats || {};

        setKpi("kpiParcels", db.total_parcels ?? 0);
        setKpi("kpiEnc",     db.total_encroachments ?? 0);
        setKpi("kpiGis",     gis.total_flags ?? gis.total_encroachment_flags ?? 0);
        setKpi("kpiUsers",   db.total_users ?? 0);

        renderSeverityChart(db.severity_breakdown || {});
        renderRecentParcels(data.recent_parcels || []);
        renderRecentEnc(data.recent_encroachments || []);
    } catch (err) {
        console.error("[Overview]", err);
    }
}

function setKpi(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = Number(val).toLocaleString();
}

function renderSeverityChart(sev) {
    const wrap = document.getElementById("severityChart");
    if (!wrap) return;
    const levels = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
    const max = Math.max(...levels.map(l => sev[l] || 0), 1);
    wrap.innerHTML = levels.map(l => {
        const count = sev[l] || 0;
        const pct = Math.round((count / max) * 100);
        return `
        <div class="sev-bar-row">
            <div class="sev-bar-label label-${l}">${l}</div>
            <div class="sev-bar-track">
                <div class="sev-bar-fill sev-${l}" style="width:${pct}%"></div>
            </div>
            <div class="sev-bar-count label-${l}">${count}</div>
        </div>`;
    }).join("");
}

function renderRecentParcels(parcels) {
    const el = document.getElementById("recentParcels");
    if (!el) return;
    if (!parcels.length) {
        el.innerHTML = '<div class="empty-state"><i class="fa-solid fa-inbox"></i><br>No parcel records yet</div>';
        return;
    }
    el.innerHTML = parcels.map(p => `
    <div class="recent-item">
        <div class="ri-icon ri-blue"><i class="fa-solid fa-map"></i></div>
        <div class="ri-text">
            <div class="ri-title">${esc(p.owner_name)}</div>
            <div class="ri-sub">${esc(p.parcel_id)} · ${esc(p.registered_land_use)}</div>
        </div>
    </div>`).join("");
}

function renderRecentEnc(records) {
    const el = document.getElementById("recentEnc");
    if (!el) return;
    if (!records.length) {
        el.innerHTML = '<div class="empty-state"><i class="fa-solid fa-check-circle"></i><br>No encroachment records</div>';
        return;
    }
    el.innerHTML = records.map(r => `
    <div class="recent-item">
        <div class="ri-icon ri-red"><i class="fa-solid fa-triangle-exclamation"></i></div>
        <div class="ri-text">
            <div class="ri-title">${esc(r.violator_name || "Unknown")}</div>
            <div class="ri-sub">${esc(r.encroachment_type)} · ${severityBadge(r.severity)}</div>
        </div>
    </div>`).join("");
}

// ════════════════════════════════════════
// PARCELS
// ════════════════════════════════════════
async function loadParcels() {
    const tbody = document.getElementById("parcelTbody");
    tbody.innerHTML = `<tr><td colspan="8" class="loading-row"><i class="fa-solid fa-spinner fa-spin"></i> Loading…</td></tr>`;

    const search   = document.getElementById("parcelSearch")?.value || "";
    const landUse  = document.getElementById("parcelLandUse")?.value || "";
    const ownerType= document.getElementById("parcelOwnerType")?.value || "";

    const params = new URLSearchParams({
        page: DS.parcelPage,
        per_page: 15,
        search, land_use: landUse, owner_type: ownerType,
        sort_by: DS.parcelSort, sort_dir: DS.parcelDir
    });

    try {
        const res = await fetch(`/api/parcels?${params}`);
        const data = await res.json();

        if (!data.parcels?.length) {
            tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:var(--text-muted)"><i class="fa-solid fa-inbox"></i> No records found</td></tr>`;
            document.getElementById("parcelPagination").innerHTML = "";
            return;
        }

        tbody.innerHTML = data.parcels.map(p => `
        <tr>
            <td style="color:var(--text-muted);font-family:monospace">${p.id}</td>
            <td style="color:var(--accent-cyan);font-family:monospace;font-size:11px">${esc(p.parcel_id)}</td>
            <td>${esc(p.survey_number)}</td>
            <td style="color:var(--text-primary);font-weight:500">${esc(p.owner_name)}</td>
            <td>${landUseBadge(p.registered_land_use)}</td>
            <td style="font-family:monospace">${(p.area_sqm||0).toLocaleString()}</td>
            <td style="color:var(--text-muted);font-size:11px">${fmtDate(p.created_at)}</td>
            <td>
                <div class="action-btns">
                    <button class="btn-icon edit" onclick="editParcel(${p.id})" title="Edit">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button class="btn-icon del" onclick="confirmDelete('parcel',${p.id},'${esc(p.parcel_id)} — ${esc(p.owner_name)}')" title="Delete">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        </tr>`).join("");

        renderPagination("parcelPagination", data.page, data.pages, (p) => {
            DS.parcelPage = p; loadParcels();
        });
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:#f87171"><i class="fa-solid fa-circle-exclamation"></i> Failed to load data</td></tr>`;
        console.error("[Parcels]", err);
    }
}

function sortParcels(col) {
    if (DS.parcelSort === col) {
        DS.parcelDir = DS.parcelDir === "asc" ? "desc" : "asc";
    } else {
        DS.parcelSort = col; DS.parcelDir = "asc";
    }
    DS.parcelPage = 1; loadParcels();
}

function openParcelForm(data = null) {
    const editing = !!data;
    document.getElementById("parcelModalTitle").innerHTML =
        `<i class="fa-solid fa-map-location-dot"></i> ${editing ? "Edit Land Parcel" : "Add Land Parcel"}`;
    document.getElementById("parcelRecordId").value = data?.id || "";

    // Fill or clear fields
    setVal("fSurveyNo",   data?.survey_number || "");
    setVal("fParcelId",   data?.parcel_id || "");
    setVal("fOwnerName",  data?.owner_name || "");
    setVal("fOwnerType",  data?.owner_type || "PRIVATE_CITIZEN");
    setVal("fLandUse",    data?.registered_land_use || "RESIDENTIAL");
    setVal("fZone",       data?.zone_name || "");
    setVal("fDeed",       data?.deed_number || "");
    setVal("fTaxId",      data?.tax_id || "");
    setVal("fArea",       data?.area_sqm ?? "");
    setVal("fMarketRate", data?.market_rate_per_sqm ?? "");
    setVal("fCoverage",   data?.max_coverage_ratio ?? "");
    setVal("fSetback",    data?.setback_meters ?? "");
    setVal("fLat",        data?.latitude ?? "");
    setVal("fLon",        data?.longitude ?? "");
    setVal("fEmail",      data?.contact_email || "");
    setVal("fPhone",      data?.contact_phone || "");
    setVal("fRegDate",    data?.registration_date || "");
    setVal("fNotes",      data?.notes || "");

    hideFormAlert("parcelFormAlert");
    openModal("parcelModal");
}

async function editParcel(id) {
    try {
        const res = await fetch(`/api/parcels/${id}`);
        const data = await res.json();
        if (data.status === "success") openParcelForm(data.parcel);
        else toast("error", "Failed to load parcel data");
    } catch { toast("error", "Network error"); }
}

async function submitParcelForm() {
    const id = document.getElementById("parcelRecordId").value;
    const editing = !!id;

    const surveyNo  = document.getElementById("fSurveyNo").value.trim();
    const ownerName = document.getElementById("fOwnerName").value.trim();
    const landUse   = document.getElementById("fLandUse").value;
    if (!surveyNo || !ownerName || !landUse) {
        showFormAlert("parcelFormAlert", "error", "Survey Number, Owner Name, and Land Use are required.");
        return;
    }

    const payload = {
        parcel_id:           document.getElementById("fParcelId").value.trim() || undefined,
        survey_number:       surveyNo,
        owner_name:          ownerName,
        owner_type:          document.getElementById("fOwnerType").value,
        registered_land_use: landUse,
        zone_name:           document.getElementById("fZone").value.trim(),
        deed_number:         document.getElementById("fDeed").value.trim(),
        tax_id:              document.getElementById("fTaxId").value.trim(),
        area_sqm:            numVal("fArea"),
        market_rate_per_sqm: numVal("fMarketRate"),
        max_coverage_ratio:  numVal("fCoverage"),
        setback_meters:      numVal("fSetback"),
        latitude:            numVal("fLat"),
        longitude:           numVal("fLon"),
        contact_email:       document.getElementById("fEmail").value.trim(),
        contact_phone:       document.getElementById("fPhone").value.trim(),
        registration_date:   document.getElementById("fRegDate").value,
        notes:               document.getElementById("fNotes").value.trim(),
    };

    const btn = document.getElementById("parcelSubmitBtn");
    btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving…';

    try {
        const url    = editing ? `/api/parcels/${id}` : "/api/parcels";
        const method = editing ? "PUT" : "POST";
        const res    = await fetch(url, { method, headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
        const data   = await res.json();

        if (data.status === "success") {
            toast("success", editing ? "Parcel updated successfully!" : "Parcel added successfully!");
            closeModal("parcelModal");
            DS.parcelPage = 1; loadParcels(); loadOverview();
        } else {
            showFormAlert("parcelFormAlert", "error", data.message || "Save failed.");
        }
    } catch { showFormAlert("parcelFormAlert", "error", "Network error. Please retry."); }
    finally { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Parcel'; }
}

// ════════════════════════════════════════
// ENCROACHMENTS
// ════════════════════════════════════════
async function loadEncroachments() {
    const tbody = document.getElementById("encTbody");
    tbody.innerHTML = `<tr><td colspan="10" class="loading-row"><i class="fa-solid fa-spinner fa-spin"></i> Loading…</td></tr>`;

    const search   = document.getElementById("encSearch")?.value || "";
    const severity = document.getElementById("encSeverity")?.value || "";
    const status   = document.getElementById("encStatus")?.value || "";

    const params = new URLSearchParams({
        page: DS.encPage, per_page: 15,
        search, severity, status
    });

    try {
        const res  = await fetch(`/api/db/encroachments?${params}`);
        const data = await res.json();

        if (!data.encroachments?.length) {
            tbody.innerHTML = `<tr><td colspan="10" class="loading-row" style="color:var(--text-muted)"><i class="fa-solid fa-inbox"></i> No encroachment records</td></tr>`;
            document.getElementById("encPagination").innerHTML = "";
            return;
        }

        tbody.innerHTML = data.encroachments.map(r => `
        <tr>
            <td style="color:var(--text-muted);font-family:monospace">${r.id}</td>
            <td style="color:var(--accent-cyan);font-family:monospace;font-size:10px">${esc(r.flag_id)}</td>
            <td style="font-size:11px">${encTypeLabel(r.encroachment_type)}</td>
            <td>${severityBadge(r.severity)}</td>
            <td style="color:var(--text-primary)">${esc(r.violator_name || "—")}</td>
            <td style="font-family:monospace">${(r.encroached_area_sqm||0).toFixed(1)}</td>
            <td style="font-family:monospace">₹${(r.estimated_penalty||0).toLocaleString()}</td>
            <td>${statusBadge(r.status)}</td>
            <td style="color:var(--text-muted);font-size:11px">${fmtDate(r.created_at)}</td>
            <td>
                <div class="action-btns">
                    <button class="btn-icon edit" onclick="editEnc(${r.id})" title="Edit">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button class="btn-icon del" onclick="confirmDelete('enc',${r.id},'Flag ${esc(r.flag_id)}')" title="Delete">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        </tr>`).join("");

        renderPagination("encPagination", data.page, data.pages, (p) => {
            DS.encPage = p; loadEncroachments();
        });
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="10" class="loading-row" style="color:#f87171"><i class="fa-solid fa-circle-exclamation"></i> Failed to load</td></tr>`;
        console.error("[Encroachments]", err);
    }
}

function openEncForm(data = null) {
    const editing = !!data;
    document.getElementById("encModalTitle").innerHTML =
        `<i class="fa-solid fa-triangle-exclamation"></i> ${editing ? "Edit Violation" : "Log Encroachment"}`;
    document.getElementById("encRecordId").value = data?.id || "";

    setVal("eType",          data?.encroachment_type || "BOUNDARY_SPILLOVER");
    setVal("eSeverity",      data?.severity || "MEDIUM");
    setVal("eViolator",      data?.violator_name || "");
    setVal("eViolatorParcel",data?.violator_parcel_id || "");
    setVal("eAffectedParcel",data?.affected_parcel_id || "");
    setVal("eAffectedOwner", data?.affected_owner || "");
    setVal("eAffLandUse",    data?.affected_land_use || "RESIDENTIAL");
    setVal("eArea",          data?.encroached_area_sqm ?? "");
    setVal("ePenalty",       data?.estimated_penalty ?? "");
    setVal("eConf",          data?.confidence ?? "0.9");
    setVal("eStatus",        data?.status || "DETECTED");
    setVal("eLat",           data?.latitude ?? "");
    setVal("eLon",           data?.longitude ?? "");
    setVal("eAction",        data?.recommended_action || "");
    setVal("eNotes",         data?.notes || "");

    hideFormAlert("encFormAlert");
    openModal("encModal");
}

async function editEnc(id) {
    try {
        const res = await fetch(`/api/db/encroachments/${id}`);
        const data = await res.json();
        if (data.status === "success") openEncForm(data.encroachment);
        else toast("error", "Failed to load record");
    } catch { toast("error", "Network error"); }
}

async function submitEncForm() {
    const id = document.getElementById("encRecordId").value;
    const editing = !!id;

    const encType       = document.getElementById("eType").value;
    const severity      = document.getElementById("eSeverity").value;
    const affectedParcel= document.getElementById("eAffectedParcel").value.trim();

    if (!encType || !severity || !affectedParcel) {
        showFormAlert("encFormAlert", "error", "Encroachment Type, Severity, and Affected Parcel ID are required.");
        return;
    }

    const payload = {
        encroachment_type:   encType,
        severity,
        violator_name:       document.getElementById("eViolator").value.trim(),
        violator_parcel_id:  document.getElementById("eViolatorParcel").value.trim(),
        affected_parcel_id:  affectedParcel,
        affected_owner:      document.getElementById("eAffectedOwner").value.trim(),
        affected_land_use:   document.getElementById("eAffLandUse").value,
        encroached_area_sqm: numVal("eArea"),
        estimated_penalty:   numVal("ePenalty"),
        confidence:          numVal("eConf") ?? 0.9,
        status:              document.getElementById("eStatus").value,
        latitude:            numVal("eLat"),
        longitude:           numVal("eLon"),
        recommended_action:  document.getElementById("eAction").value.trim(),
        notes:               document.getElementById("eNotes").value.trim(),
    };

    const btn = document.getElementById("encSubmitBtn");
    btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving…';

    try {
        const url    = editing ? `/api/db/encroachments/${id}` : "/api/db/encroachments";
        const method = editing ? "PUT" : "POST";
        const res    = await fetch(url, { method, headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
        const data   = await res.json();

        if (data.status === "success") {
            toast("success", editing ? "Record updated!" : "Violation logged!");
            closeModal("encModal");
            DS.encPage = 1; loadEncroachments(); loadOverview();
        } else {
            showFormAlert("encFormAlert", "error", data.message || "Save failed.");
        }
    } catch { showFormAlert("encFormAlert", "error", "Network error. Please retry."); }
    finally { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Record'; }
}

// ════════════════════════════════════════
// USERS
// ════════════════════════════════════════
async function checkAdminRole() {
    try {
        const res = await fetch("/api/me");
        if (!res.ok) return;
        const data = await res.json();
        const item = document.getElementById("usersNavItem");
        if (data.user?.role !== "admin" && item) {
            item.style.display = "none";
        }
    } catch {}
}

async function loadUsers() {
    const tbody = document.getElementById("userTbody");
    tbody.innerHTML = `<tr><td colspan="8" class="loading-row"><i class="fa-solid fa-spinner fa-spin"></i> Loading…</td></tr>`;
    try {
        const res  = await fetch("/api/users");
        const data = await res.json();
        if (res.status === 403) {
            tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:#f87171"><i class="fa-solid fa-lock"></i> Admin access required</td></tr>`;
            return;
        }
        if (!data.users?.length) {
            tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:var(--text-muted)"><i class="fa-solid fa-inbox"></i> No users found</td></tr>`;
            return;
        }
        tbody.innerHTML = data.users.map(u => `
        <tr>
            <td style="color:var(--text-muted);font-family:monospace">${u.id}</td>
            <td style="color:var(--text-primary);font-weight:600">${esc(u.username)}</td>
            <td>${esc(u.full_name || "—")}</td>
            <td style="color:var(--text-muted);font-size:12px">${esc(u.email)}</td>
            <td>${roleBadge(u.role)}</td>
            <td>${u.is_active ? '<span class="badge badge-green">Active</span>' : '<span class="badge badge-gray">Inactive</span>'}</td>
            <td style="color:var(--text-muted);font-size:11px">${u.last_login ? fmtDate(u.last_login) : "Never"}</td>
            <td>
                <div class="action-btns">
                    <button class="btn-icon edit" onclick="editUser(${u.id},'${esc(u.username)}','${esc(u.email)}','${esc(u.full_name||'')}','${u.role}',${u.is_active})" title="Edit">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button class="btn-icon del" onclick="confirmDelete('user',${u.id},'User: ${esc(u.username)}')" title="Delete">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </td>
        </tr>`).join("");
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:#f87171"><i class="fa-solid fa-circle-exclamation"></i> Failed to load</td></tr>`;
        console.error("[Users]", err);
    }
}

function openUserForm(data = null) {
    const editing = !!data;
    document.getElementById("userModalTitle").innerHTML =
        `<i class="fa-solid fa-user-${editing ? 'pen' : 'plus'}"></i> ${editing ? "Edit User" : "Add User"}`;
    document.getElementById("userRecordId").value = data?.id || "";

    setVal("uUsername", data?.username || "");
    setVal("uEmail",    data?.email || "");
    setVal("uFullName", data?.full_name || "");
    setVal("uRole",     data?.role || "officer");
    setVal("uPassword", "");
    setVal("uActive",   data?.is_active === false ? "false" : "true");

    // Password required only when creating
    document.getElementById("pwdRequired").textContent = editing ? "(optional)" : "*";
    document.getElementById("uUsername").readOnly = editing;

    hideFormAlert("userFormAlert");
    openModal("userModal");
}

function editUser(id, username, email, fullName, role, isActive) {
    openUserForm({ id, username, email, full_name: fullName, role, is_active: isActive });
}

async function submitUserForm() {
    const id = document.getElementById("userRecordId").value;
    const editing = !!id;

    const username = document.getElementById("uUsername").value.trim();
    const email    = document.getElementById("uEmail").value.trim();
    const password = document.getElementById("uPassword").value;

    if (!editing && (!username || !email || !password)) {
        showFormAlert("userFormAlert", "error", "Username, email, and password are required.");
        return;
    }
    if (password && password.length < 8) {
        showFormAlert("userFormAlert", "error", "Password must be at least 8 characters.");
        return;
    }

    const payload = {
        username, email,
        full_name: document.getElementById("uFullName").value.trim(),
        role:      document.getElementById("uRole").value,
        is_active: document.getElementById("uActive").value === "true",
    };
    if (password) payload.password = password;

    const btn = document.getElementById("userSubmitBtn");
    btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving…';

    try {
        const url    = editing ? `/api/users/${id}` : "/api/users";
        const method = editing ? "PUT" : "POST";
        const res    = await fetch(url, { method, headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
        const data   = await res.json();

        if (data.status === "success") {
            toast("success", editing ? "User updated!" : "User created!");
            closeModal("userModal");
            loadUsers(); loadOverview();
        } else {
            showFormAlert("userFormAlert", "error", data.message || "Save failed.");
        }
    } catch { showFormAlert("userFormAlert", "error", "Network error. Please retry."); }
    finally { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save User'; }
}

// ════════════════════════════════════════
// DELETE
// ════════════════════════════════════════
function confirmDelete(type, id, label) {
    const urls = {
        parcel: `/api/parcels/${id}`,
        enc:    `/api/db/encroachments/${id}`,
        user:   `/api/users/${id}`,
    };
    DS.deletePending = {
        url: urls[type],
        onSuccess: () => {
            if (type === "parcel") { DS.parcelPage = 1; loadParcels(); }
            else if (type === "enc") { DS.encPage = 1; loadEncroachments(); }
            else if (type === "user") loadUsers();
            loadOverview();
        }
    };
    document.getElementById("deleteMessage").textContent =
        `You are about to permanently delete: "${label}". This cannot be undone.`;
    openModal("deleteModal");
}

async function executeDelete() {
    if (!DS.deletePending) return;
    const { url, onSuccess } = DS.deletePending;

    const btn = document.getElementById("deleteConfirmBtn");
    btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Deleting…';

    try {
        const res  = await fetch(url, { method: "DELETE" });
        const data = await res.json();
        if (data.status === "success") {
            toast("success", "Record deleted successfully.");
            closeModal("deleteModal");
            onSuccess();
        } else {
            toast("error", data.message || "Deletion failed.");
        }
    } catch { toast("error", "Network error during deletion."); }
    finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-trash-can"></i> Delete Permanently';
        DS.deletePending = null;
    }
}

// ════════════════════════════════════════
// PAGINATION
// ════════════════════════════════════════
function renderPagination(containerId, current, total, onPage) {
    const el = document.getElementById(containerId);
    if (!el || total <= 1) { if (el) el.innerHTML = ""; return; }

    let html = `<button class="page-btn" ${current<=1?"disabled":""} onclick="(${onPage.toString()})(${current-1})">
        <i class="fa-solid fa-chevron-left"></i></button>`;

    const range = pagRange(current, total);
    for (const p of range) {
        if (p === "…") {
            html += `<span class="page-info">…</span>`;
        } else {
            html += `<button class="page-btn ${p===current?"active":""}" onclick="(${onPage.toString()})(${p})">${p}</button>`;
        }
    }

    html += `<button class="page-btn" ${current>=total?"disabled":""} onclick="(${onPage.toString()})(${current+1})">
        <i class="fa-solid fa-chevron-right"></i></button>
        <span class="page-info">Page ${current} of ${total}</span>`;

    el.innerHTML = html;
}

function pagRange(cur, total) {
    if (total <= 7) return Array.from({length: total}, (_,i) => i+1);
    const pages = [];
    pages.push(1);
    if (cur > 3) pages.push("…");
    for (let p = Math.max(2, cur-1); p <= Math.min(total-1, cur+1); p++) pages.push(p);
    if (cur < total-2) pages.push("…");
    pages.push(total);
    return pages;
}

// ════════════════════════════════════════
// MODALS
// ════════════════════════════════════════
function openModal(id)  { document.getElementById(id)?.classList.add("open"); }
function closeModal(id) { document.getElementById(id)?.classList.remove("open"); }

// Close on outside click
document.addEventListener("click", e => {
    if (e.target.classList.contains("modal-overlay")) {
        e.target.classList.remove("open");
    }
});

// ════════════════════════════════════════
// TOASTS
// ════════════════════════════════════════
function toast(type, msg) {
    const icons = { success: "fa-check-circle", error: "fa-circle-exclamation", info: "fa-circle-info" };
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.innerHTML = `<i class="fa-solid ${icons[type]||'fa-bell'}"></i><span>${esc(msg)}</span>`;
    document.getElementById("toastContainer")?.appendChild(el);
    setTimeout(() => el.style.opacity = "0", 3500);
    setTimeout(() => el.remove(), 3900);
}

// ════════════════════════════════════════
// HELPERS
// ════════════════════════════════════════
function esc(s) {
    if (s == null) return "";
    return String(s)
        .replace(/&/g,"&amp;").replace(/</g,"&lt;")
        .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.value = val ?? "";
}

function numVal(id) {
    const v = document.getElementById(id)?.value;
    return v === "" || v == null ? null : Number(v);
}

function fmtDate(iso) {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        return d.toLocaleDateString("en-IN", {day:"2-digit",month:"short",year:"numeric"}) +
               " " + d.toLocaleTimeString("en-IN", {hour:"2-digit",minute:"2-digit"});
    } catch { return iso; }
}

function showFormAlert(id, type, msg) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `form-alert ${type}`;
    el.innerHTML = `<i class="fa-solid fa-${type==="error"?"circle-exclamation":"check-circle"}"></i> ${esc(msg)}`;
    el.style.display = "flex";
}
function hideFormAlert(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
}

// Badges
function severityBadge(s) {
    const map = {CRITICAL:"badge-critical",HIGH:"badge-high",MEDIUM:"badge-medium",LOW:"badge-low"};
    return `<span class="badge ${map[s]||'badge-gray'}">${esc(s)}</span>`;
}

function statusBadge(s) {
    const map = {
        DETECTED:"badge-medium", UNDER_REVIEW:"badge-blue",
        NOTICE_ISSUED:"badge-amber", RESOLVED:"badge-green", DISMISSED:"badge-gray"
    };
    return `<span class="badge ${map[s]||'badge-gray'}">${esc((s||"").replace(/_/g," "))}</span>`;
}

function landUseBadge(s) {
    const short = (s||"").replace(/_/g," ");
    return `<span class="badge badge-blue">${esc(short)}</span>`;
}

function roleBadge(r) {
    return r === "admin"
        ? `<span class="badge badge-amber">Admin</span>`
        : `<span class="badge badge-blue">Officer</span>`;
}

function encTypeLabel(t) {
    const map = {
        BOUNDARY_SPILLOVER:      "Boundary Spillover",
        GOVERNMENT_LAND_TRESPASS:"Gov. Land Trespass",
        WATERBODY_BUFFER_VIOLATION:"Waterbody Buffer",
        UNAUTHORIZED_LAND_USE:   "Unauthorized Use",
        SETBACK_EXCESS:          "Setback Excess",
    };
    return esc(map[t] || t);
}

// Debounce utility
function debounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}


// ═══════════════════════════════════════════════
// AUDIT LOGS  (admin only — appended to dashboard.js)
// ═══════════════════════════════════════════════

async function loadAuditLogs() {
    const tbody = document.getElementById("auditTbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="8" class="loading-row"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</td></tr>`;

    const params = new URLSearchParams({
        page:     DS.auditPage,
        per_page: 30,
        search:   document.getElementById("auditSearch")?.value  || "",
        action:   document.getElementById("auditAction")?.value  || "",
        resource: document.getElementById("auditResource")?.value || "",
    });

    try {
        const res  = await fetch("/api/audit-logs?" + params);
        const data = await res.json();

        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:#f87171"><i class="fa-solid fa-lock"></i> ${esc(data.message || "Access denied")}</td></tr>`;
            return;
        }

        if (!data.logs || !data.logs.length) {
            tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:var(--text-muted)"><i class="fa-solid fa-inbox"></i> No audit entries</td></tr>`;
            document.getElementById("auditPagination").innerHTML = "";
            return;
        }

        const actionColors = {CREATED:"badge-green",UPDATED:"badge-blue",DELETED:"badge-critical",LOGIN:"badge-gray",LOGOUT:"badge-gray",SIGNUP:"badge-cyan",SCAN:"badge-amber",RESET:"badge-medium"};
        tbody.innerHTML = data.logs.map(function(log) {
            var cls = actionColors[log.action] || "badge-gray";
            return "<tr>" +
                "<td style='color:var(--text-muted);font-family:monospace;font-size:11px'>" + log.id + "</td>" +
                "<td style='font-size:11px;color:var(--text-muted);white-space:nowrap'>" + fmtDate(log.created_at) + "</td>" +
                "<td style='color:var(--text-primary);font-weight:500'>" + esc(log.actor_name) + "</td>" +
                "<td><span class='badge " + cls + "'>" + esc(log.action) + "</span></td>" +
                "<td style='font-size:11px'>" + esc(log.resource) + "</td>" +
                "<td style='font-family:monospace;font-size:11px;color:var(--accent-cyan)'>" + esc(log.resource_id || "—") + "</td>" +
                "<td style='font-size:11px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' title='" + esc(log.detail) + "'>" + esc(log.detail) + "</td>" +
                "<td style='font-size:10px;color:var(--text-muted)'>" + esc(log.ip_address || "—") + "</td>" +
            "</tr>";
        }).join("");

        renderPagination("auditPagination", data.page, data.pages, function(p) {
            DS.auditPage = p;
            loadAuditLogs();
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading-row" style="color:#f87171"><i class="fa-solid fa-circle-exclamation"></i> Failed to load audit logs</td></tr>`;
    }
}
