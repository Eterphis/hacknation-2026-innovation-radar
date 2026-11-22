"""Test obciążeniowy API Radaru (issue #31, zadanie 4). Tylko odczyty, które robi UI.

Pełny pomiar (50 rps przez 3 min, profil public 2 vCPU / 4 GB):
    locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 60 -r 10 -t 3m \
        --csv .house/reports/load/po --exit-code-on-error 1
Strażnik w CI (job load-smoke): -u 10 -r 5 -t 30s, bez progu rps.

Każdy użytkownik w on_start pobiera identyfikatory kart z /api/ideas i profile z /api/personas (nic na sztywno).
Ruch ~1 zapytanie na 1,2 s na użytkownika, więc ~60 użytkowników = ~50 rps.
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task

VOIVODESHIPS = ["", "pomorskie", "podkarpackie", "mazowieckie", "małopolskie", "śląskie", "dolnośląskie", "lubelskie",
                "wielkopolskie", "zachodniopomorskie"]
BUDGETS = ["niski", "sredni", "wysoki", "bardzo_wysoki"]
STAGES = ["exploring", "tech_ready", "business_ready", "market_ready"]
GOALS = ["zysk", "wdrozenie", "partner", "finansowanie"]
FACETS = [{}, {"maturity": "business_ready,market_ready"}, {"cost_level": "niski,sredni"}, {"sector": "Q_zdrowie"},
          {"voivodeship": "podkarpackie"}, {"q": "seniorzy"}, {"sort": "likes"}, {"institution_type": "szkola,uczelnia"}]


class RadarUser(HttpUser):
    wait_time = between(0.8, 1.6)

    def on_start(self):
        ideas = self.client.get("/api/ideas", params={"limit": 200}, name="/api/ideas [on_start]").json()["items"]
        self.ids = [i["card_id"] for i in ideas] or [1]
        self.sectors = sorted({i["sector"] for i in ideas if i.get("sector")})
        self.roles = [p["key"] for p in self.client.get("/api/personas", name="/api/personas [on_start]").json()]

    @task(4)
    def match(self):
        sectors = ",".join(random.sample(self.sectors, k=min(len(self.sectors), random.randint(0, 3))))
        self.client.get("/api/match", name="/api/match", params={
            "role": random.choice(self.roles), "voivodeship": random.choice(VOIVODESHIPS), "sectors": sectors,
            "budget": random.choice(BUDGETS), "stage": random.choice(STAGES), "goal": random.choice(GOALS), "limit": 24})

    @task(4)
    def ideas(self):
        self.client.get("/api/ideas", name="/api/ideas", params={**random.choice(FACETS), "limit": 24, "offset": 0})

    @task(2)
    def clusters(self):
        self.client.get("/api/clusters", name="/api/clusters", params={"mode": random.choice(["tematy", "rynki", "podobne"])})

    @task(3)
    def card(self):
        self.client.get(f"/api/cards/{random.choice(self.ids)}", name="/api/cards/{id}")
