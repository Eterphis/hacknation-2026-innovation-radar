// Dymny test tras: każda trasa ładuje się bez błędów konsoli i sieci, ma nagłówek, szkielety znikają. Zrzut całej strony
// trafia do test-results/screens/<projekt>/<trasa>.png (artefakt CI, nie porównanie pikselowe).
import { expect, failText, mainHeading, openRoute, screenPath, test } from "../fixtures";
import { ROUTE_DEFS, ROUTE_KEYS } from "../routes";

test("lista tras aplikacji jest pokryta przez routes.ts", async ({ page, theme }) => {
  await openRoute(page, "#/", theme);
  const keys: string[] = await page.evaluate(() => Object.keys((globalThis as any).eval("ROUTES")));
  const missing = keys.filter(k => !ROUTE_KEYS.includes(k));
  expect(missing, "trasy bez testu: dopisz je do e2e/routes.ts").toEqual([]);
});

for (const r of ROUTE_DEFS) {
  test(`trasa ${r.name}`, async ({ page, seed, theme }, testInfo) => {
    for (const { hash, shot } of r.visits(seed)) {
      await test.step(hash, async () => {
        await openRoute(page, hash, theme);
        await expect(failText(page)).toHaveCount(0);
        await expect(mainHeading(page)).toBeVisible();
        await page.screenshot({ path: screenPath(testInfo, shot), fullPage: true });
      });
    }
  });
}

test("prefers-reduced-motion: animacje loadera, tras i przejść mają czas 0", async ({ page, theme }) => {
  await openRoute(page, "#/", theme);
  const durations = await page.evaluate(() => {
    // te same klasy, co w loaderze, pasku trasy, kreatorze i liście: sprawdzamy reguły CSS, a nie chwilę animacji
    const probes = ["ld-sweep", "ld-draw", "routebar on", "reveal", "wiz-main out", "fade", "reel active"];
    const host = document.createElement("div"); host.setAttribute("aria-hidden", "true"); document.body.appendChild(host);
    const out = probes.map(cls => { const el = document.createElement("div"); el.className = cls; host.appendChild(el);
      const cs = getComputedStyle(el), sec = (v: string) => Math.max(...v.split(",").map(x => parseFloat(x) * (x.trim().endsWith("ms") ? 0.001 : 1)));
      return { cls, animation: cs.animationName === "none" ? 0 : sec(cs.animationDuration), transition: sec(cs.transitionDuration) }; });
    host.remove(); return out;
  });
  for (const d of durations) {
    expect.soft(d.animation, `${d.cls}: animation-duration`).toBeLessThanOrEqual(0.01);
    expect.soft(d.transition, `${d.cls}: transition-duration`).toBeLessThanOrEqual(0.01);
  }
});

test("pełny poland.json: nie przy starcie, dopiero na mapie (loader rysuje granicę z wbudowanego obrysu)", async ({ page, theme }) => {
  const fetched: string[] = [];
  page.on("request", r => { if (r.url().includes("/static/poland")) fetched.push(new URL(r.url()).pathname); });
  await openRoute(page, "#/odkrywaj", theme);
  expect(fetched).toEqual([]);
  const map = page.waitForResponse(r => r.url().endsWith("/static/poland.json"));
  await openRoute(page, "#/mapa", theme);
  expect((await map).status()).toBe(200);
  await expect(page.getByRole("group", { name: /Mapa Polski/ })).toBeVisible();
});
