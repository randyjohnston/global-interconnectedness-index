"""GDELT BigQuery client for geopolitical event data."""

import logging

from google.cloud import bigquery

from gii.config import settings
from gii.data_sources.country_codes import fips_to_iso3
from gii.models.country import CountryPair
from gii.models.geopolitics import CooperationScore

logger = logging.getLogger(__name__)

GDELT_QUERY = """
SELECT
    Actor1CountryCode,
    Actor2CountryCode,
    AVG(GoldsteinScale) AS avg_goldstein,
    COUNTIF(GoldsteinScale > 0) / COUNT(*) AS cooperative_ratio,
    COUNT(*) AS event_count
FROM `{dataset}.events`
WHERE
    CAST(SUBSTR(CAST(SQLDATE AS STRING), 1, 4) AS INT64) = @year
    AND Actor1CountryCode IS NOT NULL
    AND Actor2CountryCode IS NOT NULL
    AND Actor1CountryCode != Actor2CountryCode
    AND Actor1CountryCode != ''
    AND Actor2CountryCode != ''
GROUP BY Actor1CountryCode, Actor2CountryCode
HAVING event_count >= @min_events
ORDER BY event_count DESC
"""


async def query_gdelt_events(
    year: int,
    min_events: int = 50,
) -> list[CooperationScore]:
    """Query GDELT BigQuery for bilateral geopolitical event aggregates.

    GDELT uses FIPS country codes, which we convert to ISO3.
    Requires GCP credentials configured via local environment variable or 
    service account.
    """
    if not settings.gcp_project_id:
        logger.warning("GCP project not configured, skipping GDELT")
        return []

    client = bigquery.Client(project=settings.gcp_project_id)

    query = GDELT_QUERY.format(dataset=settings.gdelt_dataset)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("year", "INT64", year),
            bigquery.ScalarQueryParameter("min_events", "INT64", min_events),
        ]
    )

    logger.info(f"GDELT: querying events for {year} (min_events={min_events})")
    query_job = client.query(query, job_config=job_config)
    rows = query_job.result()

    # Aggregate by canonical country pair (GDELT has directional rows)
    pair_data: dict[tuple[str, str], dict] = {}

    for row in rows:
        iso3_a = fips_to_iso3(row.Actor1CountryCode)
        iso3_b = fips_to_iso3(row.Actor2CountryCode)

        if not iso3_a or not iso3_b:
            continue

        pair = CountryPair.create(iso3_a, iso3_b)
        key = (pair.country_a, pair.country_b)

        if key not in pair_data:
            pair_data[key] = {
                "goldstein_sum": 0.0,
                "coop_sum": 0.0,
                "event_count": 0,
                "row_count": 0,
            }

        d = pair_data[key]
        d["goldstein_sum"] += row.avg_goldstein * row.event_count
        d["coop_sum"] += row.cooperative_ratio * row.event_count
        d["event_count"] += row.event_count
        d["row_count"] += 1

    results = []
    for (a, b), d in pair_data.items():
        total = d["event_count"]
        if total == 0:
            continue
        results.append(CooperationScore(
            country_a=a,
            country_b=b,
            period=str(year),
            avg_goldstein=d["goldstein_sum"] / total,
            cooperative_ratio=d["coop_sum"] / total,
            event_count=total,
        ))

    logger.info(f"GDELT: {len(results)} country-pair scores for {year}")
    return results
