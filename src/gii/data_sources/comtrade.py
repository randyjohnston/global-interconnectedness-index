"""UN Comtrade API v2 client for bilateral trade data."""

import logging

import httpx

from gii.config import settings
from gii.data_sources.country_codes import ISO3_TO_COMTRADE_NUMERIC
from gii.models.trade import BilateralTrade

logger = logging.getLogger(__name__)

# Comtrade flow codes
EXPORT_CODE = "X"
IMPORT_CODE = "M"


async def fetch_bilateral_trade(
    reporter_iso3: str,
    partner_iso3_list: list[str],
    year: int,
) -> list[BilateralTrade]:
    """Fetch bilateral trade flows for a reporter against multiple partners.

    Uses Comtrade API v2: GET /data/v1/get/C/A/HS
    Free tier: 100 calls/day, so batch partners.
    """
    reporter_code = ISO3_TO_COMTRADE_NUMERIC.get(reporter_iso3)
    if reporter_code is None:
        logger.warning(f"Unknown Comtrade code for {reporter_iso3}")
        return []

    partner_codes = []
    code_to_iso3 = {}
    for p in partner_iso3_list:
        code = ISO3_TO_COMTRADE_NUMERIC.get(p)
        if code is not None:
            partner_codes.append(code)
            code_to_iso3[code] = p

    if not partner_codes:
        return []

    params = {
        "reporterCode": str(reporter_code),
        "partnerCode": ",".join(str(c) for c in partner_codes),
        "period": str(year),
        "flowCode": f"{EXPORT_CODE},{IMPORT_CODE}",
        "cmdCode": "TOTAL",
        "partner2Code": "0",
        "motCode": "0",
        "customsCode": "C00",
    }

    headers = {}
    if settings.comtrade_api_key:
        headers["Ocp-Apim-Subscription-Key"] = settings.comtrade_api_key

    url = f"{settings.comtrade_base_url}/C/A/HS"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # Build bilateral trade from export/import records
    # Key: partner_iso3 -> {"exports": X, "imports": X}
    flows: dict[str, dict[str, float]] = {}

    for record in data.get("data", []):
        partner_code = record.get("partnerCode")
        partner_iso3 = code_to_iso3.get(partner_code)
        if partner_iso3 is None:
            continue

        if partner_iso3 not in flows:
            flows[partner_iso3] = {"exports": 0.0, "imports": 0.0}

        flow_code = record.get("flowCode")
        value = record.get("primaryValue", 0) or 0

        if flow_code == EXPORT_CODE:
            flows[partner_iso3]["exports"] = float(value)
        elif flow_code == IMPORT_CODE:
            flows[partner_iso3]["imports"] = float(value)

    results = []
    for partner_iso3, f in flows.items():
        results.append(BilateralTrade(
            country_a=reporter_iso3,
            country_b=partner_iso3,
            period=str(year),
            exports_a_to_b=f["exports"],
            exports_b_to_a=f["imports"],
        ))

    logger.info(f"Comtrade: {reporter_iso3} -> {len(results)} bilateral flows for {year}")
    return results
