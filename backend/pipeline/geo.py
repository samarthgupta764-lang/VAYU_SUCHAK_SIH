"""
City <-> IATA and rough route distances. One source of truth, shared by the
scrapers, the base-reference builder, the cache seeder and ML feature building.
"""

from __future__ import annotations

import re

CITY_TO_IATA: dict[str, str] = {
    "DELHI": "DEL", "NEW DELHI": "DEL",
    "MUMBAI": "BOM", "BOMBAY": "BOM", "NAVI MUMBAI": "BOM",
    "BENGALURU": "BLR", "BANGALORE": "BLR",
    "KOLKATA": "CCU", "CALCUTTA": "CCU",
    "CHENNAI": "MAA", "MADRAS": "MAA",
    "HYDERABAD": "HYD",
    "GUWAHATI": "GAU",
    "AHMEDABAD": "AMD", "PUNE": "PNQ",
    "GOA": "GOI", "DABOLIM": "GOI", "MOPA": "GOI",
    "COCHIN": "COK", "KOCHI": "COK",
    "JAIPUR": "JAI", "LUCKNOW": "LKO", "PATNA": "PAT",
    "THIRUVANANTHAPURAM": "TRV", "TRIVANDRUM": "TRV",
    "SRINAGAR": "SXR", "NAGPUR": "NAG", "INDORE": "IDR",
    "BHUBANESWAR": "BBI", "RAIPUR": "RPR", "RANCHI": "IXR",
    "VARANASI": "VNS", "AMRITSAR": "ATQ", "CHANDIGARH": "IXC",
    "COIMBATORE": "CJB", "VISAKHAPATNAM": "VTZ", "VIJAYAWADA": "VGA",
    "MANGALORE": "IXE", "MADURAI": "IXM", "TIRUCHIRAPALLI": "TRZ",
    "PORT BLAIR": "IXZ", "LEH": "IXL", "DEHRADUN": "DED",
    "IMPHAL": "IMF", "AGARTALA": "IXA", "DIBRUGARH": "DIB",
    "BAGDOGRA": "IXB", "SILCHAR": "IXS", "JAMMU": "IXJ",
}

_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

# second/third airports that serve the same metro — a DEL→NMI (Navi Mumbai) fare
# is a Delhi–Mumbai fare for index purposes. Maps the alt airport to the metro.
AIRPORT_TO_METRO: dict[str, str] = {
    "NMI": "BOM",           # Navi Mumbai
    "DXN": "DEL",           # Noida (Jewar)
    "HDO": "DEL",           # Hindon (Ghaziabad)
}


def metro(code: str) -> str:
    """Airport IATA -> the metro code the index groups it under."""
    c = str(code).strip().upper()
    return AIRPORT_TO_METRO.get(c, c)


# Indian scheduled domestic carriers — the index is a *domestic* airfare index,
# so a Google-Flights routing on Emirates / SriLankan / Thai is dropped.
DOMESTIC_CARRIERS: frozenset[str] = frozenset({
    "6E",   # IndiGo
    "AI",   # Air India
    "IX",   # Air India Express
    "QP",   # Akasa Air
    "SG",   # SpiceJet
    "UK",   # Vistara (merged into AI, still on old tickets)
    "S5",   # Star Air
    "9I",   # Alliance Air
    "I5",   # AIX Connect (ex-AirAsia India, merged)
    "2T",   # TruJet
})


def is_domestic_carrier(code: str) -> bool:
    return str(code).strip().upper() in DOMESTIC_CARRIERS


def same_metro(a: str, b: str) -> bool:
    return metro(a) == metro(b)


def city_to_iata(city: str) -> str | None:
    c = str(city).strip().upper()
    if c in CITY_TO_IATA:
        return CITY_TO_IATA[c]
    return CITY_TO_IATA.get(_PAREN.sub("", c).strip())


def route_key(a: str, b: str) -> str | None:
    """Two city names -> 'DEL-BOM' (directed). None if either is unknown or equal."""
    ia, ib = city_to_iata(a), city_to_iata(b)
    if not (ia and ib) or ia == ib:
        return None
    return f"{ia}-{ib}"


def undirected(route: str) -> str:
    a, b = route.split("-")
    return "-".join(sorted((a, b)))


# rough great-circle distances (km) — feeds price-per-km without an airports DB
ROUTE_KM: dict[str, int] = {
    "DEL-BOM": 1140, "DEL-BLR": 1710, "DEL-CCU": 1300, "DEL-MAA": 1760,
    "DEL-HYD": 1260, "DEL-GAU": 1420, "DEL-AMD": 780, "DEL-PNQ": 1170,
    "DEL-GOI": 1520, "DEL-COK": 2060, "DEL-JAI": 240, "DEL-LKO": 420,
    "BOM-BLR": 840, "BOM-CCU": 1650, "BOM-MAA": 1030, "BOM-HYD": 620,
    "BOM-GOI": 430, "BOM-AMD": 440, "BOM-COK": 1080, "BOM-PNQ": 120,
    "BLR-CCU": 1560, "BLR-MAA": 290, "BLR-HYD": 500, "BLR-COK": 360,
    "BLR-GOI": 480, "CCU-MAA": 1360, "CCU-HYD": 1180, "CCU-GAU": 530,
    "MAA-HYD": 520, "MAA-COK": 500, "HYD-GOI": 570,
}


def route_km(route: str) -> int | None:
    return ROUTE_KM.get(undirected(route)) or ROUTE_KM.get(route.upper())
