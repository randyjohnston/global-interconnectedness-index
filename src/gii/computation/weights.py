"""Pillar weight configuration for composite index."""

from dataclasses import dataclass

from gii.config import settings


@dataclass
class PillarWeights:
    trade: float = 0.40
    travel: float = 0.30
    geopolitics: float = 0.30

    @classmethod
    def from_settings(cls) -> "PillarWeights":
        return cls(
            trade=settings.weight_trade,
            travel=settings.weight_travel,
            geopolitics=settings.weight_geopolitics,
        )

    def for_available(self, available: list[str]) -> dict[str, float]:
        """Re-weight for available pillars only, normalizing to sum=1."""
        raw = {
            "trade": self.trade,
            "travel": self.travel,
            "geopolitics": self.geopolitics,
        }
        subset = {k: v for k, v in raw.items() if k in available}
        total = sum(subset.values())
        if total == 0:
            return {k: 1.0 / len(subset) for k in subset}
        return {k: v / total for k, v in subset.items()}
