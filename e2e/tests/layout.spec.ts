// Układ na 375 px (projekty mobilne): bez poziomego przewijania, każdy <img> ma alt, każda grafika AI oznaczona.
import { expect, openRoute, test } from "../fixtures";
import { ROUTE_DEFS } from "../routes";

// Katalogi z ilustracjami wygenerowanymi przez AI (Higgsfield): tła sektorów, grup, banery, kreator, puste stany, przewodnicy.
const AI_DIRS = /\/static\/(sectors|hero|banners|wizard|empty|guides)\//;
const AI_MARK = /ilustracja AI|ilustracje: Higgsfield \(AI|portret: ilustracja AI/;

for (const r of ROUTE_DEFS) {
  test(`375 px: ${r.name}`, async ({ page, seed, theme }) => {
    for (const { hash } of r.visits(seed)) {
      await test.step(hash, async () => {
        await openRoute(page, hash, theme);
        const m = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: window.innerWidth }));
        expect(m.scroll, `${hash}: poziome przewijanie (scrollWidth ${m.scroll} > ${m.width})`).toBeLessThanOrEqual(m.width);

        const imgs = await page.locator("img").evaluateAll(els => els.map(e => ({ src: (e as HTMLImageElement).src, alt: e.getAttribute("alt"), ai: e.hasAttribute("data-ai"),
          visible: !!(e as HTMLElement).offsetParent })));
        for (const i of imgs) {
          expect(i.alt, `${i.src}: brak atrybutu alt`).not.toBeNull();
          if (AI_DIRS.test(i.src)) expect(i.ai, `${i.src}: grafika AI bez data-ai`).toBe(true);
        }
        // grafiki AI (także tła CSS) muszą mieć widoczne oznaczenie na stronie: podpis przy obrazie albo stopka z autorstwem
        const usesAi = imgs.some(i => i.visible && AI_DIRS.test(i.src)) || await page.evaluate(re => [...document.querySelectorAll<HTMLElement>("*")]
          .some(e => new RegExp(re).test(getComputedStyle(e).backgroundImage + (getComputedStyle(e, "::before").backgroundImage || ""))
            || new RegExp(re).test(e.style.cssText)), AI_DIRS.source);
        if (usesAi) await expect(page.getByText(AI_MARK).filter({ visible: true }).first()).toBeVisible();
      });
    }
  });
}
