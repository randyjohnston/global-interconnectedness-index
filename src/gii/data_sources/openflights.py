"""OpenFlights data fetcher — route counts per country pair."""

import csv
import io
import logging
from collections import Counter

import httpx

from gii.models.travel import FlightRoute

logger = logging.getLogger(__name__)

AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"


async def _fetch_csv(url: str) -> list[list[str]]:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    reader = csv.reader(io.StringIO(resp.text))
    return list(reader)


async def fetch_flight_routes(period: str) -> list[FlightRoute]:
    """Fetch OpenFlights routes and aggregate by country pair.

    airports.dat columns: id, name, city, country, IATA, ICAO, lat, lon, alt, tz, DST, tz_db, type, source
    routes.dat columns: airline, airline_id, source_airport, source_id, dest_airport, dest_id, codeshare, stops, equipment
    """
    airports_data, routes_data = await _fetch_csv(AIRPORTS_URL), await _fetch_csv(ROUTES_URL)

    # Build airport_id -> country_iso3 mapping
    airport_country: dict[str, str] = {}
    for row in airports_data:
        if len(row) < 14:
            continue
        airport_id = row[0]
        iata = row[4].strip()
        country_name = row[3].strip()
        # OpenFlights uses country names; we also have IATA codes
        # Map via the airport ID which routes reference
        # Store country name for now, we'll need a name->iso3 mapping
        airport_country[airport_id] = country_name
        if iata and iata != "\\N":
            airport_country[iata] = country_name

    # We need country name -> ISO2 -> ISO3. Use a simple mapping for top countries.
    country_name_to_iso3 = _build_country_name_map()

    # Count routes per country pair
    pair_counts: Counter[tuple[str, str]] = Counter()

    for row in routes_data:
        if len(row) < 9:
            continue
        src_id = row[3].strip()
        dst_id = row[5].strip()

        src_country = airport_country.get(src_id)
        dst_country = airport_country.get(dst_id)

        if not src_country or not dst_country or src_country == dst_country:
            continue

        src_iso3 = country_name_to_iso3.get(src_country)
        dst_iso3 = country_name_to_iso3.get(dst_country)

        if not src_iso3 or not dst_iso3:
            continue

        pair = tuple(sorted([src_iso3, dst_iso3]))
        pair_counts[pair] += 1

    results = [
        FlightRoute(country_a=a, country_b=b, period=period, route_count=count)
        for (a, b), count in pair_counts.items()
    ]
    logger.info(f"OpenFlights: {len(results)} country-pair routes")
    return results


def _build_country_name_map() -> dict[str, str]:
    """Map common OpenFlights country names to ISO3."""
    return {
        "United States": "USA", "China": "CHN", "Germany": "DEU", "Japan": "JPN",
        "United Kingdom": "GBR", "France": "FRA", "India": "IND", "Italy": "ITA",
        "Brazil": "BRA", "Canada": "CAN", "South Korea": "KOR", "Russia": "RUS",
        "Australia": "AUS", "Spain": "ESP", "Mexico": "MEX", "Indonesia": "IDN",
        "Netherlands": "NLD", "Saudi Arabia": "SAU", "Turkey": "TUR",
        "Switzerland": "CHE", "Poland": "POL", "Sweden": "SWE", "Belgium": "BEL",
        "Thailand": "THA", "Argentina": "ARG", "Nigeria": "NGA", "Austria": "AUT",
        "Norway": "NOR", "United Arab Emirates": "ARE", "Israel": "ISR",
        "Singapore": "SGP", "Malaysia": "MYS", "Philippines": "PHL",
        "South Africa": "ZAF", "Colombia": "COL", "Egypt": "EGY", "Vietnam": "VNM",
        "Chile": "CHL", "Ireland": "IRL", "Denmark": "DNK", "Finland": "FIN",
        "Portugal": "PRT", "Czech Republic": "CZE", "New Zealand": "NZL",
        "Greece": "GRC", "Peru": "PER", "Kenya": "KEN", "Pakistan": "PAK",
        "Bangladesh": "BGD", "Taiwan": "TWN",
        # Alternate names used in OpenFlights
        "Korea": "KOR", "Czechia": "CZE", "Türkiye": "TUR",
    }
