/* Funding dashboard — vanilla JS, no build step.
   Data model:
     data.json        auto-fetched opportunities (read-only display)
     tracking.json    { "<id>": {status, notes, updated}, "_manual": [ {opportunity} ] }
   Persistence:
     - working copy of tracking lives in localStorage (instant, per-device)
     - optional "Sync" commits it to the repo via the GitHub Contents API so it
       survives across devices and feeds the email alerts
*/
"use strict";

const STATUSES = ["New", "Reviewing", "Applied", "Not eligible", "Skipped"];
const LS_TRACK = "vh_tracking";
const LS_DIRTY = "vh_dirty";
const LS_GH = "vh_gh";
const HIGHLIGHT_DAYS = 30;

let DATA = { meta: {}, opportunities: [] };
let TRACK = { _manual: [] };
let VIEW = [];

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const todayISO = () => new Date().toISOString().slice(0, 10);

function daysUntil(iso) {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  return Math.round((d - new Date(todayISO() + "T00:00:00")) / 86400000);
}

/* ---------- GitHub settings ---------- */
function ghSettings() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem(LS_GH) || "{}"); } catch (e) {}
  // Auto-detect owner/repo from a project Pages URL: <owner>.github.io/<repo>/
  if ((!s.owner || !s.repo) && location.hostname.endsWith("github.io")) {
    s.owner = s.owner || location.hostname.split(".")[0];
    s.repo = s.repo || (location.pathname.split("/").filter(Boolean)[0] || "");
  }
  s.branch = s.branch || "main";
  s.path = s.path || "site/tracking.json";
  return s;
}

/* ---------- Load ---------- */
async function loadData() {
  try {
    const r = await fetch("data.json?_=" + Date.now());
    DATA = await r.json();
  } catch (e) { DATA = { meta: {}, opportunities: [] }; }
}

async function loadTracking() {
  const dirty = localStorage.getItem(LS_DIRTY) === "1";
  const local = localStorage.getItem(LS_TRACK);

  // Try to fetch the freshest committed copy (public repo raw), else local file.
  let server = null;
  const gh = ghSettings();
  const raw = gh.owner && gh.repo
    ? `https://raw.githubusercontent.com/${gh.owner}/${gh.repo}/${gh.branch}/${gh.path}?_=${Date.now()}`
    : "tracking.json?_=" + Date.now();
  try { server = await (await fetch(raw)).json(); }
  catch (e) { try { server = await (await fetch("tracking.json?_=" + Date.now())).json(); } catch (_) {} }

  if (dirty && local) {
    TRACK = JSON.parse(local);
    showSyncBanner("You have unsaved local changes. Use ⚙︎ Sync to save them to the repo.");
  } else if (server) {
    TRACK = server;
    localStorage.setItem(LS_TRACK, JSON.stringify(TRACK));
  } else if (local) {
    TRACK = JSON.parse(local);
  }
  if (!TRACK._manual) TRACK._manual = [];
}

function saveLocal(dirty = true) {
  localStorage.setItem(LS_TRACK, JSON.stringify(TRACK));
  if (dirty) localStorage.setItem(LS_DIRTY, "1");
}

/* ---------- Model helpers ---------- */
function allOpps() {
  const manual = (TRACK._manual || []).map((m) => ({ ...m, source_type: "manual" }));
  return DATA.opportunities.concat(manual);
}
function statusOf(o) {
  const t = TRACK[o.id];
  return (t && t.status) || "New";
}

/* ---------- Rendering ---------- */
function renderMeta() {
  const m = DATA.meta || {};
  const bar = $("#meta-bar");
  const when = m.generated_at ? new Date(m.generated_at).toLocaleString() : "—";
  const src = (m.sources || []).map((s) => {
    const msg = s.message ? ` — ${esc(s.message)}` : "";
    return `<span class="src-pill" title="${esc(s.status)}${esc(msg)}">
      <span class="dot ${esc(s.status)}"></span>${esc(s.name)} (${s.count})</span>`;
  }).join("");
  bar.innerHTML = `<span>Last updated <b>${esc(when)}</b></span> ${src}`;
}

function renderStats() {
  const opps = allOpps();
  const open = opps.filter((o) => !o.expired);
  const soon = open.filter((o) => { const d = daysUntil(o.deadline); return d !== null && d >= 0 && d <= HIGHLIGHT_DAYS; });
  const nw = DATA.opportunities.filter((o) => o.is_new).length;
  const active = opps.filter((o) => ["Reviewing", "Applied"].includes(statusOf(o))).length;
  const tiles = [
    { n: open.length, l: "Open opportunities" },
    { n: nw, l: "New this refresh", cls: "new" },
    { n: soon.length, l: "Closing ≤30 days", cls: "hot" },
    { n: active, l: "Reviewing / Applied" },
  ];
  $("#stats").innerHTML = tiles.map((t) =>
    `<div class="stat ${t.cls || ""}"><div class="n">${t.n}</div><div class="l">${t.l}</div></div>`).join("");
}

function fillFilters() {
  const opps = allOpps();
  const uniq = (key) => Array.from(new Set(opps.flatMap((o) => o[key] || []))).sort();
  const set = (sel, vals) => {
    const el = $(sel); const cur = el.value;
    el.innerHTML = el.children[0].outerHTML + vals.map((v) => `<option>${esc(v)}</option>`).join("");
    el.value = cur;
  };
  set("#f-source", Array.from(new Set(opps.map((o) => o.source))).sort());
  set("#f-theme", uniq("themes"));
  set("#f-geo", uniq("geography"));
  const st = $("#f-status");
  st.innerHTML = st.children[0].outerHTML + STATUSES.map((s) => `<option>${esc(s)}</option>`).join("");
}

function applyFilters() {
  const q = $("#search").value.trim().toLowerCase();
  const fSource = $("#f-source").value, fTheme = $("#f-theme").value,
        fGeo = $("#f-geo").value, fStatus = $("#f-status").value;
  const hideExp = $("#f-hide-expired").checked, soonOnly = $("#f-soon").checked, newOnly = $("#f-new").checked;

  VIEW = allOpps().filter((o) => {
    if (hideExp && o.expired) return false;
    if (newOnly && !o.is_new) return false;
    if (fSource && o.source !== fSource) return false;
    if (fTheme && !(o.themes || []).includes(fTheme)) return false;
    if (fGeo && !(o.geography || []).includes(fGeo)) return false;
    if (fStatus && statusOf(o) !== fStatus) return false;
    if (soonOnly) { const d = daysUntil(o.deadline); if (!(d !== null && d >= 0 && d <= HIGHLIGHT_DAYS)) return false; }
    if (q) {
      const hay = [o.title, o.donor, o.source, o.description, (o.themes || []).join(" "),
                   (o.geography || []).join(" ")].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  sortView();
  renderRows();
}

function sortView() {
  const key = $("#sort").value;
  const far = "9999-12-31";
  VIEW.sort((a, b) => {
    if (key === "deadline") {
      const ea = a.expired ? 1 : 0, eb = b.expired ? 1 : 0;
      if (ea !== eb) return ea - eb;
      return (a.deadline || far).localeCompare(b.deadline || far);
    }
    if (key === "relevance") return (b.relevance_score || 0) - (a.relevance_score || 0);
    if (key === "first_seen") return (b.date_first_seen || "").localeCompare(a.date_first_seen || "");
    if (key === "source") return (a.source || "").localeCompare(b.source || "");
    if (key === "status") return STATUSES.indexOf(statusOf(a)) - STATUSES.indexOf(statusOf(b));
    return 0;
  });
}

function deadlineCell(o) {
  if (!o.deadline) return `<span class="deadline"><span class="deadline-rel">no deadline stated</span></span>`;
  const d = daysUntil(o.deadline);
  let cls = "deadline", rel;
  if (d < 0) { cls += " closed"; rel = `closed ${-d}d ago`; }
  else if (d <= HIGHLIGHT_DAYS) { cls += " soon"; rel = d === 0 ? "due today" : `in ${d} day${d === 1 ? "" : "s"}`; }
  else { rel = `in ${d} days`; }
  const ap = o.deadline_approx ? ` <span class="approx">≈</span>` : "";
  return `<span class="${cls}"><span class="deadline-date">${esc(o.deadline)}${ap}</span>
    <div class="deadline-rel">${rel}</div></span>`;
}

function rowHTML(o) {
  const st = statusOf(o);
  const themes = (o.themes || []).map((t) => `<span class="chip theme">${esc(t)}</span>`).join("");
  const geos = (o.geography || []).map((g) => `<span class="chip">${esc(g)}</span>`).join("");
  const badges = (o.is_new ? `<span class="badge new">New</span>` : "") +
                 (o.source_type === "manual" ? `<span class="badge manual">Manual</span>` : "");
  const titleHTML = o.url
    ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.title)}</a>`
    : esc(o.title);
  const seen = o.date_first_seen ? `first seen ${esc(o.date_first_seen)}` : "";
  const opts = STATUSES.map((s) => `<option ${s === st ? "selected" : ""}>${s}</option>`).join("");
  return `<tr class="${o.expired ? "expired" : ""}" data-id="${esc(o.id)}">
    <td class="col-status">
      <select class="status-select" data-status="${esc(st)}" data-id="${esc(o.id)}">${opts}</select>
    </td>
    <td class="col-opp">
      <div class="opp-title">${titleHTML} ${badges}</div>
      <div class="opp-meta">
        <b>${esc(o.source)}</b>${o.donor ? " · " + esc(o.donor) : ""}
        ${seen ? " · " + seen : ""}
        ${o.relevance_score != null ? ` · relevance ${o.relevance_score}` : ""}
      </div>
      <div class="chips">${themes}${geos}</div>
      ${o.description ? `<div class="opp-desc">${esc(o.description)}</div>` : ""}
    </td>
    <td class="col-deadline">${deadlineCell(o)}</td>
    <td class="col-fund">${esc(o.funding_range || "—")}</td>
    <td class="col-elig">${o.eligibility_notes ? `<span class="elig">${esc(o.eligibility_notes)}</span>` : "—"}</td>
    <td class="col-act">${o.source_type === "manual" ? `<button class="rowmenu" data-edit="${esc(o.id)}" title="Edit">✎</button>` : ""}</td>
  </tr>`;
}

function renderRows() {
  $("#rows").innerHTML = VIEW.map(rowHTML).join("");
  $("#empty").classList.toggle("hidden", VIEW.length > 0);
  $("#foot-note").textContent = `${VIEW.length} shown · ${allOpps().length} total tracked`;
}

function renderAll() {
  renderMeta(); renderStats(); fillFilters(); applyFilters();
}

/* ---------- Status editing ---------- */
function setStatus(id, status) {
  if (status === "New" && !TRACK[id]) { /* default, no need to store */ }
  else {
    TRACK[id] = Object.assign({}, TRACK[id], { status, updated: todayISO() });
  }
  saveLocal();
  renderStats();
}

/* ---------- Manual add/edit ---------- */
function openModal(o) {
  $("#modal-title").textContent = o ? "Edit opportunity" : "Add opportunity";
  $("#m-id").value = o ? o.id : "";
  $("#m-title").value = o ? o.title : "";
  $("#m-source").value = o ? (Array.from($("#m-source").options).some((op) => op.value === o.source) ? o.source : "Other") : "OCHA GMS / Lebanon Humanitarian Fund";
  $("#m-donor").value = o ? (o.donor || "") : "";
  $("#m-url").value = o ? (o.url || "") : "";
  $("#m-deadline").value = o ? (o.deadline || "") : "";
  $("#m-funding").value = o ? (o.funding_range || "") : "";
  $("#m-geo").value = o ? (o.geography || []).join(", ") : "Lebanon";
  $("#m-themes").value = o ? (o.themes || []).join(", ") : "MHPSS";
  $("#m-desc").value = o ? (o.description || "") : "";
  $("#m-elig").value = o ? (o.eligibility_notes || "") : "";
  $("#m-delete").classList.toggle("hidden", !o);
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); }

function saveManual(e) {
  e.preventDefault();
  const id = $("#m-id").value || ("manual-" + Date.now().toString(36));
  const list = TRACK._manual || (TRACK._manual = []);
  const splitList = (v) => v.split(",").map((s) => s.trim()).filter(Boolean);
  const rec = {
    id, source_type: "manual",
    source: $("#m-source").value,
    title: $("#m-title").value.trim(),
    donor: $("#m-donor").value.trim(),
    url: $("#m-url").value.trim(),
    deadline: $("#m-deadline").value || null,
    deadline_approx: false,
    funding_range: $("#m-funding").value.trim(),
    geography: splitList($("#m-geo").value),
    themes: splitList($("#m-themes").value),
    description: $("#m-desc").value.trim(),
    eligibility_notes: $("#m-elig").value.trim(),
    relevance_score: null,
    date_first_seen: todayISO(),
    is_new: false, expired: false,
  };
  const i = list.findIndex((x) => x.id === id);
  if (i >= 0) list[i] = rec; else list.push(rec);
  saveLocal();
  closeModal();
  renderAll();
}

function deleteManual() {
  const id = $("#m-id").value;
  TRACK._manual = (TRACK._manual || []).filter((x) => x.id !== id);
  delete TRACK[id];
  saveLocal();
  closeModal();
  renderAll();
}

/* ---------- GitHub sync ---------- */
function showSyncBanner(msg) {
  const b = $("#sync-banner");
  if (!msg) { b.classList.add("hidden"); return; }
  b.innerHTML = `<div class="inner">${esc(msg)}</div>`;
  b.classList.remove("hidden");
}

async function syncToGitHub() {
  const gh = ghSettings();
  const status = $("#s-status");
  if (!gh.token || !gh.owner || !gh.repo) {
    status.textContent = "Enter owner, repo and a token first.";
    return;
  }
  status.textContent = "Saving…";
  const api = `https://api.github.com/repos/${gh.owner}/${gh.repo}/contents/${gh.path}`;
  const headers = { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" };
  try {
    let sha;
    const cur = await fetch(`${api}?ref=${gh.branch}&_=${Date.now()}`, { headers });
    if (cur.ok) sha = (await cur.json()).sha;
    const body = {
      message: "Update tracking (statuses / manual entries) via dashboard",
      content: b64utf8(JSON.stringify(TRACK, null, 2) + "\n"),
      branch: gh.branch,
    };
    if (sha) body.sha = sha;
    const put = await fetch(api, { method: "PUT", headers, body: JSON.stringify(body) });
    if (!put.ok) throw new Error("HTTP " + put.status + " — " + (await put.text()).slice(0, 120));
    localStorage.removeItem(LS_DIRTY);
    showSyncBanner("");
    status.textContent = "Saved ✓";
  } catch (e) {
    status.textContent = "Error: " + e.message;
  }
}
function b64utf8(str) {
  return btoa(String.fromCharCode(...new TextEncoder().encode(str)));
}

/* ---------- Settings modal ---------- */
function openSettings() {
  const gh = ghSettings();
  $("#s-owner").value = gh.owner || "";
  $("#s-repo").value = gh.repo || "";
  $("#s-branch").value = gh.branch || "main";
  $("#s-path").value = gh.path || "site/tracking.json";
  $("#s-token").value = gh.token || "";
  $("#s-status").textContent = localStorage.getItem(LS_DIRTY) === "1" ? "You have unsaved changes." : "";
  $("#settings").classList.remove("hidden");
}
function saveSettings(e) {
  e.preventDefault();
  const gh = {
    owner: $("#s-owner").value.trim(), repo: $("#s-repo").value.trim(),
    branch: $("#s-branch").value.trim() || "main", path: $("#s-path").value.trim() || "site/tracking.json",
    token: $("#s-token").value.trim(),
  };
  localStorage.setItem(LS_GH, JSON.stringify(gh));
  if (localStorage.getItem(LS_DIRTY) === "1") syncToGitHub();
  else $("#s-status").textContent = "Saved ✓";
}

/* ---------- Wire up ---------- */
function bind() {
  ["#search", "#f-source", "#f-theme", "#f-geo", "#f-status", "#sort"].forEach((s) =>
    $(s).addEventListener("input", applyFilters));
  ["#f-hide-expired", "#f-soon", "#f-new"].forEach((s) =>
    $(s).addEventListener("change", applyFilters));

  $("#rows").addEventListener("change", (e) => {
    if (e.target.classList.contains("status-select")) {
      const id = e.target.dataset.id;
      e.target.dataset.status = e.target.value;
      setStatus(id, e.target.value);
    }
  });
  $("#rows").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-edit]");
    if (btn) {
      const o = (TRACK._manual || []).find((x) => x.id === btn.dataset.edit);
      if (o) openModal(o);
    }
  });

  $("#btn-add").addEventListener("click", () => openModal(null));
  $("#m-cancel").addEventListener("click", closeModal);
  $("#opp-form").addEventListener("submit", saveManual);
  $("#m-delete").addEventListener("click", deleteManual);
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

  $("#btn-settings").addEventListener("click", openSettings);
  $("#s-cancel").addEventListener("click", () => $("#settings").classList.add("hidden"));
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#settings").addEventListener("click", (e) => { if (e.target.id === "settings") $("#settings").classList.add("hidden"); });
}

async function init() {
  bind();
  await loadData();
  await loadTracking();
  renderAll();
}
init();
