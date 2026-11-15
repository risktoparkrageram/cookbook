from pytest_cases import parametrize_with_cases

from cookbook.units import Amount, BaseUnit, MeasureSystem, parse_quantity

# quantity text as written, the recipe's measure system, the expected parse
type QuantityCase = tuple[str, MeasureSystem, Amount | None]


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
