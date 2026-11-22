/* Radar Innowacji · pages v3: idea page, saved ideas, community likes, branched wizard, reels, clusters, lighter home.
   Loaded after app.js and shares its globals (icon, plate, api, F, route…). */

// ------------------------------------------------------------------ shared components
// NCBR stories arrive as "Tytuł: … Zajawka: … Jaki problem rozwiązuje projekt: …": keep the prose, drop the form labels
const tidy = s => String(s || "").replace(/^\s*Tytuł:.*?(?=Zajawka:|Jaki problem|Opis:|$)/i, "")
  .replace(/\b(Zajawka|Jaki problem rozwiązuje projekt|Opis projektu|Opis|Efekty|Rezultaty):\s*/gi, "").replace(/\s+/g, " ").trim();
const sectorImg = (s, wide = false) => s ? `/static/sectors/${wide ? "wide/" : ""}${s}.webp` : "";
const bannerImg = k => `/static/banners/${k}.webp`;
const BANNER_BY_ROUTE = {mapa: "mapa", wdrozenia: "wdrozenia", portfel: "portfel", zrodla: "zrodla", porownaj: "portfel", dla: "dopasuj", graf: "klastry"};
function header(pre, preIcon, title, lead, actions = "", banner = "") {
  banner = banner || BANNER_BY_ROUTE[location.hash.replace(/^#\/?/, "").split(/[/?]/)[0]] || "";
  return `<div class="page-header reveal ${banner ? "has-banner" : ""}" ${banner ? `style="--banner:url('${bannerImg(banner)}')"` : ""}><div><p class="pretitle">${icon(preIcon)}${pre}</p><h1>${title}</h1>${lead ? `<p class="lead">${lead}</p>` : ""}</div>${actions}</div>`;
}
function emptyArt(kind, msg, action = "") {
  return `<div class="empty art reveal"><img src="/static/empty/${kind}.webp" alt="" loading="lazy" onerror="this.remove()"><p>${esc(msg)}</p>${action}</div>`;
}

// saved ideas (this browser) + community likes (server, anonymous voter id)
let SAVED = loadJSON("radar-saved", {});
const saveSaved = () => saveJSON("radar-saved", SAVED);
function toggleSave(i) {
  if (SAVED[i.card_id]) delete SAVED[i.card_id];
  else SAVED[i.card_id] = {card_id: i.card_id, title: i.title, institution: i.institution || "", sector: i.sector, voivodeship: i.voivodeship,
    city: i.city || null, maturity: i.maturity, score: i.score, likes: i.likes || 0, cost_level: i.cost_level, amount: i.amount || null, at: new Date().toISOString().slice(0, 10)};
  saveSaved(); return !!SAVED[i.card_id];
}
async function like(id) {
  const r = await api(`/api/cards/${id}/like`, {method: "POST", headers: {"X-Voter": voter}});
  r.liked ? liked.add(id) : liked.delete(id); saveLiked(); return r;
}
const IDX = {};  // card_id -> idea (for save buttons inside lists)
const likeBtn = (id, n) => `<button class="mini-act like-b ${liked.has(id) ? "on" : ""}" data-like="${id}" aria-pressed="${liked.has(id)}" aria-label="Polub (ocena społeczności)" title="Ocena społeczności">${icon("heart")}<span>${n || 0}</span></button>`;
const saveBtn = id => `<button class="mini-act save-b ${SAVED[id] ? "on" : ""}" data-save="${id}" aria-pressed="${!!SAVED[id]}" aria-label="Zapisz" title="${SAVED[id] ? "Zapisane" : "Zapisz na później"}">${icon("bookmark")}</button>`;

function ideaItem(i, extra = "") {
  IDX[i.card_id] = i;
  const lvl = i.maturity_i ?? LVLK[i.maturity] ?? 0;
  return `<article class="item reveal" tabindex="0" data-card="${i.card_id}">${avatar(SECTOR_ICON[i.sector] || "lightbulb")}
    <h3>${esc(i.title)} ${demo(i.synthetic)}</h3>${ring(i.score, "sm")}
    <div class="plates">${locPlate(i, "sm")}${moneyPlate(i, "sm")}<span class="plate sm"><span class="pi">${icon("gauge")}</span>${stepper(lvl)}</span>${extra}</div>
    <div class="item-acts">${likeBtn(i.card_id, i.likes)}${saveBtn(i.card_id)}</div></article>`;
}
// compact tile for grids (home picks, clusters, saved)
function ideaTile(i) {
  IDX[i.card_id] = i;
  const lvl = LVLK[i.maturity] ?? 0;
  return `<article class="itile reveal" tabindex="0" data-card="${i.card_id}">
    <div class="itile-img" style="--img:url('${sectorImg(i.sector, true)}')"><span class="chip-s">${icon(SECTOR_ICON[i.sector] || "layers")}${esc(lp("sector", i.sector).split(",")[0])}</span>${ring(i.score, "sm")}</div>
    <div class="itile-b"><h3>${esc(short(i.title || "", 90))}</h3><div class="faint ell">${esc(i.institution || "")}</div>
      <div class="plates">${locPlate(i, "sm")}<span class="plate sm"><span class="pi">${icon("gauge")}</span>${stepper(lvl)}</span></div>
      <div class="item-acts">${likeBtn(i.card_id, i.likes)}${saveBtn(i.card_id)}</div></div></article>`;
}
function bindCards(root) {
  $$("[data-card]", root).forEach(el => {
    const open = e => { if (e.target.closest("[data-like],[data-save],a,button")) return; e.preventDefault(); if (el.dataset.card) openCard(+el.dataset.card); };
    el.onclick = open; el.onkeydown = e => { if (e.key === "Enter" && e.target === el) openCard(+el.dataset.card); }; });
  $$("[data-like]", root).forEach(b => b.onclick = async e => { e.stopPropagation(); const r = await like(+b.dataset.like);
    b.classList.toggle("on", r.liked); b.setAttribute("aria-pressed", r.liked); const n = $("span", b); if (n) n.textContent = r.likes;
    b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop"); });
  $$("[data-save]", root).forEach(b => b.onclick = e => { e.stopPropagation(); const id = +b.dataset.save, i = IDX[id] || {card_id: id, title: b.dataset.title || ""};
    const on = toggleSave(i); b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); toast(on ? "Zapisano · Portfel → Zapisane" : "Usunięto z zapisanych"); });
}
function toast(msg) { let t = $("#toast"); if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("on"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 2200); }

// cards open as their own page (shareable link, back button works)
function openCard(id) { if (id) location.hash = "#/pomysl/" + id; }
function closeCard() { $("#scrim")?.classList.remove("on"); $("#drawer")?.classList.remove("on"); }

// ------------------------------------------------------------------ boot loader + route progress (Poland's border draws itself)
const LOADER = {n: 0, total: 4, done() { this.n++; this.set(this.n / this.total); },
  set(p) { const path = $("#ld-path"), shape = $("#pl-shape"); if (!path || !shape) return; const L = shape.getTotalLength(); path.style.strokeDasharray = L; path.style.strokeDashoffset = L * (1 - Math.min(1, p));
    const pct = $("#ld-pct"); if (pct) pct.textContent = Math.round(Math.min(1, p) * 100) + "%"; },
  t0: performance.now(),
  hide() { this.set(1); const wait = Math.max(450, 1400 - (performance.now() - this.t0));  // one full radar turn at least
    setTimeout(() => $("#loader")?.classList.add("off"), wait); setTimeout(() => $("#loader")?.remove(), wait + 700); } };
LOADER.set(.04);
SPRITE.then(() => LOADER.done());
let FIRST = true;
const _route = route;
route = async function () {
  const bar = $("#routebar"); bar?.classList.remove("done"); bar?.classList.add("on");
  await _route();
  bar?.classList.add("done"); setTimeout(() => bar?.classList.remove("on", "done"), 400);
  if (FIRST) { FIRST = false; LOADER.hide(); }
};
window.removeEventListener("hashchange", _route); window.addEventListener("hashchange", () => route());
api("/static/poland.json").then(p => { POLAND = POLAND || p; LOADER.done(); }).catch(() => LOADER.done());
api("/api/labels").then(() => LOADER.done()).catch(() => LOADER.done());
api("/api/personas").then(p => { PERSONAS = PERSONAS || p; LOADER.done(); }).catch(() => LOADER.done());

Object.assign(ROUTES, {"": pageHome, pomysl: pageIdea, dopasuj: pageMatch, odkrywaj: pageExplore, rolki: pageReels, klastry: pageClusters, portfel: pageDeals2, zapisane: pageSaved});

// ------------------------------------------------------------------ PRZEGLĄD (calm entry: one promise, one action, a few picks)
async function pageHome(v) {
  const [d, src] = await Promise.all([api("/api/insights"), api("/api/sources")]);
  if (d.empty) { v.innerHTML = header("Radar innowacji", "radar", "Radar czeka na pierwsze pobranie", "Uruchom źródła w zakładce Źródła.") + `<a class="btn" href="#/zrodla">${icon("radar")}Źródła</a>`; return; }
  const k = d.kpi, live = src.filter(s => s.active && s.mode === "pull").length, records = src.reduce((a, s) => a + s.records, 0);
  PERSONAS = PERSONAS || await api("/api/personas");
  const TABS = [["standouts", "Wyróżniają się", "sparkles"], ["realized", "Gotowe do powielenia", "circle-check"], ["cheap", "Tanio i szybko", "piggy-bank"],
    ["advanced", "Najbardziej zaawansowane", "rocket"], ["budget", "Duży budżet", "banknote"], ["hidden", "Ukryte perełki", "gem"]];
  const MORE = {standouts: {sort: "score"}, advanced: {maturity: "business_ready,market_ready"}, realized: {maturity: "business_ready,market_ready", innovation_type: "organizacyjna,edukacyjna,spoleczna,procesowa,uslugowa"},
    cheap: {cost_level: "niski,sredni", maturity: "tech_ready,business_ready,market_ready"}, budget: {cost_level: "wysoki,bardzo_wysoki"}, hidden: {institution_type: "szkola,uczelnia,instytut"}};
  v.innerHTML = `<section class="hero reveal" style="--hero:url('${bannerImg("home")}')"><div class="hero-in">
      <p class="pretitle">${icon("radar")}Radar sam przeszukuje ${live} źródeł · ${records.toLocaleString("pl-PL")} rekordów</p>
      <h1>Polskie innowacje, które warto wdrożyć</h1>
      <p class="lead">Znajdujemy pomysły w uczelniach, szkołach, instytutach i samorządach, wyceniamy je i pokazujemy, kto może je wdrożyć.</p>
      <div class="chips"><a class="btn big" href="#/dopasuj?edit=1">${icon("target")}Dopasuj w 30 sekund</a><a class="btn-soft" href="#/rolki">${icon("clapperboard")}Przeglądaj rolki</a><a class="btn-soft" href="#/zglos">${icon("lightbulb")}Zgłoś innowację</a></div></div></section>
    <div class="kpis3">${[["copy", k.ready_to_copy, "gotowych do powielenia"], ["piggy-bank", k.cheap_wins, "szybkich wdrożeń za mały budżet"], ["map-pin", k.voivodeships, "województw z pomysłami"]]
      .map(([ic, n, t]) => `<div class="kpi reveal">${icon(ic)}<b data-count="${n}">${n}</b><span>${t}</span></div>`).join("")}</div>
    <section class="sec-block reveal"><div class="sec-h"><h2>Kim jesteś?</h2><span class="faint">pokażemy to, co ma dla Ciebie sens biznesowy</span></div>
      <div class="who-row">${PERSONAS.map(p => `<a class="who-chip" href="#/dopasuj?edit=1&role=${p.key}" style="--img:url('${heroImg(p.key)}')"><span>${icon(p.icon)}</span><b>${esc(p.name.split(" i ")[0])}</b></a>`).join("")}</div></section>
    <section class="sec-block reveal"><div class="sec-h"><h2>Na dziś</h2><div class="tabs" role="tablist">${TABS.map(([key, lab, ic], n) => `<button role="tab" class="tab ${n ? "" : "on"}" data-tab="${key}" aria-selected="${!n}">${icon(ic)}${lab}</button>`).join("")}</div></div>
      <p class="faint rule" id="hrule"></p><div class="tiles" id="hpicks"></div><a class="more" id="hmore" href="#/odkrywaj">Zobacz wszystkie ${icon("arrow-right")}</a></section>
    <section class="sec-block reveal"><div class="sec-h"><h2>Rynek w pigułce</h2><a class="more" href="#/klastry">Tematy i rynki ${icon("arrow-right")}</a></div>
      <div class="grid g-5-7 start"><div class="card">${cardH("map", "Gdzie powstają", "kliknij województwo")}<div class="card-b" id="minimap"></div></div>
      <div class="card">${cardH("trending-up", "Gorące obszary", "rozpęd: nowe pomysły, oceny i polubienia", "", true)}<div class="card-b"><div class="bars">${d.trends.slice(0, 7).map(t => `<div class="bar" data-tech="${esc(t.key)}">${icon(TECH_ICON[t.key] || "layers")}<span>${esc(t.pl)}</span><div class="track"><i style="width:${Math.round(t.heat / Math.max(...d.trends.map(x => x.heat), 1) * 100)}%"></i></div><span class="v">${t.heat}</span></div>`).join("")}</div></div></div></div></section>`;
  const show = key => { $$(".tab", v).forEach(b => { const on = b.dataset.tab === key; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
    const box = $("#hpicks"); box.classList.add("fade"); setTimeout(() => { box.innerHTML = (d[key] || []).slice(0, 6).map(ideaTile).join("") || `<p class="faint">Brak pozycji.</p>`;
      box.classList.remove("fade"); stagger(box); bindCards(box); }, 140);
    $("#hrule").textContent = d.rules[key] || ""; $("#hmore").href = "#/odkrywaj?" + qs(MORE[key] || {}); };
  $$(".tab", v).forEach(b => b.onclick = () => show(b.dataset.tab)); show("standouts");
  countUp(v);
  $$(".bar[data-tech]", v).forEach(b => b.onclick = () => go("odkrywaj", {tech_area: b.dataset.tech}));
  drawPoland($("#minimap"), await api("/api/regions"), {compact: true});
}
function countUp(root) { $$("[data-count]", root).forEach(el => { const n = +el.dataset.count; if (!n || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const t0 = performance.now(), dur = 900; const step = t => { const p = Math.min(1, (t - t0) / dur); el.textContent = Math.round(n * (1 - Math.pow(1 - p, 3))).toLocaleString("pl-PL"); if (p < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); }); }

// ------------------------------------------------------------------ POMYSŁ (own page; essentials first, details in tabs)
async function pageIdea(v) {
  const id = +F._sub; if (!id) return go("odkrywaj");
  const c = await api(`/api/cards/${id}`), a = c.assessment || {}, r = c.record, lvl = LVLK[c.maturity] ?? 0, b = c.business, inv = c.investor;
  const idea = {card_id: c.id, title: c.solution_name || r.title, institution: (r.affiliations || [])[0] || "", sector: r.sector, voivodeship: r.voivodeship, maturity: c.maturity, score: a.total ?? c.score, likes: c.likes, cost_level: c.basal?.cost_level?.value};
  IDX[c.id] = idea;
  const info = {city: null, voivodeship: r.voivodeship};
  const kpis = b ? [["trending-up", money(inv?.adjusted?.licence_or_spinoff_pln ?? b.valuation.licence_or_spinoff_pln), "wartość licencji / spin-off"], ["banknote", money(b.deploy_cost_pln), "koszt wdrożenia u odbiorcy"],
    ["clock", b.payback, "zwrot"], ["users", b.adopters.count.toLocaleString("pl-PL"), "potencjalnych odbiorców"]] : [];
  const tabs = [
    ["biz", "Biznes", "briefcase", () => bizSection(b)],
    ["inv", "Dla inwestora", "trending-up", () => investorSection(inv)],
    ["how", "Jak wdrożyć", "rocket", () => a.paths ? `<div class="sec">${a.paths.map(p => `<p class="path-h">${icon(PATH_ICON[p.path] || "arrow-right")}<b>${esc(p.path)}</b><span class="faint">${esc(p.why)}</span></p><ul class="steps">${p.steps.map(s => `<li>${icon("chevron-right")}<span>${esc(s.step)}<span class="who">${esc(s.who)}${s.time ? " · " + esc(s.time) : ""}</span></span></li>`).join("")}</ul>`).join("")}
      ${a.recipients ? `<p class="pretitle" style="margin-top:1.25rem">${icon("users")}Odbiorcy i partnerzy</p><div class="plates">${a.recipients.map(x => plate(x.kind === "typ odbiorcy" ? "users" : "building-2", x.name, x.kind)).join("")}</div>` : ""}</div>` : ""],
    ["risk", "Ryzyka", "shield-alert", () => a.risks ? `<div class="sec"><ul class="steps">${a.risks.map(x => `<li>${icon("shield-alert")}<span>${esc(x.risk)}<span class="who">${esc(x.level || "")} · mitygacja: ${esc(x.mitigation)} · ${esc(x.owner)}</span></span></li>`).join("")}</ul>
      ${a.metrics ? `<p class="pretitle" style="margin-top:1.25rem">${icon("activity")}Mierniki skuteczności</p><ul class="steps">${a.metrics.map(m => `<li>${icon("target")}<span>${esc(m)}</span></li>`).join("")}</ul>` : ""}</div>` : ""],
    ["sim", "Podobne", "layers", () => a.similar?.length ? `<div class="items">${a.similar.map(s => `<div class="item" data-card="${s.card_id || ""}">${avatar("copy")}<h3>${esc(s.title)}</h3>${ring(s.similarity * 100, "sm")}<div class="plates">${s.voivodeship ? plate("map-pin", s.voivodeship, "", "sm red") : ""}</div></div>`).join("")}</div>` : `<p class="faint">Brak bliskich odpowiedników — to może być nisza.</p>`],
    ["src", "Źródło i ocena", "book-open", () => `<div class="sec">${a.scores ? `<div class="crit">${Object.entries(a.scores).map(([k, x]) => `<span>${esc(CRIT[k] || k)} <span class="faint">${Math.round((a.criteria?.[k]?.weight || 0) * 100)}%</span></span><div class="mini"><i style="width:${x.score * 20}%"></i></div><b class="mono">${x.score}</b><span class="why">${esc(x.why)}</span>`).join("")}</div>` : ""}
      <p class="muted" style="margin-top:1rem">${esc(r.abstract || "").slice(0, 1400)}</p>
      <p class="faint">${esc(r.source_id)}${r.year ? " · " + r.year : ""}${r.url ? ` · <a href="${esc(r.url)}" target="_blank" rel="noopener">${icon("external-link")} oryginał</a>` : ""} · ocena: ${esc(a.by || "")} · basal ${esc(c.basal?.version || "")}</p>
      <div class="chips" style="margin-top:1rem"><button class="btn-soft good" data-d="approved">${icon("circle-check")}Zatwierdź</button><button class="btn-soft bad" data-d="rejected">${icon("ban")}Odrzuć</button><span class="faint" style="align-self:center">decyzja operatora: ${esc(c.decision)}</span></div></div>`],
  ].filter(t => t[3]());
  v.innerHTML = `<a class="back" href="javascript:history.back()">${icon("chevron-left")}Wróć</a>
    <section class="idea-hero reveal" style="--img:url('${sectorImg(r.sector, true)}')"><div class="idea-hero-in">
      <div class="plates">${sectorPlate(r.sector)}${locPlate(info)}${instPlate(c.basal?.institution_type?.value)}${demo(c.synthetic)}</div>
      <h1>${esc(c.solution_name || r.title)}</h1><p class="faint">${esc((r.affiliations || []).slice(0, 2).join(" · "))}</p>
      <div class="idea-meta"><span class="plate"><span class="pi">${icon("gauge")}</span>${stepper(lvl)}<span>${LVL[lvl]}</span></span>${ring(a.total ?? c.score)}
        <button class="pill like-b ${liked.has(c.id) ? "on" : ""}" data-like="${c.id}" aria-pressed="${liked.has(c.id)}">${icon("heart")}<span>${c.likes}</span><small>ocena społeczności</small></button></div></div></section>
    ${kpis.length ? `<div class="kpis4">${kpis.map(([ic, val, t]) => `<div class="kpi reveal">${icon(ic)}<b>${val}</b><span>${t}</span></div>`).join("")}</div>` : ""}
    <section class="card reveal idea-sum"><div class="card-b"><p class="pretitle">${icon("sparkles")}W skrócie</p><p class="clamp" id="sum">${esc(tidy(a.summary || c.summary_pl || ""))}</p><button class="link" id="sum-more">Czytaj całość</button>
      <div class="idea-acts">${saveBtnBig(c.id)}${dealActions(c)}</div></div></section>
    <div class="tabs big reveal" role="tablist">${tabs.map(([k, l, ic], n) => `<button role="tab" class="tab ${n ? "" : "on"}" data-t="${k}" aria-selected="${!n}">${icon(ic)}${l}</button>`).join("")}</div>
    <section class="card reveal"><div class="card-b" id="tabbody"></div></section>`;
  const showTab = k => { const t = tabs.find(x => x[0] === k); $$(".tab[data-t]", v).forEach(b => { const on = b.dataset.t === k; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
    const box = $("#tabbody"); box.classList.add("fade"); setTimeout(() => { box.innerHTML = t[3](); box.classList.remove("fade"); bindCards(box);
      $$("[data-d]", box).forEach(bt => bt.onclick = async () => { await api(`/api/cards/${id}/decision`, {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({decision: bt.dataset.d})}); toast("Zapisano decyzję"); }); }, 120); };
  $$(".tab[data-t]", v).forEach(b => b.onclick = () => showTab(b.dataset.t)); showTab(tabs[0][0]);
  $("#sum-more").onclick = () => { $("#sum").classList.toggle("open"); $("#sum-more").textContent = $("#sum").classList.contains("open") ? "Zwiń" : "Czytaj całość"; };
  bindDealActions(c);
  const sb = $("#savebig"); sb.onclick = () => { const on = toggleSave(idea); sb.classList.toggle("on", on); sb.innerHTML = icon("bookmark") + (on ? "Zapisane" : "Zapisz"); toast(on ? "Zapisano · Portfel → Zapisane" : "Usunięto z zapisanych"); };
  bindCards($(".idea-hero", v));
  document.title = (c.solution_name || r.title || "Pomysł").slice(0, 60) + " · Radar Innowacji";
}
const saveBtnBig = id => `<button class="btn ${SAVED[id] ? "on" : ""}" id="savebig">${icon("bookmark")}${SAVED[id] ? "Zapisane" : "Zapisz"}</button>`;

// ------------------------------------------------------------------ ODKRYWAJ (facets + load more, infinite scroll)
async function pageExplore(v) {
  v.innerHTML = header("Odkrywaj", "layers", "Wszystkie pomysły", "Filtruj po osiach Basala. Wyniki doładowują się podczas przewijania.",
    `<div class="chips"><input type="search" id="q" placeholder="Szukaj: smog, seniorzy, wodór…" value="${esc(F.q || "")}" style="width:260px">
     <select id="sort" class="chip" aria-label="Sortuj"><option value="score">najlepsze</option><option value="likes">ocena społeczności</option><option value="priority">priorytet Basala</option><option value="newest">najnowsze</option></select></div>`, "odkrywaj") +
    `<div class="grid g-side start"><aside class="card facets"><div class="card-b" id="facets"></div></aside><div id="results"></div></div>`;
  $("#sort").value = F.sort || "score";
  $("#q").oninput = debounce(e => { F.q = e.target.value; loadExplore(); }, 300);
  $("#sort").onchange = e => { F.sort = e.target.value; loadExplore(); };
  await loadExplore();
}
const PAGE = 24;
async function loadExplore() {
  const f = {...F}; delete f._sub;
  const r = await api("/api/ideas?" + qs({...f, sort: F.sort || "score", limit: PAGE, offset: 0}));
  const ax = {sector: ["Sektor", "factory"], maturity: ["Dojrzałość", "gauge"], cost_level: ["Koszt", "banknote"], voivodeship: ["Województwo", "map-pin"],
    tech_area: ["Obszar technologii", "cpu"], innovation_type: ["Typ innowacji", "lightbulb"], institution_type: ["Instytucja", "building-2"]};
  $("#facets").innerHTML = Object.entries(ax).map(([a, [nm, ic]], n) => `<details class="facet" ${n < 3 || F[a] ? "open" : ""}><summary class="pretitle">${icon(ic)}${nm}${F[a] ? `<span class="dot"></span>` : ""}</summary><div class="chips">${(r.facets[a] || []).map(o =>
    `<button class="chip ${(F[a] || "").split(",").includes(o.value) ? "on" : ""}" data-ax="${a}" data-v="${esc(o.value)}">${esc(a === "maturity" ? LVL[LVLK[o.value]] : a === "institution_type" ? (INST_PL[o.value] || o.value) : o.pl.split(" (")[0].split(",")[0])}<span class="n">${o.count}</span></button>`).join("")}</div></details>`).join("")
    + `<div class="chips"><button class="btn-soft" id="fclear">${icon("x")}Wyczyść</button><button class="btn-soft" id="fgraph">${icon("network")}Na grafie</button></div>`;
  $$("[data-ax]", $("#facets")).forEach(b => b.onclick = () => { const a = b.dataset.ax, val = b.dataset.v, cur = new Set((F[a] || "").split(",").filter(Boolean));
    cur.has(val) ? cur.delete(val) : cur.add(val); F[a] = [...cur].join(","); history.replaceState(null, "", "#/odkrywaj?" + qs(F)); loadExplore(); });
  $("#fclear").onclick = () => { F = {sort: F.sort}; history.replaceState(null, "", "#/odkrywaj"); loadExplore(); };
  $("#fgraph").onclick = () => go("graf", F);
  const res = $("#results");
  res.innerHTML = `<div class="res-h"><b>${r.total.toLocaleString("pl-PL")} pomysłów</b><span class="faint">kliknij, by wejść w pomysł · ${icon("heart")} ocena społeczności · ${icon("bookmark")} zapisz</span></div>
    <div class="items" id="list">${r.items.map(i => ideaItem(i)).join("") || emptyArt("brak", "Nic nie pasuje do filtrów. Usuń któryś z nich.")}</div>
    <div class="loadmore"><button class="btn-soft" id="more" ${r.items.length >= r.total ? "hidden" : ""}>${icon("chevron-down")}Załaduj więcej</button><span class="faint" id="cnt">${Math.min(r.items.length, r.total)} z ${r.total}</span></div>`;
  bindCards(res); stagger(res);
  let offset = r.items.length, busy = false;
  const more = async () => { if (busy || offset >= r.total) return; busy = true; $("#more").classList.add("busy");
    const n = await api("/api/ideas?" + qs({...f, sort: F.sort || "score", limit: PAGE, offset}));
    const tmp = document.createElement("div"); tmp.innerHTML = n.items.map(i => ideaItem(i)).join("");
    const added = [...tmp.children]; added.forEach(el => $("#list").appendChild(el)); bindCards($("#list")); added.forEach((el, k) => el.style.animationDelay = k * 40 + "ms");
    offset += n.items.length; $("#cnt").textContent = `${Math.min(offset, r.total)} z ${r.total}`; $("#more").hidden = offset >= r.total; $("#more").classList.remove("busy"); busy = false; };
  $("#more").onclick = more;
  if (window.IntersectionObserver) { const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && more()), {rootMargin: "400px"}); io.observe($(".loadmore")); }
}

// ------------------------------------------------------------------ DOPASUJ (branched questions per audience, no re-render on multi-select)
const SECTOR_OPTS = keys => keys.map(k => [k, lp("sector", k).split(",")[0], SECTOR_ICON[k] || "layers"]);
const ALL_SECTORS = () => Object.keys(LABELS.sector || {});
const REGION_Q = (opt = true) => ({k: "voivodeship", img: "region", q: "Gdzie działasz?", hint: "Najpierw pokażemy rozwiązania z Twojego województwa, potem sprawdzone gdzie indziej.",
  opts: () => [["", "Cała Polska", "map"], ...(LABELS.voivodeship || []).map(x => [x, x, "map-pin"])], skip: opt});
const BUDGET_Q = (keys = COSTK) => ({k: "budget", img: "budget", q: "Ile możesz przeznaczyć na wdrożenie?", hint: "Pokażemy tylko to, na co Cię stać — z kosztem kopii, nie budowy od zera.",
  opts: () => [["niski", "do 100 tys. zł", "piggy-bank"], ["sredni", "do 2 mln zł", "banknote"], ["wysoki", "do 20 mln zł", "wallet"], ["bardzo_wysoki", "bez limitu", "trending-up"]].filter(o => keys.includes(o[0]))});
const FLOW = {
  inwestorzy: {goal: "zysk", qs: [
    {k: "budget", img: "budget", q: "Jaki ticket rozważasz?", hint: "Dobierzemy pomysły, których wdrożenie mieści się w tej skali.", opts: () => [["niski", "do 100 tys. zł (anioł)", "piggy-bank"], ["sredni", "do 2 mln zł (seed)", "banknote"], ["wysoki", "2–20 mln zł (VC)", "wallet"], ["bardzo_wysoki", "powyżej 20 mln zł", "trending-up"]]},
    {k: "sectors", img: "sectors", multi: true, q: "Które branże są w Twojej tezie?", hint: "Możesz wybrać kilka. Bez wyboru pokażemy wszystkie.", opts: () => SECTOR_OPTS(ALL_SECTORS())},
    {k: "stage", img: "stage", q: "Na jakim etapie wchodzisz?", hint: "Wcześniej = taniej i większe ryzyko. Później = mniejsze ryzyko, wyższa wycena.", opts: () => [["tech_ready", "Technologia gotowa (prototyp, patent)", "flask-conical"], ["business_ready", "Gotowe do wdrożenia", "circle-check"], ["market_ready", "Już na rynku, skalowanie", "trending-up"]]},
    REGION_Q()]},
  samorzady: {goal: "wdrozenie", stage: "business_ready", qs: [
    {k: "sub", img: "role", q: "Jaką instytucję reprezentujesz?", hint: "Od tego zależą typowe problemy i programy finansowania.", opts: () => [["gmina", "Gmina lub miasto", "landmark"], ["powiat", "Powiat", "building-2"], ["szpital", "Szpital lub placówka zdrowia", "hospital"], ["inna", "Inna instytucja publiczna", "building-2"]]},
    {...REGION_Q(false), q: "W którym województwie?", hint: "Programy regionalne FE i sąsiedzi, którzy już coś wdrożyli."},
    {k: "sectors", img: "sectors", multi: true, q: "Co chcesz poprawić?", hint: "Wybierz problemy — pokażemy rozwiązania, które już działają gdzie indziej.", opts: p => SECTOR_OPTS(p.sub === "szpital" ? ["Q_zdrowie", "J_ict", "O_administracja"] : ["H_transport", "E_srodowisko", "D_energetyka", "O_administracja", "Q_zdrowie", "P_edukacja", "R_kultura", "J_ict"])},
    BUDGET_Q()]},
  uczelnie: {stage: "exploring", qs: [
    {k: "goal", img: "goal", q: "Czego szuka Twoja jednostka?", hint: "Inaczej wygląda komercjalizacja, a inaczej szukanie partnera.", opts: () => [["zysk", "Komercjalizacji wyników (licencja, spin-off)", "briefcase"], ["partner", "Partnera z przemysłu lub samorządu", "handshake"], ["finansowanie", "Grantu na następny krok", "piggy-bank"]]},
    {k: "sectors", img: "sectors", multi: true, q: "W jakich dziedzinach?", hint: "Pokażemy podobne prace i kto ich potrzebuje.", opts: () => SECTOR_OPTS(ALL_SECTORS())},
    REGION_Q()]},
  szkoly: {goal: "wdrozenie", qs: [
    {k: "sub", img: "role", q: "Jaka to placówka?", hint: "Dobierzemy programy do wieku uczniów.", opts: () => [["przedszkole", "Przedszkole", "sprout"], ["podstawowa", "Szkoła podstawowa", "school"], ["ponadpodstawowa", "Liceum lub technikum", "graduation-cap"], ["zawodowa", "Szkoła branżowa", "hammer"]]},
    {k: "sectors", img: "sectors", multi: true, q: "Co chcecie rozwijać?", hint: "Edukację uwzględniamy zawsze; dodaj obszary tematyczne.", opts: () => [["P_edukacja", "Metody nauczania", "book-open"], ["J_ict", "Cyfryzacja i programowanie", "cpu"], ["E_srodowisko", "Ekologia", "recycle"], ["Q_zdrowie", "Zdrowie i sport", "hospital"], ["R_kultura", "Kultura i społeczność", "users"]]},
    BUDGET_Q(["niski", "sredni"]), REGION_Q()]},
  startupy: {stage: "tech_ready", qs: [
    {k: "goal", img: "goal", q: "Czego potrzebujesz najbardziej?", hint: "Ułożymy wyniki pod Twój najbliższy krok.", opts: () => [["zysk", "Technologii do licencji", "flask-conical"], ["partner", "Rynku z popytem publicznym", "landmark"], ["wdrozenie", "Gotowego rozwiązania do skalowania", "rocket"], ["finansowanie", "Finansowania", "piggy-bank"]]},
    {k: "sectors", img: "sectors", multi: true, q: "W jakiej branży działasz?", hint: "Możesz wybrać kilka.", opts: () => SECTOR_OPTS(ALL_SECTORS())},
    REGION_Q(), BUDGET_Q()]},
  innowatorzy: {qs: [
    {k: "stage", img: "stage", q: "Na jakim etapie jest Twój pomysł?", hint: "Pokażemy pomysły z tego samego etapu i jak zrobiły następny krok.", opts: () => [["exploring", "Mam pomysł", "lightbulb"], ["tech_ready", "Mam prototyp", "flask-conical"], ["business_ready", "Działa u mnie", "circle-check"]]},
    {k: "sectors", img: "sectors", multi: true, q: "Czego dotyczy?", hint: "Sprawdzimy, czy ktoś już robi coś podobnego.", opts: () => SECTOR_OPTS(ALL_SECTORS())},
    {k: "goal", img: "goal", q: "Czego szukasz?", hint: "", opts: () => [["partner", "Sprawdzić, czy ktoś już to zrobił", "search"], ["finansowanie", "Pieniędzy na prototyp", "piggy-bank"], ["wdrozenie", "Partnera do wdrożenia", "handshake"]]},
    REGION_Q()]},
};
const ROLE_Q = {k: "role", img: "role", q: "Kim jesteś?", hint: "Kolejne pytania dopasujemy do Ciebie. Zajmie to ok. 30 sekund.", opts: () => (PERSONAS || []).map(p => [p.key, p.name, p.icon])};
const flowFor = p => [ROLE_Q, ...((FLOW[p.role] || FLOW.innowatorzy).qs)];
const loadProfile = () => loadJSON("radar-profile", null);
const saveProfile = p => saveJSON("radar-profile", p);
function profileParams(p) {
  const fl = FLOW[p.role] || {};
  let sectors = [...(p.sectors || [])];
  if (p.role === "szkoly" && !sectors.includes("P_edukacja")) sectors.unshift("P_edukacja");
  if (p.role === "samorzady" && p.sub === "szpital" && !sectors.length) sectors = ["Q_zdrowie"];
  return {role: p.role, voivodeship: p.voivodeship || "", sectors: sectors.join(","), budget: p.budget || "wysoki", goal: p.goal || fl.goal || "wdrozenie", stage: p.stage || fl.stage || "exploring", limit: 24};
}
async function pageMatch(v) {
  PERSONAS = PERSONAS || await api("/api/personas");
  let prof = F.edit ? null : loadProfile();
  if (!prof) { prof = {role: F.role || "", step: F.role ? 1 : 0, sectors: []}; return wizard(v, prof); }
  const pp = profileParams(prof);
  const r = await api("/api/match?" + qs(pp));
  const who = (PERSONAS.find(p => p.key === prof.role) || {}).name || "";
  const chips = [who, prof.voivodeship || "cała Polska", COST_RANGE[pp.budget], ...(pp.sectors ? pp.sectors.split(",").map(s => lp("sector", s).split(",")[0]) : [])].filter(Boolean);
  v.innerHTML = header("Dopasowane do Ciebie", "target", `${r.total} pomysłów, od najlepiej dopasowanych`, `<span class="chips">${chips.map(c => `<span class="plate sm">${esc(c)}</span>`).join("")}</span>`,
    `<div class="chips"><a class="btn-soft" href="#/dopasuj?edit=1">${icon("filter")}Zmień odpowiedzi</a><button class="btn" id="wsub">${icon("rss")}Powiadamiaj o nowych</button></div>`, "dopasuj") +
    `<div id="wsubout"></div><div class="tiles2" id="mlist">${r.items.map(i => matchCard(i, r.metric)).join("") || emptyArt("brak", "Nic nie pasuje: poszerz budżet albo obszary.")}</div>`;
  r.items.forEach(i => IDX[i.card_id] = i);
  bindCards(v);
  $("#wsub").onclick = async () => {
    const w = await api("/api/watch", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({profile: {...prof, ...pp, sectors: pp.sectors.split(",").filter(Boolean)}, min_match: 70})});
    $("#wsubout").innerHTML = `<div class="card reveal" style="margin:0 0 1.5rem"><div class="card-b"><p class="pretitle">${icon("rss")}Subskrypcja bez logowania i bez e-maila</p>
      <p>Nowe pomysły z dopasowaniem od 70% trafią do tego kanału (czytnik RSS, Slack, Teams):</p><div class="chips"><code class="mono" style="word-break:break-all">${esc(w.feed_url)}</code><button class="btn-soft" id="wcopy">${icon("copy")}Kopiuj</button></div></div></div>`;
    $("#wcopy").onclick = () => { navigator.clipboard?.writeText(w.feed_url); toast("Skopiowano adres kanału"); }; };
}
function wizard(v, prof) {
  const steps = flowFor(prof), st = steps[prof.step], opts = st.opts(prof), total = steps.length;
  const sel = val => st.multi ? (prof[st.k] || []).includes(val) : prof[st.k] === val;
  v.innerHTML = `<section class="wiz">
    <div class="wiz-side reveal"><img src="/static/wizard/${st.img}.webp" alt="" onerror="this.style.visibility='hidden'"></div>
    <div class="wiz-main"><div class="wiz-top"><p class="pretitle">${icon("target")}Dopasuj radar · ${prof.step + 1} z ${total}</p><div class="wiz-bar"><i style="width:${(prof.step + 1) / total * 100}%"></i></div></div>
      <div class="wiz-q" key="${prof.step}"><h1>${esc(st.q)}</h1>${st.hint ? `<p class="lead">${esc(st.hint)}</p>` : ""}
      <div class="wiz-opts ${opts.length > 8 ? "many" : ""}" role="${st.multi ? "group" : "radiogroup"}">${opts.map(([val, lab, ic]) => `<button class="wiz-opt ${sel(val) ? "on" : ""}" data-v="${esc(val)}" role="${st.multi ? "checkbox" : "radio"}" aria-checked="${sel(val)}">${avatar(ic)}<span>${esc(lab)}</span>${st.multi ? `<i class="tick">${icon("check")}</i>` : ""}</button>`).join("")}</div></div>
      <div class="chips wiz-nav">${prof.step ? `<button class="btn-soft" id="wback">${icon("chevron-left")}Wstecz</button>` : ""}
        ${st.multi ? `<button class="btn" id="wnext">${icon("arrow-right")}<span id="wnl">${(prof[st.k] || []).length ? "Dalej" : "Wszystkie obszary"}</span></button>` : ""}
        ${st.skip ? `<button class="btn-soft" id="wskip">Pomiń</button>` : ""}</div></div></section>`;
  const next = () => { if (prof.step < total - 1) { prof.step++; anim(v, () => wizard(v, prof)); } else { delete prof.step; saveProfile(prof); go("dopasuj", {}); } };
  $$(".wiz-opt", v).forEach(b => b.onclick = () => {
    if (st.multi) {  // toggle in place: no re-render, no jump
      const s = new Set(prof[st.k] || []); s.has(b.dataset.v) ? s.delete(b.dataset.v) : s.add(b.dataset.v); prof[st.k] = [...s];
      const on = s.has(b.dataset.v); b.classList.toggle("on", on); b.setAttribute("aria-checked", on); $("#wnl").textContent = s.size ? `Dalej (${s.size})` : "Wszystkie obszary";
    } else { if (st.k === "role" && prof.role !== b.dataset.v) { prof = {role: b.dataset.v, step: 0, sectors: []}; } prof[st.k] = b.dataset.v;
      $$(".wiz-opt", v).forEach(x => x.classList.toggle("on", x === b)); setTimeout(next, 180); } });
  if ($("#wnext")) $("#wnext").onclick = next;
  if ($("#wskip")) $("#wskip").onclick = () => { prof[st.k] = st.multi ? [] : ""; next(); };
  if ($("#wback")) $("#wback").onclick = () => { prof.step--; anim(v, () => wizard(v, prof), true); };
  stagger(v);
}
function anim(v, fn, back = false) { const q = $(".wiz-main", v); if (!q || matchMedia("(prefers-reduced-motion: reduce)").matches) return fn();
  q.classList.add(back ? "out-back" : "out"); setTimeout(fn, 160); }
function matchCard(i, metric) {
  const b = i.business, lvl = LVLK[i.maturity] ?? 0;
  return `<article class="card biz mcard reveal" data-card="${i.card_id}" tabindex="0">
    <div class="mcard-top"><div class="mcard-img" style="--img:url('${sectorImg(i.sector, true)}')"></div>${ring(i.match, "match")}</div>
    <div class="card-b"><h3>${esc(short(i.title || "", 110))}</h3><div class="faint ell">${esc(i.institution || "")}</div>
      <div class="biz-value"><small>${esc(METRIC_PL[metric] || "wartość")}</small><b>${money(b.metric)}</b></div>
      <ul class="why">${i.why.slice(0, 3).map(w => `<li>${icon("check")}${esc(w)}</li>`).join("")}</ul>
      <div class="plates">${locPlate(i, "sm")}${plate("clock", b.payback, "", "sm")}<span class="plate sm"><span class="pi">${icon("gauge")}</span>${stepper(lvl)}</span></div>
      <div class="item-acts">${likeBtn(i.card_id, i.likes)}${saveBtn(i.card_id)}</div></div></article>`;
}

// ------------------------------------------------------------------ ROLKI (illustration you can see, three facts, one action)
async function pageReels(v) {
  const items = await api("/api/feed?limit=50");
  v.innerHTML = `<div class="reels" id="reels">${items.map((i, n) => { const b = i.brief || {}, lvl = LVLK[b.maturity] ?? 0; IDX[i.card_id] = {...i, title: b.solution, maturity: b.maturity, score: b.score};
    return `<section class="reel" data-n="${n}" aria-label="Pomysł ${n + 1} z ${items.length}" style="--reel-bg:url('${sectorImg(i.sector) || heroImg("innowatorzy")}')">
      <article class="reel-card"><div class="reel-art" style="--img:url('${sectorImg(i.sector) || heroImg("innowatorzy")}')"><div class="reel-progress" aria-hidden="true"><i></i></div>
          <div class="plates">${sectorPlate(i.sector, "sm glass")}${locPlate(i, "sm glass")}</div><span class="reel-ai">${icon("sparkles")}ilustracja AI</span></div>
        <div class="reel-body"><div class="reel-top">${avatar(INST_ICON[i.institution_type] || "building-2")}<div class="who"><b>${esc(i.institution || INST_PL[i.institution_type] || "Instytucja")}</b><small>${esc(INST_PL[i.institution_type] || "")} ${demo(i.synthetic)}</small></div>${ring(b.score, "sm")}</div>
          <div class="reel-title">${esc(b.solution)}</div>
          <div class="reel-hook">${esc(tidy(b.hook))}</div>
          <div class="reel-facts"><div>${icon("banknote")}<small>Budżet</small><b>${esc(i.amount ? pln(i.amount) : (COST_RANGE[i.cost_level] || "—"))}</b></div>
            <div>${icon("gauge")}<small>Etap</small><b>${esc(LVL[lvl])}</b></div><div>${icon("target")}<small>Pierwszy krok</small><b>${esc(short(b.next_step || "—", 60))}</b></div></div>
          <div class="reel-foot"><button class="like ${liked.has(i.card_id) ? "on" : ""}" data-rlike="${i.card_id}" aria-pressed="${liked.has(i.card_id)}" aria-label="Lubię to">${icon("heart")}</button><span class="likes-n" id="ln-${i.card_id}">${i.likes}</span>
            ${saveBtn(i.card_id)}<a class="btn" style="margin-left:auto" href="#/pomysl/${i.card_id}">${icon("arrow-right")}Otwórz</a></div></div>
      </article></section>`; }).join("") || emptyArt("brak", "Brak briefów.")}</div><div class="reel-dots" id="dots">${items.map(() => "<i></i>").join("")}</div>
    <div class="reel-nav"><button class="btn-icon" id="rprev" aria-label="Poprzedni pomysł">${icon("chevron-down", "flip")}</button><button class="btn-icon" id="rnext" aria-label="Następny pomysł">${icon("chevron-down")}</button><span class="kbd-hint">↑ ↓ · L · S</span></div>`;
  const box = $("#reels"), reels = $$(".reel", v), dots = $$("#dots i"); let cur = 0;
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("active"); cur = +e.target.dataset.n; dots.forEach((d, k) => d.classList.toggle("on", k === cur)); } else e.target.classList.remove("active"); }), {root: box, threshold: .6});
  reels.forEach(r => io.observe(r)); reels[0]?.classList.add("active");
  const goTo = n => reels[Math.max(0, Math.min(reels.length - 1, n))]?.scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
  $("#rprev").onclick = () => goTo(cur - 1); $("#rnext").onclick = () => goTo(cur + 1);
  const toggleLike = async (btn, force) => { const id = +btn.dataset.rlike; if (force && liked.has(id)) return; const r = await like(id);
    btn.classList.toggle("on", r.liked); btn.setAttribute("aria-pressed", r.liked); $("#ln-" + id).textContent = r.likes; btn.classList.remove("pop"); void btn.offsetWidth; btn.classList.add("pop"); };
  const onKey = e => { if (!document.body.contains(box)) { document.removeEventListener("keydown", onKey); return; } if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); goTo(cur + 1); } else if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); goTo(cur - 1); }
    else if (e.key === "l" || e.key === "L") { const b = $("[data-rlike]", reels[cur]); if (b) toggleLike(b); } else if (e.key === "s" || e.key === "S") $("[data-save]", reels[cur])?.click(); };
  document.addEventListener("keydown", onKey);
  $$("[data-rlike]", v).forEach(b => b.onclick = () => toggleLike(b));
  $$(".reel-card", v).forEach(c => c.ondblclick = e => { if (e.target.closest("button,a")) return; const b = $("[data-rlike]", c); const burst = document.createElement("div"); burst.className = "burst"; burst.innerHTML = icon("heart"); c.appendChild(burst); setTimeout(() => burst.remove(), 800); toggleLike(b, true); });
  bindCards(v);
}

// ------------------------------------------------------------------ KLASTRY (three ways to see the whole collection)
async function pageClusters(v) {
  const mode = F.mode || "tematy";
  const d = await api("/api/clusters?" + qs({mode}));
  const MODES = [["tematy", "Tematy", "layers", "technologia × branża: tak myśli inwestor o portfelu"], ["rynki", "Rynki", "users", "kto kupi: grupy odbiorców i wielkość rynku"], ["podobne", "Podobne metody", "network", "grupy podobnych opisów ponad granicami branż (embeddingi Basala)"]];
  const cur = MODES.find(m => m[0] === mode);
  v.innerHTML = header("Klastry", "component", "Cała baza w kilkunastu grupach", esc(cur[3]) + ` · ${d.total.toLocaleString("pl-PL")} unikalnych pomysłów`,
    `<div class="tabs">${MODES.map(([k, l, ic]) => `<button class="tab ${k === mode ? "on" : ""}" data-mode="${k}">${icon(ic)}${l}</button>`).join("")}</div>`, "klastry") +
    `<div class="clusters">${d.clusters.map((c, n) => { const tot = c.maturity.reduce((a, b) => a + b, 0) || 1;
      return `<article class="cluster reveal" data-k="${n}"><div class="cl-img" style="--img:url('${sectorImg(c.sector, true)}')"><span class="cl-n">${c.size}</span></div>
        <div class="cl-b"><h3>${esc(c.name)}</h3>${c.keywords?.length ? `<div class="kw">${c.keywords.slice(0, 4).map(w => `<span>${esc(w)}</span>`).join("")}</div>` : ""}
          <div class="mat" title="badania · technologia · gotowe · na rynku">${c.maturity.map((m, k) => `<i style="flex:${m / tot};" class="m${k}"></i>`).join("")}</div>
          <div class="plates">${plate("circle-check", c.ready + " gotowych", "", "sm")}${plate("map-pin", c.regions + " woj.", "", "sm red")}${c.adopters ? plate("users", c.adopters.toLocaleString("pl-PL") + " odbiorców", "", "sm") : ""}${plate("heart", c.likes + " polubień", "", "sm")}</div>
          <button class="link cl-open" aria-expanded="false">${icon("chevron-down")}Pokaż najlepsze</button></div>
        <div class="cl-items"><div class="items">${c.items.map(i => ideaItem(i)).join("")}</div>
          ${c.sector ? `<a class="more" href="#/odkrywaj?${qs({sector: c.sector, tech_area: c.tech_area || ""})}">Wszystkie ${c.size} ${icon("arrow-right")}</a>` : ""}</div></article>`; }).join("") || emptyArt("brak", "Za mało danych do grupowania.")}</div>`;
  $$("[data-mode]", v).forEach(b => b.onclick = () => go("klastry", {mode: b.dataset.mode}));
  $$(".cl-open", v).forEach(b => b.onclick = () => { const el = b.closest(".cluster"), on = !el.classList.contains("open"); el.classList.toggle("open", on); b.setAttribute("aria-expanded", on); b.innerHTML = icon("chevron-down") + (on ? "Zwiń" : "Pokaż najlepsze"); });
  bindCards(v);
}

// ------------------------------------------------------------------ PORTFEL: funnel + saved
async function pageDeals2(v) {
  const tab = F.tab || (Object.keys(loadJSON("radar-deals", {})).length || !Object.keys(SAVED).length ? "lejek" : "zapisane");
  if (tab === "zapisane") return pageSaved(v, true);
  await pageDeals(v);
  const h = $(".page-header", v); if (h) h.insertAdjacentHTML("afterend", portfolioTabs("lejek"));
  if (!Object.keys(DEALS).length) { const e = $(".empty", v); if (e) e.outerHTML = emptyArt("portfel", "Portfel jest pusty. Wejdź w pomysł i kliknij „Do portfela”.", `<a class="btn" href="#/dla/inwestorzy">${icon("trending-up")}Pomysły dla inwestorów</a>`); }
}
const portfolioTabs = cur => `<div class="tabs reveal" style="margin-bottom:1.25rem"><a class="tab ${cur === "lejek" ? "on" : ""}" href="#/portfel?tab=lejek">${icon("kanban")}Lejek transakcji</a><a class="tab ${cur === "zapisane" ? "on" : ""}" href="#/portfel?tab=zapisane">${icon("bookmark")}Zapisane (${Object.keys(SAVED).length})</a></div>`;
async function pageSaved(v) {
  SAVED = loadJSON("radar-saved", {});
  const list = Object.values(SAVED).sort((a, b) => (b.at || "").localeCompare(a.at || ""));
  v.innerHTML = header("Portfel", "bookmark", "Zapisane pomysły", "Twoja krótka lista. Zostaje w tej przeglądarce; przenieś do lejka, gdy zaczynasz rozmowy.",
      list.length >= 2 ? `<a class="btn-soft" href="#/porownaj?ids=${list.slice(0, 4).map(i => i.card_id).join(",")}">${icon("git-compare-arrows")}Porównaj pierwsze ${Math.min(4, list.length)}</a>` : "", "zapisane") + portfolioTabs("zapisane") +
    (list.length ? `<div class="tiles">${list.map(ideaTile).join("")}</div>` : emptyArt("zapisane", "Nic jeszcze nie zapisano. Kliknij zakładkę przy pomyśle, aby go tu dodać.", `<a class="btn" href="#/rolki">${icon("clapperboard")}Przeglądaj rolki</a>`));
  bindCards(v);
  $$("[data-save]", v).forEach(b => b.addEventListener("click", () => setTimeout(() => !b.classList.contains("on") && b.closest(".itile")?.classList.add("gone"), 50)));
}

// ------------------------------------------------------------------ ZGŁOŚ (submission + live pipeline tracker)
const STAGE_PL = {normalize: "Ujednolicenie danych", resolve_org: "Rozpoznanie instytucji", dedup: "Szukanie duplikatów", gate: "Klasyfikacja Basal",
  link: "Powiązania", extract: "Karta pomysłu", maturity: "Dojrzałość", score: "Ocena i ścieżka"};
ROUTES.zglos = pageSubmit;
async function pageSubmit(v) {
  const types = [["szkola", "Szkoła / placówka"], ["uczelnia", "Uczelnia"], ["instytut", "Instytut badawczy"], ["jst", "Samorząd (JST)"], ["inna_publiczna", "Inna instytucja publiczna"], ["firma", "Firma / startup"]];
  v.innerHTML = header("Zgłoś innowację", "lightbulb", "Masz pomysł albo rozwiązanie, które działa?", "Zgłoszenie przechodzi ten sam potok co dane z baz publicznych: klasyfikacja, karta, ocena, ścieżka i odbiorcy. Bez konta. Nie podawaj danych osobowych.", "", "dopasuj") +
    `<div class="grid g-7-5 start"><form class="card reveal sub-form" id="subf"><div class="card-b">
      <label>Nazwa rozwiązania<input name="title" required minlength="8" maxlength="200" placeholder="np. Wspólny kalendarz zajęć pozalekcyjnych gminy"></label>
      <label>Opis: problem, co robicie inaczej, efekt<textarea name="description" required minlength="80" rows="6" placeholder="Jaki problem rozwiązuje, kto z tego korzysta, co już działa (min. 80 znaków)"></textarea><small class="faint" id="cnt">0 / 80</small></label>
      <div class="two"><label>Instytucja<input name="institution" maxlength="200" placeholder="np. SP nr 1 w Rzeszowie"></label>
        <label>Typ instytucji<select name="institution_type"><option value="">—</option>${types.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select></label></div>
      <div class="two"><label>Województwo<select name="region"><option value="">—</option>${(LABELS.voivodeship || []).map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
        <label>Link (opcjonalnie)<input name="url" type="url" placeholder="https://"></label></div>
      <label>Słowa kluczowe (po przecinku)<input name="keywords" placeholder="edukacja, harmonogram, rodzice"></label>
      <div class="chips" style="margin-top:1rem"><button class="btn big" type="submit">${icon("arrow-right")}Wyślij do radaru</button><span class="faint">Ocena pojawi się zwykle w ciągu minuty.</span></div></div></form>
      <aside class="card reveal" id="track">${cardH("radar", "Co się stanie", "ten sam potok co dla danych z baz publicznych")}<div class="card-b"><ol class="track">${Object.values(STAGE_PL).map(s => `<li><i></i>${s}</li>`).join("")}</ol>
        <p class="faint">Zgłoszenia mają najwyższy priorytet w kolejce i nigdy nie są odrzucane po cichu: wątpliwości Basala trafiają do operatora razem z kartą.</p></div></aside></div>`;
  const f = $("#subf"), d = $("textarea", f);
  d.oninput = () => $("#cnt").textContent = `${d.value.length} / 80`;
  f.onsubmit = async e => { e.preventDefault(); const fd = Object.fromEntries(new FormData(f));
    const body = {...fd, keywords: (fd.keywords || "").split(",").map(x => x.trim()).filter(Boolean)};
    Object.keys(body).forEach(k => body[k] === "" && delete body[k]);
    const btn = $("button[type=submit]", f); btn.disabled = true; btn.classList.add("busy");
    try { const r = await api("/api/ingest/zgloszenia/manual", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
      saveJSON("radar-submissions", [...loadJSON("radar-submissions", []), {raw_id: r.raw_id, title: body.title, at: new Date().toISOString()}].slice(-20));
      trackSubmission(r.raw_id); toast("Zgłoszenie przyjęte"); }
    catch (err) { toast("Nie udało się wysłać: " + String(err).slice(0, 80)); btn.disabled = false; btn.classList.remove("busy"); } };
}
async function trackSubmission(rawId) {
  const box = $("#track"); if (!box) return;
  const t0 = Date.now();
  const draw = st => { const done = st.stages.filter(s => s.status !== "pending").length;
    box.innerHTML = cardH("radar", st.card_id ? "Gotowe: pomysł oceniony" : "Radar przetwarza zgłoszenie", `#${rawId} · ${Math.round((Date.now() - t0) / 1000)} s`, "", true) +
      `<div class="card-b"><div class="wiz-bar"><i style="width:${done / st.stages.length * 100}%"></i></div><ol class="track live">${st.stages.map(s => `<li class="${s.status === "pending" ? "" : s.status === "ok" ? "ok" : "warn"}"><i></i>${STAGE_PL[s.stage] || s.stage}${s.detail && s.status !== "ok" ? `<small>${esc(String(s.detail).slice(0, 90))}</small>` : ""}</li>`).join("")}</ol>
      ${st.labels ? `<div class="plates">${st.labels.sector ? sectorPlate(st.labels.sector, "sm") : ""}${st.labels.voivodeship ? plate("map-pin", st.labels.voivodeship, "", "sm red") : ""}${st.labels.innovation_type ? plate("lightbulb", lp("innovation_type", st.labels.innovation_type), "", "sm") : ""}</div>` : ""}
      ${st.review_reasons?.length ? `<p class="faint">${icon("shield-alert")} Do weryfikacji przez operatora: ${esc(st.review_reasons.join("; ").slice(0, 200))}</p>` : ""}
      ${st.card_id ? `<a class="btn" href="#/pomysl/${st.card_id}">${icon("arrow-right")}Zobacz ocenę, wycenę i ścieżkę</a>` : ""}</div>`; };
  for (let i = 0; i < 120; i++) { let st; try { st = await api(`/api/submissions/${rawId}`); } catch (e) { break; }
    if (!document.body.contains(box)) return; draw(st); if (st.card_id || st.record_status === "rejected") return;
    await new Promise(r => setTimeout(r, i < 20 ? 1500 : 4000)); }
}
