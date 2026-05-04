"""Dashboard HTML routes — serves Jinja2 templates with HTMX."""

import json
import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from langgraph.types import Command
from pathlib import Path
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from gii.api.dependencies import get_db, get_repo

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter(tags=["dashboard"])

# In-memory store for pending HITL review sessions
_active_sessions: dict[str, dict] = {}


@router.get("/", response_class=HTMLResponse)
def dashboard_home(request: Request, period: str | None = Query(None), session: Session = Depends(get_db)):
    repo = get_repo(session)
    if period is None:
        period = repo.get_latest_period() or str(date.today().year)
    snapshots = repo.get_snapshots(period)
    countries = repo.list_countries()

    top_10 = snapshots[:10]
    bottom_10 = snapshots[-10:] if len(snapshots) > 10 else []

    return templates.TemplateResponse(request, "index.html", {
        "period": period,
        "total_pairs": len(snapshots),
        "total_countries": len(countries),
        "top_pairs": top_10,
        "bottom_pairs": bottom_10,
    })


@router.get("/rankings", response_class=HTMLResponse)
def rankings_page(request: Request, period: str | None = Query(None), session: Session = Depends(get_db)):
    repo = get_repo(session)
    if period is None:
        period = repo.get_latest_period() or str(date.today().year)
    snapshots = repo.get_snapshots(period)

    # Aggregate by country
    country_scores: dict[str, list[float]] = {}
    for s in snapshots:
        country_scores.setdefault(s.country_a, []).append(s.composite_score)
        country_scores.setdefault(s.country_b, []).append(s.composite_score)

    rankings = [
        {"country": c, "avg_score": round(
            sum(scores) / len(scores), 2), "pair_count": len(scores)}
        for c, scores in country_scores.items()
    ]
    rankings.sort(key=lambda x: x["avg_score"], reverse=True)

    countries = {c.iso3: c.name for c in repo.list_countries()}

    return templates.TemplateResponse(request, "rankings.html", {
        "period": period,
        "rankings": rankings,
        "country_names": countries,
    })


@router.get("/pair/{country_a}/{country_b}", response_class=HTMLResponse)
def pair_detail(request: Request, country_a: str, country_b: str, session: Session = Depends(get_db)):
    repo = get_repo(session)
    history = repo.get_pair_history(country_a, country_b)
    countries = {c.iso3: c.name for c in repo.list_countries()}

    return templates.TemplateResponse(request, "pair_detail.html", {
        "country_a": country_a,
        "country_b": country_b,
        "country_a_name": countries.get(country_a, country_a),
        "country_b_name": countries.get(country_b, country_b),
        "history": history,
    })


@router.get("/admin/pipelines", response_class=HTMLResponse)
def pipeline_admin(request: Request):
    return templates.TemplateResponse(request, "admin.html")


# --- HTMX Partials ---


@router.get("/partials/score-card/{country_a}/{country_b}/{period}", response_class=HTMLResponse)
def score_card_partial(request: Request, country_a: str, country_b: str, period: str, session: Session = Depends(get_db)):
    repo = get_repo(session)
    snapshots = repo.get_snapshots(period)

    from gii.models.country import CountryPair
    pair = CountryPair.create(country_a, country_b)
    snapshot = next((s for s in snapshots if s.country_a ==
                    pair.country_a and s.country_b == pair.country_b), None)
    narrative = repo.get_narrative(country_a, country_b, period)
    countries = {c.iso3: c.name for c in repo.list_countries()}

    return templates.TemplateResponse(request, "partials/score_card.html", {
        "snapshot": snapshot,
        "narrative": narrative,
        "country_a": pair.country_a,
        "country_b": pair.country_b,
        "country_a_name": countries.get(pair.country_a, pair.country_a),
        "country_b_name": countries.get(pair.country_b, pair.country_b),
        "period": period,
    })


@router.get("/api/narrative/stream/{country_a}/{country_b}/{period}")
async def stream_narrative(country_a: str, country_b: str, period: str):
    """SSE endpoint — streams narrative tokens from the deep agent."""
    from gii.agents.narrative import build_agent
    from gii.models.country import CountryPair
    from gii.storage.database import get_session
    from gii.storage.repository import Repository

    pair = CountryPair.create(country_a, country_b)

    async def event_generator():
        from gii.agents.llm import is_llm_configured
        if not is_llm_configured():
            yield {"event": "error", "data": "LLM provider not configured"}
            return

        session = get_session()
        repo = Repository(session)
        countries = {c.iso3: c.name for c in repo.list_countries()}
        name_a = countries.get(pair.country_a, pair.country_a)
        name_b = countries.get(pair.country_b, pair.country_b)

        thread_id = str(uuid.uuid4())
        agent = build_agent(streaming=True)
        config = {
            "configurable": {"thread_id": thread_id},
            "run_name": "generate_narrative",
            "tags": ["ui"],
            "metadata": {"country_a": pair.country_a, "country_b": pair.country_b, "period": period},
        }

        full_text = ""
        task_depth = 0        # >0 means we're inside a subagent task call
        task_count = 0        # how many task tool calls have completed
        supervisor_has_tools = False  # True once supervisor has made tool calls

        try:
            yield {"event": "status", "data": json.dumps({"text": "Dispatching domain analysts..."})}

            async for event in agent.astream_events(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Generate a narrative for {name_a} ({pair.country_a}) "
                                f"and {name_b} ({pair.country_b}) in period {period}. "
                                f"Use the tools to gather data first."
                            ),
                        }
                    ],
                },
                version="v2",
                config=config,
            ):
                kind = event.get("event")

                # Track entry/exit of task tool to know when we're in a subagent
                if kind == "on_tool_start" and event.get("name") == "task":
                    task_depth += 1
                    continue
                elif kind == "on_tool_end" and event.get("name") == "task":
                    task_depth -= 1
                    task_count += 1
                    analysts = {1: "Trade", 2: "Travel", 3: "Geopolitics"}
                    label = analysts.get(task_count, f"Analyst {task_count}")
                    yield {"event": "status", "data": json.dumps({"text": f"{label} analyst done..."})}
                    if task_count >= 3 and task_depth == 0:
                        yield {"event": "status", "data": json.dumps({"text": f"{label} analyst done. Synthesising narrative..."})}
                    continue

                # Skip all LLM events from subagents
                if task_depth > 0:
                    continue

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if not chunk:
                        continue
                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        supervisor_has_tools = True
                        continue
                    # Extract text from content
                    text = ""
                    if isinstance(chunk.content, str):
                        text = chunk.content
                    elif isinstance(chunk.content, list):
                        for block in chunk.content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text += block.get("text", "")
                    if text and supervisor_has_tools:
                        full_text += text
                        yield {"event": "token", "data": json.dumps({"token": text})}

            # Check if the agent is waiting for HITL approval
            state = await agent.aget_state(config)
            if state.next:
                _active_sessions[thread_id] = {
                    "agent": agent,
                    "config": config,
                    "full_text": full_text,
                    "country_a": pair.country_a,
                    "country_b": pair.country_b,
                    "period": period,
                }
                yield {"event": "review", "data": json.dumps({"thread_id": thread_id})}
            else:
                yield {"event": "done", "data": json.dumps({"success": True})}

        except Exception as e:
            logger.error(
                f"Narrative stream failed for {pair.country_a}-{pair.country_b}: {e}")
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
        finally:
            session.close()

    return EventSourceResponse(event_generator())


@router.post("/api/narrative/review/{thread_id}")
async def review_narrative(thread_id: str, request: Request):
    """Resume a HITL-interrupted narrative agent with an approve or reject decision."""
    body = await request.json()
    decision = body.get("decision")
    if decision not in ("approve", "reject"):
        return JSONResponse({"error": "decision must be 'approve' or 'reject'"}, status_code=400)

    session_data = _active_sessions.pop(thread_id, None)
    if not session_data:
        return JSONResponse({"error": "Review session not found or already resolved"}, status_code=404)

    agent = session_data["agent"]
    config = session_data["config"]

    # Resume the agent with the user's decision
    # deepagents expects {"decisions": [{"type": "approve"|"reject", ...}]}
    await agent.ainvoke(
        Command(resume={"decisions": [{"type": decision}]}),
        config=config,
    )

    return JSONResponse({"status": decision + "d"})
