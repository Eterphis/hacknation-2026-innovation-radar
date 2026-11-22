// Records the demo film's picture: one scene per narration clip, each scene lasts exactly as long as its voice
// (docs/film/durations.json), so the voice track can be laid on top without editing. Output: docs/film/raw/*.webm
//   node e2e/scripts/film.mjs http://localhost:8088
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BASE = (process.argv[2] || "http://localhost:8088").replace(/\/$/, "");
const D = JSON.parse(fs.readFileSync(path.join(ROOT, "docs/film/durations.json"), "utf8")).durations;
const GAP = 0.7, ADA = 11;  // pause after each line; seconds of the guide's own voice in scene 7
const RAW = path.join(ROOT, "docs/film/raw");
fs.rmSync(RAW, { recursive: true, force: true });

const browser = await chromium.launch({ channel: process.env.FILM_CHANNEL || "msedge", args: ["--autoplay-policy=no-user-gesture-required", "--mute-audio"] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: RAW, size: { width: 1280, height: 720 } },
  locale: "pl-PL", colorScheme: "light" });
const page = await ctx.newPage();
const pause = ms => page.waitForTimeout(ms);
const settled = async () => { await page.waitForFunction(() => !document.querySelector("#view")?.hasAttribute("aria-busy"), null, { timeout: 30000 }); await pause(400); };
const smooth = async (sel, block = "start") => { await page.evaluate(([s, b]) => document.querySelector(s)?.scrollIntoView({ behavior: "smooth", block: b }), [sel, block]); await pause(900); };
const timeline = [];
let t = Date.now();
async function scene(id, run, extra = 0) {
  const start = Date.now(), len = (D[id] + GAP + extra) * 1000;
  timeline.push({ id, at: (start - t) / 1000, len: len / 1000 });
  await run(len);
  const left = start + len - Date.now();
  if (left > 0) await pause(left); else console.warn(`scena ${id} przekroczyła czas o ${-left} ms`);
}

// warm the caches first so no scene waits on a cold endpoint, then start the clock with the first frame
for (const p of ["/api/insights", "/api/regions", "/api/clusters", "/api/personas/inwestorzy", "/api/match?role=samorzady&voivodeship=pomorskie"])
  await fetch(BASE + p).catch(() => {});
await page.goto(`${BASE}/?theme=light#/`);
t = Date.now();

await scene("01-start", async len => {
  await settled(); await pause(len * .55);
  await page.mouse.wheel(0, 380); await pause(600);
});
await scene("02-mapa", async len => {
  await smooth("#homemap", "center"); await pause(len * .45);
  await page.goto(`${BASE}/?theme=light#/mapa?voivodeship=pomorskie`); await settled();
});
await scene("03-kreator", async () => {
  await page.goto(`${BASE}/?theme=light#/`); await settled();
  await page.getByRole("link", { name: "Dopasuj w 30 sekund" }).click(); await settled(); await pause(1200);
  await page.getByRole("radio", { name: "Samorządy i instytucje publiczne" }).click(); await pause(1500);
  await page.getByRole("radio", { name: "Gmina lub miasto" }).click(); await pause(1500);
  await page.getByRole("radio", { name: "pomorskie", exact: true }).click(); await pause(1200);
  await page.getByRole("button", { name: "Pokaż wyniki" }).click(); await settled();
  await page.mouse.wheel(0, 250);
});
await scene("04-pomysl", async len => {
  const local = page.getByRole("main").getByRole("article").filter({ hasText: "Twój region: pomorskie" }).first();
  await local.getByRole("heading", { level: 3 }).click(); await settled(); await pause(len * .45);
  await page.mouse.wheel(0, 520); await pause(800);
});
await scene("05-specyfikacja", async len => {
  const href = await page.getByRole("link", { name: "Specyfikacja wdrożenia" }).getAttribute("href");
  const back = page.url();
  await page.goto(new URL(href, BASE).href.replace(/[?&]auto=1/, "")); await pause(len * .5);
  await page.mouse.wheel(0, 500); await pause(len * .3);
  await page.goto(back);
});
await scene("06-inwestor", async len => {
  await page.goto(`${BASE}/?theme=light#/dla/inwestorzy`); await settled(); await pause(1200);
  await page.getByRole("main").getByRole("article").first().click(); await settled(); await pause(800);
  await page.getByRole("tab", { name: "Dla inwestora" }).click(); await pause(len * .3);
  await page.getByRole("button", { name: "Do portfela" }).click(); await pause(1000);
  await page.goto(`${BASE}/?theme=light#/portfel?tab=lejek`); await settled();
});
await scene("07-przewodnik", async () => {
  await page.evaluate(() => localStorage.setItem("radar-guide", "ada"));
  await page.goto(`${BASE}/?theme=light#/pomysl/1019`); await settled();
  await pause((D["07-przewodnik"] - 1) * 1000);  // the narrator speaks, then Ada tells the story herself
  timeline.push({ id: "ada", at: (Date.now() - t) / 1000, len: ADA });
  await page.locator("#glisten").click();
}, ADA);
await scene("08-zgloszenie", async len => {
  await page.evaluate(() => typeof stopSpeech === "function" && stopSpeech());
  await page.goto(`${BASE}/?theme=light#/zglos`); await settled();
  await page.fill("#subf [name=title]", "Wspólny kalendarz sal sportowych gminy i szkół");
  await page.fill("#subf [name=description]", "Gmina i szkoły udostępniają sale mieszkańcom przez jeden kalendarz online. Kluby rezerwują terminy, dyrektorzy widzą obłożenie, a gmina rozlicza opłaty. Działa w jednej gminie od roku.");
  await page.fill("#subf [name=institution]", "Urząd Gminy");
  await page.selectOption("#subf [name=region]", "lubelskie");
  await page.getByRole("button", { name: "Wyślij do radaru" }).click(); await pause(len * .3);
  await page.locator("#scopebtn").click(); await pause(700);
  await page.locator('[data-scope="pomorskie"]').click(); await settled(); await pause(1500);
  await page.locator("#a11ybtn").click(); await pause(600);
  await page.locator('[data-fs="2"]').click(); await pause(700);
  await page.locator('[data-sw="contrast"]').click(); await pause(1200);
});
await scene("09-koniec", async len => {
  await page.evaluate(() => { A11Y = {...A11Y_DEF}; applyA11y(); document.querySelectorAll(".pop").forEach(p => { p.hidden = true; }); setScope(""); });
  await page.goto(`${BASE}/?theme=light#/zrodla`); await settled(); await pause(len * .5);
  await page.goto(`${BASE}/?theme=light#/`); await settled();
});

const video = await page.video().path();
await ctx.close(); await browser.close();
fs.writeFileSync(path.join(ROOT, "docs/film/timeline.json"), JSON.stringify({ video, timeline }, null, 1));
console.log("video", video, "scen:", timeline.length, "koniec", ((Date.now() - t) / 1000).toFixed(1), "s");
