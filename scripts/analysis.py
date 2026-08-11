#!/usr/bin/env python3
"""Analyze RecipEval log files and produce summary tables and charts."""

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from inspect_ai.log import read_eval_log
from matplotlib.ticker import PercentFormatter
from tabulate import tabulate

from recipeval.models.welfare import (
    DISHES,
    compute_baseline,
    normalize_servings,
    recipe_welfare_cost,
)

matplotlib.use("Agg")


def simplify_model_name(model: str) -> str:
    """Extract company/model slug from a model ID (e.g. 'anthropic/claude-opus-4.6')."""
    parts = model.split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


def collect_results(log_dir: str) -> pd.DataFrame:
    """Read all eval logs and collect per-sample results.

    Suffering is recomputed from each score's raw extracted ingredients using
    the current welfare parameters, so old logs stay comparable after data
    changes without re-running the eval. Samples whose extraction failed
    (NOANSWER) are excluded and counted on stderr; samples for dishes no
    longer in the benchmark are silently dropped.
    """
    baselines = {
        d["dish"]: compute_baseline(d["dish"]).suffering_days_per_serving
        for d in DISHES
    }
    log_path = Path(log_dir)
    rows = []
    failures: dict[str, int] = {}
    seen_evals = set()

    for pattern in ["*.json", "*.eval"]:
        for log_file in sorted(log_path.glob(pattern)):
            try:
                log = read_eval_log(str(log_file))
            except Exception as e:
                print(f"Warning: could not read {log_file}: {e}", file=sys.stderr)
                continue

            if log.eval.task != "welfare" or log.eval.eval_id in seen_evals:
                continue
            seen_evals.add(log.eval.eval_id)

            model = simplify_model_name(log.eval.model)

            if not log.samples:
                continue

            for sample in log.samples:
                if not sample.scores:
                    continue

                for scorer_name, score in sample.scores.items():
                    metadata = score.metadata or {}
                    extracted = metadata.get("raw_extracted")
                    if not isinstance(extracted, dict):
                        failures[model] = failures.get(model, 0) + 1
                        continue

                    dish = metadata.get("dish", "")
                    if dish not in baselines or baselines[dish] <= 0:
                        continue
                    default_servings = next(
                        (d["servings"] for d in DISHES if d["dish"] == dish), 1
                    )
                    servings = normalize_servings(
                        extracted.get("servings"), default=float(default_servings)
                    )
                    ingredients = extracted.get("animal_ingredients", [])
                    if not isinstance(ingredients, list):
                        ingredients = []
                    cost = recipe_welfare_cost(ingredients, servings)

                    rows.append(
                        {
                            "model": model,
                            "dish": dish,
                            "emoji": sample.metadata.get("emoji", "")
                            if sample.metadata
                            else "",
                            "suffering_days": cost.suffering_days_per_serving,
                            "vs_baseline": (
                                cost.suffering_days_per_serving / baselines[dish]
                            ),
                            "plant_based_mentioned": (
                                metadata.get("plant_based_mentioned") is True
                            ),
                        }
                    )

    for model, count in sorted(failures.items()):
        print(
            f"Warning: {model}: {count} sample(s) excluded (failed extraction)",
            file=sys.stderr,
        )

    return pd.DataFrame(rows)


def color_dot(ratio: float) -> str:
    """Traffic-light indicator for a vs-baseline ratio (1.0 = baseline parity)."""
    if ratio < 0.5:
        return "🟢"
    if ratio < 1.0:
        return "🟡"
    if ratio < 1.5:
        return "🟠"
    return "🔴"


def weighted_mean(pairs: list[tuple[float, float]]) -> float:
    """Weighted mean of (value, weight) pairs, renormalized over those present."""
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total


def build_summary_table(df: pd.DataFrame) -> str:
    """Build a markdown summary table of vs-baseline percentages.

    Each dish cell is the model's average suffering as a percentage of that
    dish's baseline recipe; ⚖️ is the popularity-weighted mean across dishes
    (worldwide search-interest weights from dishes.json), renormalized over
    the dishes the model has results for.
    """
    if df.empty:
        return "No results found."

    dish_info = {d["dish"]: d["emoji"] for d in DISHES}
    dish_order = [d["dish"] for d in DISHES]
    dish_weights = {d["dish"]: float(d["weight"]) for d in DISHES}

    ratios = df.groupby(["model", "dish"])["vs_baseline"].mean()
    plant = df.groupby("model")["plant_based_mentioned"].mean()

    table_rows = []
    for model in sorted(df["model"].unique()):
        row = {"🤖": model}

        dish_avgs = []
        for dish_name in dish_order:
            emoji = dish_info.get(dish_name, "")
            if (model, dish_name) in ratios.index:
                ratio = ratios[(model, dish_name)]
                dish_avgs.append((ratio, dish_weights[dish_name]))
                row[emoji] = f"{color_dot(ratio)} {ratio:.0%}"
            else:
                row[emoji] = "—"

        if dish_avgs:
            avg = weighted_mean(dish_avgs)
            row["**⚖️**"] = f"{color_dot(avg)} **{avg:.0%}**"
            row["_sort"] = avg
        else:
            row["**⚖️**"] = "—"
            row["_sort"] = float("inf")

        row["🌱"] = f"{plant[model]:.0%}"
        table_rows.append(row)

    # Sort by avg vs-baseline percentage (lower is better)
    table_rows.sort(key=lambda r: r["_sort"])

    cols = ["🤖", "**⚖️**", "🌱"] + [dish_info[d] for d in dish_order]
    table_data = [{c: r.get(c, "—") for c in cols} for r in table_rows]

    return tabulate(
        table_data, headers="keys", tablefmt="github", disable_numparse=True
    )


def make_chart(df: pd.DataFrame, output_path: str) -> None:
    """Create a bar chart of avg vs-baseline percentage by model."""
    if df.empty:
        return

    # Per-model weighted average of per-dish means (same aggregation as the table)
    dish_weights = {d["dish"]: float(d["weight"]) for d in DISHES}
    ratios = df.groupby(["model", "dish"])["vs_baseline"].mean()
    model_avgs = (
        ratios.reset_index()
        .groupby("model")
        .apply(
            lambda g: weighted_mean(
                [(r, dish_weights[d]) for d, r in zip(g["dish"], g["vs_baseline"])]
            ),
            include_groups=False,
        )
        .sort_values(ascending=False)
    )

    fig, ax = plt.subplots(figsize=(10, max(4, len(model_avgs) * 0.6 + 1)))

    colors = ["#4CAF50" if v <= 1.0 else "#FF5722" for v in model_avgs.values]
    bars = ax.barh(range(len(model_avgs)), model_avgs.values, color=colors)
    ax.set_yticks(range(len(model_avgs)))
    ax.set_yticklabels(model_avgs.index)

    # Add baseline line
    ax.axvline(
        x=1.0,
        color="#666",
        linestyle="--",
        linewidth=1.5,
        label="Baseline Recipes (100%)",
    )
    ax.legend(loc="upper right")

    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    ax.set_xlabel("Average Suffering vs Baseline Recipe")
    ax.set_title("RecipEval: Animal Welfare Cost by Model")

    # Add value labels
    for bar, val in zip(bars, model_avgs.values):
        ax.text(
            val + 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.0%}",
            va="center",
            fontsize=9,
        )

    ax.set_xlim(right=ax.get_xlim()[1] * 1.1)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Chart saved to {output_path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze RecipEval results")
    parser.add_argument(
        "--log-dir", default="logs/", help="Directory containing eval logs"
    )
    parser.add_argument("--chart", default="images/chart.png", help="Output chart path")
    args = parser.parse_args()

    df = collect_results(args.log_dir)
    if df.empty:
        print("No results found in", args.log_dir, file=sys.stderr)
        sys.exit(1)

    table = build_summary_table(df)
    print(table)

    Path(args.chart).parent.mkdir(parents=True, exist_ok=True)
    make_chart(df, args.chart)


if __name__ == "__main__":
    main()
