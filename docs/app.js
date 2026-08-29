/* Job Scanner dashboard — static, reads data/jobs.json produced by scan.py.
   All filtering/sorting/age math happens here; statuses live in localStorage. */
"use strict";

const REFRESH_MS = 120000;
const AFTER_HOURS = ["evening", "night", "swing", "oncall"];
const CATS = {
  azure: ["azure", "avd", "intune", "m365", "microsoft", "virtual desktop", "nerdio"],
  cloud: ["cloud", "azure", "aws", "devops", "infrastructure", "platform", "sre", "reliability"],
  data: ["data", "sql", "dba", "database", "etl", "warehouse", "analytics", "bi ", "power bi", "databricks", "fabric", "synapse"],
  security: ["security", "cmmc", "nist", "compliance", "fedramp"],
  support: ["support", "technical account", "noc", "help desk", "tam"],
};

let DATA = { jobs: [], config: {} };
let statuses = load("js_status", {});
let notified = new Set(load("js_notified", []));

function load(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }
function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }

const $ = id => document.getElementById(id);
const esc = s => (s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function recencyPoints(m) {
  return m <= 30 ? 25 : m <= 60 ? 20 : m <= 120 ? 12 : m <= 240 ? 6 : m <= 720 ? 3 : 0;
}
function ageMinutes(iso) { return Math.max(0, (Date.now() - Date.parse(iso)) / 60000); }
function fmtAge(m) {
  m = Math.round(m);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m ago`;
  return `${Math.floor(h / 24)}d ${h % 24}h ago`;
}

function enrich(j) {
  const age = ageMinutes(j.posted_at);
  return {
    ...j,
    age,
    dscore: Math.min(100, j.score + recencyPoints(age)),
    status: statuses[j.id] || "new",
    isWeekend: j.shift_tags.includes("weekend"),
    isAfterHours: j.shift_tags.some(t => AFTER_HOURS.includes(t)),
  };
}

function filtered() {
  const f = {
    age: +$("f-age").value, sort: $("f-sort").value, score: +$("f-score").value || 0,
    status: $("f-status").value, cat: $("f-cat").value, source: $("f-source").value,
    q: $("f-q").value.trim().toLowerCase(), company: $("f-company").value.trim().toLowerCase(),
    remote: $("f-remote").checked, weekend: $("f-weekend").checked,
    afterhours: $("f-afterhours").checked, swing: $("f-swing").checked, night: $("f-night").checked,
  };
  let out = DATA.jobs.map(enrich).filter(j => {
    if (["applied", "favorite", "ignored"].includes(f.status)) {
      if (j.status !== f.status) return false;      // saved jobs ignore the age cap
    } else {
      if (j.age > f.age * 60) return false;
      if (f.status === "active" && j.status === "ignored") return false;
      if (f.status === "new" && j.status !== "new") return false;
      if (f.status === "all") { /* everything */ }
    }
    if (j.dscore < f.score) return false;
    if (f.remote && !j.remote) return false;
    if (f.weekend && !j.isWeekend) return false;
    if (f.afterhours && !j.isAfterHours) return false;
    if (f.swing && !j.shift_tags.includes("swing")) return false;
    if (f.night && !j.shift_tags.includes("night")) return false;
    if (f.source && j.source !== f.source && !j.other_sources.includes(f.source)) return false;
    if (f.q && !(j.title + " " + j.description).toLowerCase().includes(f.q)) return false;
    if (f.company && !j.company.toLowerCase().includes(f.company)) return false;
    if (f.cat) {
      const t = j.title.toLowerCase();
      if (!CATS[f.cat].some(k => t.includes(k))) return false;
    }
    return true;
  });
  const by = {
    best: (a, b) => b.dscore - a.dscore || a.age - b.age,
    newest: (a, b) => a.age - b.age,
    score: (a, b) => b.dscore - a.dscore,
    weekend: (a, b) => (b.isWeekend - a.isWeekend) || b.shift_score - a.shift_score || b.dscore - a.dscore,
    afterhours: (a, b) => b.shift_score - a.shift_score || b.dscore - a.dscore,
    salary: (a, b) => (b.salary_min || 0) - (a.salary_min || 0) || b.dscore - a.dscore,
  };
  out.sort(by[f.sort] || by.best);
  return out;
}

function card(j) {
  const sc = j.dscore >= 65 ? "s-hi" : j.dscore >= 40 ? "s-mid" : "s-lo";
  const cls = ["card", "st-" + j.status,
    j.isWeekend ? "is-weekend" : "", j.isAfterHours ? "is-afterhours" : ""].join(" ");
  const srcs = [j.source, ...j.other_sources].join(" + ");
  return `<article class="${cls}" data-id="${esc(j.id)}">
    <div class="c-top">
      <div class="c-title">${esc(j.title)}</div>
      <div class="score ${sc}">${j.dscore}</div>
    </div>
    <div class="c-co">${esc(j.company)}${j.location ? " · " + esc(j.location) : ""}</div>
    <div class="badges">
      <span class="b age ${j.age <= 60 ? "fresh" : ""}">${fmtAge(j.age)}</span>
      ${j.remote ? '<span class="b remote">Remote</span>' : ""}
      ${j.isWeekend ? '<span class="b wk">WEEKEND</span>' : ""}
      ${j.isAfterHours ? '<span class="b ah">AFTER-HOURS</span>' : ""}
      ${j.shift_tags.filter(t => !["weekend"].includes(t)).map(t => `<span class="b">${t}</span>`).join("")}
      ${j.salary ? `<span class="b sal">${esc(j.salary)}</span>` : ""}
      <span class="b">${esc(srcs)}</span>
      ${j.status !== "new" ? `<span class="b">${j.status}</span>` : ""}
    </div>
    <div class="c-more">
      ${j.description ? `<p class="c-desc">${esc(j.description)}…</p>` : ""}
      <div class="c-meta">posted ${new Date(j.posted_at).toLocaleString()} · first seen ${new Date(j.first_seen).toLocaleString()} · base score ${j.score} · shift score ${j.shift_score}</div>
      <div class="c-actions">
        <a class="apply" href="${esc(j.url)}" target="_blank" rel="noopener">Apply ↗</a>
        <button data-st="applied" class="${j.status === "applied" ? "on" : ""}">✓ Applied</button>
        <button data-st="favorite" class="${j.status === "favorite" ? "on" : ""}">★ Favorite</button>
        <button data-st="ignored" class="${j.status === "ignored" ? "on" : ""}">✕ Ignore</button>
      </div>
    </div>
  </article>`;
}

function render() {
  const jobs = filtered();
  const thr = DATA.config.notification_threshold || 70;

  const secs = [
    ["sec-hot", jobs.filter(j => j.age <= 60 && j.dscore >= thr)],
    ["sec-weekend", jobs.filter(j => j.isWeekend)],
    ["sec-afterhours", jobs.filter(j => j.isAfterHours && !j.isWeekend)],
    ["sec-newest", [...jobs].sort((a, b) => a.age - b.age)],
  ];
  const shown = new Set();
  for (const [id, list] of secs) {
    const el = $(id);
    const top = list.filter(j => !shown.has(j.id)).slice(0, 6);
    el.hidden = top.length === 0 || (id === "sec-newest" && jobs.length <= 6);
    el.querySelector(".cards").innerHTML = top.map(card).join("");
    if (id !== "sec-newest") top.forEach(j => shown.add(j.id));
  }
  $("all-cards").innerHTML = jobs.map(card).join("");
  $("all-count").textContent = `${jobs.length} job${jobs.length === 1 ? "" : "s"}`;
  $("empty").hidden = jobs.length > 0;

  const gen = DATA.generated_at ? fmtAge(ageMinutes(DATA.generated_at)) : "?";
  $("scan-info").textContent = `last scan ${gen} · ${DATA.jobs.length} jobs in window`;

  const meta = DATA.source_meta || {};
  $("src-health").textContent = "sources: " + Object.entries(meta)
    .map(([n, m]) => `${m.error ? "⚠" : "✓"} ${n}`).join("  ");
}

function notify(jobs) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  if (localStorage.getItem("js_notify") !== "1") return;
  const thr = DATA.config.notification_threshold || 70;
  let sent = 0;
  for (const j of jobs.map(enrich)) {
    if (notified.has(j.id) || j.age > 240 || sent >= 3) continue;
    const strong = j.dscore >= thr;
    const shifty = (j.isWeekend || j.isAfterHours) && j.dscore >= 45;
    if (!strong && !shifty) continue;
    new Notification(`${j.isWeekend ? "📅 " : j.isAfterHours ? "🌙 " : "🔥 "}${j.title}`, {
      body: `${j.company} · ${j.dscore}% match · ${fmtAge(j.age)}`,
      tag: j.id, icon: "icon.svg",
    });
    notified.add(j.id);
    sent++;
  }
  save("js_notified", [...notified].slice(-800));
}

async function refresh() {
  try {
    const r = await fetch(`data/jobs.json?_=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    DATA = await r.json();
    populateSources();
    render();
    notify(DATA.jobs);
  } catch (e) {
    $("scan-info").textContent = "couldn't load job data — " + e.message;
  }
}

function populateSources() {
  const sel = $("f-source"), cur = sel.value;
  const names = [...new Set(DATA.jobs.flatMap(j => [j.source, ...j.other_sources]))].sort();
  sel.innerHTML = '<option value="">All sources</option>' +
    names.map(n => `<option${n === cur ? " selected" : ""}>${n}</option>`).join("");
}

/* ---------------- events ---------------- */
document.addEventListener("click", e => {
  const btn = e.target.closest("button[data-st]");
  const cardEl = e.target.closest(".card");
  if (btn && cardEl) {
    e.stopPropagation();
    const id = cardEl.dataset.id, st = btn.dataset.st;
    statuses[id] = statuses[id] === st ? "viewed" : st;   // toggle off -> viewed
    save("js_status", statuses);
    render();
    return;
  }
  if (e.target.closest("a")) return;
  if (cardEl) {
    cardEl.classList.toggle("open");
    const id = cardEl.dataset.id;
    if (!statuses[id]) { statuses[id] = "viewed"; save("js_status", statuses); }
  }
});

for (const id of ["f-age", "f-sort", "f-score", "f-status", "f-cat", "f-source",
  "f-remote", "f-weekend", "f-afterhours", "f-swing", "f-night"])
  $(id).addEventListener("change", render);
for (const id of ["f-q", "f-company"]) $(id).addEventListener("input", render);

$("btn-refresh").onclick = refresh;
$("btn-filters").onclick = () => $("filters").classList.toggle("show");
$("btn-notify").onclick = async () => {
  if (localStorage.getItem("js_notify") === "1") {
    localStorage.setItem("js_notify", "0");
  } else {
    const p = await Notification.requestPermission();
    localStorage.setItem("js_notify", p === "granted" ? "1" : "0");
  }
  syncNotifyBtn();
};
function syncNotifyBtn() {
  $("btn-notify").classList.toggle("on", localStorage.getItem("js_notify") === "1");
}

document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
setInterval(refresh, REFRESH_MS);
setInterval(render, 60000);          // ages/scores tick even between fetches

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
syncNotifyBtn();
refresh();
