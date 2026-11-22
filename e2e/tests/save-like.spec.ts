// Zapis pomysłu (przeglądarka) i polubienie (serwer, anonimowy voter).
// Endpoint POST /api/cards/{id}/like przełącza głos: drugie kliknięcie tego samego votera cofa polubienie.
import type { TestInfo } from "@playwright/test";
import { expect, openRoute, test } from "../fixtures";

// Każdy projekt i każde powtórzenie (--repeat-each) polubia inny pomysł, więc równoległe przebiegi nie mieszają liczników.
// (desktop: pomysły od końca listy, mobile: od środka; dane demo mają > 2 × liczba powtórzeń pomysłów)
const cardFor = (ids: number[], t: TestInfo) => {
  const base = t.project.name.startsWith("mobile") ? Math.floor(ids.length / 2) : 0;
  return ids[ids.length - 1 - ((base + t.repeatEachIndex) % ids.length)];
};

test("zapisany pomysł jest w Portfel → Zapisane, także po przeładowaniu", async ({ page, seed, theme }) => {
  const idea = seed.ideas[0];
  await openRoute(page, `#/pomysl/${idea.card_id}`, theme);
  const title = await page.getByRole("main").getByRole("heading", { level: 1 }).innerText();
  await page.getByRole("button", { name: "Zapisz", exact: true }).click();
  await expect(page.getByRole("button", { name: "Zapisane", exact: true })).toBeVisible();

  await openRoute(page, "#/portfel?tab=zapisane", theme);
  const saved = page.getByRole("main").getByRole("article");
  await expect(saved).toHaveCount(1);
  await expect(saved.first()).toContainText(title.slice(0, 40));
  await page.reload();
  await expect(page.getByRole("main").getByRole("article")).toHaveCount(1);
  await expect(page.getByRole("main").getByRole("article").first()).toContainText(title.slice(0, 40));
});

test("polubienie podnosi licznik o 1 w UI i w API, drugie kliknięcie je cofa", async ({ page, seed, theme, request }, testInfo) => {
  const id = cardFor(seed.ids, testInfo);
  await openRoute(page, `#/pomysl/${id}`, theme);
  const btn = page.getByRole("button", { name: /ocena społeczności/ });
  const count = async () => Number((await btn.innerText()).match(/\d+/)![0]);
  const before = await count();
  expect((await (await request.get(`/api/cards/${id}`)).json()).likes).toBe(before);
  await expect(btn).toHaveAttribute("aria-pressed", "false");

  const liked = page.waitForResponse(r => r.url().endsWith(`/api/cards/${id}/like`) && r.request().method() === "POST");
  await btn.click();
  expect((await (await liked).json()).liked).toBe(true);
  await expect(btn).toContainText(String(before + 1));
  await expect(btn).toHaveAttribute("aria-pressed", "true");
  expect((await (await request.get(`/api/cards/${id}`)).json()).likes).toBe(before + 1);

  const unliked = page.waitForResponse(r => r.url().endsWith(`/api/cards/${id}/like`) && r.request().method() === "POST");
  await btn.click();
  expect((await (await unliked).json()).liked).toBe(false);
  await expect(btn).toContainText(String(before));
  await expect(btn).toHaveAttribute("aria-pressed", "false");
  expect((await (await request.get(`/api/cards/${id}`)).json()).likes).toBe(before);
});
