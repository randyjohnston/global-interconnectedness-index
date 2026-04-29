"""LangChain tools wrapping data access for agents."""

import logging

from langchain_core.tools import tool

from gii.config import settings
from gii.storage.database import get_session
from gii.storage.repository import Repository

logger = logging.getLogger(__name__)


@tool
def query_recent_ingestion(source: str, period: str) -> str:
    """Get statistics about the most recent data ingestion for a source.

    Args:
        source: One of "trade", "flights", "geopolitics"
        period: The time period to check, e.g. a year like "2024" or a quarter like "2024-Q1"
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
        period: Time period, e.g. a year like "2024" or a quarter like "2024-Q1"
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


# --- Domain-specific tools for subagents ---


def query_trade_data(country_a: str, country_b: str, period: str) -> str:
    """Query bilateral trade data for a country pair including raw volumes, index scores, and period-over-period changes.

    Args:
        country_a: ISO3 code of first country
        country_b: ISO3 code of second country
        period: Time period, e.g. "2024"
    """
    from gii.models.country import CountryPair

    session = get_session()
    repo = Repository(session)
    pair = CountryPair.create(country_a, country_b)
    parts: list[str] = []

    trades = repo.get_trade(period)
    trade_row = next(
        (t for t in trades if t.country_a == pair.country_a and t.country_b == pair.country_b),
        None,
    )
    if trade_row:
        parts.append(f"Bilateral Trade ({period}):")
        parts.append(f"  Exports {pair.country_a} → {pair.country_b}: ${trade_row.exports_a_to_b:,.0f}")
        parts.append(f"  Exports {pair.country_b} → {pair.country_a}: ${trade_row.exports_b_to_a:,.0f}")
        parts.append(f"  Total bilateral: ${trade_row.total_bilateral:,.0f}")
    else:
        parts.append(f"No raw trade data for {pair.country_a}-{pair.country_b} in {period}")

    snapshots = repo.get_snapshots(period)
    snap = next(
        (s for s in snapshots if s.country_a == pair.country_a and s.country_b == pair.country_b),
        None,
    )
    if snap and snap.trade_normalized is not None:
        parts.append(f"Trade Index: raw={snap.trade_raw:.2f}, normalized={snap.trade_normalized:.1f}/100")

    history = repo.get_pair_history(country_a, country_b)
    if len(history) >= 2:
        curr, prev = history[-1], history[-2]
        if curr.trade_normalized is not None and prev.trade_normalized is not None:
            d = curr.trade_normalized - prev.trade_normalized
            parts.append(f"Trade Delta vs previous period: {prev.trade_normalized:.1f} → {curr.trade_normalized:.1f} ({d:+.1f})")

    session.close()
    return "\n".join(parts)


def query_travel_data(country_a: str, country_b: str, period: str) -> str:
    """Query flight connectivity data for a country pair including route counts, index scores, and period-over-period changes.

    Args:
        country_a: ISO3 code of first country
        country_b: ISO3 code of second country
        period: Time period, e.g. "2024"
    """
    from gii.models.country import CountryPair

    session = get_session()
    repo = Repository(session)
    pair = CountryPair.create(country_a, country_b)
    parts: list[str] = []

    flights = repo.get_flights(period)
    flight_row = next(
        (f for f in flights if f.country_a == pair.country_a and f.country_b == pair.country_b),
        None,
    )
    if flight_row:
        parts.append(f"Flight Connectivity ({period}):")
        parts.append(f"  Route count: {flight_row.route_count}")
    else:
        parts.append(f"No flight data for {pair.country_a}-{pair.country_b} in {period}")

    snapshots = repo.get_snapshots(period)
    snap = next(
        (s for s in snapshots if s.country_a == pair.country_a and s.country_b == pair.country_b),
        None,
    )
    if snap and snap.travel_normalized is not None:
        parts.append(f"Travel Index: raw={snap.travel_raw:.2f}, normalized={snap.travel_normalized:.1f}/100")

    history = repo.get_pair_history(country_a, country_b)
    if len(history) >= 2:
        curr, prev = history[-1], history[-2]
        if curr.travel_normalized is not None and prev.travel_normalized is not None:
            d = curr.travel_normalized - prev.travel_normalized
            parts.append(f"Travel Delta vs previous period: {prev.travel_normalized:.1f} → {curr.travel_normalized:.1f} ({d:+.1f})")

    session.close()
    return "\n".join(parts)


def query_geopolitics_data(country_a: str, country_b: str, period: str) -> str:
    """Query geopolitics scores for a country pair including Goldstein scale, cooperation ratio, event count, and period-over-period changes.

    Args:
        country_a: ISO3 code of first country
        country_b: ISO3 code of second country
        period: Time period, e.g. "2024"
    """
    from gii.models.country import CountryPair

    session = get_session()
    repo = Repository(session)
    pair = CountryPair.create(country_a, country_b)
    parts: list[str] = []

    geo_rows = repo.get_geopolitics(period)
    geo_row = next(
        (g for g in geo_rows if g.country_a == pair.country_a and g.country_b == pair.country_b),
        None,
    )
    if geo_row:
        parts.append(f"Geopolitics Scores ({period}):")
        parts.append(f"  Avg Goldstein: {geo_row.avg_goldstein:.2f}")
        parts.append(f"  Cooperative ratio: {geo_row.cooperative_ratio:.2%}")
        parts.append(f"  Event count: {geo_row.event_count}")
    else:
        parts.append(f"No geopolitics data for {pair.country_a}-{pair.country_b} in {period}")

    snapshots = repo.get_snapshots(period)
    snap = next(
        (s for s in snapshots if s.country_a == pair.country_a and s.country_b == pair.country_b),
        None,
    )
    if snap and snap.geopolitics_normalized is not None:
        parts.append(f"Geopolitics Index: raw={snap.geopolitics_raw:.2f}, normalized={snap.geopolitics_normalized:.1f}/100")

    history = repo.get_pair_history(country_a, country_b)
    if len(history) >= 2:
        curr, prev = history[-1], history[-2]
        if curr.geopolitics_normalized is not None and prev.geopolitics_normalized is not None:
            d = curr.geopolitics_normalized - prev.geopolitics_normalized
            parts.append(f"Geopolitics Delta vs previous period: {prev.geopolitics_normalized:.1f} → {curr.geopolitics_normalized:.1f} ({d:+.1f})")

    session.close()
    return "\n".join(parts)


# --- Tavily web search with domain whitelists ---


def _tavily_search(query: str, allowed_domains: list[str]) -> str:
    """Shared Tavily search logic."""
    from tavily import TavilyClient

    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            include_domains=allowed_domains,
            max_results=5,
        )
        results = response.get("results", [])
        if not results:
            return "No relevant results found."
        parts = []
        for r in results:
            parts.append(f"**{r.get('title', 'Untitled')}**")
            parts.append(f"  Source: {r.get('url', '')}")
            parts.append(f"  {r.get('content', '')[:300]}")
            parts.append("")
        return "\n".join(parts)
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return f"Web search unavailable: {e}"


def build_trade_search():
    domains = [d.strip() for d in settings.tavily_trade_domains.split(",") if d.strip()]

    @tool
    def search_trade_news(query: str) -> str:
        """Search for recent international trade news, tariffs, trade agreements, and commerce developments between countries."""
        return _tavily_search(query, domains)

    return search_trade_news


def build_travel_search():
    domains = [d.strip() for d in settings.tavily_travel_domains.split(",") if d.strip()]

    @tool
    def search_travel_news(query: str) -> str:
        """Search for recent travel, aviation, and tourism news including new flight routes, travel restrictions, and tourism trends."""
        return _tavily_search(query, domains)

    return search_travel_news


def build_geopolitics_search():
    domains = [d.strip() for d in settings.tavily_geopolitics_domains.split(",") if d.strip()]

    @tool
    def search_geopolitics_news(query: str) -> str:
        """Search for recent geopolitical news including diplomatic relations, sanctions, treaties, and international cooperation."""
        return _tavily_search(query, domains)

    return search_geopolitics_news
