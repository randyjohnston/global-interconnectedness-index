from pydantic import BaseModel


class FlightRoute(BaseModel):
    """Aggregated flight route count between two countries."""

    country_a: str
    country_b: str
    period: str
    route_count: int = 0


class VisitorFlow(BaseModel):
    """Tourist/visitor flow from origin to destination."""

    origin: str
    destination: str
    period: str
    visitor_count: int = 0
