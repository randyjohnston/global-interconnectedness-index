from pydantic import BaseModel


class BilateralTrade(BaseModel):
    """Bilateral trade flow between two countries for a period."""

    country_a: str
    country_b: str
    period: str  # e.g. "2025" or "2025-Q1"
    exports_a_to_b: float = 0.0
    exports_b_to_a: float = 0.0

    @property
    def total_bilateral(self) -> float:
        return self.exports_a_to_b + self.exports_b_to_a
