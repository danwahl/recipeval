#!/usr/bin/env python3
"""Measure how consistently a grader extracts the same recipes twice.

Recipe text is held fixed from an existing eval log and graded twice at
temperature 0, so any disagreement is the grader's own noise rather than the
model under test varying. Pass two prompt files to compare them on the same
inputs.

    uv run scripts/grader_agreement.py logs/<run>.eval
    uv run scripts/grader_agreement.py logs/<run>.eval --limit 40
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from inspect_ai.log import read_eval_log
from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model

from recipeval.models.welfare import normalize_servings, recipe_welfare_cost
from recipeval.prompts.extractor import EXTRACTION_TEMPLATE
from recipeval.scorers.extractor import (
    GRADER_ATTEMPT_TIMEOUT,
    GRADER_MAX_TOKENS,
    parse_extraction,
)

CONFIG = GenerateConfig(
    temperature=0.0,
    max_tokens=GRADER_MAX_TOKENS,
    reasoning_effort="low",
    attempt_timeout=GRADER_ATTEMPT_TIMEOUT,
)


def load_recipes(log_file: str, limit: int | None) -> list[tuple[str, str, int]]:
    """(dish, recipe text, default servings) for each sample in a log."""
    log = read_eval_log(log_file)
    out = []
    for sample in log.samples or []:
        text = sample.output.completion if sample.output else ""
        meta = sample.metadata or {}
        if text:
            out.append((meta.get("dish", ""), text, int(meta.get("servings", 1))))
    return out[:limit] if limit else out


async def grade(model_name: str, template: str, text: str) -> dict | None:
    model = get_model(model_name)
    result = await model.generate(
        [ChatMessageUser(content=template.replace("{response}", text))], config=CONFIG
    )
    return parse_extraction(result.completion)


def cost_of(extracted: dict | None, default_servings: int) -> float | None:
    """Suffering-days per serving, the number the benchmark actually reports."""
    if not isinstance(extracted, dict):
        return None
    servings = normalize_servings(
        extracted.get("servings"), default=float(default_servings)
    )
    ingredients = extracted.get("animal_ingredients", [])
    if not isinstance(ingredients, list):
        ingredients = []
    return recipe_welfare_cost(ingredients, servings).suffering_days_per_serving


async def run_arm(
    name: str, model: str, template: str, recipes: list[tuple[str, str, int]]
) -> None:
    started = time.time()
    passes = []
    for _ in range(2):
        passes.append(
            await asyncio.gather(*(grade(model, template, t) for _, t, _ in recipes))
        )

    identical = close = failures = 0
    for (dish, _, servings), a, b in zip(recipes, *passes):
        ca, cb = cost_of(a, servings), cost_of(b, servings)
        if ca is None or cb is None:
            failures += 1
            continue
        if ca == cb:
            identical += 1
        if max(ca, cb) <= 1.05 * min(ca, cb):
            close += 1

    n = len(recipes)
    print(
        f"{name:28} identical {identical / n:5.0%}  within 5% {close / n:5.0%}  "
        f"failures {failures}/{n}  wall {(time.time() - started) / 60:.1f} min"
    )


async def show_diffs(
    model: str, other: str, recipes: list[tuple[str, str, int]]
) -> None:
    """Grade once under each prompt and print where the two disagree.

    Consistency says nothing about which prompt is right, so the dishes that
    move most are the ones worth reading by hand against the recipe text.
    """
    new, old = (
        await asyncio.gather(
            *(grade(model, EXTRACTION_TEMPLATE, t) for _, t, _ in recipes)
        ),
        await asyncio.gather(*(grade(model, other, t) for _, t, _ in recipes)),
    )
    rows = []
    for (dish, _, servings), a, b in zip(recipes, new, old):
        ca, cb = cost_of(a, servings), cost_of(b, servings)
        if ca is None or cb is None or cb == 0:
            continue
        rows.append((abs(ca / cb - 1), dish, cb, ca, b, a))

    print(f"\n{'dish':24} {'old':>9} {'new':>9}   change")
    for delta, dish, cb, ca, b, a in sorted(rows, reverse=True)[:12]:
        print(f"{dish:24} {cb:9.4f} {ca:9.4f}   {ca / cb - 1:+.0%}")
        print(f"    old: {json.dumps(b.get('animal_ingredients'))}")
        print(f"    new: {json.dumps(a.get('animal_ingredients'))}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_file")
    ap.add_argument("--model", default="openrouter/google/gemini-3.7-flash")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--baseline-prompt",
        default=None,
        help="JSON file of a prompt to compare against",
    )
    ap.add_argument(
        "--diff",
        action="store_true",
        help="show per-dish disagreements between the two prompts",
    )
    args = ap.parse_args()

    recipes = load_recipes(args.log_file, args.limit)
    print(
        f"{len(recipes)} recipes from {Path(args.log_file).name}, graded twice each\n"
    )
    other = (
        json.loads(Path(args.baseline_prompt).read_text())["template"]
        if args.baseline_prompt
        else None
    )

    if args.diff and other:
        await show_diffs(args.model, other, recipes)
        return

    await run_arm("current prompt", args.model, EXTRACTION_TEMPLATE, recipes)
    if other:
        await run_arm("comparison prompt", args.model, other, recipes)


if __name__ == "__main__":
    asyncio.run(main())
