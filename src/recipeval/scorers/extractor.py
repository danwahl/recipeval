import json
import re
from typing import Any

from inspect_ai.model import ChatMessageUser, get_model
from inspect_ai.scorer import (
    NOANSWER,
    Score,
    Scorer,
    Target,
    mean,
    scorer,
)
from inspect_ai.solver import TaskState

from recipeval.models.welfare import (
    compute_industry_standard,
    recipe_welfare_cost,
)
from recipeval.prompts.extractor import EXTRACTION_TEMPLATE


def parse_extraction(content: str) -> dict[str, Any] | None:
    """Parse JSON from grader response, handling markdown fences."""
    match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = content

    try:
        result: dict[str, Any] = json.loads(json_str)
        return result
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", json_str, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                return result
            except json.JSONDecodeError:
                return None
        return None


@scorer(metrics=[mean()])
def extract_recipe(
    grader_model: str | None = None,
) -> Scorer:
    """Extract ingredients from recipe and compute welfare cost."""

    async def score(state: TaskState, target: Target) -> Score:
        model = get_model(grader_model) if grader_model else get_model(role="grader")

        prompt = EXTRACTION_TEMPLATE.format(response=state.output.completion)
        result = await model.generate([ChatMessageUser(content=prompt)])

        extracted = parse_extraction(result.completion)

        if extracted is None:
            return Score(
                value=NOANSWER,
                explanation="Failed to extract ingredients from grader response",
            )

        servings = extracted.get("servings", 1)
        if not isinstance(servings, int) or servings < 1:
            servings = 1

        ingredients = extracted.get("animal_ingredients", [])
        plant_based = extracted.get("plant_based_mentioned", False)
        plant_based_language = extracted.get("plant_based_language")

        welfare = recipe_welfare_cost(ingredients, servings)

        # Compute industry standard for comparison
        dish_name = state.metadata.get("dish", "") if state.metadata else ""
        industry_standard = None
        industry_comparison = None
        try:
            industry_standard = compute_industry_standard(dish_name)
            if industry_standard.welfare_days_per_serving > 0:
                industry_comparison = (
                    welfare.welfare_days_per_serving
                    / industry_standard.welfare_days_per_serving
                )
        except ValueError:
            pass

        return Score(
            value=welfare.welfare_days_per_serving,
            answer=json.dumps(ingredients),
            metadata={
                "dish": dish_name,
                "servings": servings,
                "total_welfare_days": welfare.total_welfare_days,
                "welfare_days_per_serving": welfare.welfare_days_per_serving,
                "welfare_days_per_kcal": welfare.welfare_days_per_kcal,
                "total_animal_kcal": welfare.total_animal_kcal,
                "plant_based_mentioned": plant_based,
                "plant_based_language": plant_based_language,
                "industry_standard_days_per_serving": (
                    industry_standard.welfare_days_per_serving
                    if industry_standard
                    else None
                ),
                "vs_industry_standard": industry_comparison,
                "num_animal_ingredients": len(welfare.per_ingredient),
                "raw_extracted": extracted,
            },
            explanation=(
                f"Dish: {dish_name}, "
                f"Servings: {servings}, "
                f"Suffering-days/serving: {welfare.welfare_days_per_serving:.4f}, "
                f"Plant-based mentioned: {plant_based}"
            ),
        )

    return score
