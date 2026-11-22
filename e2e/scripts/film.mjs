// Records the demo film's picture in 1920x1080: an animated intro, the app scene by scene, a closing card.
// Each scene lasts exactly as long as its narration (docs/film/durations.json), so the voice can be laid on top
// without editing. A drawn cursor glides to every click and a caption slides in per scene.
//   node e2e/scripts/film.mjs http://localhost:8088      (or: python scripts/film.py)
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BASE = (process.argv[2] || "http://localhost:8088").replace(/\/$/, "");
const D = JSON.parse(fs.readFileSync(path.join(ROOT, "docs/film/durations.json"), "utf8")).durations;
const SCENES = JSON.parse(fs.readFileSync(path.join(ROOT, "docs/film/scenes.json"), "utf8"));
const CAP = Object.fromEntries(SCENES.map(s => [s.id, s.caption]));
const GAP = 0.8;
const RAW = path.join(ROOT, "docs/film/raw");
const INTRO = pathToFileURL(path.join(ROOT, "docs/film/intro.html")).href;
const PL = (fs.readFileSync(path.join(ROOT, "app/radar/api/static/index.html"), "utf8").match(/<path id="pl-shape" d="([^"]+)"/) || [])[1] || "";
fs.rmSync(RAW, { recursive: true, force: true });

const W = 1920, H = 1080;
const browser = await chromium.launch({ channel: process.env.FILM_CHANNEL || "msedge", args: ["--mute-audio"] });
const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: RAW, size: { width: W, height: H } },
  locale: "pl-PL", colorScheme: "light", reducedMotion: "no-preference" });
// film overlay: a cursor that glides to each click and a caption pill; reinstalled on every page load
await ctx.addInitScript(([pl]) => {
  window.PL_SHAPE = pl;
  const css = `#film-cursor{position:fixed;z-index:99999;left:0;top:0;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;
    background:rgba(190,26,52,.18);border:2.5px solid #BE1A34;box-shadow:0 4px 14px rgba(0,0,0,.18);pointer-events:none;
    transition:transform .75s cubic-bezier(.45,.05,.2,1);}
    #film-cursor.tap{animation:filmtap .45s ease-out}@keyframes filmtap{50%{box-shadow:0 0 0 16px rgba(190,26,52,.18)}}
    #film-cap{position:fixed;z-index:99998;left:48px;bottom:44px;display:flex;align-items:center;gap:14px;padding:16px 26px 16px 18px;border-radius:18px;
    background:rgba(20,19,18,.86);color:#fff;font:700 26px "Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;letter-spacing:-.01em;
    transform:translateY(40px);opacity:0;transition:transform .6s cubic-bezier(.2,.8,.2,1),opacity .6s;pointer-events:none;}
    #film-cap i{width:10px;height:34px;border-radius:6px;background:linear-gradient(#fff 50%,#BE1A34 50%)}
    #film-cap.on{transform:none;opacity:1}
    #gdock{display:none !important}`;
  const install = () => { if (document.getElementById("film-cursor") || !document.body) return;
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
    const c = document.createElement("div"); c.id = "film-cursor"; c.style.transform = `translate(${innerWidth * .6}px, ${innerHeight * .55}px)`; document.body.appendChild(c);
    const p = document.createElement("div"); p.id = "film-cap"; document.body.appendChild(p); };
  document.addEventListener("DOMContentLoaded", install);
  window.__mv = (x, y) => { install(); const c = document.getElementById("film-cursor"); if (c) c.style.transform = `translate(${x}px, ${y}px)`; };
  window.__tap = () => { const c = document.getElementById("film-cursor"); if (!c) return; c.classList.remove("tap"); void c.offsetWidth; c.classList.add("tap"); };
  window.__cap = t => { install(); const p = document.getElementById("film-cap"); if (!p) return; p.classList.remove("on");
    if (t) setTimeout(() => { p.innerHTML = "<i></i>" + t; p.classList.add("on"); }, 250); };
}, [PL]);

const page = await ctx.newPage();
const pause = ms => page.waitForTimeout(ms);
const settled = async () => { await page.waitForFunction(() => !document.querySelector("#view")?.hasAttribute("aria-busy"), null, { timeout: 30000 }).catch(() => {}); await pause(500); };
const cap = async id => page.evaluate(t => window.__cap?.(t), CAP[id] || "");
async function click(locator) {  // glide the drawn cursor to the element, then click it
  const el = locator.first(); await el.scrollIntoViewIfNeeded().catch(() => {});
  const b = await el.boundingBox();
  if (b) { await page.evaluate(([x, y]) => window.__mv?.(x, y), [b.x + b.width / 2, b.y + b.height / 2]); await pause(800); await page.evaluate(() => window.__tap?.()); await pause(150); }
  await el.click();
}
async function glide(x, y, ms = 900) { await page.evaluate(([a, b]) => window.__mv?.(a, b), [x, y]); await pause(ms); }
async function scroll(px, steps = 6) { for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, px / steps); await pause(90); } }
const go = async hash => { await page.goto(`${BASE}/?theme=light#/${hash}`); await settled(); };
const timeline = [];
let t0 = Date.now();
async function scene(id, run, minLen = 0) {
  const start = Date.now(), len = Math.max(minLen, D[id] + GAP) * 1000;
  timeline.push({ id, at: (start - t0) / 1000, len: len / 1000 });
  await run(len);
  const left = start + len - Date.now();
  if (left > 0) await pause(left); else console.warn(`scena ${id} dłuższa o ${-left} ms`);
}

for (const p of ["/api/insights", "/api/regions", "/api/clusters", "/api/personas/inwestorzy", "/api/feed?limit=10", "/api/sources",
  "/api/match?role=samorzady&voivodeship=pomorskie"]) await fetch(BASE + p).catch(() => {});
await page.goto(`${INTRO}?part=intro`);
t0 = Date.now();

await scene("00-intro", async () => {}, 13.5);
await scene("01-start", async len => {
  await page.goto(`${BASE}/?theme=light#/`); await settled(); await cap("01-start");
  await glide(W * .3, H * .55, len * .35); await scroll(420, 8); await pause(600);
});
await scene("02-mapa", async len => {
  await cap("02-mapa");
  await page.evaluate(() => document.querySelector("#homemap")?.scrollIntoView({ behavior: "smooth", block: "center" })); await pause(1200);
  await click(page.locator('#homemap path[data-v="pomorskie"]')); await settled(); await cap("02-mapa");
  await glide(W * .7, H * .5, len * .2);
});
await scene("03-zrodla", async len => {
  await go("zrodla"); await cap("03-zrodla"); await pause(len * .3); await scroll(600, 10); await pause(len * .2); await scroll(400, 8);
});
await scene("04-kreator", async () => {
  await go(""); await cap("04-kreator");
  await click(page.getByRole("link", { name: "Dopasuj w 30 sekund" })); await settled(); await pause(700);
  await click(page.getByRole("radio", { name: "Samorządy i instytucje publiczne" })); await pause(1100);
  await click(page.getByRole("radio", { name: "Gmina lub miasto" })); await pause(1100);
  await click(page.getByRole("radio", { name: "pomorskie", exact: true })); await pause(900);
  await click(page.getByRole("button", { name: "Pokaż wyniki" })); await settled(); await cap("04-kreator");
  await scroll(300, 6);
});
await scene("05-pomysl", async len => {
  const local = page.getByRole("main").getByRole("article").filter({ hasText: "Twój region: pomorskie" });
  await click((await local.count()) ? local.getByRole("heading", { level: 3 }) : page.getByRole("main").getByRole("article").getByRole("heading", { level: 3 }));
  await settled(); await cap("05-pomysl"); await pause(len * .4); await scroll(520, 8);
});
await scene("06-inwestor", async len => {
  await go("dla/inwestorzy"); await cap("06-inwestor"); await pause(900);
  await click(page.getByRole("main").getByRole("article")); await settled(); await cap("06-inwestor"); await pause(600);
  await click(page.getByRole("tab", { name: "Dla inwestora" })); await pause(len * .22);
  await click(page.getByRole("button", { name: "Do portfela" })); await pause(900);
  await go("portfel?tab=lejek"); await cap("06-inwestor");
});
await scene("07-rolki", async len => {
  await go("rolki"); await cap("07-rolki"); await pause(len * .35);
  await page.keyboard.press("ArrowDown"); await pause(len * .3); await page.keyboard.press("ArrowDown");
});
await scene("08-dostepnosc", async () => {
  await go(""); await cap("08-dostepnosc"); await pause(600);
  await click(page.locator("#a11ybtn")); await pause(900);
  await click(page.locator('[data-fs="2"]')); await pause(1200);
  await click(page.locator('[data-sw="contrast"]')); await pause(1400);
  await page.keyboard.press("Escape"); await pause(400);
  await click(page.locator("#scopebtn")); await pause(800);
  await click(page.locator('[data-scope="pomorskie"]')); await settled(); await cap("08-dostepnosc"); await pause(1500);
});
await scene("09-wdrozenie", async len => {
  await page.evaluate(() => { try { A11Y = { ...A11Y_DEF }; applyA11y(); setScope(""); } catch (e) {} });
  await page.goto(process.env.FILM_GRAFANA || "http://localhost:3000/d/radar?orgId=1&kiosk&from=now-1h&to=now");
  await pause(2500); await cap("09-wdrozenie");
  await glide(W * .35, H * .4, len * .3); await scroll(700, 10); await pause(len * .2); await scroll(700, 10);
});
await scene("10-koniec", async () => {
  await page.evaluate(() => { try { A11Y = { ...A11Y_DEF }; applyA11y(); setScope(""); } catch (e) {} });
  await page.goto(`${INTRO}?part=outro`);
}, 9);

const video = await page.video().path();
await ctx.close(); await browser.close();
fs.writeFileSync(path.join(ROOT, "docs/film/timeline.json"), JSON.stringify({ video, timeline }, null, 1));
console.log("video", video, "scen:", timeline.length, "koniec", ((Date.now() - t0) / 1000).toFixed(1), "s");
