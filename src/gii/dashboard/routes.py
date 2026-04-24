"""Dashboard HTML routes — serves Jinja2 templates with HTMX."""

import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from gii.api.dependencies import get_db, get_repo

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
def dashboard_home(request: Request, period: str = Query("2025"), session: Session = Depends(get_db)):
    repo = get_repo(session)
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
def rankings_page(request: Request, period: str = Query("2025"), session: Session = Depends(get_db)):
    repo = get_repo(session)
    snapshots = repo.get_snapshots(period)

    # Aggregate by country
    country_scores: dict[str, list[float]] = {}
    for s in snapshots:
        country_scores.setdefault(s.country_a, []).append(s.composite_score)
        country_scores.setdefault(s.country_b, []).append(s.composite_score)

    rankings = [
        {"country": c, "avg_score": round(sum(scores) / len(scores), 2), "pair_count": len(scores)}
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
    snapshot = next((s for s in snapshots if s.country_a == pair.country_a and s.country_b == pair.country_b), None)
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
    from gii.config import settings
    from gii.models.country import CountryPair
    from gii.storage.database import get_session
    from gii.storage.repository import Repository

    pair = CountryPair.create(country_a, country_b)

    async def event_generator():
        if not settings.nvidia_api_key:
            yield {"event": "error", "data": "NVIDIA API key not configured"}
            return

        session = get_session()
        repo = Repository(session)
        countries = {c.iso3: c.name for c in repo.list_countries()}
        name_a = countries.get(pair.country_a, pair.country_a)
        name_b = countries.get(pair.country_b, pair.country_b)

        agent = build_agent()
        full_text = ""
        # Track each LLM call: buffer text, flush only if no tool calls
        current_call_text = ""
        current_call_has_tools = False

        try:
            yield {"event": "status", "data": json.dumps({"text": "Agent gathering data..."})}

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
                config={
                    "run_name": "generate_narrative",
                    "tags": ["ui"],
                    "metadata": {"country_a": pair.country_a, "country_b": pair.country_b, "period": period},
                },
            ):
                kind = event.get("event")

                if kind == "on_chat_model_start":
                    # New LLM call starting — reset per-call tracking
                    current_call_text = ""
                    current_call_has_tools = False

                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if not chunk:
                        continue
                    # If this chunk contains tool calls, mark the call as tool-calling
                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        current_call_has_tools = True
                    # Buffer text content
                    if hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                        current_call_text += chunk.content
                        # Only stream if this call hasn't made tool calls
                        if not current_call_has_tools:
                            full_text += chunk.content
                            yield {"event": "token", "data": json.dumps({"token": chunk.content})}

                elif kind == "on_chat_model_end":
                    if current_call_has_tools and current_call_text:
                        # This was a tool-calling round that also had text — don't include
                        pass
                    elif current_call_has_tools:
                        yield {"event": "status", "data": json.dumps({"text": "Writing narrative..."})}

            # Save completed narrative to DB
            if full_text.strip():
                repo.save_narrative(pair.country_a, pair.country_b, period, full_text)
                repo.commit()

            yield {"event": "done", "data": json.dumps({"success": True})}

        except Exception as e:
            logger.error(f"Narrative stream failed for {pair.country_a}-{pair.country_b}: {e}")
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
        finally:
            session.close()

    return EventSourceResponse(event_generator())
