"""GET /api/cards/{id}/procurement: public procurement dossier (JSON, or ?format=html for print / PDF).

Uses only existing tables (cards, records) and fields the pipeline already computed; see radar.procurement.
Registered in radar.api.main after PR #36 merges (main.py is changed there).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from radar.db import session
from radar.models import Card

router = APIRouter(prefix="/api", tags=["procurement"])


@router.get("/cards/{card_id}/procurement")
def card_procurement(card_id: int, format: str = "json", auto: bool = False):
    from radar.business import business_case
    from radar.investor import _org_key, implementers
    from radar.procurement import dossier, render

    with session() as s:
        c = s.get(Card, card_id)
        if c is None or not c.maturity:
            raise HTTPException(404)
        r = c.record
        bc = business_case(r, c)
        impl = implementers(s, r.sector, r.voivodeship, exclude=_org_key(r.extra, r.affiliations), n=4)
        d = dossier(r, c, bc, impl)
    if format == "html":
        return HTMLResponse(render(d, auto_print=auto))
    return d
