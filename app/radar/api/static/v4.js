/* v4: accessibility panel, regional work mode, the map on the home page. Loaded last (after guides.js).
   Nothing here generates text: everything shown comes from the API's stored data. */

// ------------------------------------------------------------------ accessibility (WCAG 2.1: 1.4.4, 1.4.12, 2.3.3)
const A11Y_KEY = "radar-a11y";
const A11Y_DEF = {fs: 0, contrast: false, read: false, links: false, calm: false, noimg: false};
let A11Y = {...A11Y_DEF}; try { A11Y = {...A11Y_DEF, ...JSON.parse(localStorage.getItem(A11Y_KEY) || "{}")}; } catch (e) {}
function applyA11y() {
  const r = document.documentElement;
  ["fs-1", "fs-2", "fs-3"].forEach((c, i) => r.classList.toggle(c, A11Y.fs === i + 1));
  ["contrast", "read", "links", "calm", "noimg"].forEach(k => r.classList.toggle("a11y-" + k, !!A11Y[k]));
  try { localStorage.setItem(A11Y_KEY, JSON.stringify(A11Y)); } catch (e) {}
}
applyA11y();
const A11Y_SWITCHES = [["contrast", "Wysoki kontrast", "ciemniejszy tekst, wyraźne obramowania"], ["read", "Czytelny tekst", "większe odstępy między literami i wierszami"],
  ["links", "Podkreśl linki", "linki widać bez koloru"], ["calm", "Bez animacji", "zatrzymuje ruch i przejścia"], ["noimg", "Bez ilustracji", "mniej bodźców, szybciej na słabym łączu"]];

// ------------------------------------------------------------------ regional work mode: one voivodeship everywhere
let SCOPE = ""; try { SCOPE = localStorage.getItem("radar-scope") || ""; } catch (e) {}
let REGION_NAMES = null;
const SCOPED = /^\/api\/(ideas|graph|feed|personas\/[a-z]+|deployments|insights|match)(\?|$)/;
const _fetch = window.fetch.bind(window);
window.fetch = (url, o) => {  // every list the UI reads gets the region, unless the page already asked for one
  if (SCOPE && typeof url === "string" && SCOPED.test(url) && !/[?&]voivodeship=/.test(url))
    url += (url.includes("?") ? "&" : "?") + "voivodeship=" + encodeURIComponent(SCOPE);
  return _fetch(url, o);
};
function setScope(v) {
  SCOPE = v || ""; try { SCOPE ? localStorage.setItem("radar-scope", SCOPE) : localStorage.removeItem("radar-scope"); } catch (e) {}
  paintScope(); toast(SCOPE ? `Tryb regionalny: ${SCOPE}` : "Cała Polska"); route();
}
function paintScope() {
  const b = $("#scopebtn"); if (!b) return;
  b.classList.toggle("on", !!SCOPE); b.setAttribute("aria-label", "Zakres danych: " + (SCOPE || "cała Polska") + ". Zmień województwo");
  b.innerHTML = icon(SCOPE ? "locate" : "map-pin") + `<span>${esc(SCOPE || "Cała Polska")}</span>`;
}

// ------------------------------------------------------------------ header tools
function popover(btn, pop) {
  const close = () => { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); };
  btn.onclick = e => { e.stopPropagation(); const open = pop.hidden; $$(".pop").forEach(p => { p.hidden = true; }); pop.hidden = !open; btn.setAttribute("aria-expanded", open);
    if (open) $("button", pop)?.focus(); };
  pop.addEventListener("click", e => e.stopPropagation());
  document.addEventListener("click", close);
  pop.addEventListener("keydown", e => { if (e.key === "Escape") { close(); btn.focus(); } });
}
async function headerTools() {
  const tools = $(".nav-tools"); if (!tools || $("#scopebtn")) return;
  tools.insertAdjacentHTML("afterbegin", `
    <div class="tool-wrap"><button class="scope-btn" id="scopebtn" aria-haspopup="true" aria-expanded="false" aria-controls="scopepop"></button>
      <div class="pop" id="scopepop" hidden role="dialog" aria-label="Tryb pracy: województwo"><h2>Tryb pracy</h2><p>Wybierz województwo, a cała aplikacja pokaże tylko jego pomysły: przegląd, listy, rolki, dopasowanie i wdrożenia.</p><div class="rlist" id="rlist"></div></div></div>
    <div class="tool-wrap"><button class="btn-icon" id="a11ybtn" aria-label="Dostępność: rozmiar tekstu, kontrast, animacje" title="Dostępność" aria-haspopup="true" aria-expanded="false" aria-controls="a11ypop">${icon("accessibility")}</button>
      <div class="pop" id="a11ypop" hidden role="dialog" aria-label="Dostępność"><h2>Dostępność</h2><p>Ustawienia zostają w tej przeglądarce.</p>
        <div class="a11y-row"><span>${icon("type")} Rozmiar tekstu</span><div class="seg2" role="group" aria-label="Rozmiar tekstu">${["A", "A+", "A++", "A+++"].map((l, i) => `<button data-fs="${i}" aria-pressed="${A11Y.fs === i}" aria-label="Rozmiar ${[100, 112, 125, 144][i]}%">${l}</button>`).join("")}</div></div>
        ${A11Y_SWITCHES.map(([k, l, d]) => `<div class="a11y-row"><span><b>${l}</b><br><small class="faint">${d}</small></span><button class="switch" role="switch" data-sw="${k}" aria-checked="${!!A11Y[k]}" aria-label="${l}">${A11Y[k] ? "wł." : "wył."}</button></div>`).join("")}
        <button class="btn-soft reset" id="a11yreset">${icon("x")}Przywróć domyślne</button></div></div>`);
  paintScope(); popover($("#scopebtn"), $("#scopepop")); popover($("#a11ybtn"), $("#a11ypop"));
  const paintA11y = () => { $$("[data-fs]").forEach(b => b.setAttribute("aria-pressed", +b.dataset.fs === A11Y.fs));
    $$("[data-sw]").forEach(b => { b.setAttribute("aria-checked", !!A11Y[b.dataset.sw]); b.textContent = A11Y[b.dataset.sw] ? "wł." : "wył."; }); };
  $$("[data-fs]").forEach(b => b.onclick = () => { A11Y.fs = +b.dataset.fs; applyA11y(); paintA11y(); });
  $$("[data-sw]").forEach(b => b.onclick = () => { A11Y[b.dataset.sw] = !A11Y[b.dataset.sw]; applyA11y(); paintA11y(); });
  $("#a11yreset").onclick = () => { A11Y = {...A11Y_DEF}; applyA11y(); paintA11y(); };
  const reg = await api("/api/regions");
  REGION_NAMES = reg.regions.map(r => [r.voivodeship, r.selected]).sort((a, b) => a[0].localeCompare(b[0], "pl"));
  const paintList = () => { $("#rlist").innerHTML = `<button class="all ${SCOPE ? "" : "on"}" data-scope="">${icon("map")} Cała Polska</button>` +
    REGION_NAMES.map(([n, c]) => `<button data-scope="${esc(n)}" class="${SCOPE === n ? "on" : ""}">${esc(n)} <small class="faint">${c}</small></button>`).join("");
    $$("[data-scope]").forEach(b => b.onclick = () => { $("#scopepop").hidden = true; setScope(b.dataset.scope); paintList(); }); };
  paintList();
}

// ------------------------------------------------------------------ pages: scope bar, home map, region shortcut on the map page
function scopeBar(v) {
  if (!SCOPE || $(".scope-bar", v)) return;
  v.insertAdjacentHTML("afterbegin", `<div class="scope-bar" role="status">${icon("locate")}Tryb regionalny: pokazujemy tylko pomysły z województwa ${esc(SCOPE)}<button class="btn-soft" id="scopeoff">${icon("map")}Cała Polska</button></div>`);
  $("#scopeoff", v).onclick = () => setScope("");
}
const _pageHome4 = pageHome;
pageHome = async function (v) {
  await _pageHome4(v);
  const kpis = $(".kpis3", v); if (!kpis) return;
  const reg = await api("/api/regions"), top = reg.regions.slice().sort((a, b) => b.selected - a.selected);
  kpis.insertAdjacentHTML("afterend", `<section class="home-map reveal" aria-label="Pomysły na mapie Polski">
    <div class="card">${cardH("map", SCOPE ? "Twoje województwo" : "Gdzie powstają", "kliknij województwo: jego pomysły")}<div class="card-b" id="homemap"></div></div>
    <div class="card">${cardH("locate", "Pracujesz w jednym regionie?", "urząd marszałkowski, ARR, samorząd: ustaw tryb regionalny")}<div class="card-b">
      <div class="rtop">${top.slice(0, 5).map(r => `<button data-goreg="${esc(r.voivodeship)}">${icon("map-pin")}${esc(r.voivodeship)}<b>${r.selected}</b></button>`).join("")}</div>
      <div class="chips" style="margin-top:.8rem"><button class="btn-soft" id="pickscope">${icon("locate")}${SCOPE ? "Zmień województwo" : "Wybierz województwo"}</button><a class="btn-soft" href="#/mapa">${icon("map")}Pełna mapa i luki</a></div></div></div></section>`);
  await drawPoland($("#homemap"), reg, {compact: true, selected: SCOPE, onPick: name => go("mapa", {voivodeship: name})});
  $$("[data-goreg]", v).forEach(b => b.onclick = () => go("mapa", {voivodeship: b.dataset.goreg}));
  $("#pickscope", v).onclick = e => { e.stopPropagation(); $("#scopebtn").click(); };
  // the old map further down repeats this one
  $("#minimap", v)?.closest(".sec-block")?.remove();  // trends live in Klastry: the home page keeps ~7 things
};
ROUTES[""] = pageHome;
const _pageMap4 = pageMap;
pageMap = async function (v) {
  await _pageMap4(v);
  const sel = F.voivodeship; if (!sel) return;
  const side = $("#side .card-h", v);
  if (side && SCOPE !== sel) { side.insertAdjacentHTML("beforeend", `<button class="btn-soft" id="setscope" style="margin-left:auto">${icon("locate")}Pracuj tylko tutaj</button>`);
    $("#setscope", v).onclick = () => setScope(sel); }
};
ROUTES.mapa = pageMap;

// every page: the scope bar on top (route() in app.js renders, then we decorate)
new MutationObserver(() => { const v = $("#view"); if (!v.hasAttribute("aria-busy")) scopeBar(v); }).observe($("#view"), {attributes: true, attributeFilter: ["aria-busy"]});

// header: drop the least needed labels step by step until the menu fits (zoom, text size, window width)
function fitHeader() {
  const b = document.body, nav = $("#nav"); if (!nav) return;
  const steps = ["hdr-1", "hdr-5", "hdr-2", "hdr-3", "hdr-4"];  // order = what we give up first
  steps.forEach(c => b.classList.toggle(c, false));
  if (matchMedia("(max-width: 768px)").matches) return;  // phones use the bottom bar
  const fits = () => nav.scrollWidth <= nav.clientWidth + 1;
  for (const c of steps) { if (fits()) return; b.classList.add(c); }
}
$$("#nav a").forEach(a => { a.title = a.textContent.trim(); });
new ResizeObserver(() => fitHeader()).observe(document.documentElement);
const _applyA11y4 = applyA11y; applyA11y = function () { _applyA11y4(); requestAnimationFrame(fitHeader); };
headerTools().then(fitHeader).catch(() => {});
fitHeader();
