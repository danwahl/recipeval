import pytest

from recipeval.models.units import CONVERSIONS, VALID_UNITS, to_canonical
from recipeval.models.welfare import INGREDIENTS


def canonical_unit(ingredient_type: str) -> str:
    result: str = INGREDIENTS[ingredient_type]["canonical_unit"]
    return result


# The conversions the extraction prompt used to ask the grader to do in its head.
# Each case is (ingredient_type, amount, unit, expected quantity in canonical unit).
PROMPT_CONVERSIONS = [
    ("butter", 1, "stick", 8),  # 1 stick = 8 tbsp
    ("butter", 1, "cup", 16),
    ("butter", 14, "g", 1),  # 1 tbsp butter ~ 14 g
    ("hard_cheese", 1, "cup", 3.6),  # grated parmesan, cheddar
    ("soft_cheese", 1, "cup", 4.0),  # shredded mozzarella, ricotta
    ("beef", 1, "lb", 16),
    ("beef", 100, "g", 3.5),
    ("beef", 1, "oz", 1),
    ("milk", 240, "ml", 1.0),  # 1 cup ~ 240 mL
    ("pork", 1, "slice_bacon", 0.5),
    ("pork", 15, "slice_deli", 1.0),  # ~15 thin pepperoni slices ~ 1 oz
    ("chicken", 1, "breast", 6),
    ("chicken", 1, "cup_cooked", 5),
    ("pork", 1, "bone_in_lb", 12.8),  # bone-in cuts count ~80%
    ("eggs", 1, "cup_mayo", 1),
    ("eggs", 1, "yolk", 1),
    ("eggs", 1, "white", 1),
    ("chicken", 12, "whole_bird_lb", 96),  # a whole bird is ~50% edible meat
    ("beef", 1, "cup_broth", 0.5),
    ("chicken", 1, "cup_broth", 0.5),
    ("fish_large", 1, "cup_broth", 0.5),  # dashi
    ("anchovies", 1, "fillet", 1),
]


@pytest.mark.parametrize("ingredient,amount,unit,expected", PROMPT_CONVERSIONS)
def test_prompt_conversions(ingredient: str, amount: float, unit: str, expected: float):
    """Python reproduces the arithmetic the prompt spelled out for the grader."""
    result = to_canonical(ingredient, amount, unit)
    assert result is not None
    assert result == pytest.approx(expected, rel=0.02)


def test_canonical_unit_is_identity():
    """Reporting an ingredient in its own canonical unit changes nothing."""
    for ingredient in INGREDIENTS:
        unit = canonical_unit(ingredient)
        if unit in CONVERSIONS[ingredient]:
            assert to_canonical(ingredient, 3, unit) == pytest.approx(3)


def test_every_ingredient_has_conversions():
    assert set(CONVERSIONS) == set(INGREDIENTS)


def test_every_ingredient_accepts_its_canonical_unit():
    """`large` and `fillet` are count units the grader may report directly."""
    for ingredient in INGREDIENTS:
        unit = canonical_unit(ingredient)
        assert unit in CONVERSIONS[ingredient] or unit in ("large", "fillet")


def test_unknown_pairings_return_none():
    assert to_canonical("beef", 1, "stick") is None  # butter-only unit
    assert to_canonical("milk", 1, "whole_bird_lb") is None
    assert to_canonical("not_an_ingredient", 1, "oz") is None
    assert to_canonical("beef", 1, "not_a_unit") is None


def test_valid_units_covers_the_vocabulary():
    assert "oz" in VALID_UNITS
    assert "whole_bird_lb" in VALID_UNITS
    assert VALID_UNITS == sorted(set(VALID_UNITS))


def test_mass_and_volume_scales_are_consistent():
    assert to_canonical("beef", 1, "kg") == pytest.approx(
        to_canonical("beef", 1000, "g")
    )
    assert to_canonical("milk", 1, "quart") == pytest.approx(
        to_canonical("milk", 2, "pint")
    )
    assert to_canonical("milk", 1, "cup") == pytest.approx(
        to_canonical("milk", 16, "tbsp")
    )


def test_recipe_cost_accepts_both_extraction_shapes():
    """Old logs store canonical `quantity`; new grading stores `amount` + `unit`."""
    from recipeval.models.welfare import recipe_welfare_cost

    old = recipe_welfare_cost([{"ingredient_type": "beef", "quantity": 16}], 4)
    new = recipe_welfare_cost(
        [{"ingredient_type": "beef", "amount": 1, "unit": "lb"}], 4
    )
    assert new.total_suffering_days == pytest.approx(old.total_suffering_days)


def test_recipe_cost_skips_unconvertible_units():
    from recipeval.models.welfare import recipe_welfare_cost

    cost = recipe_welfare_cost(
        [{"ingredient_type": "beef", "amount": 1, "unit": "stick"}], 4
    )
    assert cost.per_ingredient == []
    assert len(cost.skipped) == 1
