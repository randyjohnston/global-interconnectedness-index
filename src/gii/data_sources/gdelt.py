"""GDELT BigQuery client for geopolitical event data."""

import logging
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account

from gii.config import settings
from gii.data_sources.country_codes import fips_to_iso3
from gii.models.country import CountryPair
from gii.models.geopolitics import CooperationScore

logger = logging.getLogger(__name__)


def _get_bigquery_client() -> bigquery.Client:
    """Build a BigQuery client using the best available credentials.

    Resolution order:
    1. GII_GCP_CREDENTIALS_PATH in .env — explicit service account JSON file
    2. GOOGLE_APPLICATION_CREDENTIALS env var — standard GCP convention
    3. Application Default Credentials (ADC) — works on GCP, or after
       running `gcloud auth application-default login` locally
    """
    # Path 1: explicit service account file from our config
    if settings.gcp_credentials_path:
        path = Path(settings.gcp_credentials_path)
        if path.exists():
            logger.info(f"GDELT: using service account from {path}")
            credentials = service_account.Credentials.from_service_account_file(
                str(path),
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            return bigquery.Client(project=settings.gcp_project_id, credentials=credentials)
        else:
            logger.warning(f"GDELT: credentials file not found at {path}, falling back to ADC")

    # Path 2 & 3: GOOGLE_APPLICATION_CREDENTIALS env var or ADC
    # google-cloud-bigquery handles both automatically
    logger.info("GDELT: using Application Default Credentials")
    return bigquery.Client(project=settings.gcp_project_id)


# Countries we track — used to validate GDELT codes
TRACKED_ISO3 = {
    "USA", "CHN", "DEU", "JPN", "GBR", "FRA", "IND", "ITA", "BRA", "CAN",
    "KOR", "RUS", "AUS", "ESP", "MEX", "IDN", "NLD", "SAU", "TUR", "CHE",
    "POL", "SWE", "BEL", "THA", "ARG", "NGA", "AUT", "NOR", "ARE", "ISR",
    "SGP", "MYS", "PHL", "ZAF", "COL", "EGY", "VNM", "CHL", "IRL", "DNK",
    "FIN", "PRT", "CZE", "NZL", "GRC", "PER", "KEN", "PAK", "BGD", "TWN",
}


def _resolve_country_code(code: str) -> str | None:
    """Resolve a GDELT country code to ISO3.

    GDELT v2 mostly uses ISO3 directly. Falls back to FIPS lookup for older codes.
    """
    code = code.strip().upper()
    if code in TRACKED_ISO3:
        return code
    # Try FIPS lookup for 2-letter codes
    return fips_to_iso3(code)


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

    GDELT v2 uses ISO 3166-1 alpha-3 country codes (e.g. USA, CHN, RUS).
    Some older events may use FIPS codes — we handle both.
    Requires GCP credentials configured via .env or ADC.
    """
    if not settings.gcp_project_id:
        logger.warning("GCP project not configured, skipping GDELT")
        return []

    client = _get_bigquery_client()

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
        iso3_a = _resolve_country_code(row.Actor1CountryCode)
        iso3_b = _resolve_country_code(row.Actor2CountryCode)

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
