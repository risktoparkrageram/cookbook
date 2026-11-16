import pytest
from pytest_cases import case, parametrize_with_cases

from cookbook.units import (
    Amount,
    BaseUnit,
    MeasureSystem,
    MetricAmount,
    QuantityToken,
    ServesOption,
    TextPiece,
    convert_text,
    metric_amount,
    parse_quantity,
    quantity_tokens,
    serves_options,
)

# quantity text as written, the recipe's measure system, the expected parse
type QuantityCase = tuple[str, MeasureSystem, Amount | None]
# quantity text as written, the expected tokens
type TokensCase = tuple[str, list[QuantityToken]]
# quantity and item as written, measure system, parsed amount, gram override, expected
type MetricCase = tuple[str, str, MeasureSystem, Amount | None, float | None, MetricAmount | None]
# recipe text, the expected pieces
type TextCase = tuple[str, list[TextPiece]]


def case_grams() -> QuantityCase:
    return "200 g", "uk", Amount(minimum=200, maximum=200, unit=BaseUnit.GRAMS)


def case_grams_without_space() -> QuantityCase:
    return "400g", "uk", Amount(minimum=400, maximum=400, unit=BaseUnit.GRAMS)


def case_kilograms_decimal() -> QuantityCase:
    return "1.5 kg", "uk", Amount(minimum=1500, maximum=1500, unit=BaseUnit.GRAMS)


def case_pound_range_with_en_dash() -> QuantityCase:
    return "1–2 lbs", "us", Amount(minimum=453.59237, maximum=907.18474, unit=BaseUnit.GRAMS)


def case_ounces_spelt_out() -> QuantityCase:
    return "8 ounces", "us", Amount(minimum=226.796185, maximum=226.796185, unit=BaseUnit.GRAMS)


def case_unicode_fraction() -> QuantityCase:
    return "½ tsp", "uk", Amount(minimum=2.5, maximum=2.5, unit=BaseUnit.MILLILITRES)


def case_unicode_mixed_number() -> QuantityCase:
    return "1½ cups", "us", Amount(minimum=360, maximum=360, unit=BaseUnit.MILLILITRES)


def case_slash_mixed_number() -> QuantityCase:
    return "1 1/2 cups", "us", Amount(minimum=360, maximum=360, unit=BaseUnit.MILLILITRES)


def case_hyphenated_mixed_number_is_not_a_backwards_range() -> QuantityCase:
    return "1-1/2 cups", "us", Amount(minimum=360, maximum=360, unit=BaseUnit.MILLILITRES)


def case_uk_cup_is_250_ml() -> QuantityCase:
    return "1 cup", "uk", Amount(minimum=250, maximum=250, unit=BaseUnit.MILLILITRES)


def case_australian_tablespoon_is_20_ml() -> QuantityCase:
    return "2 tbsp", "au", Amount(minimum=40, maximum=40, unit=BaseUnit.MILLILITRES)


def case_uk_tablespoon_is_15_ml() -> QuantityCase:
    return "2 tablespoons", "uk", Amount(minimum=30, maximum=30, unit=BaseUnit.MILLILITRES)


def case_us_pint_differs_from_uk() -> QuantityCase:
    return "1 pint", "us", Amount(minimum=473.18, maximum=473.18, unit=BaseUnit.MILLILITRES)


def case_fluid_ounces_with_dot() -> QuantityCase:
    return "4 fl. oz", "uk", Amount(minimum=113.64, maximum=113.64, unit=BaseUnit.MILLILITRES)


def case_compound_sums_compatible_units() -> QuantityCase:
    return "2 tbsp + 1 tsp", "uk", Amount(minimum=35, maximum=35, unit=BaseUnit.MILLILITRES)


def case_compound_of_weight_and_volume_is_unparsed() -> QuantityCase:
    return "100 g + 2 tbsp", "uk", None


def case_multiplied_pack_size() -> QuantityCase:
    return "2 x 400g tins", "uk", Amount(minimum=800, maximum=800, unit=BaseUnit.GRAMS)


def case_range_with_to() -> QuantityCase:
    return "3 to 4 tbsp", "uk", Amount(minimum=45, maximum=60, unit=BaseUnit.MILLILITRES)


def case_approximate_prefix_is_dropped() -> QuantityCase:
    return "about 2 tbsp", "uk", Amount(minimum=30, maximum=30, unit=BaseUnit.MILLILITRES)


def case_heaped_qualifier_is_dropped() -> QuantityCase:
    return "1 heaped tsp", "uk", Amount(minimum=5, maximum=5, unit=BaseUnit.MILLILITRES)


def case_stick_of_butter() -> QuantityCase:
    return "1 stick", "us", Amount(minimum=113, maximum=113, unit=BaseUnit.GRAMS)


def case_multiplied_piece_size_is_one_piece() -> QuantityCase:
    return '1 × 3" piece', "us", Amount(minimum=1, maximum=1, unit=None)


def case_length_is_not_converted() -> QuantityCase:
    return "5 cm piece", "uk", None


def case_weight_in_brackets_replaces_a_count() -> QuantityCase:
    return "½ head (~700 g)", "uk", Amount(minimum=700, maximum=700, unit=BaseUnit.GRAMS)


def case_count_without_unit() -> QuantityCase:
    return "2", "uk", Amount(minimum=2, maximum=2, unit=None)


def case_count_with_unknown_word() -> QuantityCase:
    return "3 cloves", "uk", Amount(minimum=3, maximum=3, unit=None)


def case_no_number_to_taste() -> QuantityCase:
    return "to taste", "uk", None


def case_empty() -> QuantityCase:
    return "", "uk", None


@parametrize_with_cases("text, system, expected", cases=".")
def test_parse_quantity(text: str, system: MeasureSystem, expected: Amount | None) -> None:
    parsed = parse_quantity(text, system)

    rounded = parsed and Amount(
        minimum=round(parsed.minimum, 6), maximum=round(parsed.maximum, 6), unit=parsed.unit
    )
    assert rounded == expected


@case(tags="tokens")
def case_tokens_dual_units_scale_both_halves() -> TokensCase:
    return "50 g / 2 oz", [
        QuantityToken(text="50", kind="metric", value=50),
        QuantityToken(text=" g / ", kind="text"),
        QuantityToken(text="2", kind="number", value=2),
        QuantityToken(text=" oz", kind="text"),
    ]


@case(tags="tokens")
def case_tokens_pack_size_after_times_is_a_size() -> TokensCase:
    return "2 x 400g tins", [
        QuantityToken(text="2", kind="number", value=2),
        QuantityToken(text=" x ", kind="text"),
        QuantityToken(text="400", kind="size", value=400),
        QuantityToken(text="g tins", kind="text"),
    ]


@case(tags="tokens")
def case_tokens_number_before_a_length_is_a_size() -> TokensCase:
    return '1 × 3" piece', [
        QuantityToken(text="1", kind="number", value=1),
        QuantityToken(text=" × ", kind="text"),
        QuantityToken(text="3", kind="size", value=3),
        QuantityToken(text='" piece', kind="text"),
    ]


@case(tags="tokens")
def case_tokens_length_without_times_is_a_size() -> TokensCase:
    return "5 cm piece", [
        QuantityToken(text="5", kind="size", value=5),
        QuantityToken(text=" cm piece", kind="text"),
    ]


@case(tags="tokens")
def case_tokens_both_ends_of_a_metric_range_are_metric() -> TokensCase:
    return "1.3–1.5 litres", [
        QuantityToken(text="1.3", kind="metric", value=1.3),
        QuantityToken(text="–", kind="text"),
        QuantityToken(text="1.5", kind="metric", value=1.5),
        QuantityToken(text=" litres", kind="text"),
    ]


@case(tags="tokens")
def case_tokens_hyphenated_mixed_number_is_one_number() -> TokensCase:
    return "1-1/2 cups", [
        QuantityToken(text="1-1/2", kind="number", value=1.5),
        QuantityToken(text=" cups", kind="text"),
    ]


@case(tags="tokens")
def case_tokens_unicode_fractions_and_compounds() -> TokensCase:
    return "1½ tbsp + ¼ tsp", [
        QuantityToken(text="1½", kind="number", value=1.5),
        QuantityToken(text=" tbsp + ", kind="text"),
        QuantityToken(text="¼", kind="number", value=0.25),
        QuantityToken(text=" tsp", kind="text"),
    ]


@case(tags="tokens")
def case_tokens_bracketed_weight_is_metric() -> TokensCase:
    return "½ head (~700 g)", [
        QuantityToken(text="½", kind="number", value=0.5),
        QuantityToken(text=" head (~", kind="text"),
        QuantityToken(text="700", kind="metric", value=700),
        QuantityToken(text=" g)", kind="text"),
    ]


@case(tags="tokens")
def case_tokens_text_without_numbers_stays_as_written() -> TokensCase:
    return "to taste", [QuantityToken(text="to taste", kind="text")]


@parametrize_with_cases("text, expected", cases=".", has_tag="tokens")
def test_quantity_tokens(text: str, expected: list[QuantityToken]) -> None:
    assert quantity_tokens(text) == expected


def test_serves_options_for_a_range_are_its_whole_multiples() -> None:
    assert serves_options(2, 4) == [
        ServesOption(factor=0.5, label="1–2", as_written=False),
        ServesOption(factor=1, label="2–4", as_written=True),
        ServesOption(factor=1.5, label="3–6", as_written=False),
        ServesOption(factor=2, label="4–8", as_written=False),
        ServesOption(factor=3, label="6–12", as_written=False),
    ]


@pytest.mark.parametrize(
    ("serves_min", "serves_max", "labels"),
    [
        (1, 2, ["1–2", "2–4", "3–6"]),
        (4, 6, ["2–3", "4–6", "6–9", "8–12", "12–18"]),
        (4, 4, ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]),
        (None, None, []),
    ],
)
def test_serves_options_labels(
    serves_min: int | None, serves_max: int | None, labels: list[str]
) -> None:
    assert [option.label for option in serves_options(serves_min, serves_max)] == labels


def test_serves_options_for_a_single_number_go_to_three_times_it() -> None:
    options = serves_options(5, 5)

    assert (len(options), options[1], options[4]) == (
        15,
        ServesOption(factor=0.4, label="2", as_written=False),
        ServesOption(factor=1, label="5", as_written=True),
    )


@case(tags="metric")
def case_metric_ounces_become_grams() -> MetricCase:
    amount = Amount(minimum=226.8, maximum=226.8, unit=BaseUnit.GRAMS)
    return (
        "8 oz",
        "paneer",
        "us",
        amount,
        None,
        MetricAmount(minimum=226.8, maximum=226.8, unit=BaseUnit.GRAMS),
    )


@case(tags="metric")
def case_metric_pound_range() -> MetricCase:
    amount = Amount(minimum=453.6, maximum=907.2, unit=BaseUnit.GRAMS)
    return (
        "1–2 lbs",
        "salmon",
        "us",
        amount,
        None,
        MetricAmount(minimum=453.6, maximum=907.2, unit=BaseUnit.GRAMS),
    )


@case(tags="metric")
def case_metric_cup_of_rice_uses_its_density() -> MetricCase:
    amount = Amount(minimum=360, maximum=360, unit=BaseUnit.MILLILITRES)
    return (
        "1½ cups",
        "basmati rice",
        "us",
        amount,
        None,
        MetricAmount(minimum=288, maximum=288, unit=BaseUnit.GRAMS),
    )


@case(tags="metric")
def case_metric_density_matches_the_end_of_the_first_clause() -> MetricCase:
    amount = Amount(minimum=120, maximum=120, unit=BaseUnit.MILLILITRES)
    return (
        "½ cup",
        "unsalted butter, softened",
        "us",
        amount,
        None,
        MetricAmount(minimum=115.2, maximum=115.2, unit=BaseUnit.GRAMS),
    )


@case(tags="metric")
def case_metric_rice_vinegar_is_not_rice() -> MetricCase:
    amount = Amount(minimum=120, maximum=120, unit=BaseUnit.MILLILITRES)
    return (
        "½ cup",
        "rice vinegar",
        "us",
        amount,
        None,
        MetricAmount(minimum=120, maximum=120, unit=BaseUnit.MILLILITRES),
    )


@case(tags="metric")
def case_metric_gram_override_beats_the_density() -> MetricCase:
    amount = Amount(minimum=250, maximum=250, unit=BaseUnit.MILLILITRES)
    return (
        "1 cup",
        "plain flour",
        "uk",
        amount,
        125,
        MetricAmount(minimum=125, maximum=125, unit=BaseUnit.GRAMS),
    )


@case(tags="metric")
def case_metric_count_with_gram_override() -> MetricCase:
    amount = Amount(minimum=2, maximum=2, unit=None)
    return (
        "2",
        "mangoes",
        "uk",
        amount,
        300,
        MetricAmount(minimum=300, maximum=300, unit=BaseUnit.GRAMS),
    )


@case(tags="metric")
def case_metric_count_without_override_stays() -> MetricCase:
    return "3 cloves", "garlic", "uk", Amount(minimum=3, maximum=3, unit=None), None, None


@case(tags="metric")
def case_metric_teaspoons_stay_spoons() -> MetricCase:
    amount = Amount(minimum=10, maximum=10, unit=BaseUnit.MILLILITRES)
    return "2 tsp", "honey", "uk", amount, None, None


@case(tags="metric")
def case_metric_australian_tablespoon_becomes_millilitres() -> MetricCase:
    amount = Amount(minimum=40, maximum=40, unit=BaseUnit.MILLILITRES)
    return (
        "2 tbsp",
        "water",
        "au",
        amount,
        None,
        MetricAmount(minimum=40, maximum=40, unit=BaseUnit.MILLILITRES),
    )


@case(tags="metric")
def case_metric_already_metric_stays() -> MetricCase:
    amount = Amount(minimum=50, maximum=50, unit=BaseUnit.GRAMS)
    return "50 g / 2 oz", "ginger", "uk", amount, None, None


@case(tags="metric")
def case_metric_pack_size_stays() -> MetricCase:
    amount = Amount(minimum=1148.2, maximum=1148.2, unit=BaseUnit.GRAMS)
    return "3 × 13.5 oz cans", "coconut milk", "us", amount, None, None


@case(tags="metric")
def case_metric_unparsed_stays() -> MetricCase:
    return "to taste", "salt", "uk", None, None, None


@parametrize_with_cases(
    "quantity, item, system, amount, grams_override, expected", cases=".", has_tag="metric"
)
def test_metric_amount(
    quantity: str,
    item: str,
    system: MeasureSystem,
    amount: Amount | None,
    grams_override: float | None,
    expected: MetricAmount | None,
) -> None:
    metric = metric_amount(quantity, item, system, amount, grams_override)

    rounded = metric and MetricAmount(
        minimum=round(metric.minimum, 6), maximum=round(metric.maximum, 6), unit=metric.unit
    )
    assert rounded == expected


@case(tags="text")
def case_text_fahrenheit_becomes_a_uk_oven_setting() -> TextCase:
    return "Bake at 350°F for 25 minutes.", [TextPiece(text="Bake at 180°C, gas 4 for 25 minutes.")]


@case(tags="text")
def case_text_degrees_without_a_scale_are_fahrenheit() -> TextCase:
    return "Heat to 400 degrees.", [TextPiece(text="Heat to 200°C, gas 6.")]


@case(tags="text")
def case_text_unusual_temperature_rounds_to_five() -> TextCase:
    return "Roast at 390 F", [TextPiece(text="Roast at 200°C")]


@case(tags="text")
def case_text_fahrenheit_after_celsius_is_dropped_with_its_separator() -> TextCase:
    return "Heat to 190°C / 375°F / gas 5.", [TextPiece(text="Heat to 190°C / gas 5.")]


@case(tags="text")
def case_text_fahrenheit_before_celsius_is_dropped_with_its_separator() -> TextCase:
    return "Preheat to 475°F / 245°C. Or grill at 500°F.", [
        TextPiece(text="Preheat to 245°C. Or grill at 260°C.")
    ]


@case(tags="text")
def case_text_low_fahrenheit_beside_celsius_is_dropped() -> TextCase:
    return "warm water (about 110°F / 43°C)", [TextPiece(text="warm water (about 43°C)")]


@case(tags="text")
def case_text_small_degrees_without_a_scale_are_left_alone() -> TextCase:
    return "Turn it 90 degrees.", [TextPiece(text="Turn it 90 degrees.")]


@case(tags="text")
def case_text_hyphenated_inches() -> TextCase:
    return "Cut into ¾-inch or 1-inch cubes", [
        TextPiece(text="Cut into "),
        TextPiece(text="¾-inch", metric="2 cm"),
        TextPiece(text=" or "),
        TextPiece(text="1-inch", metric="2.5 cm"),
        TextPiece(text=" cubes"),
    ]


@case(tags="text")
def case_text_tin_size_in_inches() -> TextCase:
    return 'a 9 x 13-inch tin, about 6" deep', [
        TextPiece(text="a "),
        TextPiece(text="9 x 13-inch", metric="23 x 33 cm"),
        TextPiece(text=" tin, about "),
        TextPiece(text='6"', metric="15 cm"),
        TextPiece(text=" deep"),
    ]


@case(tags="text")
def case_text_slash_fractions_of_an_inch() -> TextCase:
    return "Roll to 1/2 inch, or 1 1/2 inches", [
        TextPiece(text="Roll to "),
        TextPiece(text="1/2 inch", metric="1.5 cm"),
        TextPiece(text=", or "),
        TextPiece(text="1 1/2 inches", metric="4 cm"),
    ]


@case(tags="text")
def case_text_count_of_pieces_converts_only_the_inches() -> TextCase:
    return "Cut into 2 x 1-inch pieces", [
        TextPiece(text="Cut into 2 x "),
        TextPiece(text="1-inch", metric="2.5 cm"),
        TextPiece(text=" pieces"),
    ]


@case(tags="text")
def case_text_quoted_word_after_a_number_is_not_inches() -> TextCase:
    return 'Add the 3 "secret" spices', [TextPiece(text='Add the 3 "secret" spices')]


@case(tags="text")
def case_text_marked_fahrenheit_converts_at_any_value() -> TextCase:
    return "Rest in water at about 110°F", [TextPiece(text="Rest in water at about 45°C")]


@case(tags="text")
def case_text_bare_f_after_a_small_number_is_left_alone() -> TextCase:
    return "Leave 10 F aside", [TextPiece(text="Leave 10 F aside")]


@case(tags="text")
def case_text_other_numbers_are_left_alone() -> TextCase:
    return "Simmer 25 minutes at 100°C, stirring 3 times.", [
        TextPiece(text="Simmer 25 minutes at 100°C, stirring 3 times.")
    ]


@parametrize_with_cases("text, expected", cases=".", has_tag="text")
def test_convert_text(text: str, expected: list[TextPiece]) -> None:
    assert convert_text(text) == expected
