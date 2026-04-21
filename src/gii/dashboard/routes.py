"""Dashboard HTML routes — serves Jinja2 templates with HTMX."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from gii.api.dependencies import get_db, get_repo

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

    return templates.TemplateResponse(request, "partials/score_card.html", {
        "snapshot": snapshot,
        "narrative": narrative,
    })
