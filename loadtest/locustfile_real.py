"""Test obciążeniowy na prawdziwych danych: to, co robi UI, łącznie ze stroną główną, mapą, rolkami i polubieniami.

    locust -f loadtest/locustfile_real.py --host http://localhost:8088 --headless -u 70 -r 10 -t 3m --csv .house/reports/load/real
    LIKES=1 locust -f loadtest/locustfile_real.py ...   # dodatkowo polubienia (każde zmienia wersję danych)

Bazuje na loadtest/locustfile.py (match, ideas, clusters, cards) i dokłada: /api/insights (Przegląd),
/api/regions (mapa), /api/feed (rolki) oraz opcjonalnie POST /like (dwa razy: polub i cofnij, bilans zero).
"""

from __future__ import annotations

import os
import random
import uuid

from locust import task

from locustfile import RadarUser

LIKES = int(os.environ.get("LIKES", "0"))


class RealUser(RadarUser):
    def on_start(self):
        super().on_start()
        self.voter = uuid.uuid4().hex

    @task(2)
    def home(self):
        self.client.get("/api/insights", name="/api/insights")

    @task(1)
    def regions(self):
        self.client.get("/api/regions", name="/api/regions")

    @task(1)
    def feed(self):
        self.client.get("/api/feed", name="/api/feed", params={"limit": 10, "offset": random.choice([0, 10, 20])})

    @task(LIKES)
    def like(self):
        cid = random.choice(self.ids)
        for _ in range(2):  # like and undo: the data changes, the totals stay the same
            self.client.post(f"/api/cards/{cid}/like", name="/api/cards/{id}/like", headers={"X-Voter": self.voter})


RadarUser.abstract = True
