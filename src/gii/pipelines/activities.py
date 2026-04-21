"""Temporal activity implementations — the actual work units."""

import asyncio
import logging
import random
from dataclasses import dataclass

from temporalio import activity

from gii.config import settings


logger = logging.getLogger(__name__)


@dataclass
class PipelineParams:
    year: int
    period: str  # e.g. "2025" or "2025-Q1"


# --- Trade Activities ---


@activity.defn
async def fetch_and_store_trade(params: PipelineParams) -> int:
    """Fetch bilateral trade from Comtrade and store in DB."""
    from gii.data_sources.comtrade import fetch_bilateral_trade
    from gii.storage.database import get_session
    from gii.storage.repository import Repository

    session = get_session()
    repo = Repository(session)

    # Get all tracked countries
    countries = repo.list_countries()
    iso3_list = [c.iso3 for c in countries]
    random.shuffle(iso3_list)

    total_stored = 0
    errors = []
    # Fetch for each reporter (Comtrade free tier: 100 calls/day, throttle to avoid 429s)
    for i, reporter in enumerate(iso3_list):
        partners = [c for c in iso3_list if c != reporter]
        try:
            trades = await fetch_bilateral_trade(reporter, partners, params.year)
            for trade in trades:
                repo.upsert_trade(trade)
            total_stored += len(trades)
            logger.info(f"Comtrade: {reporter} ({i+1}/{len(iso3_list)}) -> {len(trades)} flows")
        except Exception as e:
            errors.append(reporter)
            logger.error(f"Comtrade fetch failed for {reporter} ({i+1}/{len(iso3_list)}): {e}")
            activity.heartbeat(f"error:{reporter}")

        activity.heartbeat(f"trade:{reporter}")
        # Rate limit: ~1.5s between calls to stay under Comtrade limits
        await asyncio.sleep(1.5)

    if errors:
        logger.warning(f"Comtrade: {len(errors)} reporters failed: {errors}")

    repo.commit()
    session.close()
    logger.info(f"Trade: stored {total_stored} bilateral records for {params.period}")
    return total_stored


# --- Travel Activities ---


@activity.defn
async def fetch_and_store_flights(params: PipelineParams) -> int:
    """Fetch OpenFlights routes and store in DB."""
    from gii.data_sources.openflights import fetch_flight_routes
    from gii.storage.database import get_session
    from gii.storage.repository import Repository

    routes = await fetch_flight_routes(params.period)

    session = get_session()
    repo = Repository(session)
    for route in routes:
        repo.upsert_flights(route)
    repo.commit()
    session.close()

    logger.info(f"Flights: stored {len(routes)} routes for {params.period}")
    return len(routes)


# --- Geopolitics Activities ---


@activity.defn
async def fetch_and_store_gdelt(params: PipelineParams) -> int:
    """Fetch GDELT events from BigQuery and store in DB."""
    from gii.data_sources.gdelt import query_gdelt_events
    from gii.storage.database import get_session
    from gii.storage.repository import Repository

    logger.info(f"GDELT activity: year={params.year}, gcp_project={settings.gcp_project_id!r}, creds={settings.gcp_credentials_path!r}")
    scores = await query_gdelt_events(params.year)
    logger.info(f"GDELT activity: query returned {len(scores)} scores")

    session = get_session()
    repo = Repository(session)
    for score in scores:
        repo.upsert_geopolitics(score)
    repo.commit()
    session.close()

    logger.info(f"GDELT: stored {len(scores)} geopolitics scores for {params.period}")
    return len(scores)


# --- Computation Activities ---


@activity.defn
async def compute_and_store_index(params: PipelineParams) -> int:
    """Compute composite index from all pillar data and store snapshots."""
    from gii.computation.composite import compute_composite_scores
    from gii.storage.database import get_session
    from gii.storage.repository import Repository

    session = get_session()
    repo = Repository(session)

    trade_rows = repo.get_trade(params.period)
    flight_rows = repo.get_flights(params.period)
    geo_rows = repo.get_geopolitics(params.period)

    scores = compute_composite_scores(trade_rows, flight_rows, geo_rows, params.period)

    for score in scores:
        repo.upsert_snapshot(
            country_a=score.country_a,
            country_b=score.country_b,
            period=score.period,
            trade_raw=score.trade.raw_value if score.trade else None,
            trade_normalized=score.trade.normalized_value if score.trade else None,
            travel_raw=score.travel.raw_value if score.travel else None,
            travel_normalized=score.travel.normalized_value if score.travel else None,
            geopolitics_raw=score.geopolitics.raw_value if score.geopolitics else None,
            geopolitics_normalized=score.geopolitics.normalized_value if score.geopolitics else None,
            composite_score=score.composite_score,
            coverage=",".join(score.coverage),
        )

    repo.commit()
    session.close()

    logger.info(f"Index: computed {len(scores)} composite scores for {params.period}")
    return len(scores)


# --- Agent Activities ---


@activity.defn
async def run_quality_check(params: PipelineParams) -> str:
    """Run LangChain data quality agent."""
    try:
        from gii.agents.quality import check_data_quality
        result = await check_data_quality(params.period)
        return result
    except Exception as e:
        logger.error(f"Quality check failed: {e}")
        return f"Quality check failed: {e}"


@activity.defn
async def generate_narratives(params: PipelineParams) -> int:
    """Run LangChain narrative agent for top movers."""
    try:
        from gii.agents.narrative import generate_period_narratives
        count = await generate_period_narratives(params.period)
        return count
    except Exception as e:
        logger.error(f"Narrative generation failed: {e}")
        return 0
