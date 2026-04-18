from pydantic import BaseModel


class GdeltEvent(BaseModel):
    """Raw GDELT event between two country actors."""

    actor1_country: str
    actor2_country: str
    goldstein_scale: float
    is_cooperative: bool
    event_date: str


class CooperationScore(BaseModel):
    """Aggregated geopolitics score for a country pair."""

    country_a: str
    country_b: str
    period: str
    avg_goldstein: float = 0.0
    cooperative_ratio: float = 0.0
    event_count: int = 0
