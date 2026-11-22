// Kreator „Dopasuj”: ścieżka „3 kliknięcia do wyniku” i wielokrotny wybór bez przeładowania widoku.
import { expect, openRoute, settled, test } from "../fixtures";

const question = (page: import("@playwright/test").Page) => page.getByRole("main").getByRole("heading", { level: 1 });

test("3 kliknięcia do wyniku: rola → 2 odpowiedzi → wyniki w < 20 s", async ({ page, theme }, testInfo) => {
  await openRoute(page, "#/dopasuj?edit=1", theme);
  await expect(question(page)).toHaveText("Kim jesteś?");
  const t0 = Date.now();
  await page.getByRole("radio", { name: "Samorządy i instytucje publiczne" }).click();             // 1: rola
  await expect(question(page)).toHaveText("Jaką instytucję reprezentujesz?");
  await page.getByRole("radio", { name: "Gmina lub miasto" }).click();                           // 2: odpowiedź
  await expect(question(page)).toHaveText("W którym województwie?");
  await page.getByRole("radio", { name: "pomorskie", exact: true }).click();                     // 3: odpowiedź
  await expect(question(page)).toHaveText("Co chcesz poprawić?");
  await page.getByRole("button", { name: "Pokaż wyniki" }).click();                              // wyniki (domyślne odpowiedzi na resztę)
  await settled(page);
  const first = page.getByRole("main").getByRole("article").first();
  await expect(first).toBeVisible();
  const ms = Date.now() - t0;
  testInfo.annotations.push({ type: "czas do pierwszego wyniku", description: `${ms} ms` });
  expect(ms).toBeLessThan(20_000);
  await expect(page.getByRole("main")).toContainText("pomorskie");
});

test("kreator otwarty z gołego #/dopasuj kończy się wynikami (bez zmiany hasha)", async ({ page, theme }) => {
  await openRoute(page, "#/dopasuj", theme);
  await page.getByRole("radio", { name: "Inwestorzy i firmy" }).click();
  await page.getByRole("radio", { name: /^do 2 mln zł/ }).click();
  await page.getByRole("button", { name: /Wszystkie obszary/ }).click();
  await page.getByRole("radio", { name: "Gotowe do wdrożenia" }).click();
  await page.getByRole("radio", { name: "Cała Polska" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /pomysłów, od najlepiej dopasowanych/ })).toBeVisible();
});

test("wielokrotny wybór nie przeładowuje widoku", async ({ page, theme }) => {
  await openRoute(page, "#/dopasuj?edit=1", theme);
  await page.getByRole("radio", { name: "Samorządy i instytucje publiczne" }).click();
  await page.getByRole("radio", { name: "Gmina lub miasto" }).click();
  await page.getByRole("radio", { name: "pomorskie", exact: true }).click();
  await expect(question(page)).toHaveText("Co chcesz poprawić?");

  // znacznik na #view i na węźle pytania + licznik hashchange: przeładowanie widoku podmieniłoby węzły
  await page.evaluate(() => {
    const w = window as any; w.__hashchanges = 0; addEventListener("hashchange", () => w.__hashchanges++);
    const view = document.getElementById("view")!; view.dataset.e2eMark = "1";
    w.__q = view.querySelector("h1"); w.__q.dataset.e2eMark = "1";
  });
  const boxes = page.getByRole("checkbox");
  expect(await boxes.count()).toBeGreaterThanOrEqual(3);
  for (const i of [0, 1, 2]) await boxes.nth(i).click();
  for (const i of [0, 1, 2]) await expect(boxes.nth(i)).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("button", { name: "Dalej (3)" })).toBeVisible();

  const state = await page.evaluate(() => { const w = window as any;
    return { view: document.getElementById("view")!.dataset.e2eMark, sameQuestion: w.__q.isConnected && w.__q.dataset.e2eMark === "1", hashchanges: w.__hashchanges }; });
  expect(state).toEqual({ view: "1", sameQuestion: true, hashchanges: 0 });

  await boxes.nth(1).click();  // odznaczenie też w miejscu
  await expect(boxes.nth(1)).toHaveAttribute("aria-checked", "false");
  await expect(page.getByRole("button", { name: "Dalej (2)" })).toBeVisible();
});
