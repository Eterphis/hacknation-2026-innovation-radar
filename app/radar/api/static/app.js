"use strict";
/* Radar Innowacji UI. Components are small functions returning HTML; pages compose them.
   Icons: one Lucide sprite (/static/icons.svg), always grey (--ink-3) unless they carry state (red). */
const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const opTok = () => { try { return localStorage.getItem("radar-operator") || ""; } catch (e) { return ""; } };
const api = (p, o = {}, retry = true) => fetch(p, {...o, headers: {...(o.headers || {}), ...(opTok() ? {"X-Operator-Token": opTok()} : {})}}).then(r => {
  if (r.status === 401 && retry && (o.method || "GET") !== "GET") { const t = prompt("Akcja operatora PCI: podaj token operatora"); if (t) { try { localStorage.setItem("radar-operator", t); } catch (e) {} return api(p, o, false); } }
  return r.ok ? r.json() : r.text().then(t => Promise.reject(t)); });
const qs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ------------------------------------------------------------------ vocabulary
const LVL = ["badania", "technologia gotowa", "gotowe do wdrożenia", "na rynku"];
const LVLK = {exploring: 0, tech_ready: 1, business_ready: 2, market_ready: 3};
const COSTK = ["niski", "sredni", "wysoki", "bardzo_wysoki"];
const COST_RANGE = {niski: "do 100 tys. zł", sredni: "100 tys. – 2 mln zł", wysoki: "2–20 mln zł", bardzo_wysoki: "> 20 mln zł"};
const CRIT = {dojrzalosc: "Dojrzałość", przenaszalnosc: "Przenaszalność", skala_problemu: "Skala problemu", koszt_wdrozenia: "Koszt wdrożenia", sila_dowodow: "Siła dowodów", nowosc: "Nowość"};
const SECTOR_ICON = {A_rolnictwo: "sprout", C_przemysl: "factory", D_energetyka: "zap", E_srodowisko: "recycle", F_budownictwo: "hammer", H_transport: "truck",
  J_ict: "cpu", M_nauka: "flask-conical", O_administracja: "landmark", P_edukacja: "book-open", Q_zdrowie: "hospital", R_kultura: "users"};
const TECH_ICON = {ai_dane: "bot", iot_czujniki: "wifi", energia_wodor: "zap", materialy: "layers", lotnictwo_kosmos: "plane", motoryzacja: "car", biotech_medtech: "hospital",
  agro_zywnosc: "sprout", srodowisko_tech: "recycle", budownictwo_tech: "hammer", oprogramowanie_euslugi: "monitor", robotyka_automatyka: "cpu", metody_nietech: "users"};
const INST_ICON = {szkola: "school", uczelnia: "graduation-cap", instytut: "flask-conical", jst: "landmark", inna_publiczna: "building-2", firma: "briefcase", unknown: "building-2"};
const INST_PL = {szkola: "Szkoła", uczelnia: "Uczelnia", instytut: "Instytut badawczy", jst: "Samorząd (JST)", inna_publiczna: "Instytucja publiczna", firma: "Firma", unknown: "Instytucja"};
const PATH_ICON = {"rozwój": "flask-conical", "komercjalizacja": "briefcase", "wdrożenie w innej organizacji (transfer)": "copy", "pilotaż": "target", "skalowanie i finansowanie": "trending-up"};
// sector -> categorical slot, fixed by entity (never by rank); validated palette (dataviz validator)
const SECTOR_SLOT = {P_edukacja: 1, Q_zdrowie: 2, J_ict: 3, O_administracja: 4, C_przemysl: 5, D_energetyka: 6, H_transport: 7};
const secColor = k => SECTOR_SLOT[k] ? `var(--s${SECTOR_SLOT[k]})` : "var(--other)";
let LABELS = {}, CFG = {}, F = {}, POLAND = null;
const lp = (axis, v) => (LABELS[axis] && !Array.isArray(LABELS[axis]) && LABELS[axis][v]) || v || "—";
const pln = n => n == null ? null : n >= 1e6 ? (n / 1e6).toLocaleString("pl-PL", {maximumFractionDigits: 1}) + " mln zł" : Math.round(n / 1000).toLocaleString("pl-PL") + " tys. zł";

// ------------------------------------------------------------------ components
const icon = (n, cls = "") => `<svg class="ic ${cls}" aria-hidden="true"><use href="#i-${n}"/></svg>`;  // sprite inlined at boot
const avatar = (n, cls = "") => `<span class="avatar ${cls}">${icon(n)}</span>`;
const plate = (ic, value, label, cls = "") => value ? `<span class="plate ${cls}" title="${esc(label || "")}"><span class="pi">${icon(ic)}</span><span>${label ? `<small>${esc(label)}</small>` : ""}${esc(value)}</span></span>` : "";
const locPlate = (i, cls = "") => (i.city || i.voivodeship) ? plate("map-pin", [i.city, i.voivodeship].filter(Boolean).join(" · "), "", "red " + cls) : "";
const moneyPlate = (i, cls = "") => plate("banknote", i.amount ? pln(i.amount) : COST_RANGE[i.cost_level || i.cost], "", cls);
const instPlate = (t, cls = "") => t ? plate(INST_ICON[t] || "building-2", INST_PL[t] || t, "", cls) : "";
const sectorPlate = (s, cls = "") => s ? plate(SECTOR_ICON[s] || "layers", lp("sector", s), "", cls) : "";
const stepper = lvl => `<span class="stepper" role="img" aria-label="Dojrzałość: ${LVL[lvl]}" title="${LVL[lvl]}">${[0, 1, 2, 3].map(i => `<i class="${i <= lvl ? "on" : ""}"></i>`).join("")}</span>`;
const ring = (score, cls = "") => { const s = Math.round(score || 0), c = 2 * Math.PI * 21;
  return `<span class="ring ${cls}" role="img" aria-label="Wynik ${s} na 100"><svg viewBox="0 0 50 50"><circle cx="25" cy="25" r="21" fill="none" stroke="var(--line)" stroke-width="5"/>
    <circle cx="25" cy="25" r="21" fill="none" stroke="var(--red)" stroke-width="5" stroke-linecap="round" stroke-dasharray="${(c * s / 100).toFixed(1)} ${c.toFixed(1)}"/></svg><b>${s}</b></span>`; };
const demo = s => s ? `<span class="badge-demo" title="Dane przykładowe (syntetyczne)">${icon("flask-conical")}przykład</span>` : "";
const empty = (msg, action = "") => `<div class="empty">${avatar("inbox")}<p>${esc(msg)}</p>${action}</div>`;
function tip(html, e) { const t = $("#tip"); if (!html) { t.style.opacity = 0; return; } t.innerHTML = html; t.style.opacity = 1;
  t.style.left = Math.min(e.clientX + 14, innerWidth - t.offsetWidth - 8) + "px"; t.style.top = Math.min(e.clientY + 14, innerHeight - t.offsetHeight - 8) + "px"; }
const stagger = root => { const els = $$(".reveal", root); els.forEach((el, i) => el.style.animationDelay = Math.min(i, 14) * 70 + "ms");
  setTimeout(() => els.forEach(el => el.classList.remove("reveal")), 1700); };  // never leave content hidden
const cardH = (ic, title, sub, tools = "", red = false) => `<div class="card-h">${avatar(ic, red ? "red" : "")}<div><h2>${title}</h2>${sub ? `<div class="faint">${sub}</div>` : ""}</div>${tools ? `<div class="tools">${tools}</div>` : ""}</div>`;

// ------------------------------------------------------------------ theme
function applyTheme(t) {
  const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $$("#theme button").forEach(b => b.setAttribute("aria-checked", b.dataset.t === t));
  try { localStorage.setItem("radar-theme", t); } catch (e) {}
}
let THEME = "system"; try { THEME = localStorage.getItem("radar-theme") || "system"; } catch (e) {}
const QT = new URLSearchParams(location.search).get("theme");  // ?theme=dark|light|system for shared links and screenshots
if (["dark", "light", "system"].includes(QT)) THEME = QT;
$$("#theme button").forEach(b => { b.innerHTML = icon({light: "sun", system: "monitor", dark: "moon"}[b.dataset.t]); b.onclick = () => { THEME = b.dataset.t; applyTheme(THEME); if (location.hash.startsWith("#/graf")) route(); }; });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => THEME === "system" && applyTheme("system"));
applyTheme(THEME);

// ------------------------------------------------------------------ router
const ROUTES = {dla: pageAudience, mapa: pageMap, graf: pageGraph, zrodla: pageSources, porownaj: pageCompare, wdrozenia: pageDeploy, portfel: pageDeals};
$$("#nav a").forEach(a => a.innerHTML = icon(a.dataset.i) + `<span>${a.textContent}</span>`);
$("#cmdbtn").innerHTML = icon("search"); $("#cmdicon").innerHTML = icon("search", "faint");
const RLOAD = `<div class="rload" role="status"><svg viewBox="0 0 100 100" aria-hidden="true"><circle class="rl-ring" cx="50" cy="50" r="46"/><circle class="rl-ring" cx="50" cy="50" r="30"/><circle class="rl-ring" cx="50" cy="50" r="14"/>
  <path class="rl-sweep" d="M50 50 L50 4 A46 46 0 0 1 89.8 27 Z" fill="var(--red)" opacity=".18"/><circle class="rl-dot" cx="68" cy="30" r="3"/><circle class="rl-dot d2" cx="30" cy="62" r="3"/><circle class="rl-dot d3" cx="72" cy="66" r="3"/></svg><span>Wczytuję…</span></div>`;
async function route() {
  const [full, query] = location.hash.replace(/^#\/?/, "").split("?");
  const [path, sub] = full.split("/");  // #/dla/samorzady -> path "dla", sub "samorzady"
  F = {...Object.fromEntries(new URLSearchParams(query || "")), ...(sub ? {_sub: sub} : {})};
  $$("#nav a").forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#/" + path));
  document.body.classList.toggle("reels-on", path === "rolki");
  const v = $("#view");
  v.setAttribute("aria-busy", "true");  // screen readers wait for the view; tests wait for this instead of sleeping
  v.innerHTML = RLOAD;
  try { await (ROUTES[path] || pageHome)(v); } catch (e) { v.innerHTML = empty("Nie udało się wczytać widoku: " + e); }
  v.removeAttribute("aria-busy");
  stagger(v); window.scrollTo(0, 0);
}
const go = (path, f) => { const q = qs(f || {}); location.hash = "#/" + path + (q ? "?" + q : ""); };
window.addEventListener("hashchange", route);

// ------------------------------------------------------------------ PRZEGLĄD
function drawPortfolio(el, pts) {
  const W = 640, H = 420, L = 64, R = 12, T = 16, B = 44, cw = (W - L - R) / 4, ch = (H - T - B) / 4, cell = {}, r = s => 5 + Math.max(0, s - 40) / 10;
  const pos = pts.map(p => { const key = p.cost_i + ":" + p.maturity_i, i = cell[key] = (cell[key] || 0) + 1, ang = i * 2.399, rad = Math.min(12 * Math.sqrt(i - 1), Math.min(cw, ch) / 2 - 12);
    return {...p, x: L + (p.cost_i + .5) * cw + Math.cos(ang) * rad, y: T + (3 - p.maturity_i + .5) * ch + Math.sin(ang) * rad}; });
  const Q = [["Szybkie wygrane", "tanio i już działa", L + 6, T + 16], ["Do skalowania", "działa, ale drogo", L + 2 * cw + 6, T + 16],
    ["Do przetestowania", "tanio, wczesny etap", L + 6, T + 2 * ch + 16], ["Duże zakłady", "drogo i wcześnie", L + 2 * cw + 6, T + 2 * ch + 16]];
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Portfel pomysłów: koszt na osi poziomej, dojrzałość na pionowej">
    <rect x="${L}" y="${T}" width="${2 * cw}" height="${2 * ch}" rx="10" fill="var(--red)" opacity=".07"/>
    ${[0, 1, 2, 3, 4].map(i => `<line class="gridl" x1="${L + i * cw}" x2="${L + i * cw}" y1="${T}" y2="${H - B}"/><line class="gridl" x1="${L}" x2="${W - R}" y1="${T + i * ch}" y2="${T + i * ch}"/>`).join("")}
    <line x1="${L + 2 * cw}" x2="${L + 2 * cw}" y1="${T}" y2="${H - B}" stroke="var(--ink)" stroke-dasharray="3 4"/><line x1="${L}" x2="${W - R}" y1="${T + 2 * ch}" y2="${T + 2 * ch}" stroke="var(--ink)" stroke-dasharray="3 4"/>
    ${Q.map(q => `<text class="ql" x="${q[2]}" y="${q[3]}">${q[0]}</text><text class="qd" x="${q[2]}" y="${q[3] + 14}">${q[1]}</text>`).join("")}
    ${["niski", "średni", "wysoki", "b. wysoki"].map((c, i) => `<text class="axis" x="${L + (i + .5) * cw}" y="${H - B + 18}" text-anchor="middle">${c}</text>`).join("")}
    <text class="axis" x="${L + 2 * cw}" y="${H - 6}" text-anchor="middle">KOSZT WDROŻENIA →</text>
    ${["badania", "technol.", "wdrożenie", "rynek"].map((l, i) => `<text class="axis" x="${L - 8}" y="${T + (3 - i + .5) * ch + 4}" text-anchor="end">${l}</text>`).join("")}
    ${pts.length > 80 ? cells(pts) : pos.map((p, i) => `<circle data-i="${i}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r(p.score).toFixed(1)}" fill="${secColor(p.sector)}" stroke="var(--bg)" stroke-width="2" style="cursor:pointer"/>`).join("")}</svg>`;
  function cells(all) { // many ideas: one bubble per cell, area ~ count, label = count (readable at any data size)
    const g = {}; all.forEach(p => (g[p.cost_i + ":" + p.maturity_i] ||= []).push(p));
    const maxN = Math.max(...Object.values(g).map(a => a.length));
    return Object.entries(g).map(([k, a]) => { const [ci, mi] = k.split(":").map(Number), x = L + (ci + .5) * cw, y = T + (3 - mi + .5) * ch, rr = 8 + Math.sqrt(a.length / maxN) * (Math.min(cw, ch) / 2 - 12);
      return `<g data-cell="${k}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="${rr.toFixed(1)}" fill="var(--red)" fill-opacity="${(.25 + .6 * a.length / maxN).toFixed(2)}" stroke="var(--red)" stroke-width="1.5"/>
        <text x="${x}" y="${y + 5}" text-anchor="middle" style="font:750 15px var(--sans);fill:var(--ink);paint-order:stroke;stroke:var(--bg);stroke-width:3px">${a.length}</text></g>`; }).join(""); }
  $$("g[data-cell]", el).forEach(gr => { const [ci, mi] = gr.dataset.cell.split(":").map(Number), a = pts.filter(p => p.cost_i === ci && p.maturity_i === mi).sort((x, y) => y.score - x.score);
    gr.onmousemove = e => tip(`<b>${a.length} pomysłów</b> · koszt ${["niski", "średni", "wysoki", "b. wysoki"][ci]} · ${LVL[mi]}<br>${a.slice(0, 3).map(p => "• " + esc(p.title.slice(0, 60))).join("<br>")}`, e);
    gr.onmouseleave = () => tip(); gr.onclick = () => go("odkrywaj", {cost_level: COSTK[ci], maturity: Object.keys(LVLK)[mi]}); });
  $$("circle[data-i]", el).forEach(c => { const p = pos[+c.dataset.i];
    c.onmousemove = e => tip(`<b>${esc(p.title)}</b><br>${esc(p.sector_pl)} · ${esc(p.voivodeship || "—")}<br>wynik ${Math.round(p.score)} · ${LVL[p.maturity_i]}`, e);
    c.onmouseleave = () => tip(); c.onclick = () => openCard(p.card_id); });
  const used = [...new Set(pts.map(p => SECTOR_SLOT[p.sector] ? p.sector : "_"))].sort((a, b) => (SECTOR_SLOT[a] || 9) - (SECTOR_SLOT[b] || 9));
  $("#plegend").innerHTML = used.map(s => `<span><i class="dot" style="background:${s === "_" ? "var(--other)" : secColor(s)}"></i>${esc(s === "_" ? "inne sektory" : lp("sector", s))}</span>`).join("");
  $("#ptable").innerHTML = `<div class="table-wrap"><table class="t"><tr><th>Pomysł</th><th>Koszt</th><th>Dojrzałość</th><th>Wynik</th></tr>${pts.slice().sort((a, b) => b.score - a.score).map(p => `<tr><td><a href="#" data-card="${p.card_id}">${esc(p.title)}</a></td><td>${["niski", "średni", "wysoki", "b. wysoki"][p.cost_i]}</td><td>${LVL[p.maturity_i]}</td><td class="mono">${Math.round(p.score)}</td></tr>`).join("")}</table></div>`;
  bindCards($("#ptable"));
}

// ------------------------------------------------------------------ MAPA POLSKI
async function drawPoland(el, reg, opts = {}) {
  POLAND = POLAND || await api("/static/poland.json");
  const mode = opts.mode || "count", by = Object.fromEntries(reg.regions.map(r => [r.voivodeship, r]));
  const val = r => mode === "gap" ? Math.max(0, r.gap) : r.selected;
  const max = Math.max(0.0001, ...reg.regions.map(val));
  const fill = r => { const t = val(r) / max; return t <= 0 ? "var(--white)" : `color-mix(in srgb, var(--red) ${Math.round(12 + 88 * t)}%, var(--white))`; };
  el.innerHTML = `<svg class="pl-map" viewBox="${POLAND.viewBox}" role="group" aria-label="Mapa Polski: ${mode === "gap" ? "luki" : "liczba pomysłów"} w województwach">
    ${POLAND.regions.map(p => { const r = by[p.name] || {selected: 0, gap: 0, ideas: 0};
      const lab = `${p.name}: ${r.selected} pomysłów${mode === "gap" && r.gap > 0 ? ", luka " + r.gap : ""}`;
      return `<path d="${p.d}" fill="${fill(r)}" data-v="${esc(p.name)}" class="${opts.selected === p.name ? "sel" : ""}" tabindex="0" role="button" aria-label="${esc(lab)}"/>`; }).join("")}
    ${POLAND.regions.map(p => { const r = by[p.name] || {selected: 0, gap: 0}; const t = val(r) / max, n = mode === "gap" ? (r.gap > 0 ? "luka" : "") : r.selected;
      return n || n === 0 && !opts.compact ? `<text x="${p.cx}" y="${p.cy}" text-anchor="middle" class="${t > .6 ? "on-red" : ""}">${n}</text>` : ""; }).join("")}</svg>
    <div class="map-scale"><span>${mode === "gap" ? "brak luki" : "0"}</span><i></i><span>${mode === "gap" ? "największa luka" : Math.round(max) + " " + (opts.unit || "pomysłów")}</span></div>
    ${opts.compact ? "" : `<div class="map-legend"><span><i style="background:var(--white)"></i>${mode === "gap" ? "brak luki" : "brak pomysłów"}</span><span><i style="background:var(--red)"></i>${mode === "gap" ? "największa luka" : "najwięcej"}</span><span>${icon("map-pin")}klik lub Enter: pomysły województwa</span></div>`}
    <p class="faint" style="margin:.5rem 0 0">Granice: ppatrzyk/polska-geojson (MIT), uproszczone.</p>`;
  $$("path[data-v]", el).forEach(p => { const r = by[p.dataset.v] || {selected: 0, ideas: 0, gap: 0, top_sectors: []};
    const html = `<b>${esc(p.dataset.v)}</b><br>${r.selected} pomysłów${reg.national_avg != null ? ` · średnio ${reg.national_avg}/woj.` : ""}${r.top_sectors?.length ? "<br>" + esc(r.top_sectors.map(t => t.pl).join(", ")) : ""}`;
    const pick = () => opts.onPick ? opts.onPick(p.dataset.v) : go("mapa", {voivodeship: p.dataset.v});
    p.onmousemove = e => tip(html, e); p.onmouseleave = () => tip();
    p.onfocus = () => { const b = p.getBoundingClientRect(); tip(html, {clientX: b.left + b.width / 2, clientY: b.top + b.height / 2}); }; p.onblur = () => tip();
    p.onclick = pick; p.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } }; });
}
async function pageMap(v) {
  const sector = F.sector || "", mode = F.mode || "count", sel = F.voivodeship || "";
  const reg = await api("/api/regions?" + qs({sector}));
  v.innerHTML = header("Mapa", "map", "Gdzie powstają pomysły, a gdzie ich brakuje",
    "Kolor = liczba pomysłów albo wielkość luki względem średniej krajowej. Kliknij województwo, by zobaczyć jego pomysły.") + `
  <div class="grid g-7-5"><div class="card reveal"><div class="card-h">${avatar("map", "red")}<div class="chips" style="margin-left:auto">
      <button class="chip ${mode === "count" ? "on" : ""}" data-mode="count">${icon("lightbulb")}Pomysły</button><button class="chip ${mode === "gap" ? "on" : ""}" data-mode="gap">${icon("target")}Luki</button></div></div>
    <div class="card-b"><div class="chips sec-row" style="margin-bottom:1rem"><button class="chip ${!sector ? "on" : ""}" data-sec="">${icon("layers")}Wszystkie</button>${reg.sectors.map(s => `<button class="chip ${sector === s.key ? "on" : ""}" data-sec="${s.key}" title="${esc(s.pl)}">${icon(SECTOR_ICON[s.key] || "layers")}${esc(s.pl.split(",")[0])}</button>`).join("")}</div>
      <div id="bigmap"></div></div></div>
    <div class="card reveal" id="side">${cardH(sel ? "map-pin" : "trending-up", sel || "Najwięcej i najmniej", sel ? "pomysły w województwie" : (sector ? lp("sector", sector) : "wszystkie sektory"))}<div class="card-b" id="sidelist"></div></div></div>`;
  await drawPoland($("#bigmap"), reg, {mode, selected: sel, onPick: name => go("mapa", {...F, voivodeship: name})});
  $$("[data-mode]", v).forEach(b => b.onclick = () => go("mapa", {...F, mode: b.dataset.mode}));
  $$("[data-sec]", v).forEach(b => b.onclick = () => go("mapa", {...F, sector: b.dataset.sec}));
  const side = $("#sidelist");
  if (sel) {
    const r = await api("/api/ideas?" + qs({voivodeship: sel, sector, sort: "score", limit: 12}));
    side.innerHTML = `<div class="items">${r.items.map(i => ideaItem(i)).join("") || empty("Brak pomysłów — to luka. Zobacz, co działa w innych województwach.", `<a class="btn-soft" href="#/odkrywaj?${qs({sector})}">${icon("arrow-right")}Rozwiązania z kraju</a>`)}</div>`;
  } else {
    const rows = reg.regions.slice().sort((a, b) => mode === "gap" ? b.gap - a.gap : b.selected - a.selected).slice(0, 8);
    side.innerHTML = `<div class="items">${rows.map(r => `<div class="item" data-v="${esc(r.voivodeship)}">${avatar("map-pin")}<h3>${esc(r.voivodeship)}</h3><span class="plate sm ${mode === "gap" ? "red" : ""}"><span class="pi">${icon(mode === "gap" ? "target" : "lightbulb")}</span>${mode === "gap" ? (r.gap > 0 ? "luka " + r.gap : "brak luki") : r.selected + " pomysłów"}</span>
      <div class="plates">${r.top_sectors.slice(0, 2).map(t => plate(SECTOR_ICON[t.sector] || "layers", t.pl.split(",")[0], "", "sm")).join("")}</div></div>`).join("")}</div>`;
    $$("[data-v]", side).forEach(x => x.onclick = () => go("mapa", {...F, voivodeship: x.dataset.v}));
  }
  bindCards(side); stagger(side);
}

// ------------------------------------------------------------------ ODKRYWAJ
// ------------------------------------------------------------------ GRAF
async function pageGraph(v) {
  // 120 best ideas: enough to read the structure, small enough to stay calm and fast on a phone
  const g = await api("/api/graph?" + qs({sector: F.sector, tech_area: F.tech_area, voivodeship: F.voivodeship, innovation_type: F.innovation_type, maturity: F.maturity, limit: 120,
    hubs: F.voivodeship ? "sector,tech_area" : "sector,tech_area"}));  // 16 voivodeship hubs crowd the picture; the Map covers regions
  const active = ["sector", "tech_area", "voivodeship", "innovation_type", "maturity"].filter(k => F[k]);
  v.innerHTML = header("Graf wiedzy", "network", "Jak pomysły łączą się ze sobą", "Kropki to pomysły (kolor = sektor). Białe węzły z ikoną to huby: sektor, obszar technologii, województwo. Czerwone linie = podobna treść.",
    active.length ? `<button class="btn-soft" id="clearf">${icon("x")}Wyczyść filtry</button>` : "") +
    `<div class="card reveal"><canvas id="graph" role="img" aria-label="Graf pomysłów; ta sama treść jest dostępna jako lista poniżej"></canvas></div><div class="legend" id="glegend"></div><div id="gtext"></div>`;
  if ($("#clearf")) $("#clearf").onclick = () => go("graf", {});
  if (!g.nodes.length) { $("#graph").outerHTML = empty("Brak pomysłów dla tych filtrów."); return; }
  drawGraph(g);
}
function drawGraph(g) {
  const cv = $("#graph"), ctx = cv.getContext("2d"), dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr; ctx.scale(dpr, dpr);
  const css = getComputedStyle(document.documentElement), C = n => css.getPropertyValue(n).trim();
  const idx = new Map(g.nodes.map((n, i) => [n.id, i]));
  // Seeded layout: hubs on a circle, each idea starts next to its sector hub (no random explosion from the centre).
  const hubs = g.nodes.filter(n => n.type !== "idea"), R0 = Math.min(W, H) * .38;
  const hubPos = new Map(hubs.map((h, i) => [h.id, {x: W / 2 + Math.cos(i / hubs.length * 2 * Math.PI) * R0, y: H / 2 + Math.sin(i / hubs.length * 2 * Math.PI) * R0}]));
  const N = g.nodes.map((n, i) => { let p = hubPos.get(n.id);
    if (!p) { const h = hubPos.get("sector:" + n.sector) || {x: W / 2, y: H / 2}; p = {x: h.x * .6 + W / 2 * .4 + Math.cos(i * 2.399) * 30, y: h.y * .6 + H / 2 * .4 + Math.sin(i * 2.399) * 30}; }
    return {...n, x: p.x, y: p.y, vx: 0, vy: 0, deg: 0}; });
  const Lk = g.links.filter(l => idx.has(l.source) && idx.has(l.target)).map(l => ({...l, s: N[idx.get(l.source)], t: N[idx.get(l.target)]}));
  Lk.forEach(l => { l.s.deg++; l.t.deg++; });
  const sim = l => l.kind === "similar" || l.kind === "possible_duplicate";
  const rad = n => n.type === "idea" ? 5 + (n.score || 40) / 20 : 11 + Math.sqrt(n.deg) * 1.6;
  // hub icons as images from the sprite (same grey icon set as the rest of the UI)
  const hubIcon = n => n.type === "sector" ? (SECTOR_ICON[n.id.split(":")[1]] || "layers") : n.type === "tech_area" ? (TECH_ICON[n.id.split(":")[1]] || "cpu") : "map-pin";
  const imgs = {};
  N.filter(n => n.type !== "idea").forEach(n => { const name = hubIcon(n); if (!imgs[name]) { const img = new Image(); fetch("/static/icons.svg?v=4").then(r => r.text()).then(t => {
    const m = t.match(new RegExp(`<symbol id="i-${name}" viewBox="0 0 24 24">([\\s\\S]*?)</symbol>`)); if (!m) return;
    img.src = "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="${C("--ink-3")}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${m[1]}</svg>`); }); imgs[name] = img; } });
  let alpha = 1, drag = null, hover = null, ox = 0, oy = 0, sc = 1, pan = null, moved = false, dirty = true;
  const VMAX = 6, FMAX = 4;  // bounded forces and speed: the layout can never blow up to Infinity/NaN
  function tick() {
    for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) { const a = N[i], b = N[j]; let dx = b.x - a.x, dy = b.y - a.y; const d2 = dx * dx + dy * dy;
      if (d2 > 62500) continue; const d = Math.sqrt(d2) || .5, f = Math.min(FMAX, 900 / Math.max(d2, 25)) * alpha;
      dx = dx / d * f; dy = dy / d * f; a.vx -= dx; a.vy -= dy; b.vx += dx; b.vy += dy; }
    for (const l of Lk) { const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y, d = Math.hypot(dx, dy) || 1;
      const k = (d - (sim(l) ? 50 : 120)) / d * (sim(l) ? .05 : .012) * alpha;  // hub springs are weak: hubs have hundreds of links
      l.s.vx += dx * k; l.s.vy += dy * k; l.t.vx -= dx * k; l.t.vy -= dy * k; }
    for (const n of N) { if (n === drag) continue; n.vx += (W / 2 - n.x) * .004 * alpha; n.vy += (H / 2 - n.y) * .004 * alpha;
      const v = Math.hypot(n.vx, n.vy); if (v > VMAX) { n.vx *= VMAX / v; n.vy *= VMAX / v; }
      n.x += n.vx; n.y += n.vy; n.vx *= .55; n.vy *= .55;
      if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) { n.x = W / 2; n.y = H / 2; n.vx = n.vy = 0; } }
    alpha = Math.max(alpha * .97, .02); dirty = true;
  }
  function fit() { const xs = N.map(n => n.x), ys = N.map(n => n.y), x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const mx = W < 600 ? 24 : 200, lab = W < 600 ? 0 : 140;  // room for labels on the right only where there is space
    sc = Math.max(.2, Math.min((W - mx) / Math.max(x1 - x0, 1), (H - 60) / Math.max(y1 - y0, 1), 2.2));
    ox = (W - lab) / 2 - (x0 + x1) / 2 * sc; oy = H / 2 - (y0 + y1) / 2 * sc; dirty = true; }
  for (let i = 0; i < 260; i++) tick();  // settle before the first frame: the user sees a calm graph, not the simulation
  alpha = .02; fit();
  const near = n => hover && (n === hover || Lk.some(l => (l.s === hover && l.t === n) || (l.t === hover && l.s === n)));
  function paint() {
    ctx.clearRect(0, 0, W, H); ctx.save(); ctx.translate(ox, oy); ctx.scale(sc, sc);
    for (const l of Lk) { const hot = hover && (l.s === hover || l.t === hover);
      ctx.strokeStyle = hot ? C("--ink") : sim(l) ? C("--red") : C("--line"); ctx.globalAlpha = hot ? .9 : sim(l) ? .55 : 1; ctx.lineWidth = (sim(l) ? 1 + l.weight * 3 : 1) / Math.sqrt(sc);
      ctx.beginPath(); ctx.moveTo(l.s.x, l.s.y); ctx.lineTo(l.t.x, l.t.y); ctx.stroke(); }
    const placed = [];  // label boxes already drawn: skip a label that would overlap (hover always wins)
    const free = (x, y, w, h) => !placed.some(b => x < b[0] + b[2] && b[0] < x + w && y < b[1] + b[3] && b[1] < y + h);
    for (const n of N) { ctx.globalAlpha = hover && !near(n) ? .28 : 1; const rr = rad(n);
      if (n.type === "idea") { ctx.beginPath(); ctx.arc(n.x, n.y, rr, 0, 7); ctx.fillStyle = C(SECTOR_SLOT[n.sector] ? `--s${SECTOR_SLOT[n.sector]}` : "--other"); ctx.fill(); ctx.lineWidth = 2 / sc; ctx.strokeStyle = C("--bg"); ctx.stroke(); }
      else { ctx.save(); ctx.shadowColor = C("--dk"); ctx.shadowBlur = 8; ctx.shadowOffsetX = 2; ctx.shadowOffsetY = 2; ctx.beginPath(); ctx.arc(n.x, n.y, rr, 0, 7); ctx.fillStyle = C("--white"); ctx.fill(); ctx.restore();
        ctx.lineWidth = 1.5 / sc; ctx.strokeStyle = C("--ink"); ctx.stroke(); const img = imgs[hubIcon(n)]; if (img && img.complete && img.naturalWidth) ctx.drawImage(img, n.x - rr * .55, n.y - rr * .55, rr * 1.1, rr * 1.1); }
      if (n.type !== "idea" || n === hover || sc > 1.4) { const fs = 12 / Math.sqrt(sc), txt = n.label.slice(0, 46);
        ctx.font = `${n.type === "idea" ? 500 : 700} ${fs}px system-ui`; const tw = ctx.measureText(txt).width, lx = n.x + rr + 5, ly = n.y - fs * .7;
        if (n === hover || free(lx, ly, tw, fs * 1.3)) { placed.push([lx, ly, tw, fs * 1.3]);
          ctx.lineJoin = "round"; ctx.lineWidth = 4 / sc; ctx.strokeStyle = C("--bg"); ctx.strokeText(txt, lx, n.y + 4);  // halo keeps labels readable over dots
          ctx.fillStyle = n.type === "idea" ? C("--ink") : C("--ink-2"); ctx.fillText(txt, lx, n.y + 4); } } }
    ctx.restore(); ctx.globalAlpha = 1;
  }
  // repaint only when something changed (drag, pan, zoom, hover, icon load): no busy loop
  (function loop() { if (drag) tick(); else if (alpha > .021) tick(); if (dirty) { paint(); dirty = false; } if (document.body.contains(cv)) requestAnimationFrame(loop); })();
  Object.values(imgs).forEach(img => img.addEventListener("load", () => dirty = true));
  const pt = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left - ox) / sc, (e.clientY - r.top - oy) / sc]; };
  const hit = (x, y) => N.find(n => (n.x - x) ** 2 + (n.y - y) ** 2 < (rad(n) + 4) ** 2);
  cv.onpointerdown = e => { const [x, y] = pt(e); drag = hit(x, y); moved = false; if (!drag) pan = [e.clientX - ox, e.clientY - oy]; cv.setPointerCapture(e.pointerId); };
  cv.onpointermove = e => { const [x, y] = pt(e);
    if (drag) { drag.x = x; drag.y = y; alpha = Math.max(alpha, .15); moved = true; } else if (pan) { ox = e.clientX - pan[0]; oy = e.clientY - pan[1]; moved = true; dirty = true; }
    else { const h = hit(x, y) || null; if (h !== hover) dirty = true; hover = h; cv.style.cursor = hover ? "pointer" : "grab"; tip(hover ? `<b>${esc(hover.label)}</b>${hover.type === "idea" ? `<br>${esc(lp("sector", hover.sector))} · ${esc(hover.voivodeship || "—")}${hover.score ? " · wynik " + Math.round(hover.score) : ""}` : `<br>${hover.deg} powiązań · kliknij, by filtrować`}` : "", e); } };
  cv.onpointerleave = () => { hover = null; dirty = true; tip(); };
  cv.onpointerup = () => { if (drag && !moved) { const n = drag; if (n.type === "idea" && n.card_id) openCard(n.card_id); else if (n.type !== "idea") go("graf", {[n.type]: n.id.split(":").slice(1).join(":")}); } drag = null; pan = null; };
  cv.onwheel = e => { e.preventDefault(); const k = e.deltaY < 0 ? 1.1 : .9, r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top; ox = mx - (mx - ox) * k; oy = my - (my - oy) * k; sc = Math.max(.15, Math.min(6, sc * k)); dirty = true; };
  const used = [...new Set(N.filter(n => n.type === "idea").map(n => SECTOR_SLOT[n.sector] ? n.sector : "_"))].sort((a, b) => (SECTOR_SLOT[a] || 9) - (SECTOR_SLOT[b] || 9));
  $("#glegend").innerHTML = used.map(s => `<span><i class="dot" style="background:${s === "_" ? "var(--other)" : secColor(s)}"></i>${esc(s === "_" ? "inne sektory" : lp("sector", s))}</span>`).join("") +
    `<span>${icon("map-pin")}hub (sektor, obszar, województwo)</span><span><i class="dot" style="background:var(--red);width:16px;height:3px;border-radius:2px"></i>podobna treść</span>`;
  // text alternative for screen readers and keyboard users: the strongest ideas and their closest neighbours
  const ideas = N.filter(n => n.type === "idea").sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, 25);
  const nb = n => Lk.filter(l => sim(l) && (l.s === n || l.t === n)).map(l => (l.s === n ? l.t : l.s).label).slice(0, 2);
  $("#gtext").innerHTML = `<details class="how"><summary>${icon("layers")}Graf jako lista (${ideas.length} najlepszych)</summary><div class="items" style="margin-top:.75rem">${ideas.map(n =>
    `<div class="item" tabindex="0" data-card="${n.card_id}">${avatar(SECTOR_ICON[n.sector] || "lightbulb")}<h3>${esc(n.label)}</h3>${ring(n.score, "sm")}<div class="plates">${n.voivodeship ? plate("map-pin", n.voivodeship, "", "sm red") : ""}${nb(n).map(t => plate("git-compare-arrows", t.slice(0, 40), "", "sm")).join("")}</div></div>`).join("")}</div></details>`;
  bindCards($("#gtext"));
}

// ------------------------------------------------------------------ ROLKI (component-built briefs)
let voter; try { voter = localStorage.getItem("radar-voter") || crypto.randomUUID(); localStorage.setItem("radar-voter", voter); } catch (e) { voter = "anon-" + Math.random().toString(36).slice(2, 12); }
let liked = new Set(); try { liked = new Set(JSON.parse(localStorage.getItem("radar-liked") || "[]")); } catch (e) {}
const saveLiked = () => { try { localStorage.setItem("radar-liked", JSON.stringify([...liked])); } catch (e) {} };
// ------------------------------------------------------------------ ŹRÓDŁA (operator)
async function pageSources(v) {
  const tab = F.tab || "zrodla";
  const T = {zrodla: ["Źródła danych", "radar"], kolejka: ["Decyzje", "inbox"], przeglad: ["Do przeglądu", "shield-alert"], liczniki: ["Potok i liczniki", "activity"], reczne: ["Dodaj ręcznie", "lightbulb"]};
  v.innerHTML = header("Panel operatora PCI", "activity", "Źródła, potok i decyzje", "Radar sam pobiera dane z baz publicznych. Tu widać, co pobrał, co odsiał i co czeka na decyzję.") +
    `<div class="chips reveal" style="margin-bottom:1.5rem">${Object.entries(T).map(([k, [n, ic]]) => `<button class="chip ${k === tab ? "on" : ""}" data-tab="${k}">${icon(ic)}${n}</button>`).join("")}</div><div id="op"></div>`;
  $$("[data-tab]", v).forEach(b => b.onclick = () => go("zrodla", {tab: b.dataset.tab}));
  const op = $("#op");
  if (tab === "zrodla") {
    const src = await api("/api/sources");
    const kindIcon = t => ({oaipmh: "book-open", rest: "network", graphql: "network", sparql: "network", snapshot: "layers", webhook: "zap", amqp: "zap", gcp_pubsub: "zap", kafka: "zap"}[t] || "radar");
    op.innerHTML = `<div class="grid g-2">${src.map(s => `<div class="card reveal">${cardH(kindIcon(s.type), esc(s.id), esc(s.description), s.mode === "pull" && s.active ? `<button class="btn-soft" data-run="${esc(s.id)}">${icon("radar")}Pobierz</button>` : "", s.active)}
      <div class="card-b"><div class="plates">${plate("layers", s.records + " rekordów", "", "sm")}${plate(s.mode === "pull" ? "clock" : "zap", s.mode === "pull" ? (s.schedule_s ? "co " + Math.round(s.schedule_s / 3600) + " h" : "ręcznie") : "push", "", "sm")}
      ${plate(s.last_status === "failed" ? "ban" : s.last_run_at ? "circle-check" : "clock", s.last_run_at ? new Date(s.last_run_at).toLocaleString("pl-PL") : "jeszcze nie pobierano", "", "sm " + (s.last_status === "failed" ? "red" : ""))}${s.active ? "" : plate("eye-off", "wyłączone", "", "sm")}${s.demo ? plate("flask-conical", "przykład", "", "sm") : ""}</div>
      ${s.last_error ? `<p class="faint" style="color:var(--red)">${esc(s.last_error)}</p>` : ""}</div></div>`).join("")}</div>`;
    $$("[data-run]", op).forEach(b => b.onclick = async () => { b.disabled = true; b.innerHTML = icon("clock") + "Pobieram…"; try { await api(`/api/sources/${b.dataset.run}/run`, {method: "POST"}); } catch (e) { alert(e); } setTimeout(route, 3000); });
  } else if (tab === "kolejka") {
    const cards = (await api("/api/cards?decision=pending&limit=200")).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    op.innerHTML = `<div class="card">${cardH("inbox", cards.length + " kart czeka na decyzję", "od najlepszych")}<div class="card-b"><div class="items">${cards.map(c => ideaItem({card_id: c.id, title: c.solution_name || c.record.title, score: c.score, sector: c.record.sector, maturity: c.maturity, voivodeship: c.record.voivodeship, synthetic: c.synthetic})).join("") || empty("Kolejka jest pusta.")}</div></div></div>`;
  } else if (tab === "przeglad") {
    const rows = await api("/api/review");
    op.innerHTML = `<div class="card">${cardH("shield-alert", rows.length + " rekordów do przeglądu", "Basal wstrzymał albo walidacja nie przeszła")}<div class="card-b"><table class="t"><tr><th>Źródło</th><th>Tytuł</th><th>Powód</th></tr>${rows.map(r => `<tr><td class="mono">${esc(r.source_id)}</td><td>${esc(r.title)}</td><td class="faint">${esc((r.reasons || []).join("; "))}</td></tr>`).join("")}</table></div></div>`;
  } else if (tab === "liczniki") {
    const s = await api("/api/stats"), order = ["normalize", "resolve_org", "dedup", "gate", "link", "extract", "maturity", "score"];
    const stIcon = {normalize: "filter", resolve_org: "building-2", dedup: "copy", gate: "shield-alert", link: "network", extract: "bot", maturity: "gauge", score: "target"};
    op.innerHTML = `<div class="grid g-4">${order.map(st => { const x = s.stages[st] || {}, ok = x.ok || 0, other = Object.entries(x).filter(([k]) => k !== "ok");
      return `<div class="card stat reveal">${avatar(stIcon[st])}<div><b>${ok}</b><span>${st}${other.length ? " · " + other.map(([k, n]) => k + " " + n).join(", ") : ""}</span></div></div>`; }).join("")}</div>
      <div class="grid g-2" style="margin-top:1.5rem"><div class="card">${cardH("layers", "Rekordy według statusu", "")}<div class="card-b"><div class="plates">${Object.entries(s.records_by_status).map(([k, n]) => plate("layers", k + " · " + n, "", "sm")).join("")}</div></div></div>
      <div class="card">${cardH("bot", "Basal uczy się od operatora", "regresja logistyczna na decyzjach zatwierdź / odrzuć")}<div class="card-b"><button class="btn-soft" id="train">${icon("sparkles")}Ucz Basala</button><p class="faint" id="trainres"></p>
      <p class="faint">Metryki Prometheus: <a href="/metrics">/metrics</a></p></div></div></div>`;
    $("#train").onclick = async () => { const r = await api("/api/basal/train", {method: "POST"}); $("#trainres").textContent = r.trained ? `Wytrenowano na ${r.n} decyzjach, trafność ${r.train_acc}.` : r.reason; };
  } else {
    op.innerHTML = `<div class="grid g-2"><div class="card reveal">${cardH("lightbulb", "Dodaj pomysł ręcznie", "uzupełnienie automatycznego radaru, np. z rozmowy z instytucją")}<div class="card-b">
      <form id="sf" style="display:flex;flex-direction:column;gap:1rem"><label class="f">Tytuł<input name="title" required></label><label class="f">Opis: problem, rozwiązanie, co działa<textarea name="description" rows="5" required></textarea></label>
      <label class="f">Instytucja<input name="institution"></label><div class="grid g-2"><label class="f">Typ instytucji<select name="institution_type"><option value="">—</option><option>szkoła</option><option>uczelnia</option><option>instytut</option><option>JST</option><option>inna instytucja publiczna</option></select></label>
      <label class="f">Województwo<select name="region"><option value="">—</option>${(LABELS.voivodeship || []).map(x => `<option>${esc(x)}</option>`).join("")}</select></label></div><div><button class="btn" type="submit">${icon("arrow-right")}Wyślij do radaru</button></div><div id="sres"></div></form></div></div>
      <div class="card reveal">${cardH("shield-alert", "Podgląd Basala", "na żywo, bez LLM")}<div class="card-b" id="preview"><p class="faint">Zacznij pisać.</p></div></div></div>`;
    const f = $("#sf"), data = () => Object.fromEntries(new FormData(f).entries());
    const AX = {sector: ["Sektor", "factory"], tech_area: ["Obszar", "cpu"], innovation_type: ["Typ", "lightbulb"], institution_type: ["Instytucja", "building-2"], maturity_hint: ["Dojrzałość", "gauge"], cost_level: ["Koszt", "banknote"], voivodeship: ["Region", "map-pin"]};
    f.oninput = debounce(async () => { const d = data(); if (!d.title || !d.description) return;
      const b = await api("/api/basal/classify", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(d)});
      const dec = {accept: ["Przyjęte", "circle-check"], hold: ["Do przeglądu", "shield-alert"], reject: ["Odrzucone", "ban"]}[b.decision];
      $("#preview").innerHTML = `<div class="plates" style="margin-bottom:1rem">${plate(dec[1], dec[0], "decyzja", b.decision === "reject" ? "red" : "")}${plate("trending-up", Math.round(b.priority * 100) + "/100", "priorytet")}</div>
        ${b.reject_reasons.length ? `<p style="color:var(--red)">${esc(b.reject_reasons.join("; "))}</p>` : ""}
        <div class="plates">${Object.entries(AX).map(([a, [nm, ic]]) => { const x = b[a], val = a === "maturity_hint" ? LVL[LVLK[x.value]] : a === "voivodeship" ? x.value : a === "institution_type" ? INST_PL[x.value] : lp(a, x.value);
          return val ? plate(ic, `${val} · ${Math.round(x.confidence * 100)}%`, nm) : ""; }).join("")}</div>`; }, 350);
    f.onsubmit = async e => { e.preventDefault(); try { const r = await api("/api/ingest/zgloszenia/manual", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(data())});
      $("#sres").innerHTML = `<p class="muted">${icon("circle-check")} Przyjęto${r.new ? "" : " (bez zmian)"}.</p>`; f.reset(); } catch (err) { $("#sres").innerHTML = `<p style="color:var(--red)">${esc(err)}</p>`; } };
  }
  bindCards(op); stagger(op);
}

// ------------------------------------------------------------------ AUDIENCES ("Dla mnie")
let PERSONAS = null;
const heroImg = key => `/static/hero/${key}.webp`;  // Higgsfield-generated backgrounds; the page works without them
const short = (t, n) => { t = t.split(":")[0]; return t.length <= n ? t : t.slice(0, t.lastIndexOf(" ", n)) + "…"; };
async function audienceTiles() {
  PERSONAS = PERSONAS || await api("/api/personas");
  return `<section class="who reveal"><p class="pretitle">${icon("users")}Kim jesteś?</p><div class="who-grid">${PERSONAS.map(p =>
    `<a class="who-tile" href="#/dla/${p.key}" style="--hero:url('${heroImg(p.key)}')">${avatar(p.icon, "red")}<b>${esc(p.name)}</b><span>${esc(short(p.promise, 72))}</span>${icon("arrow-right", "go")}</a>`).join("")}</div></section>`;
}
// headline value: licence / spin-off for a technology, adopters' savings for an openly transferred way of working
const headVal = (b, inv) => b?.valuation?.open_model ? [b.valuation.public_value_3y_pln, b.valuation.headline]
  : [inv?.adjusted?.licence_or_spinoff_pln ?? b?.valuation?.licence_or_spinoff_pln ?? 0, "wartość licencji / spin-off"];
const METRIC_PL = {licence_or_spinoff_pln: "wartość licencji / spin-off", savings_per_adopter_pln: "oszczędność na odbiorcę", royalty_3y_pln: "tantiemy w 3 lata",
  som_3y_pln: "rynek osiągalny w 3 lata", deploy_cost_pln: "koszt wdrożenia"};
const money = n => n == null ? "—" : n >= 1e9 ? (n / 1e9).toLocaleString("pl-PL", {maximumFractionDigits: 1}) + " mld zł" : pln(n);
async function pageAudience(v) {
  const key = F._sub;
  if (!key) { v.innerHTML = header("Dla mnie", "users", "Radar dopasowany do Ciebie", "Wybierz, kim jesteś. Pokażemy pomysły, które mają dla Ciebie sens biznesowy, z wyceną i pierwszym krokiem.") + await audienceTiles(); return; }
  const d = await api("/api/personas/" + key + (F.voivodeship ? "?voivodeship=" + encodeURIComponent(F.voivodeship) : ""));
  const s = d.summary;
  v.innerHTML = `<section class="aud-hero reveal" style="--hero:url('${heroImg(key)}')"><div class="aud-in"><p class="pretitle">${icon(d.icon)}${esc(d.name)}</p>
      <h1>${esc(d.promise.split(":")[0])}</h1><p class="lead">${esc(d.promise.split(":").slice(1).join(":") || d.promise)}</p>
      <div class="plates">${plate("lightbulb", s.ideas + " pomysłów")}${plate("banknote", money(s.metric_sum_pln), METRIC_PL[d.metric])}${plate("trending-up", money(s.som_3y_sum_pln), "rynek w 3 lata")}${plate("map-pin", s.regions + " województw", "", "red")}</div></div></section>
    <div class="chips reveal" style="margin:1.5rem 0">${(PERSONAS || await api("/api/personas")).map(p => `<a class="chip ${p.key === key ? "on" : ""}" href="#/dla/${p.key}">${icon(p.icon)}${esc(p.name.split(" ")[0])}</a>`).join("")}</div>
    <div class="grid g-2">${d.items.map(i => bizCard(i, d)).join("") || empty("Brak dopasowanych pomysłów.")}</div>`;
  bindCards(v);
}
function bizCard(i, d) {
  const b = i.business, lvl = LVLK[i.maturity] ?? 0;
  return `<article class="card biz reveal" data-card="${i.card_id}" tabindex="0"><div class="card-h">${avatar(SECTOR_ICON[i.sector] || "lightbulb")}<div><h3>${esc(i.title)}</h3><div class="faint">${esc(i.institution || "")}</div></div>${ring(i.score, "sm")}</div>
    <div class="card-b"><div class="biz-value"><small>${esc(METRIC_PL[d.metric] || "wartość")}</small><b>${money(b.metric)}</b></div>
      <div class="plates">${locPlate(i, "sm")}${plate("banknote", money(b.deploy_cost_pln), "", "sm")}${plate("users", b.adopters.count.toLocaleString("pl-PL") + " odbiorców", "", "sm")}${plate("clock", b.payback, "", "sm")}<span class="plate sm"><span class="pi">${icon("gauge")}</span>${stepper(lvl)}</span></div>
      ${b.funding.length ? `<div class="plates" style="margin-top:.5rem">${b.funding.map(f => plate("piggy-bank", f, "", "sm")).join("")}</div>` : ""}
      <div class="biz-cta">${icon("arrow-right")}${esc(d.cta)}</div></div></article>`;
}
function bizSection(b) {
  if (!b) return "";
  const m = b.market, max = Math.max(m.tam_pln, 1), bar = (lab, val, cls) => `<div class="mk"><span>${lab}</span><div class="mini"><i style="width:${Math.max(2, val / max * 100)}%"></i></div><b class="mono">${money(val)}</b></div>`;
  return `<div class="sec"><p class="pretitle">${icon("briefcase")}Model biznesowy i wycena</p>
    <div class="biz-kpis">${[["banknote", money(b.deploy_cost_pln), "koszt wdrożenia u odbiorcy"], ["trending-up", money(headVal(b)[0]), headVal(b)[1]],
      ["piggy-bank", money(b.savings_per_adopter_pln), "oszczędność vs budowa od zera"], ["clock", b.payback, "zwrot"]].map(([ic, v, t]) => `<div class="tile">${icon(ic)}<div><small>${t}</small><b>${v}</b></div></div>`).join("")}</div>
    <div class="market">${bar("TAM (cały rynek)", m.tam_pln)}${bar("SAM (region)", m.sam_pln)}${bar("SOM (3 lata)", m.som_3y_pln)}</div>
    <div class="plates" style="margin-top:.75rem">${plate("users", b.adopters.count.toLocaleString("pl-PL") + " " + b.adopters.who)}${plate("briefcase", b.model)}${b.funding.map(f => plate("piggy-bank", f.programme, f.for)).join("")}</div>
    <details class="how"><summary>${icon("filter")}Założenia wyceny (bez AI, jawne reguły)</summary><ul class="steps" style="margin-top:.5rem">${b.assumptions.map(a => `<li>${icon("chevron-right")}<span>${esc(a)}</span></li>`).join("")}</ul></details></div>`;
}

// ------------------------------------------------------------------ PERSONALIZATION ("Dopasuj radar")
// ------------------------------------------------------------------ DEAL FLOW (investor pipeline), COMPARE, DEPLOYMENTS
const STAGES_D = [["nowe", "Nowe", "inbox"], ["kontakt", "Kontakt", "users"], ["dd", "Due diligence", "shield-alert"], ["term", "Term sheet", "file-text"], ["odrzucone", "Odrzucone", "ban"]];
const loadJSON = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? d; } catch (e) { return d; } };
const saveJSON = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
let DEALS = loadJSON("radar-deals", {}), CMP = loadJSON("radar-compare", []);
const saveDeals = () => saveJSON("radar-deals", DEALS), saveCmp = () => saveJSON("radar-compare", CMP);
const STRENGTH_PL = {none: "brak śladów", weak: "patenty instytucji", medium: "zgłoszenie / wynalazek", strong: "patent udzielony"};

function dealActions(c) {
  const inDeals = !!DEALS[c.id], inCmp = CMP.includes(c.id);
  return `<div class="chips deal-actions" style="margin-top:1rem">
    <button class="btn" id="adeal">${icon(inDeals ? "check" : "plus")}${inDeals ? "W portfelu" : "Do portfela"}</button>
    <button class="btn-soft" id="acmp">${icon("git-compare-arrows")}${inCmp ? "W porównaniu" : "Porównaj"}${CMP.length ? ` (${CMP.length})` : ""}</button>
    <a class="btn-soft" href="/api/cards/${c.id}/memo" target="_blank" rel="noopener">${icon("file-text")}Memo PDF</a>
    <a class="btn-soft" href="/api/cards/${c.id}/memo?kind=wykonawca" target="_blank" rel="noopener">${icon("handshake")}Specyfikacja wdrożenia</a></div>`;
}
function bindDealActions(c) {
  const val = headVal(c.business, c.investor)[0];
  $("#adeal").onclick = () => { if (DEALS[c.id]) delete DEALS[c.id]; else DEALS[c.id] = {stage: "nowe", title: c.solution_name || c.record.title, value: val,
      readiness: c.investor?.readiness?.score ?? null, org: (c.record.affiliations || [])[0] || "", voivodeship: c.record.voivodeship, note: "", at: new Date().toISOString().slice(0, 10)};
    saveDeals(); $(".deal-actions").outerHTML = dealActions(c); bindDealActions(c); };
  $("#acmp").onclick = () => { CMP = CMP.includes(c.id) ? CMP.filter(x => x !== c.id) : [...CMP, c.id].slice(-4); saveCmp();
    if (CMP.length >= 2 && CMP.includes(c.id)) { closeCard(); go("porownaj", {ids: CMP.join(",")}); return; }
    $(".deal-actions").outerHTML = dealActions(c); bindDealActions(c); };
}
function investorSection(inv, b) {
  if (!inv) return "";
  const r = inv.readiness, t = inv.traction, ip = inv.ip, cp = inv.comparables, adj = inv.adjusted;
  const parts = Object.entries(r.parts), maxp = {"dojrzałość": 35, "ochrona IP": 20, "trakcja": 20, "zespół": 10, "ścieżka komercjalizacji": 15};
  return `<div class="sec"><p class="pretitle">${icon("trending-up")}Dla inwestora · gotowość inwestycyjna</p>
    <div class="inv-top">${ring(r.score)}<div><b>${esc(r.label)}</b><div class="inv-parts">${parts.map(([k, x]) => `<span>${esc(k)}</span><div class="mini"><i style="width:${x / (maxp[k] || 20) * 100}%"></i></div><b class="mono">${x}/${maxp[k] || 20}</b>`).join("")}</div></div></div>
    <div class="plates" style="margin-top:.75rem">${plate("shield-alert", STRENGTH_PL[ip.strength], "ochrona IP")}${plate("coins", t.grants ? money(t.public_funding_pln) + " w " + t.grants + " proj." : "brak w bazie", "trakcja instytucji")}
      ${inv.team.people ? plate("users", inv.team.people + " os." + (inv.team.prior_records ? ", " + inv.team.prior_records + " innych prac" : ""), "zespół") : ""}${inv.commercial.route ? plate("briefcase", inv.commercial.route, "komercjalizacja") : ""}
      ${cp.median_pln ? plate("git-compare-arrows", money(cp.median_pln), "mediana podobnych projektów") : ""}</div>
    ${b?.valuation?.open_model ? `<p class="faint" style="margin-top:.75rem">${icon("handshake")} Model działania przekazywany otwarcie (zwykle z pieniędzy publicznych): bez licencji do sprzedaży. Dla inwestora to raczej usługa wdrożeniowa niż udziały.</p>` : ""}
    ${adj?.reasons?.length && !b?.valuation?.open_model ? `<p class="faint" style="margin-top:.75rem">${icon("sparkles")} Wycena po dowodach: <b>${money(adj.licence_or_spinoff_pln)}</b> (szansa ${Math.round(adj.success_probability * 100)}%) · ${esc(adj.reasons.join("; "))}</p>` : ""}
    ${cp.items.length ? `<details class="how"><summary>${icon("layers")}Porównywalne zrealizowane projekty (${cp.items.length})</summary><div class="items" style="margin-top:.5rem">${cp.items.map(x => `<div class="item" data-card="${x.card_id || ""}">${avatar("copy")}<h3>${esc(x.title)}</h3><span class="plate sm"><span class="pi">${icon("banknote")}</span>${money(x.amount)}</span><div class="plates">${x.voivodeship ? plate("map-pin", x.voivodeship, "", "sm red") : ""}${x.year ? plate("clock", String(x.year), "", "sm") : ""}</div></div>`).join("")}</div></details>` : ""}</div>`;
}

async function pageDeals(v) {
  DEALS = loadJSON("radar-deals", {}); CMP = loadJSON("radar-compare", []);
  const ids = Object.keys(DEALS);
  const total = st => ids.filter(i => DEALS[i].stage === st).reduce((a, i) => a + (DEALS[i].value || 0), 0);
  v.innerHTML = header("Portfel inwestora", "kanban", "Twój lejek transakcji", "Dodawaj pomysły z karty („Do portfela”), przesuwaj między etapami, zapisuj notatki. Dane zostają w tej przeglądarce.",
      `<div class="chips"><a class="btn" href="#/dopasuj">${icon("target")}Znajdź pomysły</a>${CMP.length >= 2 ? `<a class="btn-soft" href="#/porownaj?ids=${CMP.join(",")}">${icon("git-compare-arrows")}Porównaj (${CMP.length})</a>` : ""}</div>`) +
    (ids.length ? `<div class="kanban">${STAGES_D.map(([k, lab, ic]) => `<section class="kcol reveal" data-st="${k}" aria-label="${lab}"><div class="kcol-h">${icon(ic)}<b>${lab}</b><span class="faint">${ids.filter(i => DEALS[i].stage === k).length} · ${money(total(k))}</span></div>
      <div class="kcol-b">${ids.filter(i => DEALS[i].stage === k).map(i => { const d = DEALS[i], si = STAGES_D.findIndex(s => s[0] === k);
        return `<article class="kcard" draggable="true" data-id="${i}" tabindex="0"><h3 data-card="${i}">${esc(d.title)}</h3><div class="faint">${esc(d.org)}</div>
          <div class="plates">${plate("banknote", money(d.value), "", "sm")}${d.readiness != null ? plate("gauge", d.readiness + "/100", "", "sm") : ""}${d.voivodeship ? plate("map-pin", d.voivodeship, "", "sm red") : ""}</div>
          <textarea class="knote" data-id="${i}" rows="2" placeholder="notatka: kontakt, termin, warunki">${esc(d.note)}</textarea>
          <div class="kmove"><button class="btn-icon" data-mv="-1" data-id="${i}" ${si === 0 ? "disabled" : ""} aria-label="Poprzedni etap">${icon("chevron-left")}</button><span class="faint">od ${esc(d.at)}</span><button class="btn-icon" data-mv="1" data-id="${i}" ${si === STAGES_D.length - 1 ? "disabled" : ""} aria-label="Następny etap">${icon("chevron-right")}</button></div></article>`; }).join("")}</div></section>`).join("")}</div>`
      : empty("Portfel jest pusty. Otwórz kartę pomysłu i kliknij „Do portfela”.", `<a class="btn" href="#/dla/inwestorzy">${icon("trending-up")}Pomysły dla inwestorów</a>`));
  $$("[data-mv]", v).forEach(b => b.onclick = () => { const d = DEALS[b.dataset.id], i = STAGES_D.findIndex(s => s[0] === d.stage) + +b.dataset.mv; d.stage = STAGES_D[Math.max(0, Math.min(STAGES_D.length - 1, i))][0]; saveDeals(); route(); });
  $$(".knote", v).forEach(t => t.oninput = debounce(() => { DEALS[t.dataset.id].note = t.value; saveDeals(); }, 300));
  $$(".kcard", v).forEach(c => c.ondragstart = e => e.dataTransfer.setData("text/plain", c.dataset.id));
  $$(".kcol", v).forEach(col => { col.ondragover = e => { e.preventDefault(); col.classList.add("over"); }; col.ondragleave = () => col.classList.remove("over");
    col.ondrop = e => { e.preventDefault(); const id = e.dataTransfer.getData("text/plain"); if (DEALS[id]) { DEALS[id].stage = col.dataset.st; saveDeals(); route(); } }; });
  $$("h3[data-card]", v).forEach(h => h.onclick = () => openCard(+h.dataset.card));
}

async function pageCompare(v) {
  const ids = (F.ids || CMP.join(",")).split(",").filter(Boolean).map(Number).slice(0, 4);
  if (ids.length < 2) { v.innerHTML = header("Porównanie", "git-compare-arrows", "Wybierz 2–4 pomysły", "") + empty("Otwórz kartę pomysłu i kliknij „Porównaj” przy co najmniej dwóch.", `<a class="btn" href="#/dopasuj">${icon("target")}Dopasuj radar</a>`); return; }
  const cs = await Promise.all(ids.map(i => api("/api/cards/" + i)));
  const rows = [
    ["Dojrzałość", c => LVLK[c.maturity] ?? 0, x => LVL[x], "max"],
    ["Gotowość inwestycyjna", c => c.investor?.readiness?.score ?? 0, x => x + "/100", "max"],
    ["Ocena radaru", c => c.assessment?.total ?? c.score ?? 0, x => Math.round(x) + "/100", "max"],
    ["Wartość (licencja albo oszczędność odbiorców)", c => headVal(c.business, c.investor)[0], money, "max"],
    ["Szansa wdrożenia", c => c.investor?.adjusted?.success_probability ?? c.business?.valuation?.success_probability ?? 0, x => Math.round(x * 100) + "%", "max"],
    ["Koszt wdrożenia", c => c.business?.deploy_cost_pln ?? 0, money, "min"],
    ["Rynek 3 lata (SOM)", c => c.business?.market?.som_3y_pln ?? 0, money, "max"],
    ["TAM", c => c.business?.market?.tam_pln ?? 0, money, "max"],
    ["Odbiorcy", c => c.business?.adopters?.count ?? 0, x => x.toLocaleString("pl-PL"), "max"],
    ["Zwrot", c => ({"< 1 rok": 1, "1–2 lata": 2, "3–5 lat": 4})[c.business?.payback] ?? 9, x => ({1: "< 1 rok", 2: "1–2 lata", 4: "3–5 lat"})[x] || "—", "min"],
    ["Ochrona IP", c => ({none: 0, weak: 1, medium: 2, strong: 3})[c.investor?.ip?.strength] ?? 0, x => ["brak", "patenty instytucji", "zgłoszenie", "patent"][x], "max"],
    ["Trakcja (środki publiczne)", c => c.investor?.traction?.public_funding_pln ?? 0, money, "max"],
    ["Ryzyka", c => (c.assessment?.risks || []).length, x => x + " zidentyfikowanych", "min"],
  ];
  v.innerHTML = header("Porównanie", "git-compare-arrows", `${cs.length} pomysły obok siebie`, "Najlepsza wartość w każdym wierszu jest wyróżniona.",
      `<div class="chips"><button class="btn-soft" id="cclear">${icon("x")}Wyczyść</button></div>`) +
    `<div class="cmp reveal" style="--n:${cs.length}"><div class="cmp-row cmp-head"><span></span>${cs.map(c => `<div class="cmp-h" data-card="${c.id}">${avatar(SECTOR_ICON[c.record.sector] || "lightbulb")}<b>${esc(short(c.solution_name || c.record.title, 70))}</b><span class="faint">${esc((c.record.affiliations || [])[0] || "")}</span></div>`).join("")}</div>
    ${rows.map(([lab, f, fmt, best]) => { const vals = cs.map(f), b = best === "max" ? Math.max(...vals) : Math.min(...vals);
      return `<div class="cmp-row"><span class="cmp-l">${lab}</span>${vals.map(x => `<span class="cmp-v ${x === b && vals.filter(y => y === b).length < vals.length ? "best" : ""}"><small>${lab}</small>${esc(fmt(x))}</span>`).join("")}</div>`; }).join("")}
    <div class="cmp-row"><span class="cmp-l">Finansowanie</span>${cs.map(c => `<span class="cmp-v"><small>Finansowanie</small>${esc((c.business?.funding || []).slice(0, 2).map(f => f.programme).join("; ") || "—")}</span>`).join("")}</div>
    <div class="cmp-row"><span class="cmp-l">Memo</span>${cs.map(c => `<span class="cmp-v"><a class="btn-soft" href="/api/cards/${c.id}/memo" target="_blank" rel="noopener">${icon("file-text")}PDF</a></span>`).join("")}</div></div>`;
  $("#cclear").onclick = () => { CMP = []; saveCmp(); go("porownaj", {}); };
  bindCards(v);
}

async function pageDeploy(v) {
  const side = F.side || "odbiorca", prof = loadProfile() || {};
  const woj = F.voivodeship ?? prof.voivodeship ?? "", sectors = F.sectors ?? (prof.sectors || []).join(","), budget = F.budget || prof.budget || "wysoki";
  const d = await api("/api/deployments?" + qs({side, voivodeship: woj, sectors, budget, limit: 12}));
  const tabs = `<div class="chips"><button class="chip ${side === "odbiorca" ? "on" : ""}" data-side="odbiorca">${icon("landmark")}Szukam rozwiązania (gmina, szkoła, szpital)</button><button class="chip ${side === "wykonawca" ? "on" : ""}" data-side="wykonawca">${icon("briefcase")}Wdrażam i sprzedaję (wykonawca)</button></div>`;
  const filters = `<div class="chips" style="margin:1rem 0"><select id="dwoj" class="chip" aria-label="Województwo"><option value="">Cała Polska</option>${(LABELS.voivodeship || []).map(x => `<option ${x === woj ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
    <select id="dbud" class="chip" aria-label="Budżet">${[["niski", "do 100 tys. zł"], ["sredni", "do 2 mln zł"], ["wysoki", "do 20 mln zł"], ["bardzo_wysoki", "bez limitu"]].map(([k, l]) => `<option value="${k}" ${k === budget ? "selected" : ""}>${l}</option>`).join("")}</select>
    ${sectors ? `<span class="plate sm">${icon("filter")}${esc(sectors.split(",").map(s => lp("sector", s).split(",")[0]).join(", "))}</span><button class="chip" id="dall">${icon("x")}wszystkie sektory</button>` : ""}</div>`;
  const item = i => `<article class="card biz reveal" data-card="${i.card_id}" tabindex="0"><div class="card-h">${avatar(SECTOR_ICON[i.sector] || "lightbulb")}<div><h3>${esc(i.title)}</h3><div class="faint">${esc(i.institution || "")}</div></div>${ring(i.score, "sm")}</div>
    <div class="card-b"><div class="biz-value"><small>${side === "wykonawca" ? "oszczędność dla klienta" : "koszt wdrożenia u Ciebie"}</small><b>${money(side === "wykonawca" ? i.savings_pln : i.deploy_cost_pln)}</b></div>
      <div class="plates">${locPlate(i, "sm")}${plate("clock", i.payback, "", "sm")}${i.funding.slice(0, 2).map(f => plate("piggy-bank", f, "", "sm")).join("")}</div>
      <p class="pretitle" style="margin:.75rem 0 .25rem">${icon("handshake")}Kto może wdrożyć</p><div class="plates">${i.implementers.map(o => plate(o.role === "twórca" ? "lightbulb" : "briefcase", short(o.name, 48) + (o.voivodeship ? " · " + o.voivodeship : ""), o.role, "sm")).join("")}</div>
      <div class="biz-cta"><a href="/api/cards/${i.card_id}/memo?kind=wykonawca" target="_blank" rel="noopener" onclick="event.stopPropagation()">${icon("file-text")}Specyfikacja wdrożenia</a></div></div></article>`;
  if (side === "wykonawca") {
    const maxr = Math.max(1, ...d.regions.map(r => r.revenue_3y_pln));
    v.innerHTML = header("Wdrożenia", "handshake", "Gdzie sprzedać gotowe rozwiązania", "Potencjał przychodu w 3 lata = odbiorcy w województwie (GUS) × koszt wdrożenia × realna adopcja. Mniej lokalnej podaży = łatwiej wejść.") + tabs + filters +
      `<div class="grid g-7-5"><div class="card reveal"><div class="card-b"><div id="dmap"></div></div></div><div class="card reveal">${cardH("trending-up", "Najlepsze rynki", "przychód 3 lata / lokalna konkurencja")}<div class="card-b"><div class="items">${d.regions.slice(0, 8).map(r => `<div class="item">${avatar("map-pin")}<h3>${esc(r.voivodeship)}</h3><span class="plate sm red"><span class="pi">${icon("banknote")}</span>${money(r.revenue_3y_pln)}</span><div class="plates">${plate("users", r.adopters.toLocaleString("pl-PL") + " odbiorców", "", "sm")}${plate("layers", r.local_supply + " lokalnych rozwiązań", "", "sm")}</div></div>`).join("")}</div></div></div></div>
      <h2 class="reveal" style="margin:2rem 0 1rem">Rozwiązania do licencji i wdrażania</h2><div class="grid g-2">${d.items.map(item).join("") || empty("Brak gotowych rozwiązań dla tych filtrów.")}</div>`;
    await drawPoland($("#dmap"), {regions: d.regions.map(r => ({voivodeship: r.voivodeship, selected: Math.round(r.revenue_3y_pln / maxr * 100), gap: 0, top_sectors: []}))},
      {compact: true, unit: "= najwyższy potencjał", onPick: name => go("wdrozenia", {...F, side, voivodeship: name})});
  } else {
    v.innerHTML = header("Wdrożenia", "handshake", "Gotowe rozwiązania dla Twojej instytucji", "Tylko sprawdzone (gotowe do wdrożenia lub na rynku): koszt, zwrot, kto wdroży i z jakiego programu sfinansować.") + tabs + filters +
      `<div class="grid g-2">${d.items.map(item).join("") || empty("Brak gotowych rozwiązań dla tych filtrów. Zwiększ budżet albo wybierz całą Polskę.")}</div>`;
  }
  $$("[data-side]", v).forEach(b => b.onclick = () => go("wdrozenia", {...F, side: b.dataset.side}));
  $("#dwoj").onchange = e => go("wdrozenia", {...F, side, voivodeship: e.target.value});
  $("#dbud").onchange = e => go("wdrozenia", {...F, side, budget: e.target.value});
  if ($("#dall")) $("#dall").onclick = () => go("wdrozenia", {...F, side, sectors: ""});
  bindCards(v);
}

// ------------------------------------------------------------------ CARD drawer
// ------------------------------------------------------------------ command bar (+ voice where supported)
const cmd = $("#cmd"), cq = $("#cmdq");
let cmdOpener = null;  // Escape returns focus to whatever opened the search
function openCmd() { if (!cmd.classList.contains("on")) cmdOpener = document.activeElement; cmd.classList.add("on"); cq.value = ""; cq.focus();
  $("#hints").innerHTML = [["seniorzy", "users"], ["smog", "wifi"], ["kompozyty", "layers"], ["wodór", "zap"], ["e-usługi", "monitor"], ["edukacja", "book-open"]].map(([h, ic]) => `<button class="chip" data-h="${h}">${icon(ic)}${h}</button>`).join("");
  $$("[data-h]", cmd).forEach(b => b.onclick = () => search(b.dataset.h)); }
function closeCmd() { if (!cmd.classList.contains("on")) return; cmd.classList.remove("on"); const o = cmdOpener; cmdOpener = null; if (o && o.focus && document.body.contains(o)) o.focus(); }
function search(q) { cmd.classList.remove("on"); cmdOpener = null; go("odkrywaj", {q}); }
$("#cmdbtn").onclick = openCmd; cmd.onclick = e => { if (e.target === cmd) closeCmd(); };
cq.onkeydown = e => { if (e.key === "Enter" && cq.value.trim()) search(cq.value.trim()); if (e.key === "Escape") closeCmd(); };
document.addEventListener("keydown", e => { if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); openCmd(); } if (e.key === "Escape") { closeCard(); closeCmd(); } });
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) { const mic = $("#mic"); mic.hidden = false; mic.innerHTML = icon("mic"); mic.onclick = () => { const r = new SR(); r.lang = "pl-PL"; mic.classList.add("on");
  r.onresult = e => { const t = e.results[0][0].transcript; cq.value = t; search(t); }; r.onend = () => mic.classList.remove("on"); r.start(); }; }

// ------------------------------------------------------------------ boot
// Inline the icon sprite once: <use> on same-document symbols works everywhere (external sprites do not).
const SPRITE = fetch("/static/icons.svg?v=4").then(r => r.text()).then(t => { const d = document.createElement("div"); d.hidden = true; d.innerHTML = t; document.body.prepend(d); }).catch(() => {});
Promise.all([SPRITE, api("/api/config").then(c => CFG = c).catch(() => {}), api("/api/labels").then(l => LABELS = l).catch(() => {})]).then(() => {
  $("#foot").innerHTML = `<nav class="foot-nav"><a href="#/klastry">${icon("component")}Klastry</a><a href="#/graf">${icon("network")}Graf powiązań</a><a href="#/zrodla">${icon("radar")}Źródła danych</a><a href="#/dla">${icon("users")}Grupy odbiorców</a><a href="/docs" target="_blank" rel="noopener">${icon("external-link")}API</a></nav>${CFG.demo_mode ? "Tryb demo (dane przykładowe) · " : ""}LLM: ${esc((CFG.llm_providers || []).join(" → "))} · ikony Lucide (ISC) · granice województw: polska-geojson (MIT) · ilustracje: Higgsfield (AI, wizualizacje)`;
  route(); });
