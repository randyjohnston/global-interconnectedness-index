from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from gii.models.country import CountryPair
from gii.models.geopolitics import CooperationScore
from gii.models.trade import BilateralTrade
from gii.models.travel import FlightRoute
from gii.storage.models import (
    BilateralTradeRow,
    CountryRow,
    FlightConnectivityRow,
    GeopoliticsScoreRow,
    IndexSnapshotRow,
    NarrativeReportRow,
)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # --- Countries ---

    def upsert_country(self, iso3: str, iso2: str, name: str, region: str = "") -> None:
        stmt = pg_insert(CountryRow).values(
            iso3=iso3, iso2=iso2, name=name, region=region
        ).on_conflict_do_update(
            index_elements=["iso3"],
            set_={"iso2": iso2, "name": name, "region": region},
        )
        self.session.execute(stmt)

    def list_countries(self) -> list[CountryRow]:
        return list(self.session.scalars(select(CountryRow).order_by(CountryRow.name)))

    # --- Trade ---

    def upsert_trade(self, trade: BilateralTrade) -> None:
        pair = CountryPair.create(trade.country_a, trade.country_b)
        # Flip export values if pair was reordered
        if pair.country_a == trade.country_a:
            a_to_b, b_to_a = trade.exports_a_to_b, trade.exports_b_to_a
        else:
            a_to_b, b_to_a = trade.exports_b_to_a, trade.exports_a_to_b
        stmt = pg_insert(BilateralTradeRow).values(
            country_a=pair.country_a, country_b=pair.country_b, period=trade.period,
            exports_a_to_b=a_to_b, exports_b_to_a=b_to_a,
            total_bilateral=a_to_b + b_to_a,
        ).on_conflict_do_update(
            index_elements=["country_a", "country_b", "period"],
            set_={"exports_a_to_b": a_to_b, "exports_b_to_a": b_to_a, "total_bilateral": a_to_b + b_to_a},
        )
        self.session.execute(stmt)

    def get_trade(self, period: str) -> list[BilateralTradeRow]:
        return list(self.session.scalars(
            select(BilateralTradeRow).where(BilateralTradeRow.period == period)
        ))

    # --- Flights ---

    def upsert_flights(self, route: FlightRoute) -> None:
        pair = CountryPair.create(route.country_a, route.country_b)
        stmt = pg_insert(FlightConnectivityRow).values(
            country_a=pair.country_a, country_b=pair.country_b,
            period=route.period, route_count=route.route_count,
        ).on_conflict_do_update(
            index_elements=["country_a", "country_b", "period"],
            set_={"route_count": route.route_count},
        )
        self.session.execute(stmt)

    def get_flights(self, period: str) -> list[FlightConnectivityRow]:
        return list(self.session.scalars(
            select(FlightConnectivityRow).where(FlightConnectivityRow.period == period)
        ))

    # --- Geopolitics ---

    def upsert_geopolitics(self, score: CooperationScore) -> None:
        pair = CountryPair.create(score.country_a, score.country_b)
        stmt = pg_insert(GeopoliticsScoreRow).values(
            country_a=pair.country_a, country_b=pair.country_b, period=score.period,
            avg_goldstein=score.avg_goldstein, cooperative_ratio=score.cooperative_ratio,
            event_count=score.event_count,
        ).on_conflict_do_update(
            index_elements=["country_a", "country_b", "period"],
            set_={
                "avg_goldstein": score.avg_goldstein,
                "cooperative_ratio": score.cooperative_ratio,
                "event_count": score.event_count,
            },
        )
        self.session.execute(stmt)

    def get_geopolitics(self, period: str) -> list[GeopoliticsScoreRow]:
        return list(self.session.scalars(
            select(GeopoliticsScoreRow).where(GeopoliticsScoreRow.period == period)
        ))

    # --- Index Snapshots ---

    def upsert_snapshot(self, **kwargs) -> None:
        stmt = pg_insert(IndexSnapshotRow).values(**kwargs).on_conflict_do_update(
            index_elements=["country_a", "country_b", "period"],
            set_={k: v for k, v in kwargs.items() if k not in ("country_a", "country_b", "period")},
        )
        self.session.execute(stmt)

    def get_snapshots(self, period: str) -> list[IndexSnapshotRow]:
        return list(self.session.scalars(
            select(IndexSnapshotRow).where(IndexSnapshotRow.period == period)
            .order_by(IndexSnapshotRow.composite_score.desc())
        ))

    def get_pair_history(self, country_a: str, country_b: str) -> list[IndexSnapshotRow]:
        pair = CountryPair.create(country_a, country_b)
        return list(self.session.scalars(
            select(IndexSnapshotRow)
            .where(IndexSnapshotRow.country_a == pair.country_a)
            .where(IndexSnapshotRow.country_b == pair.country_b)
            .order_by(IndexSnapshotRow.period)
        ))

    # --- Narratives ---

    def save_narrative(self, country_a: str, country_b: str, period: str, text: str) -> None:
        self.session.add(NarrativeReportRow(
            country_a=country_a, country_b=country_b, period=period, narrative_text=text,
        ))

    def commit(self) -> None:
        self.session.commit()
