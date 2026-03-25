import pytest

from recipeval.models.welfare import (
    DISHES,
    INGREDIENTS,
    PRODUCTS,
    SPECIES,
    compute_baseline,
    ingredient_welfare_cost,
    recipe_welfare_cost,
    suffering_per_kcal,
)


def test_one_egg():
    """Canonical sanity check: 1 egg ≈ 0.153 suffering-days (≈3.7 hours)."""
    cost = ingredient_welfare_cost("eggs", 1)
    assert abs(cost - 0.153) < 0.01


def test_suffering_per_kcal_ordering():
    """Chicken meat > egg > pork > beef > dairy per calorie."""
    assert suffering_per_kcal("chicken_meat") > suffering_per_kcal("chicken_egg")
    assert suffering_per_kcal("chicken_egg") > suffering_per_kcal("pork")
    assert suffering_per_kcal("pork") > suffering_per_kcal("beef")
    assert suffering_per_kcal("beef") > suffering_per_kcal("dairy")


def test_suffering_per_kcal_chicken_dairy_ratio():
    """Chicken meat is ~450x worse than dairy per calorie."""
    ratio = suffering_per_kcal("chicken_meat") / suffering_per_kcal("dairy")
    assert 400 < ratio < 500


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


def test_recipe_skips_unknown_ingredients():
    result = recipe_welfare_cost(
        [
            {"ingredient_type": "eggs", "quantity": 1},
            {"ingredient_type": "unicorn_tears", "quantity": 99},
        ],
        servings=1,
    )
    assert len(result.per_ingredient) == 1


def test_baseline_cobb_salad():
    result = compute_baseline("Cobb Salad")
    days = result.total_suffering_days
    assert 2.5 < days < 4.5  # ~3.3 days expected


def test_all_dishes_have_positive_cost():
    for dish in DISHES:
        result = compute_baseline(dish["dish"])
        assert result.total_suffering_days > 0, f"{dish['dish']} has zero cost"


def test_per_serving_less_than_total():
    for dish in DISHES:
        result = compute_baseline(dish["dish"])
        assert result.suffering_days_per_serving <= result.total_suffering_days


def test_data_files_load():
    assert len(SPECIES) == 5
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


def test_fish_large_much_cheaper_than_fish_small():
    """Large fish should be ~150x cheaper per kcal than small fish."""
    ratio = suffering_per_kcal("fish_small") / suffering_per_kcal("fish_large")
    assert 100 < ratio < 200


def test_unknown_dish_raises():
    with pytest.raises(ValueError):
        compute_baseline("Nonexistent Dish")
