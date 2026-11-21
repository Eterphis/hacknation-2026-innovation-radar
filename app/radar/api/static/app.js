"use strict";
/* Radar Innowacji UI. Components are small functions returning HTML; pages compose them.
   Icons: one Lucide sprite (/static/icons.svg), always grey (--ink-3) unless they carry state (red). */
const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const api = (p, o) => fetch(p, o).then(r => r.ok ? r.json() : r.text().then(t => Promise.reject(t)));
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
function ideaItem(i, extra = "") {
  const lvl = i.maturity_i ?? LVLK[i.maturity] ?? 0;
  return `<div class="item reveal" tabindex="0" data-card="${i.card_id}">${avatar(SECTOR_ICON[i.sector] || "lightbulb")}
    <h3>${esc(i.title)} ${demo(i.synthetic)}</h3>${ring(i.score, "sm")}
    <div class="plates">${locPlate(i, "sm")}${moneyPlate(i, "sm")}<span class="plate sm"><span class="pi">${icon("gauge")}</span>${stepper(lvl)}</span>${extra}</div></div>`;
}
function bindCards(root) { $$("[data-card]", root).forEach(el => { el.onclick = e => { e.preventDefault(); openCard(+el.dataset.card); }; el.onkeydown = e => { if (e.key === "Enter") openCard(+el.dataset.card); }; }); }
function tip(html, e) { const t = $("#tip"); if (!html) { t.style.opacity = 0; return; } t.innerHTML = html; t.style.opacity = 1;
  t.style.left = Math.min(e.clientX + 14, innerWidth - t.offsetWidth - 8) + "px"; t.style.top = Math.min(e.clientY + 14, innerHeight - t.offsetHeight - 8) + "px"; }
const stagger = root => { const els = $$(".reveal", root); els.forEach((el, i) => el.style.animationDelay = Math.min(i, 14) * 70 + "ms");
  setTimeout(() => els.forEach(el => el.classList.remove("reveal")), 1700); };  // never leave content hidden
const header = (pre, preIcon, title, lead, actions = "") => `<div class="page-header reveal"><div><p class="pretitle">${icon(preIcon)}${pre}</p><h1>${title}</h1>${lead ? `<p class="lead">${lead}</p>` : ""}</div>${actions}</div>`;
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
const ROUTES = {"": pageHome, dla: pageAudience, mapa: pageMap, odkrywaj: pageExplore, graf: pageGraph, rolki: pageReels, zrodla: pageSources};
$$("#nav a").forEach(a => a.innerHTML = icon(a.dataset.i) + `<span>${a.textContent}</span>`);
$("#cmdbtn").innerHTML = icon("search"); $("#cmdicon").innerHTML = icon("search", "faint");
async function route() {
  const [full, query] = location.hash.replace(/^#\/?/, "").split("?");
  const [path, sub] = full.split("/");  // #/dla/samorzady -> path "dla", sub "samorzady"
  F = {...Object.fromEntries(new URLSearchParams(query || "")), ...(sub ? {_sub: sub} : {})};
  $$("#nav a").forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#/" + path));
  document.body.classList.toggle("reels-on", path === "rolki");
  const v = $("#view");
  v.innerHTML = '<div class="skel" style="width:40%;height:2.4rem;margin-top:2rem"></div><div class="skel"></div><div class="skel" style="width:70%"></div>';
  try { await (ROUTES[path] || pageHome)(v); } catch (e) { v.innerHTML = empty("Nie udało się wczytać widoku: " + e); }
  stagger(v); window.scrollTo(0, 0);
}
const go = (path, f) => { const q = qs(f || {}); location.hash = "#/" + path + (q ? "?" + q : ""); };
window.addEventListener("hashchange", route);

// ------------------------------------------------------------------ PRZEGLĄD
async function pageHome(v) {
  const [d, src] = await Promise.all([api("/api/insights"), api("/api/sources")]);
  const live = src.filter(s => s.active && s.mode === "pull"), records = src.reduce((a, s) => a + s.records, 0);
  if (d.empty) { v.innerHTML = header("Radar innowacji", "radar", "Radar czeka na pierwsze pobranie", "Uruchom źródła w zakładce Źródła.") + `<a class="btn" href="#/zrodla">${icon("radar")}Źródła</a>`; return; }
  const k = d.kpi, maxHeat = Math.max(...d.trends.map(t => t.heat), 1);
  // Readability: 4 items per insight + "Więcej" into Explore with the matching filter; the rule hides behind an (i) button.
  const MORE = {standouts: {sort: "score"}, advanced: {maturity: "business_ready,market_ready"}, realized: {maturity: "business_ready,market_ready", innovation_type: "organizacyjna,edukacyjna,spoleczna,procesowa,uslugowa"},
    cheap: {cost_level: "niski,sredni", maturity: "tech_ready,business_ready,market_ready"}, budget: {cost_level: "wysoki,bardzo_wysoki"}, hidden: {institution_type: "szkola,uczelnia,instytut"}};
  const list = (key, extra) => { const all = d[key] || [];
    return `<div class="items">${all.slice(0, 4).map(i => ideaItem(i, extra ? extra(i) : "")).join("") || `<p class="faint">Brak pozycji spełniających regułę.</p>`}</div>` +
      (MORE[key] && all.length ? `<a class="more" href="#/odkrywaj?${qs(MORE[key])}">Więcej ${icon("arrow-right")}</a>` : ""); };
  const info = key => `<button class="info" data-info="${key}" aria-expanded="false" aria-label="Jak liczymy">${icon("filter")}</button>`;
  const section = (ic, title, sub, key, body, red) => `<div class="card reveal">${cardH(ic, title, sub, info(key), red)}<div class="card-b"><p class="info-pop" id="pop-${key}">${esc(d.rules[key])}</p>${body}</div></div>`;
  v.innerHTML = header(`Radar sam przeszukuje ${live.length} źródeł · ${records.toLocaleString("pl-PL")} rekordów`, "radar", "Ukryte innowacje z instytucji publicznych",
    "Pomysły z publikacji, projektów, patentów i inwestycji: odsiane przez Basala, ocenione przez agenta wdrożeniowego według jawnych kryteriów i skierowane do odbiorców.",
    `<a class="btn" href="#/dla">${icon("users")}Pokaż dla mnie</a>`) + `
  <div id="who"></div>
  <div class="grid g-4">${[
    ["copy", k.ready_to_copy, "gotowych do powielenia w innej instytucji", true],
    ["piggy-bank", k.cheap_wins, "szybkich wdrożeń przy małym budżecie"],
    ["banknote", k.need_budget, `czeka na duże finansowanie${k.budget_needed_pln ? " · " + pln(k.budget_needed_pln) : ""}`],
    ["users", k.nontech_share + "%", "to innowacje nietechnologiczne"]].map(([ic, n, t, red]) => `<div class="card stat reveal">${avatar(ic, red ? "red" : "")}<div><b>${n}</b><span>${t}</span></div></div>`).join("")}</div>
  <section class="band"><div class="grid g-5-7">
    <div class="card reveal">${cardH("map", "Gdzie powstają", `${k.voivodeships} województw z pomysłami`, `<a class="btn-soft" href="#/mapa">${icon("arrow-right")}</a>`)}<div class="card-b" id="minimap"></div></div>
    <div class="card reveal">${cardH("target", "Portfel: koszt × dojrzałość", "kliknij komórkę, by zobaczyć pomysły")}<div class="card-b"><div class="chart" id="portfolio"></div><div class="legend" id="plegend"></div>
      <details class="how"><summary>${icon("layers")}Pokaż jako tabelę</summary><div id="ptable"></div></details></div></div></div></section>
  <div class="grid g-2">
    ${section("trending-up", "Gorące trendy", "obszary technologii z największym rozpędem", "trends",
      `<div class="bars">${d.trends.map(t => `<div class="bar" data-tech="${esc(t.key)}">${icon(TECH_ICON[t.key] || "layers")}<span>${esc(t.pl)}</span><div class="track"><i style="width:${Math.round(t.heat / maxHeat * 100)}%"></i></div><span class="v">${t.heat}</span></div>`).join("")}</div>`, true)}
    ${section("sparkles", "Wyróżniają się", "wysoki wynik i brak bliskich odpowiedników", "standouts", list("standouts"))}
    ${section("rocket", "Najbardziej zaawansowane", "najmocniejsze dowody: wdrożenia, patenty, pilotaże", "advanced", list("advanced"))}
    ${section("circle-check", "Gotowe do powielenia", "działa u twórcy, można przenieść", "realized", list("realized", i => i.path ? plate(PATH_ICON[i.path] || "arrow-right", i.path, "", "sm") : ""))}
    ${section("piggy-bank", "Tanio i szybko", "niski koszt, gotowy co najmniej prototyp", "cheap", list("cheap"))}
    ${section("banknote", "Wymaga dużego budżetu", "kandydaci do funduszy UE, NCBR i partnerstw", "budget", list("budget"))}
    ${section("gem", "Ukryte perełki", "szkoły, uczelnie i instytuty, o których mało kto wie", "hidden", list("hidden"))}
    ${section("git-compare-arrows", "Dublowanie prac", "te zespoły rozwiązują ten sam problem", "duplicates",
      `<div class="items">${d.duplicates.map(p => `<div class="item reveal" data-card="${p.a.card_id}">${avatar("copy")}<h3>${esc(p.a.title)}</h3>${ring(p.similarity * 100, "sm")}
        <div class="plates">${plate("arrow-right", p.b.title, "", "sm")}${plate("map-pin", [p.a.voivodeship, p.b.voivodeship].filter(Boolean).join(" ↔ "), "", "sm red")}</div></div>`).join("") || '<p class="faint">Brak par powyżej progu.</p>'}</div>`)}
  </div>
  <section class="band">${cardH("map-pin", "Luki regionalne", "sektory z pomysłami w kraju, ale bez podaży w części województw — tu warto przenieść rozwiązania")}
    <div class="card-b"><div class="grid g-2">${d.gaps.map(g => `<a class="item reveal" href="#/mapa?sector=${esc(g.sector)}&mode=gap">${avatar(SECTOR_ICON[g.sector] || "layers")}<h3>${esc(g.pl)}</h3>
      <span class="plate sm red"><span class="pi">${icon("map-pin")}</span>${g.missing.length}/16 bez podaży</span><div class="plates">${plate("trending-up", g.source_regions.join(", "), "", "sm")}${plate("lightbulb", g.ideas + " pomysłów", "", "sm")}</div></a>`).join("")}</div></div></section>`;
  drawPortfolio($("#portfolio"), d.portfolio);
  $("#who").innerHTML = await audienceTiles();
  const reg = await api("/api/regions");
  await drawPoland($("#minimap"), reg, {compact: true});
  $$("[data-info]", v).forEach(b => b.onclick = () => { const open = b.getAttribute("aria-expanded") !== "true";
    b.setAttribute("aria-expanded", open); $("#pop-" + b.dataset.info).classList.toggle("on", open); });
  $$(".bar[data-tech]", v).forEach(b => { const t = d.trends.find(x => x.key === b.dataset.tech);
    b.onmousemove = e => tip(`<b>${esc(t.pl)}</b><br>${t.ideas} pomysłów · ${t.likes} polubień<br>średnia ocena ${t.avg_score} · ${t.regions} woj. · ${t.ready} gotowych`, e);
    b.onmouseleave = () => tip(); b.onclick = () => go("odkrywaj", {tech_area: t.key}); });
  bindCards(v);
}

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
  el.innerHTML = `<svg class="pl-map" viewBox="${POLAND.viewBox}" role="img" aria-label="Mapa Polski: ${mode === "gap" ? "luki" : "liczba pomysłów"} w województwach">
    ${POLAND.regions.map(p => { const r = by[p.name] || {selected: 0, gap: 0, ideas: 0};
      const lab = `${p.name}: ${r.selected} pomysłów${mode === "gap" && r.gap > 0 ? ", luka " + r.gap : ""}`;
      return `<path d="${p.d}" fill="${fill(r)}" data-v="${esc(p.name)}" class="${opts.selected === p.name ? "sel" : ""}" tabindex="0" role="button" aria-label="${esc(lab)}"/>`; }).join("")}
    ${POLAND.regions.map(p => { const r = by[p.name] || {selected: 0, gap: 0}; const t = val(r) / max, n = mode === "gap" ? (r.gap > 0 ? "luka" : "") : r.selected;
      return n || n === 0 && !opts.compact ? `<text x="${p.cx}" y="${p.cy}" text-anchor="middle" class="${t > .6 ? "on-red" : ""}">${n}</text>` : ""; }).join("")}</svg>
    <div class="map-scale"><span>${mode === "gap" ? "brak luki" : "0"}</span><i></i><span>${mode === "gap" ? "największa luka" : Math.round(max) + " pomysłów"}</span></div>
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
async function pageExplore(v) {
  v.innerHTML = header("Odkrywaj", "layers", "Wszystkie pomysły", "Filtruj po każdej osi Basala. Wyniki od najlepszych.",
    `<div style="display:flex;gap:.75rem;flex-wrap:wrap"><input type="search" id="q" placeholder="Szukaj w tytułach i opisach" value="${esc(F.q || "")}" style="width:280px">
     <select id="sort" style="width:auto"><option value="score">najlepsze</option><option value="likes">najczęściej lubiane</option><option value="priority">priorytet Basala</option><option value="newest">najnowsze</option></select></div>`) +
    `<div class="grid g-side"><aside class="card"><div class="card-b" id="facets"></div></aside><div id="results"></div></div>`;
  $("#sort").value = F.sort || "score";
  $("#q").oninput = debounce(e => { F.q = e.target.value; loadExplore(); }, 300);
  $("#sort").onchange = e => { F.sort = e.target.value; loadExplore(); };
  await loadExplore();
}
async function loadExplore() {
  const r = await api("/api/ideas?" + qs({...F, sort: F.sort || "score"}));
  const ax = {sector: ["Sektor", "factory"], tech_area: ["Obszar technologii", "cpu"], maturity: ["Dojrzałość", "gauge"], cost_level: ["Koszt", "banknote"],
    innovation_type: ["Typ innowacji", "lightbulb"], institution_type: ["Instytucja", "building-2"], voivodeship: ["Województwo", "map-pin"]};
  $("#facets").innerHTML = Object.entries(ax).map(([a, [nm, ic]]) => `<div style="margin-bottom:1.25rem"><p class="pretitle">${icon(ic)}${nm}</p><div class="chips">${(r.facets[a] || []).map(o =>
    `<button class="chip ${(F[a] || "").split(",").includes(o.value) ? "on" : ""}" data-ax="${a}" data-v="${esc(o.value)}">${esc(a === "maturity" ? LVL[LVLK[o.value]] : a === "institution_type" ? (INST_PL[o.value] || o.value) : o.pl.split(" (")[0])}<span class="n">${o.count}</span></button>`).join("")}</div></div>`).join("")
    + `<div class="chips"><button class="btn-soft" id="fclear">${icon("x")}Wyczyść</button><button class="btn-soft" id="fgraph">${icon("network")}Na grafie</button></div>`;
  $$("[data-ax]", $("#facets")).forEach(b => b.onclick = () => { const a = b.dataset.ax, val = b.dataset.v, cur = new Set((F[a] || "").split(",").filter(Boolean));
    cur.has(val) ? cur.delete(val) : cur.add(val); F[a] = [...cur].join(","); history.replaceState(null, "", "#/odkrywaj?" + qs(F)); loadExplore(); });
  $("#fclear").onclick = () => { F = {sort: F.sort}; history.replaceState(null, "", "#/odkrywaj"); loadExplore(); };
  $("#fgraph").onclick = () => go("graf", F);
  $("#results").innerHTML = `<div class="card">${cardH("lightbulb", r.total + " pomysłów", "kliknij, by otworzyć kartę")}<div class="card-b"><div class="items">${r.items.map(i => ideaItem(i, i.path ? plate(PATH_ICON[i.path] || "arrow-right", i.path, "", "sm") : "")).join("") || empty("Nic nie pasuje do filtrów.")}</div></div></div>`;
  bindCards($("#results")); stagger($("#results"));
}

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
  N.filter(n => n.type !== "idea").forEach(n => { const name = hubIcon(n); if (!imgs[name]) { const img = new Image(); fetch("/static/icons.svg").then(r => r.text()).then(t => {
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
async function pageReels(v) {
  const items = await api("/api/feed?limit=50");
  v.innerHTML = `<div class="reels" id="reels">${items.map((i, n) => { const b = i.brief || {}, lvl = LVLK[b.maturity] ?? 0;
    return `<section class="reel" data-n="${n}" aria-label="Pomysł ${n + 1} z ${items.length}"><article class="reel-card"><div class="reel-progress" aria-hidden="true"><i></i></div>
      <div class="reel-top">${avatar(INST_ICON[i.institution_type] || "building-2")}<div class="who"><b>${esc(i.institution || INST_PL[i.institution_type] || "Instytucja")}</b><small>${esc(INST_PL[i.institution_type] || "")} ${demo(i.synthetic)}</small></div>${ring(b.score)}</div>
      <div class="plates">${locPlate(i)}${sectorPlate(i.sector)}</div>
      <div class="reel-title">${esc(b.solution)}</div>
      <div class="reel-hook">${esc(b.hook)}</div>
      <div class="reel-grid">
        <div class="tile">${icon("banknote")}<div><small>Budżet</small><b>${esc(i.amount ? pln(i.amount) : (COST_RANGE[i.cost_level] || "—"))}</b></div></div>
        <div class="tile">${icon("gauge")}<div><small>${esc(LVL[lvl])}</small>${stepper(lvl)}</div></div>
        <div class="tile">${icon(PATH_ICON[b.path] || "arrow-right")}<div><small>Ścieżka</small><b>${esc(b.path || "—")}</b></div></div>
        <div class="tile">${icon("users")}<div><small>Dla kogo</small><b>${esc((b.for_whom || [])[0] || "—")}</b></div></div>
        <div class="tile wide">${icon("target")}<div><small>Pierwszy krok</small><b>${esc(b.next_step || "—")}</b></div></div>
      </div>
      <div class="reel-foot"><button class="like ${liked.has(i.card_id) ? "on" : ""}" data-like="${i.card_id}" aria-pressed="${liked.has(i.card_id)}" aria-label="Lubię to">${icon("heart")}</button>
        <span class="likes-n" id="ln-${i.card_id}">${i.likes}</span><a class="btn-soft" style="margin-left:auto" href="#" data-card="${i.card_id}">${icon("arrow-right")}Karta</a></div>
    </article></section>`; }).join("") || empty("Brak briefów.")}</div><div class="reel-dots" id="dots">${items.map(() => "<i></i>").join("")}</div>
    <div class="reel-nav"><button class="btn-icon" id="rprev" aria-label="Poprzedni pomysł (strzałka w górę)">${icon("chevron-down", "flip")}</button>
      <button class="btn-icon" id="rnext" aria-label="Następny pomysł (strzałka w dół)">${icon("chevron-down")}</button><span class="kbd-hint">↑ ↓ · L</span></div>`;
  const box = $("#reels"), reels = $$(".reel", v), dots = $$("#dots i");
  let cur = 0;
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("active"); cur = +e.target.dataset.n;
    dots.forEach((d, k) => d.classList.toggle("on", k === cur)); } else e.target.classList.remove("active"); }), {root: box, threshold: .6});
  reels.forEach(r => io.observe(r)); if (reels[0]) reels[0].classList.add("active");
  const goTo = n => { n = Math.max(0, Math.min(reels.length - 1, n)); reels[n]?.scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"}); };
  $("#rprev").onclick = () => goTo(cur - 1); $("#rnext").onclick = () => goTo(cur + 1);
  const onKey = e => { if (!document.body.contains(box)) { document.removeEventListener("keydown", onKey); return; }
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || $("#drawer").classList.contains("on")) return;
    if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); goTo(cur + 1); }
    else if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); goTo(cur - 1); }
    else if (e.key === "l" || e.key === "L") { const b = $("[data-like]", reels[cur]); if (b) toggleLike(b); } };
  document.addEventListener("keydown", onKey);
  async function toggleLike(btn, force) {
    const id = +btn.dataset.like; if (force && liked.has(id)) return;
    const r = await api(`/api/cards/${id}/like`, {method: "POST", headers: {"X-Voter": voter}});
    r.liked ? liked.add(id) : liked.delete(id); saveLiked();
    btn.classList.toggle("on", r.liked); btn.setAttribute("aria-pressed", r.liked); $("#ln-" + id).textContent = r.likes;
    btn.classList.remove("pop"); void btn.offsetWidth; btn.classList.add("pop");
  }
  $$("[data-like]", v).forEach(b => b.onclick = () => toggleLike(b));
  $$(".reel-card", v).forEach(c => c.ondblclick = e => { if (e.target.closest("button,a")) return; const b = $("[data-like]", c); const burst = document.createElement("div");
    burst.className = "burst"; burst.innerHTML = icon("heart"); c.appendChild(burst); setTimeout(() => burst.remove(), 800); toggleLike(b, true); });
  bindCards(v);
}

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
async function audienceTiles() {
  PERSONAS = PERSONAS || await api("/api/personas");
  return `<section class="who reveal"><p class="pretitle">${icon("users")}Kim jesteś?</p><div class="who-grid">${PERSONAS.map(p =>
    `<a class="who-tile" href="#/dla/${p.key}" style="--hero:url('${heroImg(p.key)}')">${avatar(p.icon, "red")}<b>${esc(p.name)}</b><span>${esc(p.promise.split(":")[0].split(",")[0])}</span>${icon("arrow-right", "go")}</a>`).join("")}</div></section>`;
}
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
    <div class="biz-kpis">${[["banknote", money(b.deploy_cost_pln), "koszt wdrożenia u odbiorcy"], ["trending-up", money(b.valuation.licence_or_spinoff_pln), "wartość licencji / spin-off"],
      ["piggy-bank", money(b.savings_per_adopter_pln), "oszczędność vs budowa od zera"], ["clock", b.payback, "zwrot"]].map(([ic, v, t]) => `<div class="tile">${icon(ic)}<div><small>${t}</small><b>${v}</b></div></div>`).join("")}</div>
    <div class="market">${bar("TAM (cały rynek)", m.tam_pln)}${bar("SAM (region)", m.sam_pln)}${bar("SOM (3 lata)", m.som_3y_pln)}</div>
    <div class="plates" style="margin-top:.75rem">${plate("users", b.adopters.count.toLocaleString("pl-PL") + " " + b.adopters.who)}${plate("briefcase", b.model)}${b.funding.map(f => plate("piggy-bank", f.programme, f.for)).join("")}</div>
    <details class="how"><summary>${icon("filter")}Założenia wyceny (bez AI, jawne reguły)</summary><ul class="steps" style="margin-top:.5rem">${b.assumptions.map(a => `<li>${icon("chevron-right")}<span>${esc(a)}</span></li>`).join("")}</ul></details></div>`;
}

// ------------------------------------------------------------------ CARD drawer
async function openCard(id) {
  $("#scrim").classList.add("on"); $("#drawer").classList.add("on"); $("#drawer-in").innerHTML = '<div class="skel" style="height:2rem;width:60%"></div><div class="skel"></div>';
  const c = await api(`/api/cards/${id}`), a = c.assessment || {}, r = c.record, lvl = LVLK[c.maturity] ?? 0;
  const info = {city: null, voivodeship: r.voivodeship, amount: Math.max(0, ...Object.values(r.amounts || {}).filter(x => typeof x === "number")) || null, cost_level: c.basal?.cost_level?.value};
  $("#drawer-in").innerHTML = `<div style="display:flex;align-items:center;gap:.75rem">${avatar(SECTOR_ICON[r.sector] || "lightbulb", "red")}<p class="pretitle" style="margin:0">Karta pomysłu · ${esc(r.source_id)}</p><button class="btn-icon" id="dclose" style="margin-left:auto" aria-label="Zamknij">${icon("x")}</button></div>
    <div style="display:flex;gap:1rem;align-items:center;margin-top:1rem"><h2 style="font-size:1.6rem;line-height:1.2;flex:1">${esc(c.solution_name || r.title)}</h2>${ring(a.total)}</div>
    <div class="plates" style="margin-top:1rem">${locPlate(info)}${moneyPlate(info)}<span class="plate"><span class="pi">${icon("gauge")}</span>${stepper(lvl)}<span>${LVL[lvl]}</span></span>${sectorPlate(r.sector)}${r.tech_area ? plate(TECH_ICON[r.tech_area] || "cpu", lp("tech_area", r.tech_area)) : ""}${instPlate(c.basal?.institution_type?.value)}${demo(c.synthetic)}</div>
    <p class="muted" style="margin-top:1rem">${esc(a.summary || c.summary_pl || "")}</p>
    ${r.affiliations?.length ? `<p class="faint">${icon("building-2")} ${esc(r.affiliations.join("; "))}${r.url ? ` · <a href="${esc(r.url)}" target="_blank" rel="noopener">${icon("external-link")} źródło</a>` : ""}</p>` : ""}
    ${bizSection(c.business)}
    ${a.scores ? `<div class="sec"><p class="pretitle">${icon("target")}Ocena wg jawnych kryteriów</p><div class="crit">${Object.entries(a.scores).map(([k, x]) => `<span>${esc(CRIT[k] || k)} <span class="faint">${Math.round((a.criteria?.[k]?.weight || 0) * 100)}%</span></span><div class="mini"><i style="width:${x.score * 20}%"></i></div><b class="mono">${x.score}</b><span class="why">${esc(x.why)}</span>`).join("")}</div></div>` : ""}
    ${a.paths ? `<div class="sec"><p class="pretitle">${icon("rocket")}Ścieżki wdrożenia · kto co robi</p>${a.paths.map(p => `<p style="margin:.75rem 0 .5rem;display:flex;gap:.5rem;align-items:center">${icon(PATH_ICON[p.path] || "arrow-right")}<b>${esc(p.path)}</b><span class="faint">${esc(p.why)}</span></p><ul class="steps">${p.steps.map(s => `<li>${icon("chevron-right")}<span>${esc(s.step)}<span class="who">${esc(s.who)}${s.time ? " · " + esc(s.time) : ""}</span></span></li>`).join("")}</ul>`).join("")}</div>` : ""}
    ${a.recipients ? `<div class="sec"><p class="pretitle">${icon("users")}Odbiorcy i partnerzy</p><div class="plates">${a.recipients.map(x => plate(x.kind === "typ odbiorcy" ? "users" : "building-2", x.name, x.kind)).join("")}</div></div>` : ""}
    ${a.risks ? `<div class="sec"><p class="pretitle">${icon("shield-alert")}Ryzyka i mitygacje</p><ul class="steps">${a.risks.map(x => `<li>${icon("shield-alert")}<span>${esc(x.risk)}<span class="who">${esc(x.level || "")} · mitygacja: ${esc(x.mitigation)} · ${esc(x.owner)}</span></span></li>`).join("")}</ul></div>` : ""}
    ${a.metrics ? `<div class="sec"><p class="pretitle">${icon("activity")}Mierniki skuteczności</p><ul class="steps">${a.metrics.map(m => `<li>${icon("target")}<span>${esc(m)}</span></li>`).join("")}</ul></div>` : ""}
    <details class="how sec"><summary>${icon("layers")}Podobne rozwiązania, region, dowody</summary>
      ${a.similar?.length ? `<div class="items" style="margin-top:.75rem">${a.similar.map(s => `<div class="item" data-card="${s.card_id || ""}">${avatar("copy")}<h3>${esc(s.title)}</h3>${ring(s.similarity * 100, "sm")}<div class="plates">${s.voivodeship ? plate("map-pin", s.voivodeship, "", "sm red") : ""}</div></div>`).join("")}</div>` : ""}
      ${(c.reasoning || []).slice(0, 1).map(s => `<ul class="steps" style="margin-top:.75rem">${s.items.map(i => `<li>${icon("book-open")}<span>${esc(i)}</span></li>`).join("")}</ul>`).join("")}
      <p class="faint">ocena: ${esc(a.by || "")} · ekstrakcja: ${esc(c.provenance?.provider)}/${esc(c.provenance?.model)} · basal: ${esc(c.basal?.version)} (${esc(c.basal?.embedder)})</p></details>
    <div class="chips" style="margin-top:2rem"><button class="btn-soft good" data-d="approved">${icon("circle-check")}Zatwierdź</button><button class="btn-soft bad" data-d="rejected">${icon("ban")}Odrzuć</button><span class="faint" style="align-self:center">decyzja: ${esc(c.decision)}</span></div>`;
  $("#dclose").onclick = closeCard;
  $$("[data-card]", $("#drawer-in")).forEach(x => x.onclick = () => x.dataset.card && openCard(+x.dataset.card));
  $$("[data-d]", $("#drawer-in")).forEach(b => b.onclick = async () => { await api(`/api/cards/${id}/decision`, {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({decision: b.dataset.d})}); closeCard(); route(); });
}
function closeCard() { $("#scrim").classList.remove("on"); $("#drawer").classList.remove("on"); }
$("#scrim").onclick = closeCard;

// ------------------------------------------------------------------ command bar (+ voice where supported)
const cmd = $("#cmd"), cq = $("#cmdq");
function openCmd() { cmd.classList.add("on"); cq.value = ""; cq.focus();
  $("#hints").innerHTML = [["seniorzy", "users"], ["smog", "wifi"], ["kompozyty", "layers"], ["wodór", "zap"], ["e-usługi", "monitor"], ["edukacja", "book-open"]].map(([h, ic]) => `<button class="chip" data-h="${h}">${icon(ic)}${h}</button>`).join("");
  $$("[data-h]", cmd).forEach(b => b.onclick = () => search(b.dataset.h)); }
function search(q) { cmd.classList.remove("on"); go("odkrywaj", {q}); }
$("#cmdbtn").onclick = openCmd; cmd.onclick = e => { if (e.target === cmd) cmd.classList.remove("on"); };
cq.onkeydown = e => { if (e.key === "Enter" && cq.value.trim()) search(cq.value.trim()); if (e.key === "Escape") cmd.classList.remove("on"); };
document.addEventListener("keydown", e => { if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); openCmd(); } if (e.key === "Escape") { closeCard(); cmd.classList.remove("on"); } });
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) { const mic = $("#mic"); mic.hidden = false; mic.innerHTML = icon("mic"); mic.onclick = () => { const r = new SR(); r.lang = "pl-PL"; mic.classList.add("on");
  r.onresult = e => { const t = e.results[0][0].transcript; cq.value = t; search(t); }; r.onend = () => mic.classList.remove("on"); r.start(); }; }

// ------------------------------------------------------------------ boot
// Inline the icon sprite once: <use> on same-document symbols works everywhere (external sprites do not).
const SPRITE = fetch("/static/icons.svg").then(r => r.text()).then(t => { const d = document.createElement("div"); d.hidden = true; d.innerHTML = t; document.body.prepend(d); }).catch(() => {});
Promise.all([SPRITE, api("/api/config").then(c => CFG = c).catch(() => {}), api("/api/labels").then(l => LABELS = l).catch(() => {})]).then(() => {
  $("#foot").innerHTML = `${CFG.demo_mode ? "Tryb demo (dane przykładowe) · " : ""}LLM: ${esc((CFG.llm_providers || []).join(" → "))} · ikony Lucide (ISC) · granice województw: polska-geojson (MIT)`;
  route(); });
