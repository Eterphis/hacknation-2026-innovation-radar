---
title: "[Handoff C] Higgsfield: grafiki i rolki-wideo dla 6 grup odbiorców, UI pod inwestorów, pitch"
labels: [ui, pitch, handoff]
---
**Dla:** trzeci agent (UI, pitch). Wklej agentowi całość.

## Stan
- Na `main` (po merge PR z `feat/personas-business`) jest:
  - zakładka „Dla mnie” z 6 grupami: inwestorzy i firmy, samorządy i instytucje publiczne, uczelnie i jednostki naukowe, szkoły i placówki, startupy i przedsiębiorstwa, indywidualni innowatorzy;
  - karta pomysłu z sekcją „Model biznesowy i wycena”: koszt wdrożenia, TAM/SAM/SOM, wartość licencji, oszczędność, zwrot, programy finansowania, jawne założenia.
- Higgsfield jest podłączony jako konektor MCP (`https://mcp.higgsfield.ai/mcp`), ale konto jest na **3-dniowym trialu**.

## Budżet kredytów (twardy limit)
- Przed każdą generacją pokaż koszt w kredytach i stan konta.
- Najpierw obrazy (tanie), wideo dopiero na końcu i tylko dla 3 pomysłów.
- Nigdy nie generuj seriami bez sprawdzenia pierwszego wyniku.

## Zadania
1. **6 teł dla grup odbiorców** (`app/radar/api/static/hero/<grupa>.webp`; nazwy: inwestorzy, samorzady, uczelnie, szkoly, startupy, innowatorzy).
   - Format 16:9 (np. 1920×1080), WebP do 300 KB.
   - Styl: miękkie, jasne, beż i biel z czerwonym akcentem (paleta strony), bez tekstu, bez logotypów, bez twarzy realnych osób.
   - Strony już mają slot na tło i działają bez niego.
2. **12 teł sektorów do rolek** (`static/sectors/<sektor>.webp`, 9:16). Na rolce rozmyte, z przyciemnieniem pod tekst i znaczkiem „wizualizacja AI”.
3. **3 rolki-wideo (5–10 s, 9:16)** dla najlepszych pomysłów z widoków dla inwestorów i samorządów. Wideo generowane z gotowego briefu (bez nowych faktów), zapisane statycznie, odtwarzane w rolce zamiast tła.
4. **Pitch** (PDF, maks. 10 slajdów, i film do 3 min). Wątek: „od artykułu w bazie do gminy, która chce wdrożyć, w 3 kliknięcia”, z prawdziwymi danymi (316 historii NCBR, Kohesio, RAD-on) i wyceną.
5. Zrzuty Playwright do CI (desktop i 375 px, jasny i ciemny).

## Zasady
Treści generowane są statyczne, czyli zero kosztów w runtime. Tekst musi być czytelny na tle (kontrast AA). Każda grafika AI jest oznaczona jako wizualizacja.

## Gotowe, gdy
- Strony `#/dla/*` mają tła.
- Rolki mają tła sektorów, a 3 z nich mają wideo.
- Pitch PDF i film są w repo albo w linkach w README.
