// Pitch PDF z prawdziwymi liczbami: pobiera /api/insights i /api/stats z działającej aplikacji, koszt z README
// („Publiczny adres i koszt”), wyniki jakości z raportów w repo; wstawia je do docs/pitch/slides.html i drukuje
// docs/pitch/pitch.pdf (Playwright page.pdf). Każdy slajd z liczbą dostaje przypis „źródło: …, <data i godzina>”.
//   E2E_BASE_URL=http://localhost:8000 node scripts/pitch.ts      (Node ≥ 22.18: typy usuwane natywnie)
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const base = process.env.E2E_BASE_URL || "http://127.0.0.1:8010";
const at = new Date().toLocaleString("pl-PL", { timeZone: "Europe/Warsaw", dateStyle: "short", timeStyle: "short" });

const get = async (path: string) => { const r = await fetch(base + path); if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`); return r.json(); };
const insights = await get("/api/insights");
const statsRaw = await get("/api/stats");
const stats = { ...statsRaw, raw_total: Object.values(statsRaw.raw_by_transport as Record<string, number>).reduce((a, b) => a + b, 0) };

// README: tabela „Publiczny adres i koszt”
const readmeText = readFileSync(join(root, "README.md"), "utf-8");
const section = readmeText.split("### Publiczny adres i koszt")[1]?.split("\n## ")[0] ?? "";
const row = (label: RegExp) => section.split("\n").find(l => label.test(l))?.split("|")[2]?.replace(/\*\*/g, "").trim().replace(/^ok\. /, "");
const readme = { cost_total: row(/^\| Razem/), cost_vps: row(/^\| VPS/), cost_llm: row(/^\| LLM/)?.split(":")[0] };
if (!readme.cost_total || !readme.cost_vps) throw new Error("README: nie znaleziono tabeli kosztów w sekcji „Publiczny adres i koszt”");

// raporty jakości (pliki w repo, nie liczby wpisane ręcznie)
const lh = JSON.parse(readFileSync(join(root, "docs/reports/lighthouse/manifest.json"), "utf-8")) as { url: string; summary: { performance: number } }[];
const lighthouse = { perf_home: Math.round(100 * lh.find(r => !r.url.includes("pomysl"))!.summary.performance),
  perf_idea: Math.round(100 * lh.find(r => r.url.includes("pomysl"))!.summary.performance) };
const csv = readFileSync(join(root, ".house/reports/load/po_stats.csv"), "utf-8").trim().split(/\r?\n/).map(l => l.split(","));
const agg = csv.find(c => c[1] === "Aggregated")!, col = (n: string) => agg[csv[0].indexOf(n)];
const load = { rps: Number(col("Requests/s")), failures: Number(col("Failure Count")) };

const DATA = { insights, stats, readme, lighthouse, load };
const SOURCES: Record<string, string> = {
  insights: `/api/insights (${base}), ${at}`, stats: `/api/stats (${base}), ${at}`,
  readme: "README.md, sekcja „Publiczny adres i koszt”", lighthouse: "docs/reports/lighthouse/manifest.json (mediana 3 przebiegów)",
  load: ".house/reports/load/po_stats.csv (locust, 3 min)",
};
const demo = (insights.kpi?.synthetic_share ?? 0) > 0
  ? `Dane demo: ${insights.kpi.synthetic_share}% rekordów to dane przykładowe (syntetyczne) z app/samples, oznaczone w aplikacji.` : "";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto("file://" + join(root, "docs/pitch/slides.html").replace(/\\/g, "/"));
const missing = await page.evaluate(({ DATA, SOURCES, demo }) => {
  const pick = (o: any, path: string) => path.split(".").reduce((a, k) => a?.[k], o);
  const fmt = (v: any, f?: string) => f === "int" ? Math.round(v).toLocaleString("pl-PL")
    : f === "dec" ? Number(v).toLocaleString("pl-PL", { maximumFractionDigits: 1 })
    : f === "pln" ? (v >= 1e6 ? (v / 1e6).toLocaleString("pl-PL", { maximumFractionDigits: 1 }) + " mln zł" : Math.round(v).toLocaleString("pl-PL") + " zł") : String(v);
  const miss: string[] = [];
  const trends = (DATA as any).insights.trends.slice(0, 6), max = Math.max(1, ...trends.map((t: any) => t.heat));
  document.querySelectorAll<HTMLElement>("[data-trends]").forEach(el => { el.innerHTML = trends.map((t: any) =>
    `<div class="bar"><span>${t.pl.split(" (")[0]}</span><div class="track"><i style="width:${Math.round(t.heat / max * 100)}%"></i></div><b data-src="insights" data-path="trends.${t.key}">${t.heat}</b></div>`).join(""); });
  document.querySelectorAll<HTMLElement>("[data-src][data-path]").forEach(el => {
    if (el.dataset.path!.startsWith("trends.")) return;
    const v = pick((DATA as any)[el.dataset.src!], el.dataset.path!);
    if (v === undefined || v === null || v === "") miss.push(`${el.dataset.src}:${el.dataset.path}`); else el.textContent = fmt(v, el.dataset.fmt);
  });
  document.querySelectorAll<HTMLElement>("[data-demo-note]").forEach(el => { el.textContent = demo; });
  document.querySelectorAll<HTMLElement>(".slide").forEach((s, i, all) => {
    const used = [...new Set([...s.querySelectorAll<HTMLElement>("[data-src]")].map(e => e.dataset.src!))];
    if (used.length) s.insertAdjacentHTML("beforeend", `<div class="src">źródło: ${used.map(u => (SOURCES as any)[u]).join(" · ")}</div>`);
    s.insertAdjacentHTML("beforeend", `<div class="num">${i + 1} / ${all.length}</div>`);
  });
  return miss;
}, { DATA, SOURCES, demo });
if (missing.length) throw new Error("brak danych dla: " + missing.join(", "));
const slides = await page.locator(".slide").count();
if (slides > 10) throw new Error(`za dużo slajdów: ${slides} (limit 10)`);
if (process.env.PITCH_PNG) {  // podgląd slajdów jako PNG (np. do przejrzenia bez czytnika PDF)
  for (let i = 0; i < slides; i++) await page.locator(".slide").nth(i).screenshot({ path: join(process.env.PITCH_PNG, `slajd-${i + 1}.png`) });
}
const out = join(root, "docs/pitch/pitch.pdf");
await page.pdf({ path: out, width: "1280px", height: "720px", printBackground: true, preferCSSPageSize: true });
await browser.close();
console.log(`pitch: ${slides} slajdów → ${out} (dane z ${base}, ${at})`);
