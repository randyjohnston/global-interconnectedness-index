"""Agent endpoints — on-demand analysis via LangChain."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from gii.api.dependencies import get_db
from gii.api.schemas import AnalyzeRequest, NarrativeResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/analyze", response_model=NarrativeResponse)
async def analyze_pair(req: AnalyzeRequest):
    """On-demand narrative analysis for a country pair."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from gii.agents.llm import get_llm, is_llm_configured
    from gii.agents.tools import get_index_delta, get_pillar_breakdown

    if not is_llm_configured():
        return NarrativeResponse(
            country_a=req.country_a, country_b=req.country_b,
            period=req.period, narrative="LLM provider not configured",
        )

    llm = get_llm(temperature=1, max_tokens=1024)
    llm_with_tools = llm.bind_tools([get_index_delta, get_pillar_breakdown])

    messages = [
        SystemMessage(content="You are an analyst. Generate a concise 2-3 sentence narrative about the interconnectedness between two countries. Use tools to get data."),
        HumanMessage(content=f"Analyze the interconnectedness between {req.country_a} and {req.country_b} for period {req.period}."),
    ]

    for _ in range(5):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)
        if not response.tool_calls:
            break
        for tc in response.tool_calls:
            fn = get_index_delta if tc["name"] == "get_index_delta" else get_pillar_breakdown
            result = fn.invoke(tc["args"])
            messages.append({"role": "tool", "content": str(result), "tool_call_id": tc["id"]})

    narrative = response.content if isinstance(response.content, str) else str(response.content)

    return NarrativeResponse(
        country_a=req.country_a, country_b=req.country_b,
        period=req.period, narrative=narrative,
    )


@router.get("/reports")
def list_reports(period: str | None = None, session: Session = Depends(get_db)):
    """List quality and narrative reports."""
    from sqlalchemy import select
    from gii.storage.models import QualityReportRow, NarrativeReportRow

    reports = []

    q_stmt = select(QualityReportRow).order_by(QualityReportRow.created_at.desc()).limit(20)
    if period:
        q_stmt = q_stmt.where(QualityReportRow.snapshot_period == period)
    for r in session.scalars(q_stmt):
        reports.append({"type": "quality", "period": r.snapshot_period, "severity": r.severity, "findings": r.findings})

    n_stmt = select(NarrativeReportRow).order_by(NarrativeReportRow.created_at.desc()).limit(20)
    if period:
        n_stmt = n_stmt.where(NarrativeReportRow.period == period)
    for r in session.scalars(n_stmt):
        reports.append({"type": "narrative", "pair": f"{r.country_a}-{r.country_b}", "period": r.period, "narrative": r.narrative_text})

    return reports
