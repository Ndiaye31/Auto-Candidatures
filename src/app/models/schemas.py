from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class JobOfferCreate(BaseModel):
    company_id: Optional[int] = None
    title: str
    location: Optional[str] = None
    contract_type: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    description_raw: Optional[str] = None


class ScoreView(BaseModel):
    job_offer_id: int
    candidate_profile_id: int
    score_total: float
    score_breakdown_json: dict
    computed_at: datetime
