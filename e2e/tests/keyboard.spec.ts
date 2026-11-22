// Nawigacja wyłącznie klawiaturą: kreator, zakładki strony pomysłu (wzorzec ARIA tabs), klastry, Escape.
import type { Locator, Page } from "@playwright/test";
import { expect, openRoute, settled, test } from "../fixtures";

/** Naciska Tab (albo Shift+Tab), aż fokus trafi na `target`. Limit chroni przed pętlą bez końca. */
async function tabTo(page: Page, target: Locator, key = "Tab", max = 80) {
  for (let i = 0; i < max; i++) {
    if (await target.evaluate(el => el === document.activeElement)) return;
    await page.keyboard.press(key);
  }
  throw new Error(`fokus nie doszedł do elementu po ${max} naciśnięciach ${key}`);
}

/** Fokus jest widoczny: obrys z :focus-visible ma ≥ 2 px i kontrast ≥ 3:1 względem tła strony. */
async function expectVisibleFocus(page: Page) {
  const f = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement, cs = getComputedStyle(el);
    const rgb = (c: string) => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    const lum = (c: number[]) => { const [r, g, b] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const bg = getComputedStyle(document.body).backgroundColor, a = lum(rgb(cs.outlineColor)), b = lum(rgb(bg));
    return { focusVisible: el.matches(":focus-visible"), style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), contrast: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) };
  });
  expect(f.focusVisible).toBe(true);
  expect(f.style).not.toBe("none");
  expect(f.width).toBeGreaterThanOrEqual(2);
  expect(f.contrast).toBeGreaterThanOrEqual(3);
}

test("kreator: cały przepływ klawiaturą, fokus widoczny i na nowym pytaniu", async ({ page, theme }) => {
  await openRoute(page, "#/dopasuj?edit=1", theme);
  const q = page.getByRole("main").getByRole("heading", { level: 1 });
  const role = page.getByRole("radio", { name: "Samorządy i instytucje publiczne" });
  await tabTo(page, role);
  await expectVisibleFocus(page);
  await page.keyboard.press("Enter");
  await expect(q).toHaveText("Jaką instytucję reprezentujesz?");
  await expect(q).toBeFocused();                                   // fokus przeszedł na nowe pytanie

  const gmina = page.getByRole("radio", { name: "Gmina lub miasto" }), powiat = page.getByRole("radio", { name: "Powiat" });
  await tabTo(page, powiat);
  await page.keyboard.press("Shift+Tab");                          // wstecz też działa
  await expect(gmina).toBeFocused();
  await page.keyboard.press("Space");
  await expect(q).toHaveText("W którym województwie?");
  await expect(q).toBeFocused();

  await tabTo(page, page.getByRole("radio", { name: "pomorskie", exact: true }));
  await page.keyboard.press("Enter");
  await expect(q).toHaveText("Co chcesz poprawić?");
  const first = page.getByRole("checkbox").first();
  await tabTo(page, first);
  await page.keyboard.press("Space");
  await expect(first).toHaveAttribute("aria-checked", "true");
  await tabTo(page, page.getByRole("button", { name: /^Dalej/ }));
  await expectVisibleFocus(page);
  await page.keyboard.press("Enter");
  await expect(q).toHaveText(/Ile możesz przeznaczyć/);
  await tabTo(page, page.getByRole("radio", { name: "do 2 mln zł" }));
  await page.keyboard.press("Enter");
  await settled(page);
  await expect(page.getByRole("main").getByRole("article").first()).toBeVisible();
});

test("strona pomysłu: zakładki jako tablist / tab / tabpanel, strzałki zmieniają zakładkę", async ({ page, seed, theme }) => {
  await openRoute(page, `#/pomysl/${seed.ids[0]}`, theme);
  const list = page.getByRole("tablist", { name: "Szczegóły pomysłu" }), tabs = list.getByRole("tab");
  const n = await tabs.count();
  expect(n).toBeGreaterThan(2);
  const panel = page.getByRole("tabpanel");
  await tabTo(page, tabs.first());                                  // roving tabindex: Tab trafia na aktywną zakładkę
  await expectVisibleFocus(page);
  const check = async (i: number) => {
    const t = tabs.nth(i);
    await expect(t).toBeFocused();
    await expect(t).toHaveAttribute("aria-selected", "true");
    await expect(t).toHaveAttribute("tabindex", "0");
    const id = await t.getAttribute("id");
    await expect(t).toHaveAttribute("aria-controls", (await panel.getAttribute("id"))!);
    await expect(panel).toHaveAttribute("aria-labelledby", id!);
    await expect(list.getByRole("tab", { selected: true })).toHaveCount(1);
  };
  await check(0);
  await page.keyboard.press("ArrowRight"); await check(1);
  await page.keyboard.press("End"); await check(n - 1);
  await page.keyboard.press("ArrowRight"); await check(0);          // zawija się
  await page.keyboard.press("ArrowLeft"); await check(n - 1);
  await page.keyboard.press("Home"); await check(0);
  await page.keyboard.press("Tab");                                 // z zakładek Tab przechodzi do panelu
  await expect(panel).toBeFocused();
});

test("klastry: do każdego klastra da się dojść i otworzyć go klawiaturą", async ({ page, theme }) => {
  await openRoute(page, "#/klastry", theme);
  const toggles = page.getByRole("button", { name: "Pokaż najlepsze" });
  const n = await toggles.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const b = page.getByRole("button", { name: /^(Pokaż najlepsze|Zwiń)$/ }).nth(i);  // po otwarciu napis zmienia się na „Zwiń”
    await tabTo(page, b, "Tab", 200);
    await expect(b).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("Enter");
    await expect(b).toHaveAttribute("aria-expanded", "true");
    const items = page.locator(`#${await b.getAttribute("aria-controls")}`).getByRole("article");
    await expect(items.first()).toBeVisible();
    await page.keyboard.press("Tab");                               // pierwszy pomysł w otwartym klastrze
    await expect(items.first()).toBeFocused();
  }
});

test("Escape zamyka wyszukiwarkę i panel przewodnika, fokus wraca na element, który je otworzył", async ({ page, theme }) => {
  await openRoute(page, "#/", theme);
  const opener = page.getByRole("button", { name: "Szukaj (klawisz /)" }), dialog = page.getByRole("dialog", { name: "Szukaj" });
  await tabTo(page, opener);
  await page.keyboard.press("Enter");
  await expect(dialog).toBeVisible();
  await expect(page.getByPlaceholder(/Szukaj pomysłów/)).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();

  const face = page.getByRole("button", { name: /^Przewodnik/ });
  await tabTo(page, face, "Tab", 200);
  await page.keyboard.press("Enter");
  await expect(face).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: "Zamknij" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(face).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: "Zamknij" })).toBeHidden();
  await expect(face).toBeFocused();
});
