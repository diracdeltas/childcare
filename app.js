const PAGE_SIZE = 50;

let allFacilities = [];
let filtered = [];
let sortKey = "total_violations";
let currentPage = 1;
let filterViolations = true;

const _parser = new DOMParser();
const toTitle = s => (s || "").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

function setHTML(el, html) {
  const doc = _parser.parseFromString(html, "text/html");
  el.innerHTML = doc.body.innerHTML;
}

function showLoading(el, text) {
  const div = document.createElement("div");
  div.className = "report-loading";
  div.textContent = text;
  el.innerHTML = "";
  el.appendChild(div);
}

function showError(el, text) {
  const p = document.createElement("p");
  p.className = "report-error";
  p.textContent = text;
  el.innerHTML = "";
  el.appendChild(p);
}

// ── DATA LOADING ──────────────────────────────────────

async function loadData() {
  const res = await fetch("data/facilities.json");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function populateFilters(facilities) {
  function fill(selectId, values) {
    const el = document.getElementById(selectId);
    values.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v; opt.textContent = v;
      el.appendChild(opt);
    });
  }
  fill("county-filter", [...new Set(facilities.map(f => f.county).filter(Boolean).map(toTitle))].sort());
  fill("type-filter",   [...new Set(facilities.map(f => f.type).filter(Boolean))].sort());
}

function updateStats(facilities) {
  let totalA = 0, totalB = 0, totalC = 0, totalSub = 0;
  for (const f of facilities) {
    totalA   += f.type_a_violations       || 0;
    totalB   += f.type_b_violations       || 0;
    totalC   += f.total_complaints        || 0;
    totalSub += f.substantiated_complaints || 0;
  }
  document.getElementById("stat-total").textContent = facilities.length.toLocaleString();
  document.getElementById("stat-type-a").textContent = totalA.toLocaleString();
  document.getElementById("stat-type-b").textContent = totalB.toLocaleString();
  document.getElementById("stat-complaints").textContent = totalC.toLocaleString();
  document.getElementById("stat-substantiated").textContent = totalSub.toLocaleString();
}

// ── FILTER + SORT ─────────────────────────────────────

function applyFilters() {
  const query = document.getElementById("search-input").value.toLowerCase().trim();
  const county = document.getElementById("county-filter").value;
  const type = document.getElementById("type-filter").value;

  filtered = allFacilities.filter(f => {
    if (filterViolations && (f.total_violations || 0) === 0 && (f.total_complaints || 0) === 0) return false;
    if (county && toTitle(f.county || "") !== county) return false;
    if (type && f.type !== type) return false;
    if (query) {
      const haystack = [f.name, f.city, f.licensee, f.address, f.county].join(" ").toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  });

  applySort();
}

function applySort() {
  filtered.sort((a, b) => {
    if (sortKey === "name_asc") {
      return (a.name || "").localeCompare(b.name || "");
    }
    if (sortKey === "most_recent_activity") {
      const da = a.most_recent_activity || "0000-00-00";
      const db = b.most_recent_activity || "0000-00-00";
      return db.localeCompare(da);
    }
    return (b[sortKey] || 0) - (a[sortKey] || 0);
  });

  currentPage = 1;
  render();
}

// ── RENDER ────────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(m,10)-1]} ${parseInt(d,10)}, ${y}`;
}

function statusDot(status) {
  const s = (status || "").toLowerCase();
  if (s === "active") return '<span class="status-dot status-active"></span>';
  if (s === "closed" || s === "inactive") return '<span class="status-dot status-closed"></span>';
  return '<span class="status-dot status-other"></span>';
}

function findingClass(finding) {
  if (!finding) return "finding-open";
  const f = finding.toLowerCase();
  if (f === "partially substantiated") return "finding-inconclusive";
  if (f.includes("substantiat") && !f.includes("unsub")) return "finding-substantiated";
  if (f.includes("unsubstantiat")) return "finding-unsubstantiated";
  if (f.includes("inconclusive")) return "finding-inconclusive";
  return "finding-other";
}

function buildComplaintHTML(complaints, facilityNumber) {
  if (!complaints || complaints.length === 0) {
    return '<p class="no-complaints">No complaints on record.</p>';
  }
  const sorted = [...complaints].sort((a, b) =>
    (b.submitted_date || "0000-00-00").localeCompare(a.submitted_date || "0000-00-00")
  );
  return `<ul class="complaints-list">${sorted.map((c, idx) => {
    const citsA = c.type_a_citations || 0;
    const citsB = c.type_b_citations || 0;
    const hasCitations = citsA > 0 || citsB > 0;
    const citBadges = [
      citsA ? `<span class="badge badge-a badge-sm">${citsA} Type A</span>` : "",
      citsB ? `<span class="badge badge-b badge-sm">${citsB} Type B</span>` : "",
    ].filter(Boolean).join(" ");
    const rid = `report-${facilityNumber}-${idx}`;
    return `
    <li class="complaint-item">
      <div class="complaint-header">
        <div>
          <span class="complaint-label">Complaint</span>
          <span class="complaint-cn">${c.control_number || "N/A"}</span>
        </div>
        <span class="finding-badge ${findingClass(c.finding)}" id="finding-${rid}">${c.finding || "Pending"}</span>
      </div>
      <div class="complaint-dates">
        Submitted: <span>${fmtDate(c.submitted_date)}</span>
        · Closed: <span>${fmtDate(c.approved_date)}</span>
        ${c.visit_dates && c.visit_dates.length ? (() => { const ud = [...new Set(c.visit_dates)]; return `· ${ud.length === 1 ? "Visit" : "Visits"}: <span>${ud.map(fmtDate).join(", ")}</span>`; })() : ""}
      </div>
      ${hasCitations ? `<div class="complaint-citations">Citations issued: ${citBadges}</div>` : ""}
      <button class="report-toggle" id="btn-${rid}"
        data-rid="${rid}" data-facility="${esc(facilityNumber)}" data-cn="${esc(c.control_number || "")}">
        <span class="arrow">▶</span> View report details
      </button>
      <div class="report-body" id="${rid}"></div>
    </li>`;
  }).join("")}</ul>`;
}

function buildInspectionsHTML(inspections, facilityNumber) {
  if (!inspections || inspections.length === 0) return "";
  const totalA = inspections.reduce((s, i) => s + (i.type_a_citations || 0), 0);
  const totalB = inspections.reduce((s, i) => s + (i.type_b_citations || 0), 0);
  if (!totalA && !totalB) return "";
  return `<div class="inspection-citations" id="insp-${esc(facilityNumber)}" data-facility="${esc(facilityNumber)}"><div class="report-loading">Loading inspection citations…</div></div>`;
}

async function loadInspectionCitations(facilityNumber) {
  const container = document.getElementById(`insp-${facilityNumber}`);
  if (!container || container.dataset.loaded) return;
  container.dataset.loaded = "1";
  try {
    const reports = await getReportList(facilityNumber);
    const inspReports = reports.map((r, i) => ({ ...r, _idx: i })).filter(r => !r.CONTROLNUMBER);
    if (!inspReports.length) { container.innerHTML = ""; return; }
    const results = await Promise.all(inspReports.map(m => getReportDetail(facilityNumber, m._idx)));
    const allDefs = [];
    const links = [];
    for (let i = 0; i < inspReports.length; i++) {
      const p = results[i];
      if (p.deficiencies && p.deficiencies.length) {
        allDefs.push(...p.deficiencies);
        links.push(`${CCLD_API}/FacilityReports?facNum=${facilityNumber}&inx=${inspReports[i]._idx}`);
      }
    }
    if (!allDefs.length) { container.innerHTML = ""; return; }
    setHTML(container, renderReport({ allegations: [], findings: [], deficiencies: allDefs }, links, { citationsLabel: "Other Citations" }));
  } catch (e) {
    container.innerHTML = "";
  }
}

function buildCard(f) {
  const hasA = (f.type_a_violations || 0) > 0;
  const hasB = (f.type_b_violations || 0) > 0;
  const hasC = (f.total_complaints || 0) > 0;
  const cardClass = hasA ? "has-type-a" : hasB ? "has-type-b" : hasC ? "has-complaints" : "";

  const cLabel = f.total_complaints === 1 ? "Complaint" : "Complaints";
  const badgesHTML = hasA || hasB || hasC ? `
    ${hasA ? `<span class="badge badge-a">⚠ ${f.type_a_violations} Type A</span>` : ""}
    ${hasB ? `<span class="badge badge-b">▲ ${f.type_b_violations} Type B</span>` : ""}
    ${hasC ? `<span class="badge badge-c">◉ ${f.total_complaints} ${cLabel}</span>` : ""}
  ` : `<span class="badge badge-zero">✓ No Violations</span>`;

  const recentLabel = f.most_recent_activity
    ? `<div class="recent-date">Most recent<strong>${fmtDate(f.most_recent_activity)}</strong></div>`
    : `<div class="recent-date">Last visit<strong>${fmtDate(f.last_visit)}</strong></div>`;

  const capacity = f.capacity ? `· Capacity: ${f.capacity}` : "";
  const phone = f.phone ? `· ${f.phone}` : "";

  return `
  <div class="facility-card ${cardClass}" data-id="${f.number}">
    <div class="card-main">
      <div class="card-left">
        <div class="facility-name">${esc(f.name || "Unknown Facility")}</div>
        <div class="facility-meta">
          <span>${statusDot(f.status)}${esc(f.city || "")}${f.county ? ", " + esc(f.county) : ""}</span>
          <span class="type-badge">${esc(f.type || "")}</span>
          ${f.licensee ? `<span>Licensee: ${esc(f.licensee)}</span>` : ""}
          ${capacity ? `<span>${capacity}</span>` : ""}
          ${phone ? `<span>${phone}</span>` : ""}
        </div>
      </div>
      <div class="card-right">
        <div class="badges">${badgesHTML}</div>
        ${recentLabel}
        <span class="expand-icon">▾</span>
      </div>
    </div>
    <div class="card-detail">
      <div class="detail-inner">
        <div class="detail-section">
          <h3>Facility Information</h3>
          <div class="info-grid">
            <span class="info-key">License #</span><span class="info-val mono">${esc(f.number || "—")}</span>
            <span class="info-key">Address</span><span class="info-val">${esc([f.address, f.city, "CA", f.zip].filter(Boolean).join(", ") || "—")}</span>
            <span class="info-key">Status</span><span class="info-val">${statusDot(f.status)}${esc(f.status || "—")}</span>
            <span class="info-key">License Date</span><span class="info-val mono">${fmtDate(f.license_effective_date)}</span>
            <span class="info-key">Last Visit</span><span class="info-val mono">${fmtDate(f.last_visit)}</span>
            <span class="info-key">District Office</span><span class="info-val">${esc(f.district_office || "—")}</span>
          </div>
          <a class="ccld-link" href="https://www.ccld.dss.ca.gov/carefacilitysearch/#/FacDetail/${esc(f.number)}" target="_blank" rel="noopener">
            View on CCLD ↗
          </a>
        </div>
        <div class="detail-section">
          <h3>Complaints (${f.total_complaints || 0})</h3>
          ${buildComplaintHTML(f.complaints, f.number)}
          ${buildInspectionsHTML(f.inspections, f.number)}
        </div>
      </div>
    </div>
  </div>`;
}

function render() {
  const container = document.getElementById("facility-list");
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageItems = filtered.slice(start, start + PAGE_SIZE);

  document.getElementById("results-count").textContent =
    `${filtered.length.toLocaleString()} result${filtered.length !== 1 ? "s" : ""}`;

  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const ep = document.createElement("p");
    ep.textContent = "No facilities match your filters.";
    empty.appendChild(ep);
    container.innerHTML = "";
    container.appendChild(empty);
    return;
  }

  const cardsHTML = pageItems.map(buildCard).join("");
  const paginationHTML = buildPagination();

  setHTML(container, cardsHTML + paginationHTML);
}

function buildPagination() {
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  if (totalPages <= 1) return "";

  let pages = [];
  pages.push(`<button class="page-btn" data-page="${currentPage-1}" ${currentPage===1?"disabled":""}>←</button>`);

  const range = pageRange(currentPage, totalPages);
  let prev = null;
  for (const p of range) {
    if (prev !== null && p - prev > 1) pages.push(`<span class="page-ellipsis">…</span>`);
    pages.push(`<button class="page-btn ${p===currentPage?"active":""}" data-page="${p}">${p}</button>`);
    prev = p;
  }

  pages.push(`<button class="page-btn" data-page="${currentPage+1}" ${currentPage===totalPages?"disabled":""}>→</button>`);
  return `<div class="pagination">${pages.join("")}</div>`;
}

function pageRange(cur, total) {
  const delta = 2;
  const range = new Set([1, total]);
  for (let i = Math.max(2, cur-delta); i <= Math.min(total-1, cur+delta); i++) range.add(i);
  return [...range].sort((a,b)=>a-b);
}

function goPage(p) {
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  render();
  document.querySelector(".controls-wrap").scrollIntoView({ behavior: "smooth", block: "start" });
}

function deriveOverallFinding(allegations) {
  const findings = allegations.map(a => (a.finding || "").toLowerCase()).filter(Boolean);
  if (!findings.length) return null;
  const hasSub   = findings.some(f => f === "substantiated");
  const hasUnsub = findings.some(f => f === "unsubstantiated");
  if (hasSub && hasUnsub) return "Partially Substantiated";
  if (hasSub)   return "Substantiated";
  if (hasUnsub) return "Unsubstantiated";
  if (findings.some(f => f === "inconclusive")) return "Inconclusive";
  return null;
}

async function prefetchFinding(rid, facilityNumber, controlNumber) {
  const badgeEl = document.getElementById(`finding-${rid}`);
  if (!badgeEl) return;
  try {
    const reports = await getReportList(facilityNumber);
    const matches = reports
      .map((r, i) => ({ ...r, _idx: i }))
      .filter(r => !controlNumber || r.CONTROLNUMBER === controlNumber);
    const parsedReports = await Promise.all(matches.map(m => getReportDetail(facilityNumber, m._idx)));
    const allAllegations = [];
    let fallback = null;
    for (const p of parsedReports) {
      allAllegations.push(...(p.allegations || []));
      if (!fallback && p.overall_finding) fallback = p.overall_finding;
    }
    const overall = deriveOverallFinding(allAllegations) || fallback;
    if (overall) {
      badgeEl.textContent = overall;
      badgeEl.className = `finding-badge ${findingClass(overall)}`;
    }
  } catch (e) { /* silent — badge keeps derived value */ }
}

function toggleCard(el) {
  const card = el.closest(".facility-card");
  const wasExpanded = card.classList.contains("expanded");
  card.classList.toggle("expanded");
  // On first expand, clear derived findings and fetch authoritative values from reports
  if (!wasExpanded && !card.dataset.prefetched) {
    card.dataset.prefetched = "1";
    card.querySelectorAll(".report-toggle[data-rid]").forEach(btn => {
      const badgeEl = document.getElementById(`finding-${btn.dataset.rid}`);
      if (badgeEl) {
        badgeEl.textContent = "…";
        badgeEl.className = "finding-badge finding-open";
      }
      prefetchFinding(btn.dataset.rid, btn.dataset.facility, btn.dataset.cn);
    });
    const inspEl = card.querySelector(".inspection-citations[data-facility]");
    if (inspEl) loadInspectionCitations(inspEl.dataset.facility);
  }
}

function esc(str) {
  return String(str || "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

// ── INIT ──────────────────────────────────────────────

// ── REPORT FETCHING ───────────────────────────────────

const CCLD_API = "https://www.ccld.dss.ca.gov/transparencyapi/api";
const CCLD_H = {
  "DSS-Transparency-Config": JSON.stringify({
    Version: "11.18.0R", deviceReady: 1,
    GUID: "a1b2c3d4-e5f6-7890-abcd-ef1234567890", DocProtocol: "https://"
  })
};

const _reportListCache = {};
const _reportDetailCache = {};

async function getReportList(facilityNumber) {
  if (_reportListCache[facilityNumber]) return _reportListCache[facilityNumber];
  const r = await fetch(`${CCLD_API}/FacilityReports/${facilityNumber}`, { headers: CCLD_H });
  const data = await r.json();
  _reportListCache[facilityNumber] = data.REPORTARRAY || [];
  return _reportListCache[facilityNumber];
}

async function getReportDetail(facilityNumber, idx) {
  const key = `${facilityNumber}:${idx}`;
  if (_reportDetailCache[key]) return _reportDetailCache[key];
  const r = await fetch(`${CCLD_API}/FacilityReports?facNum=${facilityNumber}&inx=${idx}`, { headers: CCLD_H });
  const html = await r.text();
  const parsed = parseReport(html);
  _reportDetailCache[key] = parsed;
  return parsed;
}

function parseReport(html) {
  const raw = html.replace(/<[^>]+>/g, " ").replace(/&lt;[^&]+&gt;/g, "").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
  const lines = raw.split("\n")
    .map(l => l.replace(/[ \t]{2,}/g, " ").trim().replace(/^\d+\s+/, ""))
    .filter(Boolean);

  const allegations = [];
  const findings = [];
  const deficiencies = [];
  // Each report section ends at "SUPERVISORS NAME". Track which section we're in
  // so we can assign the section-level finding (Substantiated/Unsubstantiated/Inconclusive)
  // to all its allegations in post-processing.
  const sectionFindings = {};
  let sectionNum = 0;

  let mode = null;
  let curDef = null;
  let defDescDone = false;

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    const lu = l.toUpperCase();

    // Section boundary — each section ends at SUPERVISORS NAME
    if (l.startsWith("SUPERVISORS NAME")) { sectionNum++; mode = null; continue; }
    if (l.startsWith("LIC9099") || l.startsWith("Failure to correct")) { mode = null; }

    if (l === "ALLEGATION(S):") { mode = "alleg"; continue; }
    if (l === "INVESTIGATION FINDINGS:") { mode = "findings"; continue; }
    if (l.startsWith("DEFICIENCY INFORMATION FOR THIS PAGE")) { mode = "deficiency"; continue; }

    // Detect finding word at the start of a line. Check UNSUBSTANTIATED first
    // since it contains SUBSTANTIATED as a substring. The word may be followed
    // by form-field text on the same HTML line (e.g. "Unsubstantiated Estimated
    // Days of Completion:") so we use startsWith, not exact match.
    const tu = l.trim().toUpperCase();
    let findingWord = null;
    if (tu.startsWith("UNSUBSTANTIATED")) findingWord = "Unsubstantiated";
    else if (tu.startsWith("SUBSTANTIATED")) findingWord = "Substantiated";
    else if (tu.startsWith("INCONCLUSIVE"))  findingWord = "Inconclusive";
    const isFinding = !!findingWord;
    if (isFinding && mode !== "alleg") {
      sectionFindings[sectionNum] = findingWord;
    }

    if (mode === "alleg") {
      if (!isFinding && !/^\d+$/.test(l) && l.length > 4) {
        allegations.push({ text: l, section: sectionNum, finding: null });
      }
    }

    if (mode === "findings") {
      if (l.length > 40 && !/^\d+$/.test(l)) findings.push(l);
      if (findings.length >= 3) mode = null;
    }

    if (mode === "deficiency") {
      // Match bare "Type A"/"Type B" or inline "Type B Section Cited CCR 101238(g)"
      if (l === "Type A" || l === "Type B" ||
          l.startsWith("Type A Section Cited") || l.startsWith("Type B Section Cited")) {
        if (curDef) deficiencies.push(curDef);
        const typeStr = l.startsWith("Type A") ? "Type A" : "Type B";
        curDef = { type: typeStr, section: "", poc_due: "", description: "", finding_text: "" };
        defDescDone = false;
        const sMatch = l.match(/CCR\s+(\S+)/);
        if (sMatch) curDef.section = "CCR § " + sMatch[1];
        continue;
      }
      if (!curDef) continue;
      if (!curDef.poc_due) {
        if (/^\d{2}\/\d{2}\/\d{4}$/.test(l)) { curDef.poc_due = l; continue; }
        const pocM = l.match(/^POC Due Date:\s*(\d{2}\/\d{2}\/\d{4})/i);
        if (pocM) { curDef.poc_due = pocM[1]; continue; }
      }
      if (!curDef.section && /^\d{5,6}(\(\w\))?/.test(l)) {
        const m = l.match(/^(\d+\(\w\)|\d+)/);
        if (m) { curDef.section = "CCR § " + m[0]; }
      }
      if (!defDescDone && l.length > 40 && (l.includes("shall") || l.includes("This requirement") || l.includes("must"))) {
        curDef.description = l.replace(/^\d+\(\w\)\s*/, "").replace(/^\(\w+\)\s*/, "").replace(/^\d+\s*/, "");
        defDescDone = true; continue;
      }
      if (curDef.description && !curDef.finding_text && l.length > 30 &&
          (l.startsWith("At ") || l.startsWith("Based on") || l.startsWith("LPA confirmed") ||
           l.startsWith("During") || l.startsWith("On "))) {
        curDef.finding_text = l;
      }
    }
  }
  if (curDef) deficiencies.push(curDef);

  // Assign each allegation the finding from its section
  for (const a of allegations) a.finding = sectionFindings[a.section] || null;

  let overall_finding = deriveOverallFinding(allegations);
  // Fallback: scan first ~25 lines if allegation-based derivation gave nothing
  if (!overall_finding) {
    for (const line of lines.slice(0, 25)) {
      const tu2 = line.trim().toUpperCase();
      if (tu2.startsWith("UNSUBSTANTIATED")) { overall_finding = "Unsubstantiated"; break; }
      if (tu2.startsWith("SUBSTANTIATED"))   { overall_finding = "Substantiated";   break; }
      if (tu2.startsWith("INCONCLUSIVE"))    { overall_finding = "Inconclusive";     break; }
    }
  }

  return { allegations, findings, deficiencies, overall_finding };
}

function renderReport(parsed, reportLinks, opts = {}) {
  if (!parsed) return `<p class="report-error">Could not load report.</p>`;
  const parts = [];

  if (parsed.allegations.length) {
    parts.push(`
      <div class="report-section">
        <div class="report-section-label">Allegation(s)</div>
        <ul class="allegation-list">
          ${parsed.allegations.map(a => `<li>${esc(a.text)}${a.finding
            ? ` <span class="finding-badge ${findingClass(a.finding)} badge-finding-inline">${esc(a.finding)}</span>`
            : ""}</li>`).join("")}
        </ul>
      </div>`);
  }

  if (parsed.deficiencies.length) {
    parts.push(`
      <div class="report-section">
        <div class="report-section-label">${opts.citationsLabel || "Citations"}</div>
        <ul class="deficiency-list">
          ${parsed.deficiencies.map(d => `
            <li class="deficiency-item">
              <div class="deficiency-header">
                <span class="badge ${d.type === "Type A" ? "badge-a" : "badge-b"} badge-sm">${esc(d.type)}</span>
                ${d.section ? `<span class="deficiency-section">${esc(d.section)}</span>` : ""}
                ${d.poc_due ? `<span class="deficiency-section">POC due ${esc(d.poc_due)}</span>` : ""}
              </div>
              ${d.description ? `<div class="deficiency-desc">${esc(d.description)}</div>` : ""}
              ${d.finding_text ? `<div class="deficiency-finding">${esc(d.finding_text)}</div>` : ""}
            </li>`).join("")}
        </ul>
      </div>`);
  }

  if (reportLinks && reportLinks.length) {
    parts.push(`<div class="report-links">${reportLinks.map((l,i) =>
      `<a class="ccld-link" href="${l}" target="_blank" rel="noopener">View full report${reportLinks.length > 1 ? " " + (i+1) : ""} ↗</a>`
    ).join("")}</div>`);
  }

  if (!parts.length) return `<p class="report-error">No additional detail available in this report.</p>`;
  return parts.join("");
}

async function toggleReport(rid, facilityNumber, controlNumber) {
  const body = document.getElementById(rid);
  const btn = document.getElementById(`btn-${rid}`);
  if (!body || !btn) return;

  const isOpen = body.classList.contains("visible");
  if (isOpen) {
    body.classList.remove("visible");
    btn.classList.remove("open");
    return;
  }

  btn.classList.add("open");
  body.classList.add("visible");

  if (body.dataset.loaded) return; // already fetched

  showLoading(body, "Loading report…");

  try {
    const reports = await getReportList(facilityNumber);
    // Match by control number; a complaint may have multiple visit reports
    const matches = reports
      .map((r, i) => ({ ...r, _idx: i }))
      .filter(r => !controlNumber || r.CONTROLNUMBER === controlNumber);

    if (!matches.length) {
      showError(body, "No report documents found for this complaint.");
      body.dataset.loaded = "1";
      return;
    }

    // Fetch and merge all matching reports — same control number can span multiple docs
    const parsedReports = await Promise.all(matches.map(m => getReportDetail(facilityNumber, m._idx)));
    const parsed = { allegations: [], findings: [], deficiencies: [] };
    let fallbackFinding = null;
    for (const p of parsedReports) {
      parsed.allegations.push(...(p.allegations || []));
      if (!parsed.findings.length) parsed.findings = p.findings;
      parsed.deficiencies.push(...p.deficiencies);
      if (!fallbackFinding && p.overall_finding) fallbackFinding = p.overall_finding;
    }
    const overallFinding = deriveOverallFinding(parsed.allegations) || fallbackFinding;
    const reportLinks = matches.map(m =>
      `https://www.ccld.dss.ca.gov/transparencyapi/api/FacilityReports?facNum=${facilityNumber}&inx=${m._idx}`
    );

    setHTML(body, renderReport(parsed, reportLinks));
    body.dataset.loaded = "1";

    // Patch the finding badge with the authoritative value from the merged reports
    if (overallFinding) {
      const badgeEl = document.getElementById(`finding-${rid}`);
      if (badgeEl) {
        badgeEl.textContent = overallFinding;
        badgeEl.className = `finding-badge ${findingClass(overallFinding)}`;
      }
    }
  } catch (e) {
    showError(body, `Error loading report: ${e}`);
  }
}

async function init() {
  let data;
  try {
    data = await loadData();
  } catch (e) {
    const msg = document.createElement("div");
    msg.className = "center-message";
    const p1 = document.createElement("p");
    p1.className = "init-error-heading";
    p1.textContent = "⚠ Could not load data";
    const p2 = document.createElement("p");
    p2.appendChild(document.createTextNode("Run "));
    const code1 = document.createElement("code");
    code1.className = "init-error-code";
    code1.textContent = "python fetch_data.py";
    p2.appendChild(code1);
    p2.appendChild(document.createTextNode(" to generate the dataset, then serve with "));
    const code2 = document.createElement("code");
    code2.className = "init-error-code";
    code2.textContent = "python -m http.server 8080";
    p2.appendChild(code2);
    msg.append(p1, p2);
    const fl = document.getElementById("facility-list");
    fl.innerHTML = "";
    fl.appendChild(msg);
    return;
  }

  allFacilities = data.facilities || [];

  const updated = new Date(data.generated_at);
  document.getElementById("updated-date").textContent =
    `Updated ${updated.toLocaleDateString("en-US",{year:"numeric",month:"long",day:"numeric"})}`;

  populateFilters(allFacilities);
  updateStats(allFacilities);
  applyFilters();

  // Event listeners
  document.getElementById("search-input").addEventListener("input", () => { currentPage = 1; applyFilters(); });
  document.getElementById("county-filter").addEventListener("change", () => { currentPage = 1; applyFilters(); });
  document.getElementById("type-filter").addEventListener("change", () => { currentPage = 1; applyFilters(); });

  document.getElementById("btn-violations").addEventListener("click", function() {
    filterViolations = !filterViolations;
    this.classList.toggle("active", filterViolations);
    applyFilters();
  });

  document.getElementById("sort-select").addEventListener("change", function() {
    sortKey = this.value;
    applySort();
  });

  document.getElementById("facility-list").addEventListener("click", e => {
    const cardMain = e.target.closest(".card-main");
    if (cardMain) { toggleCard(cardMain); return; }
    const reportBtn = e.target.closest(".report-toggle");
    if (reportBtn) { toggleReport(reportBtn.dataset.rid, reportBtn.dataset.facility, reportBtn.dataset.cn); return; }
    const pageBtn = e.target.closest(".page-btn[data-page]");
    if (pageBtn) { goPage(Number(pageBtn.dataset.page)); }
  });
}

init();
