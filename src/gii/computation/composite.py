"""Composite index computation — combine normalized sub-indices."""

import math

from gii.computation.normalize import normalize_to_0_100
from gii.computation.weights import PillarWeights
from gii.models.index import CompositeScore, SubIndex
from gii.storage.models import (
    BilateralTradeRow,
    FlightConnectivityRow,
    GeopoliticsScoreRow,
)


def compute_trade_raw(row: BilateralTradeRow) -> float:
    """Log-transformed bilateral trade value."""
    return math.log(row.total_bilateral + 1)


def compute_geopolitics_raw(row: GeopoliticsScoreRow) -> float:
    """Shifted Goldstein + cooperative ratio blend.

    Goldstein shifted from [-10,+10] to [0,20].
    Blend: 0.6 * shifted_goldstein + 0.4 * cooperative_ratio * 20
    """
    shifted = row.avg_goldstein + 10.0  # [0, 20]
    coop_scaled = row.cooperative_ratio * 20.0  # [0, 20]
    return 0.6 * shifted + 0.4 * coop_scaled


def compute_composite_scores(
    trade_rows: list[BilateralTradeRow],
    flight_rows: list[FlightConnectivityRow],
    geopolitics_rows: list[GeopoliticsScoreRow],
    period: str,
    weights: PillarWeights | None = None,
) -> list[CompositeScore]:
    """Compute composite scores for all country pairs in a period.

    1. Compute raw values per pillar
    2. Normalize each pillar to 0-100 across all pairs
    3. Weighted average for composite score
    """
    if weights is None:
        weights = PillarWeights.from_settings()

    # Index all data by canonical pair
    trade_by_pair = {(r.country_a, r.country_b): r for r in trade_rows}
    flight_by_pair = {(r.country_a, r.country_b): r for r in flight_rows}
    geo_by_pair = {(r.country_a, r.country_b): r for r in geopolitics_rows}

    all_pairs = set(trade_by_pair) | set(flight_by_pair) | set(geo_by_pair)
    if not all_pairs:
        return []

    # Compute raw values
    pair_list = sorted(all_pairs)
    trade_raw = [float(trade_by_pair[p].total_bilateral) if p in trade_by_pair else None for p in pair_list]
    trade_for_norm = [compute_trade_raw(trade_by_pair[p]) if p in trade_by_pair else None for p in pair_list]
    flight_raw = [float(flight_by_pair[p].route_count) if p in flight_by_pair else None for p in pair_list]
    geo_raw = [compute_geopolitics_raw(geo_by_pair[p]) if p in geo_by_pair else None for p in pair_list]

    # Normalize each pillar (only non-None values)
    # Trade uses log-transform for normalization but stores actual bilateral value as raw
    trade_norm = _normalize_sparse(trade_for_norm)
    flight_norm = _normalize_sparse(flight_raw)
    geo_norm = _normalize_sparse(geo_raw)

    # Coverage confidence: small discount for missing pillars so pairs with
    # real data are preferred, all else being equal.
    COVERAGE_CONFIDENCE = {3: 1.0, 2: 0.95, 1: 0.85}
    NEUTRAL = 50.0  # midpoint of 0-100 scale, used for missing pillars

    # Build composite scores
    results = []
    for i, (a, b) in enumerate(pair_list):
        available = []
        pillar_scores = {}

        if trade_norm[i] is not None:
            available.append("trade")
            pillar_scores["trade"] = SubIndex(pillar="trade", raw_value=trade_raw[i], normalized_value=trade_norm[i])

        if flight_norm[i] is not None:
            available.append("travel")
            pillar_scores["travel"] = SubIndex(pillar="travel", raw_value=flight_raw[i], normalized_value=flight_norm[i])

        if geo_norm[i] is not None:
            available.append("geopolitics")
            pillar_scores["geopolitics"] = SubIndex(pillar="geopolitics", raw_value=geo_raw[i], normalized_value=geo_norm[i])

        if not available:
            continue

        # Use actual weights for all 3 pillars — missing pillars get neutral (50)
        w_all = weights.for_available(["trade", "travel", "geopolitics"])
        composite = (
            w_all["trade"] * (pillar_scores["trade"].normalized_value if "trade" in pillar_scores else NEUTRAL)
            + w_all["travel"] * (pillar_scores["travel"].normalized_value if "travel" in pillar_scores else NEUTRAL)
            + w_all["geopolitics"] * (pillar_scores["geopolitics"].normalized_value if "geopolitics" in pillar_scores else NEUTRAL)
        )

        # Apply coverage confidence discount
        composite *= COVERAGE_CONFIDENCE[len(available)]

        # Carry raw geopolitics components for UI display
        geo_row = geo_by_pair.get((a, b))

        results.append(CompositeScore(
            country_a=a, country_b=b, period=period,
            trade=pillar_scores.get("trade"),
            trade_log=round(trade_for_norm[i], 4) if trade_for_norm[i] is not None else None,
            travel=pillar_scores.get("travel"),
            geopolitics=pillar_scores.get("geopolitics"),
            geopolitics_avg_goldstein=round(geo_row.avg_goldstein, 3) if geo_row else None,
            geopolitics_cooperative_ratio=round(geo_row.cooperative_ratio, 3) if geo_row else None,
            geopolitics_event_count=geo_row.event_count if geo_row else None,
            composite_score=round(composite, 2),
            coverage=available,
        ))

    return results


def _normalize_sparse(values: list[float | None]) -> list[float | None]:
    """Normalize only non-None values, preserving None positions."""
    non_none = [(i, v) for i, v in enumerate(values) if v is not None]
    if not non_none:
        return values

    raw = [v for _, v in non_none]
    normalized = normalize_to_0_100(raw)

    result: list[float | None] = [None] * len(values)
    for (i, _), norm_val in zip(non_none, normalized):
        result[i] = round(norm_val, 2)
    return result
