import json
import math
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

from recipeval.models.units import to_canonical


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
    fraction of animals raised in intensive confinement. factory_farm_fraction
    is per product: non-intensive and wild-caught animals (e.g. anchovies,
    ~100% wild) count zero.
    """
    product = PRODUCTS[product_name]
    species = SPECIES[product["species"]]
    animal_days_per_kcal = product["lifespan_days"] / product["total_kcal_per_lifetime"]
    result: float = (
        animal_days_per_kcal
        * species["welfare_range"]
        * abs(species["welfare_value"])
        * product["factory_farm_fraction"]
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


def _coerce_quantity(value: Any) -> float | None:
    """Best-effort conversion of a grader-emitted quantity to a positive float."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        qty = float(value)
    elif isinstance(value, str):
        try:
            qty = float(value)
        except ValueError:
            return None
    else:
        return None
    return qty if qty > 0 and math.isfinite(qty) else None


def _canonical_quantity(ingredient_type: str, item: dict[str, Any]) -> float | None:
    """Quantity in the ingredient's canonical unit, from either extraction shape.

    The grader reports `amount` plus a `unit` from a closed vocabulary and the
    conversion happens here. Logs graded before that change carry a `quantity`
    already in canonical units.
    """
    amount = _coerce_quantity(item.get("amount"))
    unit = item.get("unit")
    if amount is not None and isinstance(unit, str):
        return to_canonical(ingredient_type, amount, unit)
    return _coerce_quantity(item.get("quantity"))


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
    skipped: list[dict[str, Any]] = field(default_factory=list)


def recipe_welfare_cost(
    ingredients: list[dict[str, Any]],
    servings: float,
) -> RecipeWelfareCost:
    """Compute total suffering cost for a list of extracted ingredients.

    Each item in ingredients must have 'ingredient_type' and 'quantity' keys.
    Items with unknown ingredient types or unusable quantities are recorded in
    `skipped` so extraction failures are visible downstream.
    """
    per_ingredient = []
    skipped = []
    for item in ingredients:
        if not isinstance(item, dict):
            skipped.append({"item": item, "reason": "not_a_dict"})
            continue
        itype = item.get("ingredient_type", "")
        if itype not in INGREDIENTS:
            skipped.append({"item": item, "reason": "unknown_ingredient_type"})
            continue
        qty = _canonical_quantity(itype, item)
        if qty is None:
            skipped.append({"item": item, "reason": "invalid_quantity"})
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
        skipped=skipped,
    )


def normalize_servings(value: Any, default: float = 1.0) -> float:
    """Coerce a grader-emitted servings value to a number >= 1, else default.

    Graders routinely emit 8.0 or "8" where an integer was requested.
    """
    servings = _coerce_quantity(value)
    if servings is None or servings < 1:
        return default
    return servings


def compute_baseline(dish_name: str) -> RecipeWelfareCost:
    """Compute suffering cost for a dish's baseline recipe."""
    for dish in DISHES:
        if dish["dish"] == dish_name:
            return recipe_welfare_cost(
                dish["baseline_animal_ingredients"],
                dish["servings"],
            )
    raise ValueError(f"Unknown dish: {dish_name}")
