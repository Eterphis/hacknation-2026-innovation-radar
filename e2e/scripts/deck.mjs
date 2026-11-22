// Pitch deck: live numbers from the API into docs/pitch/deck.html, screenshots of the running app and Grafana,
// printed to docs/pitch/pitch.pdf (10 slides, 1280x720).
//   node e2e/scripts/deck.mjs http://localhost:8088 [http://localhost:3000]
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BASE = (process.argv[2] || "http://localhost:8088").replace(/\/$/, "");
const GRAFANA = (process.argv[3] || "http://localhost:3000").replace(/\/$/, "");
const IMG = path.join(ROOT, "docs/pitch/img"); fs.mkdirSync(IMG, { recursive: true });
const j = async p => (await fetch(BASE + p)).json();
const [ins, src] = await Promise.all([j("/api/insights"), j("/api/sources")]);
const pl = n => Number(n).toLocaleString("pl-PL");
const vars = { sources: src.filter(s => s.active && !s.id.startsWith("demo-")).length, ideas: pl(ins.kpi.ideas), institutions: pl(ins.kpi.institutions),
  voivodeships: ins.kpi.voivodeships, ready: pl(ins.kpi.ready_to_copy), rps: "110",
  stamp: new Date().toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" }) };

const browser = await chromium.launch({ channel: process.env.FILM_CHANNEL || "msedge" });
const shot = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 });
const settled = async () => { await shot.waitForFunction(() => !document.querySelector("#view")?.hasAttribute("aria-busy"), null, { timeout: 30000 }).catch(() => {}); await shot.waitForTimeout(900); };
await shot.addInitScript(() => { const s = document.createElement("style"); s.textContent = "#gdock{display:none!important}"; document.addEventListener("DOMContentLoaded", () => document.head.appendChild(s)); });
await shot.goto(`${BASE}/?theme=light#/dopasuj?edit=1`); await settled(); await shot.waitForTimeout(2500);
await shot.screenshot({ path: path.join(IMG, "kreator.png") });
const first = await shot.locator("main article[data-card]").first().getAttribute("data-card").catch(() => null);
await shot.goto(`${BASE}/?theme=light#/pomysl/${first || 1243}`); await settled();
await shot.screenshot({ path: path.join(IMG, "pomysl.png") });
// phone screenshots (390x844, like an iPhone 14) for the mobile slide
const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
await phone.addInitScript(() => { const s = document.createElement("style"); s.textContent = "#gdock{display:none!important}"; document.addEventListener("DOMContentLoaded", () => document.head.appendChild(s)); });
for (const [hash, name] of [["", "mobile-home"], ["rolki", "mobile-rolki"]]) {
  await phone.goto(`${BASE}/?theme=light#/${hash}`);
  await phone.waitForFunction(() => !document.querySelector("#view")?.hasAttribute("aria-busy"), null, { timeout: 30000 }).catch(() => {});
  await phone.waitForTimeout(2500); await phone.screenshot({ path: path.join(IMG, name + ".png") });
}
await shot.goto(`${GRAFANA}/d/radar?orgId=1&kiosk&from=now-1h&to=now`); await shot.waitForLoadState("networkidle").catch(() => {}); await shot.waitForTimeout(2500);
await shot.screenshot({ path: path.join(IMG, "grafana.png") });

let html = fs.readFileSync(path.join(ROOT, "docs/pitch/deck.html"), "utf8");
for (const [k, v] of Object.entries(vars)) html = html.replaceAll(`{{${k}}}`, String(v));
const filled = path.join(ROOT, "docs/pitch/deck.filled.html"); fs.writeFileSync(filled, html);
const page = await browser.newPage();
await page.goto(pathToFileURL(filled).href); await page.waitForTimeout(500);
const out = path.join(ROOT, "docs/pitch/pitch.pdf");
await page.pdf({ path: out, width: "1280px", height: "720px", printBackground: true, preferCSSPageSize: true });
await browser.close();
console.log("pdf", out, vars);
