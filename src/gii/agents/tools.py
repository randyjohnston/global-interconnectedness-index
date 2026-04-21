"""LangChain tools wrapping data access for agents."""

from langchain_core.tools import tool

from gii.storage.database import get_session
from gii.storage.repository import Repository


@tool
def query_recent_ingestion(source: str, period: str) -> str:
    """Get statistics about the most recent data ingestion for a source.

    Args:
        source: One of "trade", "flights", "geopolitics"
        period: The time period to check, e.g. "2025"
    """
    session = get_session()
    repo = Repository(session)

    if source == "trade":
        rows = repo.get_trade(period)
        session.close()
        if not rows:
            return f"No trade data found for {period}"
        avg_total = sum(r.total_bilateral for r in rows) / len(rows)
        return f"Trade: {len(rows)} bilateral pairs for {period}. Avg bilateral volume: ${avg_total:,.0f}"

    elif source == "flights":
        rows = repo.get_flights(period)
        session.close()
        if not rows:
            return f"No flight data found for {period}"
        total_routes = sum(r.route_count for r in rows)
        return f"Flights: {len(rows)} country-pairs, {total_routes} total routes for {period}"

    elif source == "geopolitics":
        rows = repo.get_geopolitics(period)
        session.close()
        if not rows:
            return f"No geopolitics data found for {period}"
        avg_goldstein = sum(r.avg_goldstein for r in rows) / len(rows)
        return f"Geopolitics: {len(rows)} country-pairs, avg Goldstein: {avg_goldstein:.2f} for {period}"

    session.close()
    return f"Unknown source: {source}"


@tool
def get_index_delta(country_a: str, country_b: str) -> str:
    """Compare current vs previous index snapshot for a country pair.

    Args:
        country_a: ISO3 code of first country
        country_b: ISO3 code of second country
    """
    session = get_session()
    repo = Repository(session)
    history = repo.get_pair_history(country_a, country_b)
    session.close()

    if len(history) < 2:
        return f"Not enough history for {country_a}-{country_b} (only {len(history)} snapshots)"

    current = history[-1]
    previous = history[-2]
    delta = current.composite_score - previous.composite_score
    pct = (delta / previous.composite_score * 100) if previous.composite_score else 0

    parts = [f"{country_a}-{country_b}: {previous.composite_score:.1f} -> {current.composite_score:.1f} ({delta:+.1f}, {pct:+.1f}%)"]

    for pillar in ["trade", "travel", "geopolitics"]:
        curr_val = getattr(current, f"{pillar}_normalized", None)
        prev_val = getattr(previous, f"{pillar}_normalized", None)
        if curr_val is not None and prev_val is not None:
            d = curr_val - prev_val
            parts.append(f"  {pillar}: {prev_val:.1f} -> {curr_val:.1f} ({d:+.1f})")

    return "\n".join(parts)


@tool
def get_pillar_breakdown(country_a: str, country_b: str, period: str) -> str:
    """Get detailed pillar breakdown for a country pair in a specific period.

    Args:
        country_a: ISO3 code of first country
        country_b: ISO3 code of second country
        period: Time period, e.g. "2025"
    """
    session = get_session()
    repo = Repository(session)
    snapshots = repo.get_snapshots(period)
    session.close()

    from gii.models.country import CountryPair
    pair = CountryPair.create(country_a, country_b)

    for s in snapshots:
        if s.country_a == pair.country_a and s.country_b == pair.country_b:
            parts = [
                f"{pair.country_a}-{pair.country_b} ({period}): composite={s.composite_score:.1f}",
                f"  Coverage: {s.coverage}",
            ]
            if s.trade_normalized is not None:
                parts.append(f"  Trade: raw={s.trade_raw:.2f}, normalized={s.trade_normalized:.1f}")
            if s.travel_normalized is not None:
                parts.append(f"  Travel: raw={s.travel_raw:.2f}, normalized={s.travel_normalized:.1f}")
            if s.geopolitics_normalized is not None:
                parts.append(f"  Geopolitics: raw={s.geopolitics_raw:.2f}, normalized={s.geopolitics_normalized:.1f}")
            return "\n".join(parts)

    return f"No snapshot found for {country_a}-{country_b} in {period}"
