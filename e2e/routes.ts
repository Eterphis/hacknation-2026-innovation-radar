// Jedna lista tras UI dla wszystkich spec-ów. Klucz = pierwszy człon hasha (klucz w ROUTES z app.js/pages.js).
// Nowa trasa w aplikacji bez wpisu tutaj = czerwony test „lista tras” w routes.spec.ts.
export type SeedData = { personas: string[]; ids: number[] };
export type RouteVisit = { hash: string; shot: string };
export type RouteDef = { key: string; name: string; visits: (d: SeedData) => RouteVisit[] };

const one = (hash: string, shot: string) => () => [{ hash, shot }];

export const ROUTE_DEFS: RouteDef[] = [
  { key: "", name: "przegląd", visits: one("#/", "przeglad") },
  { key: "dla", name: "dla mnie", visits: one("#/dla", "dla") },
  { key: "dla", name: "dla <persona>", visits: d => d.personas.map(p => ({ hash: `#/dla/${p}`, shot: `dla-${p}` })) },
  { key: "dopasuj", name: "dopasuj", visits: one("#/dopasuj", "dopasuj") },
  { key: "odkrywaj", name: "odkrywaj", visits: one("#/odkrywaj", "odkrywaj") },
  { key: "pomysl", name: "pomysł", visits: d => [{ hash: `#/pomysl/${d.ids[0]}`, shot: "pomysl" }] },
  { key: "klastry", name: "klastry", visits: one("#/klastry", "klastry") },
  { key: "rolki", name: "rolki", visits: one("#/rolki", "rolki") },
  { key: "mapa", name: "mapa", visits: one("#/mapa", "mapa") },
  { key: "graf", name: "graf", visits: one("#/graf", "graf") },
  { key: "zrodla", name: "źródła", visits: one("#/zrodla", "zrodla") },
  { key: "wdrozenia", name: "wdrożenia", visits: one("#/wdrozenia", "wdrozenia") },
  { key: "porownaj", name: "porównaj", visits: d => [{ hash: `#/porownaj?ids=${d.ids[0]},${d.ids[1]}`, shot: "porownaj" }] },
  { key: "portfel", name: "portfel: lejek", visits: one("#/portfel?tab=lejek", "portfel-lejek") },
  { key: "portfel", name: "portfel: zapisane", visits: one("#/portfel?tab=zapisane", "portfel-zapisane") },
  { key: "zapisane", name: "zapisane", visits: one("#/zapisane", "zapisane") },
];

export const ROUTE_KEYS = [...new Set(ROUTE_DEFS.map(r => r.key))].sort();
export const allVisits = (d: SeedData) => ROUTE_DEFS.flatMap(r => r.visits(d));
