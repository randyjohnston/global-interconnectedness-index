from pydantic import BaseModel


class FlightRoute(BaseModel):
    """Aggregated flight route count between two countries."""

    country_a: str
    country_b: str
    period: str
    route_count: int = 0
