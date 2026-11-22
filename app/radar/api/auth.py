"""Who may change things. Reading, matching, liking, saving and submitting need no account (nothing personal is
stored). Operator actions (decisions on cards, retraining Basal, triggering pulls) need RADAR_OPERATOR_TOKEN when it
is set; unset = open, for local demos. Partners use their own keys on /api/v1 (radar.api.deals)."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def operator(x_operator_token: str | None = Header(default=None)) -> None:
    token = os.environ.get("RADAR_OPERATOR_TOKEN", "")
    if token and not hmac.compare_digest((x_operator_token or "").encode(), token.encode()):
        raise HTTPException(401, "wymagany token operatora (nagłówek X-Operator-Token)")
