#!/usr/bin/env python3
"""Diagnostic: compare the benchmark's weighted animal-calorie exposure
against worldwide consumption shares.

For each dish baseline, ingredient calories are grouped by consumption
category and weighted by the dish's popularity weight. The resulting shares
show which animal categories the benchmark's baselines expose models to,
next to each category's share of worldwide animal-source calories (FAO food
balance sheets via Our World in Data; fish split via FAO SOFIA). This is a
published diagnostic, not an input to scoring.
"""

import sys

from tabulate import tabulate

from recipeval.models.welfare import DISHES, INGREDIENTS, PRODUCTS

# Product -> consumption category
CATEGORY = {
    "dairy": "dairy",
    "pork": "pork",
    "chicken_meat": "chicken",
    "beef": "beef",
    "chicken_egg": "eggs",
    "fish_large": "farmed fish",
    "fish_small": "wild fish",
    "shrimp": "shrimp",
}

# Share of worldwide animal-source food calories, FAO/OWID + FAO SOFIA
FAO_KCAL_SHARE = {
    "dairy": 0.33,
    "pork": 0.18,
    "chicken": 0.17,
    "beef": 0.11,
    "eggs": 0.08,
    "farmed fish": 0.07,
    "wild fish": 0.06,
    "shrimp": 0.003,
}


def benchmark_exposure() -> dict[str, float]:
    """Popularity-weighted share of baseline calories by consumption category."""
    total_weight = sum(d["weight"] for d in DISHES)
    exposure: dict[str, float] = {c: 0.0 for c in FAO_KCAL_SHARE}

    for dish in DISHES:
        dish_kcal: dict[str, float] = {}
        for ing in dish["baseline_animal_ingredients"]:
            info = INGREDIENTS[ing["ingredient_type"]]
            category = CATEGORY[info["product"]]
            kcal = ing["quantity"] * info["kcal_per_unit"]
            dish_kcal[category] = dish_kcal.get(category, 0.0) + kcal

        dish_total = sum(dish_kcal.values())
        for category, kcal in dish_kcal.items():
            exposure[category] += (kcal / dish_total) * (dish["weight"] / total_weight)

    return exposure


def main() -> None:
    exposure = benchmark_exposure()
    fao_total = sum(FAO_KCAL_SHARE.values())

    rows = []
    for category in FAO_KCAL_SHARE:
        bench = exposure[category]
        fao = FAO_KCAL_SHARE[category] / fao_total
        ratio = bench / fao if fao else float("inf")
        rows.append(
            {
                "category": category,
                "benchmark": f"{bench:.1%}",
                "consumption": f"{fao:.1%}",
                "ratio": f"{ratio:.2f}x",
            }
        )

    print(tabulate(rows, headers="keys", tablefmt="github", disable_numparse=True))
    unmapped = sorted(set(PRODUCTS) - set(CATEGORY))
    if unmapped:
        print(f"Warning: unmapped products: {unmapped}", file=sys.stderr)
    print(
        "\nbenchmark = popularity-weighted share of baseline animal calories;"
        "\nconsumption = category share of worldwide animal-source calories.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
