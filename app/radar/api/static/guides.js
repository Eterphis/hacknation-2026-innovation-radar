/* Guides: Higgsfield portraits that tell a project's story and help choose. Nothing is generated while you wait:
   the text was prepared in advance (rules or the local Bielik 1.5B, stored in the card) and the voice is a
   pre-recorded mp3 (ElevenLabs, one voice per guide: /static/audio/index.json). No recording: subtitles only.
   Loaded after pages.js. */

let GUIDES = null, GUIDE = null, SPEAKING = false;
const GUIDE_BY_ROLE = {inwestorzy: "ada", samorzady: "tomek", startupy: "tomek", szkoly: "ola", uczelnie: "profesor", innowatorzy: "radek"};
const guideKey = () => { try { return localStorage.getItem("radar-guide") || GUIDE_BY_ROLE[(loadProfile() || {}).role] || "radek"; } catch (e) { return "radek"; } };
async function loadGuides() { GUIDES = GUIDES || await api("/api/guides"); GUIDE = GUIDES.find(g => g.key === guideKey()) || GUIDES[0]; return GUIDES; }
let AUDIO_IDX = null, PLAYER = null;
const audioIndex = async () => AUDIO_IDX = AUDIO_IDX || await fetch("/static/audio/index.json").then(r => r.ok ? r.json() : {}).catch(() => ({}));
async function textSha(text) {  // the recording belongs to this exact text (a regenerated narration needs a new recording)
  if (!crypto?.subtle) return null;
  const h = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text));
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 12);
}
async function clipFor(key, text) {
  const idx = await audioIndex(), c = idx[key]; if (!c) return null;
  if (c.sha) { const s = await textSha(text); if (s && s !== c.sha) return null; }
  return c;
}

function guideDock() {
  if ($("#gdock")) return;
  const d = document.createElement("div"); d.id = "gdock"; d.className = "gdock";
  d.innerHTML = `<button class="gface" id="gface" aria-label="Przewodnik: posłuchaj albo poproś o pomoc" aria-expanded="false" aria-controls="gpanel"><img alt="" width="68" height="68" decoding="async" data-ai><span class="gwave"><i></i><i></i><i></i></span></button><span class="gai" aria-hidden="true">AI</span>
    <section class="gpanel" id="gpanel" aria-live="polite" hidden><div class="ghead"><img alt="" width="84" height="84" decoding="async" data-ai><div><b id="gname"></b><small id="grole"></small></div>
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
async function sayIntro() { const c = await clipFor("intro-" + GUIDE.key); say(c ? c.text : `Cześć, tu ${GUIDE.name}, ${GUIDE.role}.`, c ? voicePlate(c, null) : "", c); }
const voicePlate = (c, by) => `<span class="plate sm">${icon("volume-2")}głos: ${esc(c.voice)} · nagrany wcześniej</span>` + (by ? `<span class="plate sm">${icon(by === "reguły" ? "filter" : "sparkles")}tekst: ${by === "reguły" ? "z faktów karty (reguły)" : "Bielik 1.5B, przygotowany wcześniej"}</span>` : "");
function paintGuide() {
  if (!GUIDE) return;
  $$("#gdock img").forEach(i => { i.src = GUIDE.img; });
  $("#gname").textContent = GUIDE.name; $("#grole").textContent = GUIDE.role + " · portret: ilustracja AI";
  $("#gpick").innerHTML = (GUIDES || []).map(g => `<button class="gp ${g.key === GUIDE.key ? "on" : ""}" data-g="${g.key}" title="${esc(g.name)}"><img src="${g.img}" alt="${esc(g.name)}" width="40" height="40" decoding="async" loading="lazy" data-ai></button>`).join("");
  $$("#gpick [data-g]").forEach(b => b.onclick = () => { try { localStorage.setItem("radar-guide", b.dataset.g); } catch (e) {}
    GUIDE = GUIDES.find(g => g.key === b.dataset.g); paintGuide(); sayIntro(); });
}
function togglePanel(open) { const p = $("#gpanel"); const on = open ?? p.hidden; p.hidden = !on; $("#gdock").classList.toggle("open", on); $("#gface").setAttribute("aria-expanded", on); }
// Escape closes the guide's panel and puts focus back on the portrait that opened it
document.addEventListener("keydown", e => { const p = $("#gpanel"); if (e.key !== "Escape" || !p || p.hidden) return; stopSpeech(); togglePanel(false); $("#gface").focus(); });
function stopSpeech() { if (PLAYER) { PLAYER.pause(); PLAYER = null; } clearTimeout(stopSpeech._t); SPEAKING = false; $("#gdock")?.classList.remove("talking"); }

function say(text, meta = "", clip = null) {
  guideDock(); togglePanel(true);
  const sub = $("#gsub"); $("#gmeta").innerHTML = meta;
  stopSpeech();
  const words = text.split(/(\s+)/);
  sub.innerHTML = words.map((w, k) => /\s+/.test(w) ? w : `<span data-w="${k}">${esc(w)}</span>`).join("");
  const dock = $("#gdock"), spans = $$("span[data-w]", sub);
  const upto = n => spans.forEach((s, i) => s.classList.toggle("on", i < n));
  if (!clip) {  // no recording for this text: subtitles at reading pace, no synthetic voice
    dock.classList.add("talking"); let k = 0;
    const tick = () => { if (k >= spans.length) { dock.classList.remove("talking"); return; } upto(++k); stopSpeech._t = setTimeout(tick, 230); }; tick(); return;
  }
  const a = PLAYER = new Audio("/static/audio/" + clip.file);
  a.onplay = () => { SPEAKING = true; dock.classList.add("talking"); };
  a.ontimeupdate = () => { if (a.duration) upto(Math.ceil(spans.length * a.currentTime / a.duration)); };
  a.onended = a.onerror = () => { SPEAKING = false; dock.classList.remove("talking"); upto(spans.length); };
  a.play().catch(() => { a.onerror(); });
}

async function tellAbout(cardId) {
  await loadGuides(); guideDock(); paintGuide(); togglePanel(true);
  $("#gsub").innerHTML = `<span class="faint">${esc(GUIDE.name)} czyta kartę…</span>`;
  const p = await api(`/api/cards/${cardId}/pitch?guide=${GUIDE.key}`);
  const clip = await clipFor(`${cardId}-${GUIDE.key}`, p.text);
  say(p.text, clip ? voicePlate(clip, p.by) : `<span class="plate sm">${icon(p.by === "reguły" ? "filter" : "sparkles")}${p.by === "reguły" ? "z faktów karty (reguły)" : "tekst: Bielik 1.5B, przygotowany wcześniej"}</span><span class="plate sm">napisy (bez nagrania)</span>`, clip);
}

// hook into pages: idea page gets "Posłuchaj", reels get "Opowiedz", the wizard shows the guide with the hint
const _pageIdea = pageIdea;
pageIdea = async function (v) {
  await _pageIdea(v);
  const acts = $(".idea-acts", v); if (!acts) return;
  await loadGuides();
  acts.insertAdjacentHTML("afterbegin", `<button class="btn guide-btn" id="glisten"><img src="${GUIDE.img}" alt="" width="26" height="26" decoding="async" data-ai>${esc(GUIDE.name)}: projekt w skrócie</button>`);
  $("#glisten").onclick = () => tellAbout(+F._sub);
};
ROUTES.pomysl = pageIdea;
const _pageReels = pageReels;
pageReels = async function (v) {
  await _pageReels(v); await loadGuides();
  $$(".reel-foot", v).forEach(f => { const id = +($("[data-rlike]", f)?.dataset.rlike); if (!id) return;
    f.insertAdjacentHTML("beforeend", `<button class="btn-icon guide-mini" data-tell="${id}" aria-label="${esc(GUIDE.name)} opowie o projekcie" title="${esc(GUIDE.name)} opowie"><img src="${GUIDE.img}" alt="" width="44" height="44" decoding="async" loading="lazy" data-ai></button>`); });
  $$("[data-tell]", v).forEach(b => b.onclick = () => tellAbout(+b.dataset.tell));
};
ROUTES.rolki = pageReels;
const _wizard = wizard;
wizard = function (v, prof) {
  _wizard(v, prof);
  if (!GUIDES) return;
  const g = GUIDES.find(x => x.key === (GUIDE_BY_ROLE[prof.role] || "radek")) || GUIDES[0];
  const hint = $(".wiz-q .lead", v);
  if (hint) { hint.outerHTML = `<div class="wiz-guide"><img src="${g.img}" alt="" width="56" height="56" decoding="async" data-ai><p class="lead">${hint.innerHTML}</p></div>`; }
  const side = $(".wiz-side img", v); if (side && prof.role && side.getAttribute("src") !== g.img) { side.src = g.img; side.classList.add("guide-portrait"); }
};
loadGuides().then(guideDock).catch(() => {});
window.addEventListener("hashchange", () => { stopSpeech(); if ($("#gpanel")) togglePanel(false); });  // a new page = a new story
