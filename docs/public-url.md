# Publiczny URL dla jury: plan tunelu

Stan: **plan**. Właściwe wdrożenie (helm, compose, CI) czeka na merge PR #11, bo ten PR zmienia `docker-compose.yml`,
`deploy/` i `.github/workflows/`. Poniżej to, co jest sprawdzone dziś, i kroki do wykonania po merge.

## Sprawdzone: tryb demo działa bez kluczy

Na czystym środowisku, bez `ANTHROPIC_API_KEY` i `OPENAI_API_KEY`, z `RADAR_LLM_PROVIDERS=mock` (2026-11-22, gałąź
`feat/pregen-local-llm` na `main` c8dee10):

```powershell
$env:RADAR_DATABASE_URL = "sqlite:///./demo.db"; $env:RADAR_LLM_PROVIDERS = "mock"; radar demo
```

- import: `demo-zgloszenia` 20, `demo-publikacje` 4, `demo-kohesio` 2 rekordy, 23 karty ocenione,
- odpowiadają kodem 200: `/`, `/api/config` (`demo_mode: true`, `llm_providers: ["mock"]`), `/api/ideas`, `/api/feed`,
  `/api/personas/samorzady`, `/api/match`, `/api/insights`, `/api/graph`, `/api/regions`,
- zdrowie usługi: `/healthz` i `/readyz` (nie `/api/health`).

Uwaga: domyślny łańcuch w `docker-compose.yml` to `local,anthropic,openai,mock`. Bez kluczy chmura jest pomijana,
ale zasada „chmura tylko po jawnym włączeniu” wymaga zmiany domyślnej wartości na `local,mock`. Ta zmiana należy do
routera po merge #11.

## Wariant A (zalecany): VPS + Cloudflare Tunnel

Mały VPS (4 vCPU, 8 GB RAM) mieści API, Postgres, RabbitMQ i Bielika 1.5B Q8 na CPU. Tunel nie wymaga otwartych
portów ani publicznego IP.

1. Na VPS: `git clone`, potem `.env` bez kluczy chmurowych:
   `RADAR_DEMO_MODE=1`, `RADAR_LLM_PROVIDERS=local,mock`, `RADAR_LOCAL_LLM_URL=http://llm:8080/v1`.
2. Start: `docker compose --profile local-llm up -d --build`, potem `docker compose exec api radar demo`.
3. Tunel bez konta (szybki test, adres `*.trycloudflare.com` zmienia się przy restarcie):
   `docker run -d --name radar-tunnel --network host cloudflare/cloudflared:latest tunnel --no-autoupdate --url http://localhost:8000`.
   Adres jest w `docker logs radar-tunnel`.
4. Stały adres (na finał): nazwany tunel na koncie Cloudflare zespołu, token w `.env` jako `TUNNEL_TOKEN`
   (nigdy w repo), usługa `cloudflared` w compose pod profilem `tunnel`. To zmiana `docker-compose.yml`, więc po #11.

## Wariant B: k3d + tunel

Po merge #11 (CI stawia już klaster k3d z chartu `deploy/helm/innovation-radar`): `k3d cluster create radar`,
`helm install radar deploy/helm/innovation-radar --set config.demoMode=true --set config.llmProviders=local\,mock`,
`kubectl port-forward svc/radar-innovation-radar-api 8000:80` i ten sam `cloudflared tunnel --url http://localhost:8000`. Więcej ruchomych części niż w wariancie A; sens ma
tylko wtedy, gdy jury ma zobaczyć Kubernetes.

## Weryfikacja (lista do odhaczenia po wdrożeniu)

- [ ] `curl -fsS https://<adres>/healthz` zwraca 200 z innej maszyny.
- [ ] Telefon na LTE (Wi-Fi wyłączone): strona główna, rolki, „Dla mnie”, karta pomysłu.
- [ ] `https://<adres>/api/config` pokazuje `demo_mode: true` i brak dostawców chmurowych.
- [ ] Zrzut ekranu z telefonu i link w komentarzu do issue #13.
- [ ] Instrukcja w README (README zmienia PR #11, dlatego dopisujemy po merge).

## Bezpieczeństwo

- Brak kluczy w obrazie i w repo; tryb demo działa wyłącznie na danych z `app/samples` (oznaczonych jako syntetyczne)
  i na lokalnym modelu.
- Szybki tunel `trycloudflare` jest publiczny dla każdego, kto zna adres: wystarczy na czas oceny, potem
  `docker rm -f radar-tunnel`.
- Endpointy zapisu (`/api/basal/train`, polubienia) warto wyłączyć lub ograniczyć w trybie demo; do decyzji po #11.
