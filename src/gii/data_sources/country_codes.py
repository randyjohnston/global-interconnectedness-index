"""ISO-3166 country code mapping utilities.

Maps between ISO3, ISO2, and various source-specific identifiers
(Comtrade numeric codes, FIPS codes used by GDELT, etc.).
"""

# GDELT uses FIPS 10-4 codes — map to ISO3
FIPS_TO_ISO3: dict[str, str] = {
    "US": "USA", "CH": "CHN", "GM": "DEU", "JA": "JPN", "UK": "GBR",
    "FR": "FRA", "IN": "IND", "IT": "ITA", "BR": "BRA", "CA": "CAN",
    "KS": "KOR", "RS": "RUS", "AS": "AUS", "SP": "ESP", "MX": "MEX",
    "ID": "IDN", "NL": "NLD", "SA": "SAU", "TU": "TUR", "SZ": "CHE",
    "PL": "POL", "SW": "SWE", "BE": "BEL", "TH": "THA", "AR": "ARG",
    "NI": "NGA", "AU": "AUT", "NO": "NOR", "AE": "ARE", "IS": "ISR",
    "SN": "SGP", "MY": "MYS", "RP": "PHL", "SF": "ZAF", "CO": "COL",
    "EG": "EGY", "VM": "VNM", "CI": "CHL", "EI": "IRL", "DA": "DNK",
    "FI": "FIN", "PO": "PRT", "EZ": "CZE", "NZ": "NZL", "GR": "GRC",
    "PE": "PER", "KE": "KEN", "PK": "PAK", "BG": "BGD", "TW": "TWN",
}

ISO3_TO_FIPS: dict[str, str] = {v: k for k, v in FIPS_TO_ISO3.items()}

# Comtrade uses ISO3 numeric codes
ISO3_TO_COMTRADE_NUMERIC: dict[str, int] = {
    "USA": 842, "CHN": 156, "DEU": 276, "JPN": 392, "GBR": 826,
    "FRA": 250, "IND": 356, "ITA": 380, "BRA": 76, "CAN": 124,
    "KOR": 410, "RUS": 643, "AUS": 36, "ESP": 724, "MEX": 484,
    "IDN": 360, "NLD": 528, "SAU": 682, "TUR": 792, "CHE": 756,
    "POL": 616, "SWE": 752, "BEL": 330, "THA": 764, "ARG": 32,
    "NGA": 566, "AUT": 40, "NOR": 578, "ARE": 784, "ISR": 376,
    "SGP": 702, "MYS": 458, "PHL": 608, "ZAF": 710, "COL": 170,
    "EGY": 818, "VNM": 704, "CHL": 152, "IRL": 372, "DNK": 208,
    "FIN": 246, "PRT": 620, "CZE": 203, "NZL": 554, "GRC": 300,
    "PER": 604, "KEN": 404, "PAK": 586, "BGD": 50, "TWN": 490,
}

COMTRADE_NUMERIC_TO_ISO3: dict[int, str] = {v: k for k, v in ISO3_TO_COMTRADE_NUMERIC.items()}

# ISO2 to ISO3
ISO2_TO_ISO3: dict[str, str] = {
    "US": "USA", "CN": "CHN", "DE": "DEU", "JP": "JPN", "GB": "GBR",
    "FR": "FRA", "IN": "IND", "IT": "ITA", "BR": "BRA", "CA": "CAN",
    "KR": "KOR", "RU": "RUS", "AU": "AUS", "ES": "ESP", "MX": "MEX",
    "ID": "IDN", "NL": "NLD", "SA": "SAU", "TR": "TUR", "CH": "CHE",
    "PL": "POL", "SE": "SWE", "BE": "BEL", "TH": "THA", "AR": "ARG",
    "NG": "NGA", "AT": "AUT", "NO": "NOR", "AE": "ARE", "IL": "ISR",
    "SG": "SGP", "MY": "MYS", "PH": "PHL", "ZA": "ZAF", "CO": "COL",
    "EG": "EGY", "VN": "VNM", "CL": "CHL", "IE": "IRL", "DK": "DNK",
    "FI": "FIN", "PT": "PRT", "CZ": "CZE", "NZ": "NZL", "GR": "GRC",
    "PE": "PER", "KE": "KEN", "PK": "PAK", "BD": "BGD", "TW": "TWN",
}

ISO3_TO_ISO2: dict[str, str] = {v: k for k, v in ISO2_TO_ISO3.items()}


def fips_to_iso3(fips: str) -> str | None:
    """Convert a GDELT FIPS code to ISO3."""
    return FIPS_TO_ISO3.get(fips.upper())


def iso2_to_iso3(iso2: str) -> str | None:
    """Convert ISO2 to ISO3."""
    return ISO2_TO_ISO3.get(iso2.upper())


def comtrade_numeric_to_iso3(code: int) -> str | None:
    """Convert Comtrade numeric code to ISO3."""
    return COMTRADE_NUMERIC_TO_ISO3.get(code)
