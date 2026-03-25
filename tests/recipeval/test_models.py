import pytest

from recipeval.models.welfare import (
    DISHES,
    INGREDIENTS,
    PRODUCTS,
    SPECIES,
    compute_industry_standard,
    ingredient_welfare_cost,
    recipe_welfare_cost,
    suffering_per_kcal,
)


def test_one_egg():
    """Canonical sanity check: 1 egg ≈ 0.000420 WY (0.42 mWY)."""
    cost = ingredient_welfare_cost("eggs", 1)
    assert abs(cost - 0.000420) < 0.0001


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
    assert result.total_welfare_years > 0
    assert result.welfare_years_per_serving < result.total_welfare_years
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


def test_industry_standard_cobb_salad():
    result = compute_industry_standard("Cobb Salad")
    mwy = result.total_welfare_years * 1000
    assert 7 < mwy < 12  # ~9.04 mWY expected


def test_all_dishes_have_positive_cost():
    for dish in DISHES:
        result = compute_industry_standard(dish["dish"])
        assert result.total_welfare_years > 0, f"{dish['dish']} has zero welfare cost"


def test_per_serving_less_than_total():
    for dish in DISHES:
        result = compute_industry_standard(dish["dish"])
        assert result.welfare_years_per_serving <= result.total_welfare_years


def test_data_files_load():
    assert len(SPECIES) == 5
    assert len(PRODUCTS) == 8
    assert len(INGREDIENTS) == 15
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


def test_unknown_dish_raises():
    with pytest.raises(ValueError):
        compute_industry_standard("Nonexistent Dish")
