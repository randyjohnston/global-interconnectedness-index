"""Seed the countries table with major trading nations."""

from gii.storage.database import get_session
from gii.storage.repository import Repository

# Top ~50 countries by trade volume + geopolitical significance
COUNTRIES = [
    ("USA", "US", "United States", "Americas"),
    ("CHN", "CN", "China", "Asia"),
    ("DEU", "DE", "Germany", "Europe"),
    ("JPN", "JP", "Japan", "Asia"),
    ("GBR", "GB", "United Kingdom", "Europe"),
    ("FRA", "FR", "France", "Europe"),
    ("IND", "IN", "India", "Asia"),
    ("ITA", "IT", "Italy", "Europe"),
    ("BRA", "BR", "Brazil", "Americas"),
    ("CAN", "CA", "Canada", "Americas"),
    ("KOR", "KR", "South Korea", "Asia"),
    ("RUS", "RU", "Russia", "Europe"),
    ("AUS", "AU", "Australia", "Oceania"),
    ("ESP", "ES", "Spain", "Europe"),
    ("MEX", "MX", "Mexico", "Americas"),
    ("IDN", "ID", "Indonesia", "Asia"),
    ("NLD", "NL", "Netherlands", "Europe"),
    ("SAU", "SA", "Saudi Arabia", "Middle East"),
    ("TUR", "TR", "Turkey", "Europe"),
    ("CHE", "CH", "Switzerland", "Europe"),
    ("POL", "PL", "Poland", "Europe"),
    ("SWE", "SE", "Sweden", "Europe"),
    ("BEL", "BE", "Belgium", "Europe"),
    ("THA", "TH", "Thailand", "Asia"),
    ("ARG", "AR", "Argentina", "Americas"),
    ("NGA", "NG", "Nigeria", "Africa"),
    ("AUT", "AT", "Austria", "Europe"),
    ("NOR", "NO", "Norway", "Europe"),
    ("ARE", "AE", "United Arab Emirates", "Middle East"),
    ("ISR", "IL", "Israel", "Middle East"),
    ("SGP", "SG", "Singapore", "Asia"),
    ("MYS", "MY", "Malaysia", "Asia"),
    ("PHL", "PH", "Philippines", "Asia"),
    ("ZAF", "ZA", "South Africa", "Africa"),
    ("COL", "CO", "Colombia", "Americas"),
    ("EGY", "EG", "Egypt", "Africa"),
    ("VNM", "VN", "Vietnam", "Asia"),
    ("CHL", "CL", "Chile", "Americas"),
    ("IRL", "IE", "Ireland", "Europe"),
    ("DNK", "DK", "Denmark", "Europe"),
    ("FIN", "FI", "Finland", "Europe"),
    ("PRT", "PT", "Portugal", "Europe"),
    ("CZE", "CZ", "Czech Republic", "Europe"),
    ("NZL", "NZ", "New Zealand", "Oceania"),
    ("GRC", "GR", "Greece", "Europe"),
    ("PER", "PE", "Peru", "Americas"),
    ("KEN", "KE", "Kenya", "Africa"),
    ("PAK", "PK", "Pakistan", "Asia"),
    ("BGD", "BD", "Bangladesh", "Asia"),
    ("TWN", "TW", "Taiwan", "Asia"),
]


def main():
    session = get_session()
    repo = Repository(session)
    for iso3, iso2, name, region in COUNTRIES:
        repo.upsert_country(iso3, iso2, name, region)
    repo.commit()
    session.close()
    print(f"Seeded {len(COUNTRIES)} countries.")


if __name__ == "__main__":
    main()
