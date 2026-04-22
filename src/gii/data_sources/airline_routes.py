"""Airline route data from github.com/Jonty/airline-route-data.

Single JSON file with all passenger airports and outbound routes,
updated weekly. No API key or rate limits — just a GitHub raw fetch.

We count unique airport-to-airport international connections between
tracked country pairs (not individual carriers or flight numbers).

Year-aware: uses the GitHub commits API to fetch the version of the
dataset closest to the requested period (latest commit within that year,
or the most recent commit before it if none exist for that year).
"""

import logging
import re

import httpx

from gii.models.travel import FlightRoute
from gii.storage.database import get_session
from gii.storage.repository import Repository

logger = logging.getLogger(__name__)

REPO = "Jonty/airline-route-data"
FILE_PATH = "airline_routes.json"
COMMITS_URL = f"https://api.github.com/repos/{REPO}/commits"


async def _resolve_commit_sha(client: httpx.AsyncClient, year: int) -> str:
    """Find the latest commit for airline_routes.json up to end of the given year.

    Uses the GitHub commits API with `until` to get the most recent commit
    for the file within or before the requested year.
    """
    resp = await client.get(COMMITS_URL, params={
        "path": FILE_PATH,
        "until": f"{year}-12-31T23:59:59Z",
        "per_page": 1,
    })
    resp.raise_for_status()
    commits = resp.json()

    if not commits:
        raise RuntimeError(f"No commits found for {FILE_PATH} up to {year}")

    sha = commits[0]["sha"]
    date = commits[0]["commit"]["committer"]["date"]
    logger.info(f"Airline routes: using commit {sha[:8]} from {date} for year {year}")
    return sha


def _extract_year(period: str) -> int:
    """Extract the year from a period string like '2025', '2025-Q1', etc."""
    match = re.match(r"(\d{4})", period)
    if not match:
        raise ValueError(f"Cannot extract year from period: {period}")
    return int(match.group(1))


async def fetch_flight_routes(period: str) -> list[FlightRoute]:
    """Fetch airline route data and aggregate unique connections by country pair.

    Pulls the version of the dataset matching the requested period's year:
    - 2025 -> latest commit from 2025
    - 2024 -> latest commit from 2024
    - If no commits exist for that year, uses the most recent prior commit.

    Each route between two airports in different tracked countries counts
    as one connection, regardless of how many carriers operate it.
    """
    year = _extract_year(period)

    # Get tracked countries from DB (ISO2 -> ISO3 mapping)
    session = get_session()
    repo = Repository(session)
    countries = repo.list_countries()
    session.close()

    iso2_to_iso3 = {c.iso2: c.iso3 for c in countries if c.iso2}

    async with httpx.AsyncClient(timeout=120) as client:
        # Resolve the correct commit for this year
        sha = await _resolve_commit_sha(client, year)

        # Fetch the file at that specific commit
        raw_url = f"https://raw.githubusercontent.com/{REPO}/{sha}/{FILE_PATH}"
        logger.info(f"Fetching airline route data for {period} (commit {sha[:8]})...")
        resp = await client.get(raw_url)
        resp.raise_for_status()
        data = resp.json()

    logger.info(f"Loaded {len(data)} airports from airline route dataset")

    # Build airport IATA -> country ISO3 for tracked countries only
    airport_to_iso3: dict[str, str] = {}
    for iata, airport in data.items():
        country_code = airport.get("country_code", "")
        iso3 = iso2_to_iso3.get(country_code)
        if iso3:
            airport_to_iso3[iata] = iso3

    logger.info(f"Mapped {len(airport_to_iso3)} airports to {len(iso2_to_iso3)} tracked countries")

    # Count unique airport-pair connections per country pair
    pair_connections: dict[tuple[str, str], set[tuple[str, str]]] = {}

    for dep_iata, airport in data.items():
        dep_iso3 = airport_to_iso3.get(dep_iata)
        if not dep_iso3:
            continue

        for route in airport.get("routes", []):
            arr_iata = route.get("iata")
            if not arr_iata:
                continue

            arr_iso3 = airport_to_iso3.get(arr_iata)
            if not arr_iso3 or arr_iso3 == dep_iso3:
                continue  # Skip domestic or untracked destinations

            pair = tuple(sorted([dep_iso3, arr_iso3]))
            connection = tuple(sorted([dep_iata, arr_iata]))

            if pair not in pair_connections:
                pair_connections[pair] = set()
            pair_connections[pair].add(connection)

    results = [
        FlightRoute(country_a=a, country_b=b, period=period, route_count=len(connections))
        for (a, b), connections in pair_connections.items()
    ]

    total_connections = sum(len(c) for c in pair_connections.values())
    logger.info(
        f"Airline routes ({period}): {len(results)} country pairs, "
        f"{total_connections} unique airport connections"
    )
    return results
