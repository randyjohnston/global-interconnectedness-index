"""Index score endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gii.api.dependencies import get_db, get_repo
from gii.api.schemas import PairScoreResponse, RankingEntry, SubIndexResponse
from gii.storage.models import CountryRow, IndexSnapshotRow

router = APIRouter(prefix="/api/index", tags=["index"])


@router.get("/scores", response_model=list[PairScoreResponse])
def list_scores(
    period: str = Query(..., description="Period to query, e.g. '2025'"),
    country: str | None = Query(None, description="Filter by country ISO3"),
    min_score: float | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    session: Session = Depends(get_db),
):
    repo = get_repo(session)
    snapshots = repo.get_snapshots(period)

    results = []
    for s in snapshots:
        if country and country.upper() not in (s.country_a, s.country_b):
            continue
        if min_score and s.composite_score < min_score:
            continue
        results.append(_snapshot_to_response(s))

    return results[offset : offset + limit]


@router.get("/scores/{country_a}/{country_b}", response_model=list[PairScoreResponse])
def get_pair_history(
    country_a: str,
    country_b: str,
    session: Session = Depends(get_db),
):
    repo = get_repo(session)
    history = repo.get_pair_history(country_a, country_b)
    return [_snapshot_to_response(s) for s in history]


@router.get("/rankings", response_model=list[RankingEntry])
def get_rankings(
    period: str = Query(...),
    limit: int = Query(50, le=200),
    session: Session = Depends(get_db),
):
    """Rank countries by average composite score across all their pairs."""
    # Query average composite score per country
    stmt_a = (
        select(
            IndexSnapshotRow.country_a.label("country"),
            func.avg(IndexSnapshotRow.composite_score).label("avg_score"),
            func.count().label("pair_count"),
        )
        .where(IndexSnapshotRow.period == period)
        .group_by(IndexSnapshotRow.country_a)
    )
    stmt_b = (
        select(
            IndexSnapshotRow.country_b.label("country"),
            func.avg(IndexSnapshotRow.composite_score).label("avg_score"),
            func.count().label("pair_count"),
        )
        .where(IndexSnapshotRow.period == period)
        .group_by(IndexSnapshotRow.country_b)
    )

    rows_a = session.execute(stmt_a).all()
    rows_b = session.execute(stmt_b).all()

    # Merge both sides
    country_data: dict[str, dict] = {}
    for row in [*rows_a, *rows_b]:
        c = row.country
        if c not in country_data:
            country_data[c] = {"total_score": 0.0, "total_pairs": 0}
        country_data[c]["total_score"] += row.avg_score * row.pair_count
        country_data[c]["total_pairs"] += row.pair_count

    # Get country names
    country_names = {
        r.iso3: r.name
        for r in session.scalars(select(CountryRow))
    }

    rankings = []
    for c, d in country_data.items():
        if d["total_pairs"] == 0:
            continue
        rankings.append(RankingEntry(
            country=c,
            country_name=country_names.get(c, c),
            avg_score=round(d["total_score"] / d["total_pairs"], 2),
            pair_count=d["total_pairs"],
        ))

    rankings.sort(key=lambda r: r.avg_score, reverse=True)
    return rankings[:limit]


@router.get("/rankings/{country}", response_model=list[PairScoreResponse])
def get_country_partners(
    country: str,
    period: str = Query(...),
    limit: int = Query(20, le=100),
    session: Session = Depends(get_db),
):
    """Get a country's top partners by composite score."""
    repo = get_repo(session)
    snapshots = repo.get_snapshots(period)

    results = [
        _snapshot_to_response(s)
        for s in snapshots
        if country.upper() in (s.country_a, s.country_b)
    ]
    return results[:limit]


def _snapshot_to_response(s: IndexSnapshotRow) -> PairScoreResponse:
    coverage = s.coverage.split(",") if s.coverage else []
    return PairScoreResponse(
        country_a=s.country_a,
        country_b=s.country_b,
        period=s.period,
        trade=SubIndexResponse(pillar="trade", raw_value=s.trade_raw, normalized_value=s.trade_normalized) if s.trade_normalized is not None else None,
        travel=SubIndexResponse(pillar="travel", raw_value=s.travel_raw, normalized_value=s.travel_normalized) if s.travel_normalized is not None else None,
        geopolitics=SubIndexResponse(pillar="geopolitics", raw_value=s.geopolitics_raw, normalized_value=s.geopolitics_normalized) if s.geopolitics_normalized is not None else None,
        composite_score=s.composite_score,
        coverage=coverage,
    )
