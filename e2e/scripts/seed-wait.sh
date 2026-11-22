#!/usr/bin/env bash
# Czeka, aż API odpowie na /readyz i /api/ideas zwróci co najmniej jeden pomysł (dane demo zasilone).
# Użycie: bash e2e/scripts/seed-wait.sh [BASE_URL] [TIMEOUT_S]   (domyślnie http://localhost:8000, 180 s)
set -euo pipefail
BASE="${1:-http://localhost:8000}"
TIMEOUT="${2:-180}"
deadline=$(( $(date +%s) + TIMEOUT ))

until curl -fsS "$BASE/readyz" >/dev/null 2>&1; do
  [ "$(date +%s)" -ge "$deadline" ] && { echo "seed-wait: $BASE/readyz nie odpowiada po ${TIMEOUT} s" >&2; exit 1; }
  sleep 2
done
echo "seed-wait: API gotowe ($BASE)"

until total=$(curl -fsS "$BASE/api/ideas?limit=1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["total"])') && [ "${total:-0}" -gt 0 ]; do
  [ "$(date +%s)" -ge "$deadline" ] && { echo "seed-wait: /api/ideas nadal puste po ${TIMEOUT} s" >&2; exit 1; }
  sleep 2
done
echo "seed-wait: dane demo gotowe (${total} pomysłów)"
