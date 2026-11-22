// Scenariusz demo (docs/scenariusz-demo.md) krok po kroku. Jeśli ten test jest czerwony, demo na scenie też się wysypie.
import { expect, openRoute, settled, test } from "../fixtures";

test("scenariusz demo: samorząd z Pomorza → pomysł → specyfikacja → inwestor → portfel i memo → klastry", async ({ page, theme }, testInfo) => {
  const t0 = Date.now(), lap = (name: string) => testInfo.annotations.push({ type: "krok", description: `${name}: ${Date.now() - t0} ms` });

  await test.step("0:00 wejście: granica Polski rysuje się w loaderze", async () => {
    await page.goto(`/?theme=${theme}#/`);
    const loader = page.getByRole("progressbar", { name: "Ładowanie Radaru Innowacji" });
    await expect(loader).toBeVisible();
    await expect(loader).toHaveCount(0);
    await settled(page);
    await expect(page.getByRole("heading", { level: 1, name: "Polskie innowacje, które warto wdrożyć" })).toBeVisible();
    lap("wejście");
  });

  let title = "";
  await test.step("0:30 „Dopasuj w 30 sekund” jako samorząd z województwa pomorskiego", async () => {
    await page.getByRole("link", { name: "Dopasuj w 30 sekund" }).click();
    await page.getByRole("radio", { name: "Samorządy i instytucje publiczne" }).click();
    await page.getByRole("radio", { name: "Gmina lub miasto" }).click();
    await page.getByRole("radio", { name: "pomorskie", exact: true }).click();
    await page.getByRole("button", { name: "Pokaż wyniki" }).click();
    await settled(page);
    await expect(page.getByRole("main").getByRole("article").first()).toBeVisible();
    // Jedyny pomysł z Pomorza w danych demo jest na etapie „technologia gotowa”, a ścieżka samorządu premiuje „gotowe
    // do wdrożenia”, więc nie jest pierwszy. Scenariusz otwiera wynik oznaczony „Twój region: pomorskie”.
    const local = page.getByRole("main").getByRole("article").filter({ hasText: "Twój region: pomorskie" }).first();
    await expect(local).toBeVisible();
    title = (await local.getByRole("heading", { level: 3 }).innerText()).trim();
    lap("wynik dopasowania");
  });

  await test.step("1:15 strona pomysłu i specyfikacja wdrożenia (memo wykonawcy)", async () => {
    await page.getByRole("main").getByRole("article").filter({ hasText: "Twój region: pomorskie" }).first().getByRole("heading", { level: 3 }).click();
    await expect(page).toHaveURL(/#\/pomysl\/\d+$/);
    await settled(page);
    await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toContainText(title.replace(/…$/, "").slice(0, 30));
    const popup = page.waitForEvent("popup");
    await page.getByRole("link", { name: "Specyfikacja wdrożenia" }).click();
    const spec = await popup;
    await expect(spec).toHaveURL(/\/memo\?kind=wykonawca/);
    await expect(spec.getByText("Specyfikacja wdrożenia").first()).toBeVisible();
    await expect(spec.getByText("Kto może wdrożyć").first()).toBeVisible();
    await spec.close();
    lap("specyfikacja");
  });

  await test.step("2:15 przełączenie na inwestora: pomysł do portfela i memo PDF", async () => {
    await openRoute(page, "#/dla/inwestorzy", theme);
    await page.getByRole("main").getByRole("article").first().click();
    await expect(page).toHaveURL(/#\/pomysl\/\d+$/);
    await settled(page);
    const ideaTitle = (await page.getByRole("main").getByRole("heading", { level: 1 }).innerText()).trim();
    await page.getByRole("button", { name: "Do portfela" }).click();
    await expect(page.getByRole("button", { name: "W portfelu" })).toBeVisible();
    const popup = page.waitForEvent("popup");
    await page.getByRole("link", { name: "Memo PDF" }).click();
    const memo = await popup;
    await expect(memo.getByText("Memo inwestycyjne").first()).toBeVisible();
    await memo.close();
    await openRoute(page, "#/portfel?tab=lejek", theme);
    const nowe = page.getByRole("region", { name: "Nowe" });
    await expect(nowe.getByRole("article")).toHaveCount(1);
    await expect(nowe).toContainText(ideaTitle.slice(0, 30));
    lap("portfel i memo");
  });

  await test.step("3:30 klastry: temat zdrowia (w danych demo nie ma klastra „AI w zdrowiu”)", async () => {
    await openRoute(page, "#/klastry", theme);
    const health = page.getByRole("main").getByRole("article").filter({ has: page.getByRole("heading", { level: 3, name: /Opieka zdrowotna/ }) }).first();
    await expect(health).toBeVisible();
    await health.getByRole("button", { name: "Pokaż najlepsze" }).click();
    await expect(health.getByRole("button", { name: "Zwiń" })).toHaveAttribute("aria-expanded", "true");
    await expect(health.getByRole("article").first()).toBeVisible();
    lap("klastry");
  });

  expect(Date.now() - t0, "cały scenariusz klikany przez test (bez mówienia) mieści się w minucie").toBeLessThan(60_000);
});
