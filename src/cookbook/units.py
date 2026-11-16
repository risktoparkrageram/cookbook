import re
import tomllib
from enum import StrEnum
from importlib import resources
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


type QuantityTokenKind = Literal["text", "number", "metric", "size"]


class QuantityToken(BaseModel):
    """
    One piece of an ingredient quantity as written, for the browser to scale.

    A "text" token is shown as written and never changes. A number token carries its value:
    "metric" numbers measure g, kg, ml or l and are rounded as metric amounts when scaled,
    "size" numbers (after "×" or before a length) never scale, and every other number is
    "number". Joining the tokens' text gives back the quantity.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    kind: QuantityTokenKind
    value: float | None = None


FRACTION_CHARACTERS = "".join(UNICODE_FRACTIONS)
NUMBER_TOKEN = re.compile(
    rf"\d+\s?[{FRACTION_CHARACTERS}]|[{FRACTION_CHARACTERS}]"
    r"|\d+(?:\s+|-)\d+/\d+|\d+/\d+|\d+(?:\.\d+)?"
)
RANGE_CONTINUATION = re.compile(
    rf"^\s*(?:-|–|—|to)\s*(?:\d+(?:\.\d+)?\s?[{FRACTION_CHARACTERS}]?|[{FRACTION_CHARACTERS}])"
)
METRIC_AFTER = re.compile(
    r"^\s*(?:g|kg|ml|l|grams?|grammes?|kilos?|kilograms?|litres?|liters?"
    r"|millilitres?|milliliters?)\b",
    re.IGNORECASE,
)
SIZE_AFTER = re.compile(r"^\s*-?\s*(?:cm|mm|\"|″|in\b|inch|inches)", re.IGNORECASE)
SIZE_BEFORE = re.compile(r"(?:^|[\s\d])[x×]\s*$", re.IGNORECASE)


def quantity_tokens(text: str) -> list[QuantityToken]:
    """
    Split a quantity as written into text and number tokens, for scaling in the browser.

    "2 x 400g tins" scales the 2 but not the 400, a size; in "50–100 g" both ends of the
    range are metric. "1-1/2" is the mixed number 1½, not a range.
    """
    tokens: list[QuantityToken] = []
    position = 0
    for match in NUMBER_TOKEN.finditer(text):
        if match.start() > position:
            tokens.append(QuantityToken(text=text[position : match.start()], kind="text"))
        before = text[: match.start()]
        after = RANGE_CONTINUATION.sub("", text[match.end() :], count=1)
        kind: QuantityTokenKind = "number"
        if SIZE_BEFORE.search(before) or SIZE_AFTER.match(after):
            kind = "size"
        elif METRIC_AFTER.match(after):
            kind = "metric"
        tokens.append(QuantityToken(text=match[0], kind=kind, value=token_value(match[0])))
        position = match.end()
    if position < len(text):
        tokens.append(QuantityToken(text=text[position:], kind="text"))
    return tokens


def token_value(text: str) -> float:
    """Read a number as NUMBER_TOKEN finds it: "1½", "½", "1-1/2", "1 1/2", "3/4", "1.5"."""
    number = text.replace("-", " ")
    if number[-1] in UNICODE_FRACTIONS:
        number = f"{number[:-1].strip()} {UNICODE_FRACTIONS[number[-1]]}".strip()
    return number_value(number)


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


def format_minutes(minutes: int) -> str:
    """Write a duration compactly for the recipe header: "20min", "2h", "2h 20min"."""
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest}min"
    return f"{hours}h" if hours else f"{rest}min"


class ServesOption(BaseModel):
    """One choice in the serves dropdown: the factor every quantity is multiplied by."""

    model_config = ConfigDict(frozen=True)

    factor: float
    label: str
    as_written: bool


RANGE_FACTORS = (0.5, 1.0, 1.5, 2.0, 3.0)


def serves_options(serves_min: int | None, serves_max: int | None) -> list[ServesOption]:
    """
    List the serves dropdown's choices; none for a recipe without a numeric serves.

    A single number n offers 1 to max(12, 3n). A range offers multiples of itself (2–4
    offers 1–2, 2–4, 3–6, 4–8, 6–12), leaving out any whose ends aren't whole numbers.
    """
    if serves_min is None or serves_min < 1:
        return []
    if serves_max is None or serves_max <= serves_min:
        return [
            ServesOption(
                factor=count / serves_min, label=str(count), as_written=count == serves_min
            )
            for count in range(1, max(12, 3 * serves_min) + 1)
        ]
    options = []
    for factor in RANGE_FACTORS:
        low, high = serves_min * factor, serves_max * factor
        if low.is_integer() and high.is_integer():
            options.append(
                ServesOption(factor=factor, label=f"{low:g}–{high:g}", as_written=factor == 1)
            )
    return options


class MetricAmount(BaseModel):
    """An ingredient's amount in grams or millilitres, for the Metric view."""

    model_config = ConfigDict(frozen=True)

    minimum: float
    maximum: float
    unit: BaseUnit


DENSITIES: dict[str, float] = tomllib.loads(
    resources.files("cookbook").joinpath("densities.toml").read_text(encoding="utf-8")
)
SPOONS = {"tsp", "tbsp"}


def metric_amount(
    quantity: str,
    item: str,
    system: MeasureSystem,
    amount: Amount | None,
    grams_override: float | None,
) -> MetricAmount | None:
    """
    Work out what the Metric view shows for an ingredient, or None to keep it as written.

    Kept as written: quantities that already give a metric amount ("50 g / 2 oz"), packs
    with a size ("3 × 13.5 oz cans"), teaspoons and tablespoons (UK cooks measure by the
    spoon; only the 20 ml Australian tablespoon is converted), and anything unparsed.
    Weights become grams. Volumes become grams with the draft's gram override or a density
    from densities.toml, else millilitres. A count with a gram override shows the grams.
    """
    tokens = quantity_tokens(quantity)
    if amount is None or any(token.kind in ("metric", "size") for token in tokens):
        return None
    if amount.unit is None:
        if grams_override is None:
            return None
        return MetricAmount(minimum=grams_override, maximum=grams_override, unit=BaseUnit.GRAMS)
    if amount.unit is BaseUnit.GRAMS:
        return MetricAmount(minimum=amount.minimum, maximum=amount.maximum, unit=BaseUnit.GRAMS)

    written_units = set()
    for match in NUMBER_TOKEN.finditer(quantity):
        rest = RANGE_CONTINUATION.sub("", quantity[match.end() :], count=1).strip()
        unit_match = UNIT_WORD.match(rest)
        if unit_match:
            words = " ".join(unit_match[1].lower().replace(".", " ").split())
            written_units.add(UNIT_ALIASES.get(words, words))
    if written_units <= SPOONS and not (system == "au" and "tbsp" in written_units):
        return None

    grams_per_ml = None
    if grams_override is not None:
        grams_per_ml = grams_override / amount.maximum
    else:
        first_clause = re.split(r"[,(]", item, maxsplit=1)[0].lower().strip()
        for name in sorted(DENSITIES, key=len, reverse=True):
            if first_clause == name or first_clause.endswith(" " + name):
                grams_per_ml = DENSITIES[name]
                break
    if grams_per_ml is None:
        return MetricAmount(
            minimum=amount.minimum, maximum=amount.maximum, unit=BaseUnit.MILLILITRES
        )
    return MetricAmount(
        minimum=amount.minimum * grams_per_ml,
        maximum=amount.maximum * grams_per_ml,
        unit=BaseUnit.GRAMS,
    )


class TextPiece(BaseModel):
    """
    A piece of recipe text as shown, Fahrenheit already replaced by Celsius.

    metric holds what the Metric view shows instead, for lengths in inches.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    metric: str | None = None


NUMBER_IN_TEXT = (
    r"\d+\s+\d+/\d+|\d+/\d+"
    rf"|\d+(?:\.\d+)?(?:\s?[{FRACTION_CHARACTERS}])?|[{FRACTION_CHARACTERS}]"
)
# "°F" marks Fahrenheit at any value; a bare "F" or "degrees" only counts from 200 to 550.
FAHRENHEIT = re.compile(
    r"(?P<degrees>\d{2,3})\s*"
    r"(?:(?P<marked>°\s*F\b)|(?:F\b|degrees(?:\s+F(?:ahrenheit)?)?\b)(?!\s+C))"
)
CELSIUS = re.compile(r"\d\s*(?:°\s*C\b|degrees\s+C)")
# How many characters either side of a Fahrenheit temperature count as "beside" it.
CELSIUS_NEARBY = 15
SEPARATOR_BEFORE = re.compile(r"\s*(?:/|,|\bor\b)\s*$")
SEPARATOR_AFTER = re.compile(r"^\s*(?:/|,|\bor\b)\s*|^\s+")
# A " means inches only straight after the number (3"), never before a quoted word (3 "big").
INCHES = re.compile(
    rf"(?P<first>{NUMBER_IN_TEXT})(?:\s*[x×]\s*(?P<second>{NUMBER_IN_TEXT}))?"
    r"(?:(?:\s*-\s*|\s*)inch(?:es)?\b|[\"″])"
)
# "9 x 13-inch" is a size only before one of these; "2 x 1-inch pieces" is a count.
CONTAINER_AFTER = re.compile(r"^\s+(?:[a-z-]+\s+)?(?:pan|tin|dish|tray|sheet)s?\b", re.IGNORECASE)
# Oven settings as UK recipes write them, by °F: (°C, gas mark).
OVEN_SETTINGS = {
    225: (110, "¼"),
    250: (120, "½"),
    275: (140, "1"),
    300: (150, "2"),
    325: (170, "3"),
    350: (180, "4"),
    375: (190, "5"),
    400: (200, "6"),
    425: (220, "7"),
    450: (230, "8"),
    475: (240, "9"),
}


def centimetres(inches: float) -> str:
    """Inches as centimetres: to the half under 5 cm ("2.5"), else whole ("15")."""
    value = inches * 2.54
    rounded = round(value * 2) / 2 if value < 5 else round(value)
    return f"{rounded:g}"


def convert_text(text: str) -> list[TextPiece]:
    """
    Show recipe text with Celsius only, and find its inches for the Metric view.

    Fahrenheit is never shown. One beside a Celsius temperature is dropped with its
    separator: "190°C / 375°F / gas 5" reads "190°C / gas 5", "475°F / 245°C" reads
    "245°C". One on its own becomes Celsius: 375°F reads "190°C, gas 5" (UK oven settings;
    other temperatures to the nearest 5 °C, without a gas mark). "350°F" is Fahrenheit at
    any value; "400 F" and "400 degrees" only from 200 to 550. "¾-inch" and "1/2 inch" get
    metric forms ("2 cm", "1.5 cm"). "9 x 13-inch" before a pan, tin, dish, tray or sheet
    is a size ("23 x 33 cm"); otherwise the first number is a count ("2 x 1-inch pieces"
    converts only the 1-inch). Other numbers ("bake 25 minutes") are left alone.
    """
    # (start, end, text shown, metric form): replacements of text[start:end].
    found: list[tuple[int, int, str, str | None]] = []
    for match in FAHRENHEIT.finditer(text):
        degrees = int(match["degrees"])
        if not match["marked"] and not 200 <= degrees <= 550:
            continue
        start, end = match.start(), match.end()
        beside = text[max(0, start - CELSIUS_NEARBY) : end + CELSIUS_NEARBY]
        if CELSIUS.search(beside):
            before = SEPARATOR_BEFORE.search(text[:start])
            after = SEPARATOR_AFTER.match(text[end:])
            if before:
                start = before.start()
            elif after:
                end += after.end()
            found.append((start, end, "", None))
        elif degrees in OVEN_SETTINGS:
            celsius, gas = OVEN_SETTINGS[degrees]
            found.append((start, end, f"{celsius}°C, gas {gas}", None))
        else:
            found.append((start, end, f"{round((degrees - 32) * 5 / 9 / 5) * 5}°C", None))
    for match in INCHES.finditer(text):
        if match["second"] and not CONTAINER_AFTER.match(text[match.end() :]):
            start = match.start("second")
            second_only = centimetres(token_value(match["second"])) + " cm"
            found.append((start, match.end(), text[start : match.end()], second_only))
            continue
        sizes = [centimetres(token_value(match["first"]))]
        if match["second"]:
            sizes.append(centimetres(token_value(match["second"])))
        found.append((match.start(), match.end(), match[0], " x ".join(sizes) + " cm"))

    pieces: list[TextPiece] = []
    position = 0
    for start, end, shown, metric in sorted(found):
        if start < position:
            continue
        plain = [text[position:start]] + ([] if metric else [shown])
        for part in plain:
            if pieces and pieces[-1].metric is None:
                pieces[-1] = TextPiece(text=pieces[-1].text + part)
            elif part:
                pieces.append(TextPiece(text=part))
        if metric:
            pieces.append(TextPiece(text=shown, metric=metric))
        position = end
    rest = text[position:]
    if pieces and pieces[-1].metric is None:
        pieces[-1] = TextPiece(text=pieces[-1].text + rest)
    elif rest or not pieces:
        pieces.append(TextPiece(text=rest))
    return pieces
