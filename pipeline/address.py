"""Standardized facility addresses for the members' map. Runs on private data only.

CDSS rewords addresses from week to week (STREET vs ST, NORTH vs N, extra spaces), so the map keys
each location on a standardized form. An address that only changed wording keeps the same key and is
never geocoded again.

Nothing here is ever written to site/: street addresses stay out of the public Market Watch files.
"""
import re
from dataclasses import dataclass

# USPS street suffix abbreviations for the words CDSS spells both ways.
SUFFIXES = {
    "ALLEY": "ALY", "AVENUE": "AVE", "AV": "AVE", "BOULEVARD": "BLVD", "CIRCLE": "CIR", "COURT": "CT",
    "COVE": "CV", "CRESCENT": "CRES", "DRIVE": "DR", "EXPRESSWAY": "EXPY", "FREEWAY": "FWY", "HIGHWAY": "HWY",
    "LANE": "LN", "LOOP": "LOOP", "PARKWAY": "PKWY", "PLACE": "PL", "PLAZA": "PLZ", "POINT": "PT", "ROAD": "RD",
    "SQUARE": "SQ", "STREET": "ST", "TERRACE": "TER", "TRAIL": "TRL", "WAY": "WAY", "CROSSING": "XING",
    "RIDGE": "RDG", "VIEW": "VW", "VISTA": "VIS", "HEIGHTS": "HTS", "GLEN": "GLN", "GROVE": "GRV",
    "MEADOW": "MDW", "MEADOWS": "MDWS", "PARK": "PARK", "PATH": "PATH", "RUN": "RUN", "WALK": "WALK",
    "KEY": "KY",
}
# Words inside a street name that CDSS spells both ways ("MT SHERROD" / "MOUNT SHERROD").
NAME_WORDS = {"MOUNT": "MT", "SAINT": "ST", "FORT": "FT"}
# A spelled-out house number ("ONE AVALON AVE").
NUMBER_WORDS = {"ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5"}
DIRECTIONS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
              "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW"}
UNIT_WORDS = {"APT", "APARTMENT", "UNIT", "STE", "SUITE", "BLDG", "BUILDING", "SPC", "SPACE", "RM", "ROOM", "FL",
              "FLOOR", "LOT", "#"}
UNIT_ABBREV = {"APARTMENT": "APT", "SUITE": "STE", "BUILDING": "BLDG", "SPACE": "SPC", "ROOM": "RM", "FLOOR": "FL"}


@dataclass(frozen=True)
class Address:
    street: str   # standardized street line without the unit, e.g. "123 N MAIN ST"
    unit: str     # e.g. "STE 2", or ""
    city: str
    zip5: str

    @property
    def key(self) -> str:
        """The cache key: one per physical street address. Units share their building's location."""
        return f"{self.street}|{self.city}|{self.zip5}" if self.street and self.city else ""

    @property
    def one_line(self) -> str:
        line = f"{self.street} {self.unit}".strip()
        return ", ".join(p for p in (line, self.city, f"CA {self.zip5}".strip()) if p)


def _tokens(text):
    text = (text or "").upper().replace("#", " # ")
    # Keep letters, digits, slashes in fractions and hyphens in house numbers; everything else is a space.
    text = re.sub(r"[^A-Z0-9/#\- ]", " ", text)
    return [t for t in text.split() if t != "-"]


def _split_unit(tokens):
    """(street tokens, unit tokens): the unit is the first unit word and what follows it."""
    for i, t in enumerate(tokens):
        if t in UNIT_WORDS and i > 0:
            return tokens[:i], tokens[i:]
    return tokens, []


def standardize_street(raw):
    """(street, unit) in USPS-style abbreviations."""
    street, unit = _split_unit(_tokens(raw))
    out = []
    for i, t in enumerate(street):
        last = i == len(street) - 1
        if i == 0 and t in NUMBER_WORDS:
            out.append(NUMBER_WORDS[t])
            continue
        if not last and t in NAME_WORDS:
            out.append(NAME_WORDS[t])
            continue
        # Directions are abbreviated only before a street name or after one at the very end, so a street
        # named for a direction (e.g. "123 NORTH ST") keeps its name.
        if t in DIRECTIONS and ((i == 1 and len(street) >= 4) or (last and i > 2)):
            t = DIRECTIONS[t]
        elif last and t in SUFFIXES:
            t = SUFFIXES[t]
        elif not last and t in SUFFIXES and i + 1 < len(street) and street[i + 1] in DIRECTIONS and i + 2 == len(street):
            # "MAIN STREET NORTH": the suffix sits before a trailing direction.
            t = SUFFIXES[t]
        out.append(t)
    unit_out = []
    for t in unit:
        unit_out.append(UNIT_ABBREV.get(t, t))
    unit_text = " ".join(unit_out).replace("# ", "#")
    return " ".join(out), unit_text


def standardize(address, city, zip_code) -> Address:
    street, unit = standardize_street(address)
    city_std = " ".join(_tokens(city))
    zip_match = re.match(r"\s*(\d{5})", zip_code or "")
    return Address(street, unit, city_std, zip_match.group(1) if zip_match else "")


def from_row(row) -> Address:
    return standardize(row.get("Facility Address"), row.get("Facility City"), row.get("Facility Zip"))
