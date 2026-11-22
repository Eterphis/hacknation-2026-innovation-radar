// axe-core (WCAG 2.0/2.1 A i AA) na każdej trasie i w stanach po interakcji, w jasnym i ciemnym motywie.
// Asercje: 0 naruszeń „critical” i 0 naruszeń color-contrast. Reszta (serious, moderate) trafia do
// test-results/axe/<projekt>/<nazwa>.json jako artefakt. Bez globalnego disableRules.
import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { expect, openRoute, settled, test } from "../fixtures";
import { ROUTE_DEFS } from "../routes";

async function audit(page: Page, testInfo: TestInfo, name: string) {
  const res = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // kanwa grafu to rysunek bez tekstu; ta sama treść jest pod nią jako lista („Graf jako lista”), która jest badana
    .exclude("#graph")
    .analyze();
  const brief = res.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map(n => ({ target: n.target.join(" "), summary: n.failureSummary })) }));
  const p = join(dirname(testInfo.config.configFile!), "test-results", "axe", testInfo.project.name, `${name}.json`);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify({ url: page.url(), violations: brief }, null, 1));
  const blocking = brief.filter(v => v.impact === "critical" || v.id === "color-contrast");
  expect(blocking, `${name}: naruszenia critical / color-contrast`).toEqual([]);
}

for (const r of ROUTE_DEFS) {
  test(`axe: ${r.name}`, async ({ page, seed, theme }, testInfo) => {
    for (const { hash, shot } of r.visits(seed)) {
      await test.step(hash, async () => { await openRoute(page, hash, theme); await audit(page, testInfo, shot); });
    }
  });
}

test("axe: kreator, każdy krok", async ({ page, theme }, testInfo) => {
  await openRoute(page, "#/dopasuj?edit=1", theme);
  await audit(page, testInfo, "kreator-1-rola");
  await page.getByRole("radio", { name: "Samorządy i instytucje publiczne" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Jaką instytucję reprezentujesz?" })).toBeVisible();
  await audit(page, testInfo, "kreator-2-instytucja");
  await page.getByRole("radio", { name: "Gmina lub miasto" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "W którym województwie?" })).toBeVisible();
  await audit(page, testInfo, "kreator-3-wojewodztwo");
  await page.getByRole("radio", { name: "pomorskie", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Co chcesz poprawić?" })).toBeVisible();
  await page.getByRole("checkbox").first().click();
  await audit(page, testInfo, "kreator-4-obszary");
  await page.getByRole("button", { name: /^Dalej/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Ile możesz przeznaczyć/ })).toBeVisible();
  await audit(page, testInfo, "kreator-5-budzet");
  await page.getByRole("radio", { name: "do 2 mln zł" }).click();
  await settled(page);
  await expect(page.getByRole("main").getByRole("article").first()).toBeVisible();
  await audit(page, testInfo, "kreator-wyniki");
});

test("axe: zakładki strony pomysłu", async ({ page, seed, theme }, testInfo) => {
  await openRoute(page, `#/pomysl/${seed.ids[0]}`, theme);
  const tabs = page.getByRole("main").getByRole("tablist").getByRole("tab");
  const n = await tabs.count();
  expect(n).toBeGreaterThan(1);
  for (let i = 0; i < n; i++) {
    await tabs.nth(i).click();
    await expect(tabs.nth(i)).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toBeVisible();
    await audit(page, testInfo, `pomysl-zakladka-${i + 1}`);
  }
});

test("axe: otwarta wyszukiwarka i otwarte klastry", async ({ page, theme }, testInfo) => {
  await openRoute(page, "#/", theme);
  await page.keyboard.press("/");
  await expect(page.getByRole("dialog", { name: "Szukaj" })).toBeVisible();
  await audit(page, testInfo, "wyszukiwarka");
  await page.keyboard.press("Escape");
  await openRoute(page, "#/klastry", theme);
  await page.getByRole("button", { name: "Pokaż najlepsze" }).first().click();
  await audit(page, testInfo, "klastry-otwarty");
});

test("axe: przewodnik (panel otwarty)", async ({ page, theme }, testInfo) => {
  await openRoute(page, "#/", theme);
  await page.getByRole("button", { name: /^Przewodnik/ }).click();
  await expect(page.getByRole("button", { name: "Zamknij" })).toBeVisible();
  await audit(page, testInfo, "przewodnik");
});
