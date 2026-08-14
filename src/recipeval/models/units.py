"""Conversion from grader-reported units to each ingredient's canonical unit.

The grader reports what a recipe says (`2 lb`, `1 whole bird`, `3 slices`) and
this table does the arithmetic. Units are a closed vocabulary: entries like
`whole_bird_lb` or `slice_bacon` carry the domain judgement (a whole bird is
~50% edible meat, a bacon slice is ~0.5 oz cooked) that the extraction prompt
used to ask the grader to apply inline.
"""

# Mass units expressed in ounces.
_OZ = {"oz": 1.0, "lb": 16.0, "g": 0.035274, "kg": 35.274}

# Volume units expressed in cups.
_CUP = {
    "cup": 1.0,
    "tbsp": 1.0 / 16,
    "tsp": 1.0 / 48,
    "fl_oz": 0.125,
    "ml": 1.0 / 236.6,
    "l": 4.2268,
    "pint": 2.0,
    "quart": 4.0,
}

# Volume units expressed in tablespoons.
_TBSP = {unit: factor * 16 for unit, factor in _CUP.items()}

# Cuts sold on the bone yield ~80% meat; a whole bird ~50%.
_MEAT = {
    **_OZ,
    "bone_in_oz": 0.8,
    "bone_in_lb": 12.8,
    "bone_in_g": 0.028219,
    "bone_in_kg": 28.219,
    "whole_bird_oz": 0.5,
    "whole_bird_lb": 8.0,
    "whole_bird_kg": 17.637,
    # Broth and stock carry a little of the animal they are named for.
    "cup_broth": 0.5,
    "ml_broth": 0.5 / 236.6,
    "l_broth": 2.1134,
}

# (ingredient_type, unit) -> quantity in that ingredient's canonical unit.
CONVERSIONS: dict[str, dict[str, float]] = {
    "beef": _MEAT,
    "pork": {
        **_MEAT,
        "slice_bacon": 0.5,
        "slice_deli": 1.0 / 15,
    },
    "chicken": {
        **_MEAT,
        "breast": 6.0,
        "thigh": 3.5,
        "cup_cooked": 5.0,
        "slice_deli": 1.0 / 15,
    },
    "shrimp": _OZ,
    "fish_large": {**_OZ, "fillet": 6.0, "can": 5.0, "cup_broth": 0.5},
    "hard_cheese": {**_OZ, "cup": 3.6, "tbsp": 0.225},
    "soft_cheese": {**_OZ, "cup": 4.0, "tbsp": 0.25},
    "anchovies": {"fillet": 1.0, "count": 1.0, "oz": 7.0, "g": 0.25, "can": 12.0},
    "eggs": {
        "count": 1.0,
        "large": 1.0,
        "yolk": 1.0,
        "white": 1.0,
        "cup_mayo": 1.0,
        "tbsp_mayo": 1.0 / 16,
    },
    "butter": {**_TBSP, "stick": 8.0, "g": 1.0 / 14, "oz": 2.0, "lb": 32.0},
    "fish_sauce": _TBSP,
    "milk": _CUP,
    "heavy_cream": _CUP,
    "sour_cream": _CUP,
    "yogurt": _CUP,
    "evaporated_milk": {**_CUP, "can": 1.5},
}

# Every unit the grader is allowed to report, for the prompt and for validation.
VALID_UNITS: list[str] = sorted({u for table in CONVERSIONS.values() for u in table})


def to_canonical(ingredient_type: str, amount: float, unit: str) -> float | None:
    """Convert an amount in a reported unit to the ingredient's canonical unit.

    Returns None when the ingredient or the unit-ingredient pairing is unknown,
    so the caller can record the item as skipped rather than guess at it.
    """
    factor = CONVERSIONS.get(ingredient_type, {}).get(unit)
    return None if factor is None else amount * factor
