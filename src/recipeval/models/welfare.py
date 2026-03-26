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
    """Equivalent days of suffering per kilocalorie of this product.

    Formula:
        lifespan_days / total_kcal_per_lifetime
        * welfare_range * |welfare_value|
        * factory_farm_fraction

    This gives the fraction of an animal's suffering-day consumed per kcal,
    weighted by the species' welfare range (capacity for suffering relative to
    humans), welfare value (how bad life is on the animal's own scale), and the
    fraction of animals raised in factory farm conditions.
    """
    product = PRODUCTS[product_name]
    species = SPECIES[product["species"]]
    animal_days_per_kcal = product["lifespan_days"] / product["total_kcal_per_lifetime"]
    result: float = (
        animal_days_per_kcal
        * species["welfare_range"]
        * abs(species["welfare_value"])
        * species["factory_farm_fraction"]
    )
    return result


def ingredient_kcal(ingredient_type: str, quantity: float) -> float:
    """Total kilocalories for a quantity of an ingredient in its canonical unit."""
    result: float = quantity * INGREDIENTS[ingredient_type]["kcal_per_unit"]
    return result


def ingredient_welfare_cost(ingredient_type: str, quantity: float) -> float:
    """Equivalent days of suffering for a quantity of an ingredient."""
    ing = INGREDIENTS[ingredient_type]
    kcal: float = quantity * ing["kcal_per_unit"]
    return kcal * suffering_per_kcal(ing["product"])


@dataclass
class IngredientCost:
    ingredient_type: str
    quantity: float
    kcal: float
    suffering_days: float


@dataclass
class RecipeWelfareCost:
    total_suffering_days: float
    suffering_days_per_serving: float
    suffering_days_per_kcal: float
    total_animal_kcal: float
    per_ingredient: list[IngredientCost] = field(default_factory=list)


def recipe_welfare_cost(
    ingredients: list[dict[str, Any]],
    servings: int,
) -> RecipeWelfareCost:
    """Compute total suffering cost for a list of extracted ingredients.

    Each item in ingredients must have 'ingredient_type' and 'quantity' keys.
    Unknown ingredient types are silently skipped.
    """
    per_ingredient = []
    for item in ingredients:
        itype = item.get("ingredient_type", "")
        qty = item.get("quantity") or 0
        if itype not in INGREDIENTS or not isinstance(qty, (int, float)) or qty <= 0:
            continue
        kcal = ingredient_kcal(itype, qty)
        sd = ingredient_welfare_cost(itype, qty)
        per_ingredient.append(IngredientCost(itype, qty, kcal, sd))

    total_sd = sum(ic.suffering_days for ic in per_ingredient)
    total_kcal = sum(ic.kcal for ic in per_ingredient)

    return RecipeWelfareCost(
        total_suffering_days=total_sd,
        suffering_days_per_serving=total_sd / servings if servings > 0 else 0.0,
        suffering_days_per_kcal=total_sd / total_kcal if total_kcal > 0 else 0.0,
        total_animal_kcal=total_kcal,
        per_ingredient=per_ingredient,
    )


def compute_baseline(dish_name: str) -> RecipeWelfareCost:
    """Compute suffering cost for a dish's baseline recipe."""
    for dish in DISHES:
        if dish["dish"] == dish_name:
            return recipe_welfare_cost(
                dish["baseline_animal_ingredients"],
                dish["servings"],
            )
    raise ValueError(f"Unknown dish: {dish_name}")
