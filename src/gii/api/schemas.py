"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel


class CountryResponse(BaseModel):
    iso3: str
    iso2: str
    name: str
    region: str


class SubIndexResponse(BaseModel):
    pillar: str
    raw_value: float | None
    normalized_value: float | None


class PairScoreResponse(BaseModel):
    country_a: str
    country_b: str
    period: str
    trade: SubIndexResponse | None = None
    travel: SubIndexResponse | None = None
    geopolitics: SubIndexResponse | None = None
    composite_score: float
    coverage: list[str]


class RankingEntry(BaseModel):
    country: str
    country_name: str
    avg_score: float
    pair_count: int


class PipelineTriggerRequest(BaseModel):
    period: str  # e.g. "2025" or "2025-Q1"


class MultiPeriodTriggerRequest(BaseModel):
    start_year: int
    end_year: int


class PipelineStatusResponse(BaseModel):
    status: str
    workflow_id: str | None = None
    message: str = ""


class AnalyzeRequest(BaseModel):
    country_a: str
    country_b: str
    period: str


class NarrativeResponse(BaseModel):
    country_a: str
    country_b: str
    period: str
    narrative: str
