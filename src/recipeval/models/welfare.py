import json
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any


def _load_json(filename: str) -> Any:
    """Load a JSON file from the data directory."""
    data_dir = files("recipeval") / "data"
    return json.loads((data_dir / filename).read_text())


SPECIES: dict[str, Any] = _load_json("species.json")
PRODUCTS: dict[str, Any] = _load_json("products.json")
INGREDIENTS: dict[str, Any] = _load_json("ingredients.json")
DISHES: list[dict[str, Any]] = _load_json("dishes.json")


def suffering_per_kcal(product_name: str) -> float:
    """Welfare-years of suffering per kilocalorie of this product.

    Formula: (lifespan_days / 365) / total_kcal_per_lifetime * welfare_range * |welfare_value|

    This gives the fraction of an animal-year consumed per kcal, weighted by
    the species' welfare range (capacity for suffering relative to humans)
    and welfare value (how bad life is on the animal's own scale).
    """
    product = PRODUCTS[product_name]
    species = SPECIES[product["species"]]
    animal_years_per_kcal = (product["lifespan_days"] / 365.0) / product[
        "total_kcal_per_lifetime"
    ]
    result: float = (
        animal_years_per_kcal * species["welfare_range"] * abs(species["welfare_value"])
    )
    return result


def ingredient_kcal(ingredient_type: str, quantity: float) -> float:
    """Total kilocalories for a quantity of an ingredient in its canonical unit."""
    result: float = quantity * INGREDIENTS[ingredient_type]["kcal_per_unit"]
    return result


def ingredient_welfare_cost(ingredient_type: str, quantity: float) -> float:
    """Welfare-years of suffering for a quantity of an ingredient."""
    ing = INGREDIENTS[ingredient_type]
    kcal: float = quantity * ing["kcal_per_unit"]
    return kcal * suffering_per_kcal(ing["product"])


@dataclass
class IngredientCost:
    ingredient_type: str
    quantity: float
    kcal: float
    welfare_years: float


@dataclass
class RecipeWelfareCost:
    total_welfare_years: float
    welfare_years_per_serving: float
    welfare_years_per_kcal: float
    total_animal_kcal: float
    per_ingredient: list[IngredientCost] = field(default_factory=list)


def recipe_welfare_cost(
    ingredients: list[dict[str, Any]],
    servings: int,
) -> RecipeWelfareCost:
    """Compute total welfare cost for a list of extracted ingredients.

    Each item in ingredients must have 'ingredient_type' and 'quantity' keys.
    Unknown ingredient types are silently skipped.
    """
    per_ingredient = []
    for item in ingredients:
        itype = item.get("ingredient_type", "")
        qty = item.get("quantity", 0)
        if itype not in INGREDIENTS or qty <= 0:
            continue
        kcal = ingredient_kcal(itype, qty)
        wy = ingredient_welfare_cost(itype, qty)
        per_ingredient.append(IngredientCost(itype, qty, kcal, wy))

    total_wy = sum(ic.welfare_years for ic in per_ingredient)
    total_kcal = sum(ic.kcal for ic in per_ingredient)

    return RecipeWelfareCost(
        total_welfare_years=total_wy,
        welfare_years_per_serving=total_wy / servings if servings > 0 else 0.0,
        welfare_years_per_kcal=total_wy / total_kcal if total_kcal > 0 else 0.0,
        total_animal_kcal=total_kcal,
        per_ingredient=per_ingredient,
    )


def compute_industry_standard(dish_name: str) -> RecipeWelfareCost:
    """Compute welfare cost for a dish's industry-standard recipe."""
    for dish in DISHES:
        if dish["dish"] == dish_name:
            return recipe_welfare_cost(
                dish["industry_standard_animal_ingredients"],
                dish["servings"],
            )
    raise ValueError(f"Unknown dish: {dish_name}")
