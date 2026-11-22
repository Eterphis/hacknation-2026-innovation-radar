# Publiczny URL dla jury

Dwie drogi, obie w `docker-compose.yml`:

| Profil | Kiedy | Co trzeba mieć |
|---|---|---|
| `tunnel` | adres dla jury bez domeny, bez otwartych portów i bez publicznego IP (VPS, laptop, k3d) | nic; stały adres wymaga konta Cloudflare |
| `public` | własna domena na VPS | rekord DNS na VPS; Caddy sam pobiera certyfikat |

## Tunel Cloudflare (profil `tunnel`)

`edge` (Caddy, `deploy/public/Caddyfile.tunnel`) przyjmuje ruch z tunelu po HTTP, ukrywa `/metrics` i
`/api/basal/train` i przekazuje resztę do `api:8000`. TLS kończy Cloudflare.

1. `.env` bez kluczy chmurowych:
   ```
   RADAR_DEMO_MODE=1
   RADAR_LLM_PROVIDERS=mock
   RADAR_LOCAL_LLM_URL=http://llm:8080/v1
   ```
   `mock` = ekstrakcja i ocena regułami (sekundy na kartę). Bielik 1.5B na CPU pisze tylko hasła (ok. 2,4 s na kartę).
   Chmura jest wyłączona, dopóki nie ustawisz `RADAR_LLM_ALLOW_CLOUD=1`.
2. Start: `docker compose --profile local-llm --profile tunnel up -d --build`, potem `docker compose exec api radar demo`.
3. Adres: `docker compose logs cloudflared`, linia z `https://….trycloudflare.com`.
4. Stały adres (na finał): tunel nazwany w panelu Cloudflare z usługą `http://edge:80`, w `.env`
   `RADAR_TUNNEL_CMD=tunnel --no-autoupdate run` i `TUNNEL_TOKEN=…` (token tylko w `.env`, nigdy w repo).
5. Koniec oceny: `docker compose stop cloudflared` (szybki tunel jest publiczny dla każdego, kto zna adres).

### k3d zamiast compose

`k3d cluster create radar`, `helm install radar deploy/helm/innovation-radar --set localLLM.enabled=true`
(domyślnie `config.demoMode: true`, `config.llmProviders: local,mock`, `config.allowCloud: false`),
`kubectl port-forward svc/radar-innovation-radar-api 8000:80` i
`docker run --rm --network host cloudflare/cloudflared:2025.11.1 tunnel --no-autoupdate --url http://localhost:8000`.
W tym wariancie `/metrics` nie jest ukryte, więc do jury lepiej compose z `edge`.

## Sprawdzone

- Tryb demo działa bez kluczy: `radar demo` importuje 26 rekordów przykładowych i ocenia 23 karty, a wszystkie
  główne endpointy odpowiadają kodem 200. `/api/config` pokazuje `demo_mode: true` i łańcuch bez chmury.
- Stos z profilami `local-llm` i `tunnel` (bez `cloudflared`) na Docker Desktop: `edge` zwraca stronę i API,
  a `/metrics` i `/api/basal/train` dostają 404.

## Lista kontrolna wdrożenia

- [ ] `curl -fsS https://<adres>/healthz` zwraca 200 z innej maszyny.
- [ ] Telefon na LTE (Wi-Fi wyłączone): strona główna, rolki, „Dla mnie”, karta pomysłu.
- [ ] `https://<adres>/api/config`: `demo_mode: true`, `llm_providers` bez chmury.
- [ ] `https://<adres>/metrics` zwraca 404.
- [ ] Zrzut ekranu z telefonu i link w komentarzu do issue #13.
