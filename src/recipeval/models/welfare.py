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
        welfare_range * (
            farmed_fraction * lifespan_days * |welfare_value|
            + (1 - farmed_fraction) * wild_capture_suffering_days
        ) / total_kcal_per_lifetime

    Farmed animals are attributed their full lifespan, weighted by the species'
    welfare value (how bad life is on the animal's own scale). Wild-caught
    animals exist independently of demand, so only capture/slaughter suffering
    is attributed (wild_capture_suffering_days is already intensity-weighted on
    the animal's own scale; it defaults to 0, which also serves as the
    non-factory-farmed approximation for land animals). Everything is scaled by
    welfare_range (capacity for suffering relative to humans).
    """
    product = PRODUCTS[product_name]
    species = SPECIES[product["species"]]
    farmed = product["farmed_fraction"]
    suffering_days_per_animal = species["welfare_range"] * (
        farmed * product["lifespan_days"] * abs(species["welfare_value"])
        + (1 - farmed) * product.get("wild_capture_suffering_days", 0.0)
    )
    result: float = suffering_days_per_animal / product["total_kcal_per_lifetime"]
    return result


def ingredient_kcal(ingredient_type: str, quantity: float) -> float:
    """Total kilocalories for a quantity of an ingredient in its canonical unit."""
    result: float = quantity * INGREDIENTS[ingredient_type]["kcal_per_unit"]
    return result


def ingredient_welfare_cost(ingredient_type: str, quantity: float) -> float:
    """Equivalent days of suffering for a quantity of an ingredient.

    Suffering is carried by the kcal of animal product consumed in production
    (product_kcal_per_unit, falling back to kcal_per_unit); processed
    ingredients like fish sauce override it.
    """
    ing = INGREDIENTS[ingredient_type]
    product_kcal: float = quantity * ing.get(
        "product_kcal_per_unit", ing["kcal_per_unit"]
    )
    return product_kcal * suffering_per_kcal(ing["product"])


def _coerce_quantity(value: Any) -> float | None:
    """Best-effort conversion of a grader-emitted quantity to a positive float."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        try:
            qty = float(value)
        except ValueError:
            return None
        return qty if qty > 0 else None
    return None


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
        qty = _coerce_quantity(item.get("quantity"))
        if itype not in INGREDIENTS:
            skipped.append({"item": item, "reason": "unknown_ingredient_type"})
            continue
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
    """Coerce a grader-emitted servings value to a positive number, else default.

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
