from pydantic import BaseModel


class Country(BaseModel):
    iso3: str
    iso2: str
    name: str
    region: str = ""


class CountryPair(BaseModel):
    """Canonical country pair with country_a < country_b (ISO3 alphabetical)."""

    country_a: str
    country_b: str

    @classmethod
    def create(cls, code1: str, code2: str) -> "CountryPair":
        a, b = sorted([code1.upper(), code2.upper()])
        return cls(country_a=a, country_b=b)
