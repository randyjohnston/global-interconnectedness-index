from pydantic import BaseModel


class SubIndex(BaseModel):
    """A single pillar sub-index score."""

    pillar: str  # "trade", "travel", "geopolitics"
    raw_value: float
    normalized_value: float  # 0-100 scale


class CompositeScore(BaseModel):
    """Full composite index for a country pair in a period."""

    country_a: str
    country_b: str
    period: str
    trade: SubIndex | None = None
    trade_log: float | None = None
    travel: SubIndex | None = None
    geopolitics: SubIndex | None = None
    geopolitics_avg_goldstein: float | None = None
    geopolitics_cooperative_ratio: float | None = None
    geopolitics_event_count: int | None = None
    composite_score: float = 0.0
    coverage: list[str] = []  # which pillars contributed


class Snapshot(BaseModel):
    """A point-in-time collection of all composite scores."""

    period: str
    scores: list[CompositeScore] = []
