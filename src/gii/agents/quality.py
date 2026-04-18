"""Data quality agent — detects anomalies in freshly ingested data."""

import logging

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

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

Use the query_recent_ingestion tool to inspect each data source.
Return a structured quality report."""


async def check_data_quality(period: str) -> str:
    """Run the data quality agent for a given period."""
    if not settings.nvidia_api_key:
        logger.warning("NVIDIA API key not configured, skipping quality check")
        return "Skipped: no API key"

    llm = ChatNVIDIA(
        model=settings.llm_model,
        api_key=settings.nvidia_api_key,
        temperature=1,
        top_p=0.95,
        max_tokens=2048,
    )

    llm_with_tools = llm.bind_tools([query_recent_ingestion])

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Check data quality for period: {period}. Query each source (trade, flights, geopolitics) and report findings."),
    ]

    # Agent loop — let the LLM call tools iteratively
    for _ in range(5):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_result = query_recent_ingestion.invoke(tool_call["args"])
            messages.append({"role": "tool", "content": str(tool_result), "tool_call_id": tool_call["id"]})

    # Extract final response
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
