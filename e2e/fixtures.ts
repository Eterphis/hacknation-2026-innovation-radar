// Wspólne fixture'y: motyw z projektu, unikalny voter na test, strażnik konsoli i sieci, dane demo z API.
import { test as base, expect, request as pwRequest, type Locator, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import type { SeedData } from "./routes";

export type Theme = "light" | "dark";
export type ThemeOptions = { theme: Theme };
export type Idea = { card_id: number; title: string; voivodeship: string | null; sector: string; likes: number };
export type Seed = SeedData & { ideas: Idea[] };
type Problem = { kind: "console" | "pageerror" | "response"; text: string };

// Jawne wyjątki strażnika konsoli. Każdy wpis musi mieć powód; lista ma być krótka.
export const ALLOWED_PROBLEMS: { pattern: RegExp; why: string }[] = [
  // (pusta: żadna trasa nie powinna dziś niczego logować jako błąd)
];

export const test = base.extend<ThemeOptions & { voter: string; guard: Problem[] }, { seed: Seed }>({
  theme: ["light", { option: true }],

  // Identyfikatory i persony pobierane z API: testy nie zakładają liczby rekordów na sztywno.
  seed: [async ({}, use, workerInfo) => {
    const ctx = await pwRequest.newContext({ baseURL: workerInfo.project.use.baseURL });
    const ideas = (await (await ctx.get("/api/ideas?limit=100&sort=score")).json()).items as Idea[];
    const personas = ((await (await ctx.get("/api/personas")).json()) as { key: string }[]).map(p => p.key);
    await ctx.dispose();
    expect(ideas.length, "baza demo musi mieć co najmniej 2 pomysły").toBeGreaterThanOrEqual(2);
    await use({ ideas, ids: ideas.map(i => i.card_id), personas });
  }, { scope: "worker" }],

  // Każdy test ma własnego votera: równoległe przebiegi nie liczą sobie nawzajem polubień.
  voter: [async ({ page }, use, testInfo) => {
    const v = ["e2e", testInfo.project.name, testInfo.workerIndex, testInfo.repeatEachIndex, Date.now().toString(36),
      Math.random().toString(36).slice(2, 8)].join("-");
    await page.addInitScript(id => { try { localStorage.setItem("radar-voter", id); } catch (e) { /* storage wyłączony */ } }, v);
    await use(v);
  }, { auto: true }],

  // Strażnik: console.error, nieobsłużone wyjątki i odpowiedzi >= 400 z własnego originu. Na końcu lista musi być pusta.
  guard: [async ({ page, baseURL }, use) => {
    const origin = new URL(baseURL!).origin, problems: Problem[] = [];
    page.on("console", m => { if (m.type() === "error") problems.push({ kind: "console", text: m.text() }); });
    page.on("pageerror", e => problems.push({ kind: "pageerror", text: String(e) }));
    page.on("response", r => { if (r.status() >= 400 && new URL(r.url()).origin === origin) problems.push({ kind: "response", text: `${r.status()} ${r.request().method()} ${r.url()}` }); });
    await use(problems);
    const left = problems.filter(p => !ALLOWED_PROBLEMS.some(a => a.pattern.test(p.text)));
    expect(left, "błędy konsoli, wyjątki albo odpowiedzi >= 400").toEqual([]);
  }, { auto: true }],
});
export { expect };

/** Otwiera trasę i czeka, aż widok się wyrenderuje (bez sleepów: aria-busy na <main>, brak szkieletów). */
export async function openRoute(page: Page, hash: string, theme: Theme) {
  const fresh = !page.url().startsWith("http");
  if (fresh) {
    await page.goto(`/?theme=${theme}${hash}`);
    await expect(page.getByRole("progressbar", { name: "Ładowanie Radaru Innowacji" })).toHaveCount(0);
  } else {
    // hashchange: listener routera jest zarejestrowany wcześniej, więc gdy nasz się wykona, widok już jest „busy”
    const changed = await page.evaluate(h => new Promise<boolean>(res => {
      if (location.hash === h) return res(false);
      addEventListener("hashchange", () => res(true), { once: true }); location.hash = h; }), hash);
    if (!changed) await page.reload();
  }
  await settled(page);
}

/** Widok skończył się ładować. */
export async function settled(page: Page) {
  await expect(page.getByRole("main")).not.toHaveAttribute("aria-busy", "true");
  await expect(page.locator("#view .skel")).toHaveCount(0);
}

export const mainHeading = (page: Page): Locator => {
  const main = page.getByRole("main");
  return main.getByRole("heading", { level: 1 }).or(main.getByRole("heading", { level: 2 })).first();
};

export const failText = (page: Page) => page.getByText("Nie udało się wczytać widoku");

/** Ścieżka zrzutu: test-results/screens/<projekt>/<nazwa>.png (artefakt do oglądania, nie asercja). */
export function screenPath(testInfo: TestInfo, name: string, dir = "screens") {
  const p = join(dirname(testInfo.config.configFile!), "test-results", dir, testInfo.project.name, `${name}.png`);
  mkdirSync(dirname(p), { recursive: true });
  return p;
}
