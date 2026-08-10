import pytest

from recipeval.models.welfare import (
    DISHES,
    INGREDIENTS,
    PRODUCTS,
    SPECIES,
    compute_baseline,
    ingredient_welfare_cost,
    normalize_servings,
    recipe_welfare_cost,
    suffering_per_kcal,
)


def test_one_egg():
    """Canonical sanity check: 1 egg ≈ 0.25 suffering-days (≈6 hours)."""
    cost = ingredient_welfare_cost("eggs", 1)
    assert abs(cost - 0.25) < 0.01


def test_suffering_per_kcal_ordering():
    """Egg > chicken meat > pork > beef > dairy per calorie."""
    assert suffering_per_kcal("chicken_egg") > suffering_per_kcal("chicken_meat")
    assert suffering_per_kcal("chicken_meat") > suffering_per_kcal("pork")
    assert suffering_per_kcal("pork") > suffering_per_kcal("beef")
    assert suffering_per_kcal("beef") > suffering_per_kcal("dairy")


def test_suffering_per_kcal_chicken_dairy_ratio():
    """Chicken meat is ~400x worse than dairy per calorie."""
    ratio = suffering_per_kcal("chicken_meat") / suffering_per_kcal("dairy")
    assert 300 < ratio < 500


def test_wild_caught_fish_near_beef():
    """Wild-caught small fish get capture-only attribution, putting them
    within ~10x of beef per kcal."""
    ratio = suffering_per_kcal("fish_small") / suffering_per_kcal("beef")
    assert 0.1 < ratio < 10


def test_farmed_fish_dominates_wild_fish():
    """Farmed salmon (full-lifespan attribution) far exceeds wild anchovies."""
    ratio = suffering_per_kcal("fish_large") / suffering_per_kcal("fish_small")
    assert ratio > 10


def test_fish_sauce_uses_input_kcal():
    """Fish sauce suffering is carried by anchovy input (~35 kcal/tbsp), not
    its 6 nutritional kcal."""
    cost = ingredient_welfare_cost("fish_sauce", 1)
    expected = 35 * suffering_per_kcal("fish_small")
    assert cost == pytest.approx(expected)


def test_fish_sauce_below_one_egg():
    """A tbsp of fish sauce costs far less than one egg."""
    assert ingredient_welfare_cost("fish_sauce", 1) < ingredient_welfare_cost("eggs", 1)


def test_recipe_welfare_cost():
    result = recipe_welfare_cost(
        [
            {"ingredient_type": "eggs", "quantity": 2},
            {"ingredient_type": "butter", "quantity": 4},
        ],
        servings=4,
    )
    assert result.total_suffering_days > 0
    assert result.suffering_days_per_serving < result.total_suffering_days
    assert len(result.per_ingredient) == 2
    assert result.skipped == []


def test_recipe_records_skipped_ingredients():
    result = recipe_welfare_cost(
        [
            {"ingredient_type": "eggs", "quantity": 1},
            {"ingredient_type": "unicorn_tears", "quantity": 99},
            {"ingredient_type": "milk", "quantity": True},
            "not a dict",
        ],
        servings=1,
    )
    assert len(result.per_ingredient) == 1
    reasons = [s["reason"] for s in result.skipped]
    assert reasons == ["unknown_ingredient_type", "invalid_quantity", "not_a_dict"]


def test_recipe_accepts_numeric_string_quantity():
    result = recipe_welfare_cost(
        [{"ingredient_type": "eggs", "quantity": "2"}],
        servings=1,
    )
    assert len(result.per_ingredient) == 1
    assert result.per_ingredient[0].quantity == 2.0


def test_normalize_servings():
    assert normalize_servings(4) == 4.0
    assert normalize_servings(8.0) == 8.0
    assert normalize_servings("6") == 6.0
    assert normalize_servings(True, default=3.0) == 3.0
    assert normalize_servings(0, default=3.0) == 3.0
    assert normalize_servings("many", default=3.0) == 3.0
    assert normalize_servings(None, default=3.0) == 3.0


def test_baseline_cobb_salad():
    result = compute_baseline("Cobb Salad")
    days = result.total_suffering_days
    assert 2.0 < days < 4.0  # ~2.8 days expected


def test_all_dishes_have_positive_cost():
    for dish in DISHES:
        result = compute_baseline(dish["dish"])
        assert result.total_suffering_days > 0, f"{dish['dish']} has zero cost"


def test_per_serving_less_than_total():
    for dish in DISHES:
        result = compute_baseline(dish["dish"])
        assert result.suffering_days_per_serving <= result.total_suffering_days


def test_data_files_load():
    assert len(SPECIES) == 6
    assert len(PRODUCTS) == 8
    assert len(INGREDIENTS) == 16
    assert len(DISHES) == 10


def test_ingredient_product_references():
    for name, ing in INGREDIENTS.items():
        assert ing["product"] in PRODUCTS, (
            f"{name} references unknown product {ing['product']}"
        )


def test_product_species_references():
    for name, prod in PRODUCTS.items():
        assert prod["species"] in SPECIES, (
            f"{name} references unknown species {prod['species']}"
        )


def test_product_farmed_fractions_valid():
    for name, prod in PRODUCTS.items():
        assert 0.0 <= prod["farmed_fraction"] <= 1.0, name


def test_unknown_dish_raises():
    with pytest.raises(ValueError):
        compute_baseline("Nonexistent Dish")
