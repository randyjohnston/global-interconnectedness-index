from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CountryRow(Base):
    __tablename__ = "countries"
    __table_args__ = {'schema': 'gii'}

    iso3: Mapped[str] = mapped_column(String(3), primary_key=True)
    iso2: Mapped[str] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(50), default="")


class BilateralTradeRow(Base):
    __tablename__ = "bilateral_trade"
    __table_args__ = (
        UniqueConstraint("country_a", "country_b", "period"),
        CheckConstraint("country_a < country_b"),
        {'schema': 'gii'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_a: Mapped[str] = mapped_column(String(3))
    country_b: Mapped[str] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(10))
    exports_a_to_b: Mapped[float] = mapped_column(Float, default=0.0)
    exports_b_to_a: Mapped[float] = mapped_column(Float, default=0.0)
    total_bilateral: Mapped[float] = mapped_column(Float, default=0.0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FlightConnectivityRow(Base):
    __tablename__ = "flight_connectivity"
    __table_args__ = (
        UniqueConstraint("country_a", "country_b", "period"),
        CheckConstraint("country_a < country_b"),
        {'schema': 'gii'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_a: Mapped[str] = mapped_column(String(3))
    country_b: Mapped[str] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(10))
    route_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GeopoliticsScoreRow(Base):
    __tablename__ = "geopolitics_scores"
    __table_args__ = (
        UniqueConstraint("country_a", "country_b", "period"),
        CheckConstraint("country_a < country_b"),
        {'schema': 'gii'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_a: Mapped[str] = mapped_column(String(3))
    country_b: Mapped[str] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(10))
    avg_goldstein: Mapped[float] = mapped_column(Float, default=0.0)
    cooperative_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IndexSnapshotRow(Base):
    __tablename__ = "index_snapshots"
    __table_args__ = (
        UniqueConstraint("country_a", "country_b", "period"),
        CheckConstraint("country_a < country_b"),
        {'schema': 'gii'}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_a: Mapped[str] = mapped_column(String(3))
    country_b: Mapped[str] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(10))
    # Trade pillar
    trade_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_log: Mapped[float | None] = mapped_column(Float, nullable=True)
    trade_normalized: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Travel pillar
    travel_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    travel_normalized: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Geopolitics pillar
    geopolitics_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    geopolitics_normalized: Mapped[float | None] = mapped_column(Float, nullable=True)
    geopolitics_avg_goldstein: Mapped[float | None] = mapped_column(Float, nullable=True)
    geopolitics_cooperative_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    geopolitics_event_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    coverage: Mapped[str] = mapped_column(String(50), default="")  # comma-separated
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class QualityReportRow(Base):
    __tablename__ = "quality_reports"
    __table_args__ = {'schema': 'gii'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_period: Mapped[str] = mapped_column(String(10))
    findings: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NarrativeReportRow(Base):
    __tablename__ = "narrative_reports"
    __table_args__ = {'schema': 'gii'}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_a: Mapped[str] = mapped_column(String(3))
    country_b: Mapped[str] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(10))
    narrative_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
