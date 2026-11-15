import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

type MeasureSystem = Literal["uk", "us", "au"]


class BaseUnit(StrEnum):
    GRAMS = "g"
    MILLILITRES = "ml"


class Amount(BaseModel):
    """
    A parsed quantity in base units: grams, millilitres, or a plain count when unit is None.

    A single value has minimum == maximum.
    """

    model_config = ConfigDict(frozen=True)

    minimum: float
    maximum: float
    unit: BaseUnit | None


UNICODE_FRACTIONS = {
    "½": "1/2",
    "⅓": "1/3",
    "⅔": "2/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅕": "1/5",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}

FIXED_UNITS: dict[str, tuple[BaseUnit, float]] = {
    "g": (BaseUnit.GRAMS, 1.0),
    "kg": (BaseUnit.GRAMS, 1000.0),
    "oz": (BaseUnit.GRAMS, 28.349523125),
    "lb": (BaseUnit.GRAMS, 453.59237),
    "stick": (BaseUnit.GRAMS, 113.0),
    "ml": (BaseUnit.MILLILITRES, 1.0),
    "l": (BaseUnit.MILLILITRES, 1000.0),
    "tsp": (BaseUnit.MILLILITRES, 5.0),
}

SYSTEM_UNITS: dict[str, dict[MeasureSystem, float]] = {
    "tbsp": {"uk": 15.0, "us": 15.0, "au": 20.0},
    "cup": {"uk": 250.0, "us": 240.0, "au": 250.0},
    "pint": {"uk": 568.26, "us": 473.18, "au": 570.0},
    "fl oz": {"uk": 28.41, "us": 29.57, "au": 28.41},
}

UNIT_ALIASES = {
    "g": "g",
    "gr": "g",
    "gram": "g",
    "grams": "g",
    "gramme": "g",
    "grammes": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "stick": "stick",
    "sticks": "stick",
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "tsp": "tsp",
    "tsps": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tbsp": "tbsp",
    "tbsps": "tbsp",
    "tbs": "tbsp",
    "tbl": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "pint": "pint",
    "pints": "pint",
    "pt": "pint",
    "fl oz": "fl oz",
    "floz": "fl oz",
    "fluid ounce": "fl oz",
    "fluid ounces": "fl oz",
}

NUMBER = r"\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?"
QUANTITY_PART = re.compile(
    rf"""^
    (?:(?:about|approx\.?|approximately|around|roughly|c\.|~)\s*)?
    (?P<low>{NUMBER})
    (?:\s*(?:-|–|—|to)\s*(?P<high>{NUMBER}))?
    \s*
    (?:(?:heaped|heaping|level|rounded|scant|generous)\s+)?
    (?P<rest>.*)
    $""",
    re.IGNORECASE | re.VERBOSE,
)
LENGTH_WORDS = {"cm", "mm", "inch", "inches", "in", '"'}
BRACKETED = re.compile(r"\(([^)]*)\)")
MULTIPLIED = re.compile(r"^(?P<count>\d+)\s*[x×]\s*(?P<each>.+)$", re.IGNORECASE)
UNIT_WORD = re.compile(r"^(fl\.?\s*oz|fluid\s+ounces?|[a-z]+)\.?(?=\s|$)", re.IGNORECASE)


def number_value(text: str) -> float:
    """Read an integer, decimal, fraction (1/2) or mixed number (1 1/2)."""
    whole, _, fraction = text.strip().rpartition(" ")
    if "/" in fraction:
        numerator, denominator = fraction.split("/")
        value = int(numerator) / int(denominator)
        return value + (int(whole) if whole else 0)
    return float(text)


def parse_part(text: str, system: MeasureSystem) -> Amount | None:
    multiplied = MULTIPLIED.match(text)
    if multiplied:
        count = int(multiplied["count"])
        each = parse_part(multiplied["each"], system)
        if each is None or each.unit is None:
            return Amount(minimum=count, maximum=count, unit=None)
        return Amount(minimum=each.minimum * count, maximum=each.maximum * count, unit=each.unit)

    match = QUANTITY_PART.match(text.strip())
    if match is None:
        return None
    low = number_value(match["low"])
    high = number_value(match["high"]) if match["high"] else low
    if high < low and high < 1:
        low, high = low + high, low + high
    elif high < low:
        return None

    rest = match["rest"]
    if rest.startswith('"') or rest.split(" ", 1)[0].lower() in LENGTH_WORDS:
        return None
    unit_match = UNIT_WORD.match(rest)
    if unit_match is None:
        return Amount(minimum=low, maximum=high, unit=None)
    unit_key = UNIT_ALIASES.get(" ".join(unit_match[1].lower().replace(".", " ").split()))
    if unit_key is None:
        return Amount(minimum=low, maximum=high, unit=None)
    if unit_key in FIXED_UNITS:
        base, factor = FIXED_UNITS[unit_key]
    else:
        base, factor = BaseUnit.MILLILITRES, SYSTEM_UNITS[unit_key][system]
    return Amount(minimum=low * factor, maximum=high * factor, unit=base)


def parse_quantity(text: str, system: MeasureSystem) -> Amount | None:
    """
    Parse an ingredient quantity as written into an Amount, or None when it has no number.

    Handles unicode and slash fractions, mixed numbers, ranges, "2 x 400g" multiples and
    "2 tbsp + 1 tsp" compounds. cup, tbsp, pint and fl oz depend on the recipe's measure
    system. Text after a recognised unit ("28g pack") is ignored; a number followed by
    anything else ("2 cloves") is a count, and "1 x 3-inch piece" is one piece. A weight
    or volume in brackets replaces a count ("½ head (~700 g)" is 700 g). Lengths
    ("5 cm piece") are not amounts.
    """
    normalised = re.sub(
        r"(\d)?\s*([½⅓⅔¼¾⅕⅛⅜⅝⅞])",
        lambda match: (match[1] + " " if match[1] else " ") + UNICODE_FRACTIONS[match[2]],
        text,
    ).strip()
    if not normalised:
        return None
    bracketed = BRACKETED.search(normalised)
    if bracketed:
        main = parse_quantity(BRACKETED.sub("", normalised), system)
        alternative = parse_quantity(bracketed[1], system)
        if (main is None or main.unit is None) and alternative and alternative.unit:
            return alternative
        return main
    parts = [parse_part(part, system) for part in normalised.split("+")]
    if any(part is None for part in parts):
        return None
    amounts = [part for part in parts if part is not None]
    if len({amount.unit for amount in amounts}) != 1:
        return None
    return Amount(
        minimum=sum(amount.minimum for amount in amounts),
        maximum=sum(amount.maximum for amount in amounts),
        unit=amounts[0].unit,
    )
