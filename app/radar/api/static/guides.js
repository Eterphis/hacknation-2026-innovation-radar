/* Guides: Higgsfield portraits that tell a project's story and help choose. Speech = the browser's own Polish
   voice (speechSynthesis), subtitles always on; no audio is sent anywhere. Loaded after pages.js. */

let GUIDES = null, GUIDE = null, SPEAKING = false;
const GUIDE_BY_ROLE = {inwestorzy: "ada", samorzady: "tomek", startupy: "tomek", szkoly: "ola", uczelnie: "profesor", innowatorzy: "radek"};
const guideKey = () => { try { return localStorage.getItem("radar-guide") || GUIDE_BY_ROLE[(loadProfile() || {}).role] || "radek"; } catch (e) { return "radek"; } };
async function loadGuides() { GUIDES = GUIDES || await api("/api/guides"); GUIDE = GUIDES.find(g => g.key === guideKey()) || GUIDES[0]; return GUIDES; }
const plVoice = () => (speechSynthesis?.getVoices() || []).filter(v => /^pl/i.test(v.lang)).sort((a, b) => (/natural|online|neural/i.test(b.name) ? 1 : 0) - (/natural|online|neural/i.test(a.name) ? 1 : 0))[0];
if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {};

function guideDock() {
  if ($("#gdock")) return;
  const d = document.createElement("div"); d.id = "gdock"; d.className = "gdock";
  d.innerHTML = `<button class="gface" id="gface" aria-label="Przewodnik: posłuchaj albo poproś o pomoc"><img alt=""><span class="gwave"><i></i><i></i><i></i></span></button>
    <section class="gpanel" id="gpanel" aria-live="polite" hidden><div class="ghead"><img alt=""><div><b id="gname"></b><small id="grole"></small></div>
      <button class="btn-icon" id="gclose" aria-label="Zamknij">${icon("x")}</button></div>
      <p class="gsub" id="gsub"></p><div class="gmeta" id="gmeta"></div>
      <div class="chips gacts"><button class="btn-soft" id="gstop">${icon("x")}Zatrzymaj</button><a class="btn-soft" href="#/dopasuj?edit=1">${icon("target")}Pomóż mi wybrać</a></div>
      <div class="gpick" id="gpick"></div></section>`;
  document.body.appendChild(d);
  $("#gface").onclick = () => togglePanel();
  $("#gclose").onclick = () => { stopSpeech(); togglePanel(false); };
  $("#gstop").onclick = stopSpeech;
  paintGuide();
}
function paintGuide() {
  if (!GUIDE) return;
  $$("#gdock img").forEach(i => { i.src = GUIDE.img; });
  $("#gname").textContent = GUIDE.name; $("#grole").textContent = GUIDE.role;
  $("#gpick").innerHTML = (GUIDES || []).map(g => `<button class="gp ${g.key === GUIDE.key ? "on" : ""}" data-g="${g.key}" title="${esc(g.name)}"><img src="${g.img}" alt="${esc(g.name)}"></button>`).join("");
  $$("#gpick [data-g]").forEach(b => b.onclick = () => { try { localStorage.setItem("radar-guide", b.dataset.g); } catch (e) {}
    GUIDE = GUIDES.find(g => g.key === b.dataset.g); paintGuide(); say(`Cześć, tu ${GUIDE.name}, ${GUIDE.role}. Wejdź w pomysł i kliknij „Posłuchaj”, a opowiem Ci o nim.`); });
}
function togglePanel(open) { const p = $("#gpanel"); const on = open ?? p.hidden; p.hidden = !on; $("#gdock").classList.toggle("open", on); }
function stopSpeech() { try { speechSynthesis.cancel(); } catch (e) {} SPEAKING = false; $("#gdock")?.classList.remove("talking"); }

function say(text, meta = "") {
  guideDock(); togglePanel(true);
  const sub = $("#gsub"); $("#gmeta").innerHTML = meta;
  stopSpeech();
  const words = text.split(/(\s+)/);
  sub.innerHTML = words.map((w, k) => /\s+/.test(w) ? w : `<span data-w="${k}">${esc(w)}</span>`).join("");
  const dock = $("#gdock");
  if (!window.speechSynthesis || !plVoice()) {  // no Polish voice: animated subtitles only
    dock.classList.add("talking"); let k = 0; const spans = $$("span[data-w]", sub);
    const tick = () => { if (k >= spans.length) { dock.classList.remove("talking"); return; } spans[k++].classList.add("on"); setTimeout(tick, 260); }; tick(); return;
  }
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "pl-PL"; u.voice = plVoice(); u.pitch = GUIDE?.pitch || 1; u.rate = GUIDE?.rate || 1;
  const offsets = []; let pos = 0; words.forEach((w, k) => { offsets.push([pos, k]); pos += w.length; });
  u.onstart = () => { SPEAKING = true; dock.classList.add("talking"); };
  u.onboundary = e => { const hit = offsets.filter(([p]) => p <= e.charIndex).pop(); if (!hit) return;
    $$("span[data-w]", sub).forEach(s => s.classList.toggle("on", +s.dataset.w <= hit[1]));
    dock.classList.remove("beat"); void dock.offsetWidth; dock.classList.add("beat"); };
  u.onend = u.onerror = () => { SPEAKING = false; dock.classList.remove("talking"); $$("span[data-w]", sub).forEach(s => s.classList.add("on")); };
  speechSynthesis.speak(u);
}

async function tellAbout(cardId) {
  await loadGuides(); guideDock(); paintGuide(); togglePanel(true);
  $("#gsub").innerHTML = `<span class="faint">${esc(GUIDE.name)} czyta kartę…</span>`;
  const p = await api(`/api/cards/${cardId}/pitch?guide=${GUIDE.key}`);
  say(p.text, `<span class="plate sm">${icon(p.by === "reguły" ? "filter" : "sparkles")}${p.by === "reguły" ? "z faktów karty (reguły)" : "Bielik 1.5B na CPU" + (p.seconds ? ` · ${p.seconds} s` : "")}</span>`);
}

// hook into pages: idea page gets "Posłuchaj", reels get "Opowiedz", the wizard shows the guide with the hint
const _pageIdea = pageIdea;
pageIdea = async function (v) {
  await _pageIdea(v);
  const acts = $(".idea-acts", v); if (!acts) return;
  await loadGuides();
  acts.insertAdjacentHTML("afterbegin", `<button class="btn guide-btn" id="glisten"><img src="${GUIDE.img}" alt="">Posłuchaj: ${esc(GUIDE.name)} opowie</button>`);
  $("#glisten").onclick = () => tellAbout(+F._sub);
};
ROUTES.pomysl = pageIdea;
const _pageReels = pageReels;
pageReels = async function (v) {
  await _pageReels(v); await loadGuides();
  $$(".reel-foot", v).forEach(f => { const id = +($("[data-rlike]", f)?.dataset.rlike); if (!id) return;
    f.insertAdjacentHTML("beforeend", `<button class="btn-icon guide-mini" data-tell="${id}" aria-label="${esc(GUIDE.name)} opowie o projekcie" title="${esc(GUIDE.name)} opowie"><img src="${GUIDE.img}" alt=""></button>`); });
  $$("[data-tell]", v).forEach(b => b.onclick = () => tellAbout(+b.dataset.tell));
};
ROUTES.rolki = pageReels;
const _wizard = wizard;
wizard = function (v, prof) {
  _wizard(v, prof);
  if (!GUIDES) return;
  const g = GUIDES.find(x => x.key === (GUIDE_BY_ROLE[prof.role] || "radek")) || GUIDES[0];
  const hint = $(".wiz-q .lead", v);
  if (hint) { hint.outerHTML = `<div class="wiz-guide"><img src="${g.img}" alt=""><p class="lead">${hint.innerHTML}</p><button class="btn-icon" id="wsay" aria-label="Przeczytaj na głos">${icon("mic")}</button></div>`;
    $("#wsay").onclick = () => { GUIDE = g; say($(".wiz-q h1", v).textContent + " " + $(".wiz-guide .lead", v).textContent); }; }
  const side = $(".wiz-side img", v); if (side && prof.role) { side.src = g.img; side.classList.add("guide-portrait"); }
};
loadGuides().then(guideDock).catch(() => {});
window.addEventListener("hashchange", () => { stopSpeech(); if ($("#gpanel")) togglePanel(false); });  // a new page = a new story
