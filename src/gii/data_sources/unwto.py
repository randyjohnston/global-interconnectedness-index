"""UNWTO visitor data ingestion from manually downloaded CSVs.

Expected CSV format (UNWTO tourism statistics):
- Columns vary by dataset, but typically:
  Country, Year, Inbound tourists (thousands), ...
- Place CSV files in data/raw/unwto/
"""

import logging
from pathlib import Path

import pandas as pd

from gii.config import settings
from gii.models.travel import VisitorFlow

logger = logging.getLogger(__name__)


def ingest_unwto_visitors(period: str | None = None) -> list[VisitorFlow]:
    """Read all UNWTO CSVs from data/raw/unwto/ and produce VisitorFlow records.

    Handles common UNWTO formats:
    - Bilateral tourism matrix (origin x destination)
    - Single-country inbound stats with origin breakdown
    """
    unwto_dir = Path(settings.data_dir) / "raw" / "unwto"
    if not unwto_dir.exists():
        logger.warning(f"UNWTO data directory not found: {unwto_dir}")
        return []

    csv_files = list(unwto_dir.glob("*.csv"))
    if not csv_files:
        logger.warning(f"No CSV files found in {unwto_dir}")
        return []

    all_flows: list[VisitorFlow] = []

    for csv_file in csv_files:
        logger.info(f"Processing UNWTO file: {csv_file.name}")
        try:
            flows = _process_unwto_csv(csv_file, period)
            all_flows.extend(flows)
        except Exception as e:
            logger.error(f"Failed to process {csv_file.name}: {e}")

    logger.info(f"UNWTO: {len(all_flows)} visitor flow records ingested")
    return all_flows


def _process_unwto_csv(filepath: Path, period: str | None) -> list[VisitorFlow]:
    """Process a single UNWTO CSV file.

    Tries to detect the format and extract bilateral visitor flows.
    """
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]

    # Normalize column names to lowercase
    col_map = {c: c.lower().strip() for c in df.columns}
    df = df.rename(columns=col_map)

    flows: list[VisitorFlow] = []
    name_to_iso3 = _country_name_map()

    # Format 1: columns like "origin", "destination", "year", "visitors"
    if "origin" in df.columns and "destination" in df.columns:
        if period:
            df = df[df["year"].astype(str) == str(period)]
        for _, row in df.iterrows():
            origin = name_to_iso3.get(str(row.get("origin", "")).strip())
            dest = name_to_iso3.get(str(row.get("destination", "")).strip())
            visitors = _safe_int(row.get("visitors", row.get("value", 0)))
            yr = str(row.get("year", period or ""))
            if origin and dest and visitors > 0:
                flows.append(VisitorFlow(
                    origin=origin, destination=dest, period=yr, visitor_count=visitors,
                ))

    # Format 2: pivot table with countries as columns
    elif "country" in df.columns and "year" in df.columns:
        if period:
            df = df[df["year"].astype(str) == str(period)]
        destination_col = "country"
        year_col = "year"
        origin_cols = [c for c in df.columns if c not in (destination_col, year_col)]
        for _, row in df.iterrows():
            dest = name_to_iso3.get(str(row[destination_col]).strip())
            yr = str(row[year_col])
            if not dest:
                continue
            for origin_name in origin_cols:
                origin = name_to_iso3.get(origin_name.strip())
                visitors = _safe_int(row.get(origin_name, 0))
                if origin and visitors > 0:
                    flows.append(VisitorFlow(
                        origin=origin, destination=dest, period=yr, visitor_count=visitors,
                    ))

    return flows


def _safe_int(val) -> int:
    try:
        if pd.isna(val):
            return 0
        return int(float(str(val).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


def _country_name_map() -> dict[str, str]:
    """Map UNWTO country names to ISO3. Case-sensitive for speed, lowercase input expected."""
    return {
        "united states": "USA", "united states of america": "USA",
        "china": "CHN", "germany": "DEU", "japan": "JPN",
        "united kingdom": "GBR", "france": "FRA", "india": "IND",
        "italy": "ITA", "brazil": "BRA", "canada": "CAN",
        "korea, republic of": "KOR", "south korea": "KOR", "korea": "KOR",
        "russian federation": "RUS", "russia": "RUS",
        "australia": "AUS", "spain": "ESP", "mexico": "MEX",
        "indonesia": "IDN", "netherlands": "NLD",
        "saudi arabia": "SAU", "turkey": "TUR", "türkiye": "TUR",
        "switzerland": "CHE", "poland": "POL", "sweden": "SWE",
        "belgium": "BEL", "thailand": "THA", "argentina": "ARG",
        "nigeria": "NGA", "austria": "AUT", "norway": "NOR",
        "united arab emirates": "ARE", "israel": "ISR",
        "singapore": "SGP", "malaysia": "MYS", "philippines": "PHL",
        "south africa": "ZAF", "colombia": "COL", "egypt": "EGY",
        "viet nam": "VNM", "vietnam": "VNM", "chile": "CHL",
        "ireland": "IRL", "denmark": "DNK", "finland": "FIN",
        "portugal": "PRT", "czech republic": "CZE", "czechia": "CZE",
        "new zealand": "NZL", "greece": "GRC", "peru": "PER",
        "kenya": "KEN", "pakistan": "PAK", "bangladesh": "BGD",
        "taiwan": "TWN", "taiwan, province of china": "TWN",
    }
