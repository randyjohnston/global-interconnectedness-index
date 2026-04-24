"""Data quality agent — detects anomalies in freshly ingested data."""

import logging

import langsmith
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from gii.agents.llm import get_llm
from gii.agents.tools import query_recent_ingestion
from gii.config import settings
from gii.storage.database import get_session
from gii.storage.models import QualityReportRow

logger = logging.getLogger(__name__)


class QualityFinding(BaseModel):
    issue: str
    severity: str  # "info", "warning", "critical"
    details: str


class QualityReport(BaseModel):
    findings: list[QualityFinding]
    summary: str


SYSTEM_PROMPT = """You are a data quality analyst for the Global Interconnectedness Index.
Your job is to review freshly ingested data and flag anomalies.

Check for:
1. Missing data — expected country pairs with no data
2. Statistical outliers — values far from historical norms
3. Temporal discontinuities — sudden jumps or drops
4. Cross-source inconsistencies — e.g., high trade but zero flights between major partners

Return a structured quality report."""


@langsmith.traceable(run_type="chain")
async def check_data_quality(period: str) -> str:
    """Run the data quality agent for a given period."""
    if not settings.nvidia_api_key:
        logger.warning("NVIDIA API key not configured, skipping quality check")
        return "Skipped: no API key"

    # Gather all source data upfront
    trade_info = query_recent_ingestion.invoke({"source": "trade", "period": period})
    flight_info = query_recent_ingestion.invoke({"source": "flights", "period": period})
    geo_info = query_recent_ingestion.invoke({"source": "geopolitics", "period": period})

    data_summary = f"""Data ingestion summary for {period}:
- {trade_info}
- {flight_info}
- {geo_info}"""

    llm = get_llm()

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Analyze this data for quality issues:\n\n{data_summary}"),
    ]

    response = await llm.ainvoke(messages)
    final_text = response.content if isinstance(response.content, str) else str(response.content)

    # Store report
    session = get_session()
    session.add(QualityReportRow(
        snapshot_period=period,
        findings={"raw_response": final_text},
        severity="info",
    ))
    session.commit()
    session.close()

    logger.info(f"Quality check completed for {period}")
    return final_text
