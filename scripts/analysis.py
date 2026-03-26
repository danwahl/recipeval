#!/usr/bin/env python3
"""Analyze RecipEval log files and produce summary tables and charts."""

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from inspect_ai.log import read_eval_log
from tabulate import tabulate

from recipeval.models.welfare import DISHES, compute_baseline

matplotlib.use("Agg")


def simplify_model_name(model: str) -> str:
    """Extract company/model slug from a model ID (e.g. 'anthropic/claude-opus-4.6')."""
    parts = model.split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


def collect_results(log_dir: str) -> pd.DataFrame:
    """Read all eval logs and collect per-sample results."""
    log_path = Path(log_dir)
    rows = []

    for pattern in ["*.json", "*.eval"]:
        for log_file in sorted(log_path.glob(pattern)):
            try:
                log = read_eval_log(str(log_file))
            except Exception as e:
                print(f"Warning: could not read {log_file}: {e}", file=sys.stderr)
                continue

            model = simplify_model_name(log.eval.model)

            if not log.samples:
                continue

            for sample in log.samples:
                if not sample.scores:
                    continue

                for scorer_name, score in sample.scores.items():
                    metadata = score.metadata or {}
                    rows.append(
                        {
                            "model": model,
                            "dish": metadata.get("dish", ""),
                            "emoji": sample.metadata.get("emoji", "")
                            if sample.metadata
                            else "",
                            "suffering_days": metadata.get(
                                "suffering_days_per_serving", 0
                            ),
                            "plant_based_mentioned": metadata.get(
                                "plant_based_mentioned", False
                            ),
                            "vs_baseline": metadata.get("vs_baseline"),
                        }
                    )

    return pd.DataFrame(rows)


def build_summary_table(df: pd.DataFrame) -> str:
    """Build a markdown summary table from results."""
    if df.empty:
        return "No results found."

    # Get dish info for columns
    dish_info = {d["dish"]: d["emoji"] for d in DISHES}
    dish_order = [d["dish"] for d in DISHES]

    models = sorted(df["model"].unique())

    # Build baseline row
    baseline_row = {"🤖": "*Baseline Recipes*"}
    baseline_values = []
    for dish_name in dish_order:
        try:
            std = compute_baseline(dish_name)
            days = std.suffering_days_per_serving
            baseline_values.append(days)
            emoji = dish_info.get(dish_name, "")
            baseline_row[f"{emoji}"] = f"{days:.2f}"
        except ValueError:
            baseline_values.append(0)
            emoji = dish_info.get(dish_name, "")
            baseline_row[f"{emoji}"] = "—"

    baseline_row["**⚖️**"] = f"**{sum(baseline_values) / len(baseline_values):.2f}**"
    baseline_row["🌱"] = "—"

    table_rows = []

    for model in models:
        mdf = df[df["model"] == model]
        row = {"🤖": model}

        dish_avgs = []
        for dish_name in dish_order:
            ddf = mdf[mdf["dish"] == dish_name]
            emoji = dish_info.get(dish_name, "")
            if not ddf.empty:
                avg_days = ddf["suffering_days"].mean()
                dish_avgs.append(avg_days)
                row[f"{emoji}"] = f"{avg_days:.2f}"
            else:
                row[f"{emoji}"] = "—"

        if dish_avgs:
            row["**⚖️**"] = f"**{sum(dish_avgs) / len(dish_avgs):.2f}**"
        else:
            row["**⚖️**"] = "—"

        pct_plant = mdf["plant_based_mentioned"].mean() * 100
        row["🌱"] = f"{pct_plant:.0f}%"

        table_rows.append(row)

    # Sort by avg suffering-days/serving (lower is better)
    table_rows.append(baseline_row)
    table_rows.sort(
        key=lambda r: (
            float(r["**⚖️**"].strip("*")) if r["**⚖️**"] != "—" else float("inf")
        )
    )

    # Build column order
    cols = ["🤖", "**⚖️**", "🌱"]
    for dish_name in dish_order:
        emoji = dish_info.get(dish_name, "")
        cols.append(f"{emoji}")

    table_data = [{c: r.get(c, "—") for c in cols} for r in table_rows]

    return tabulate(
        table_data, headers="keys", tablefmt="github", disable_numparse=True
    )


def make_chart(df: pd.DataFrame, output_path: str) -> None:
    """Create a bar chart of avg suffering-days/serving by model."""
    if df.empty:
        return

    # Compute per-model averages
    model_avgs = (
        df.groupby("model")["suffering_days"].mean().sort_values(ascending=False)
    )

    # Add baseline reference
    baseline_values = []
    for dish in DISHES:
        std = compute_baseline(dish["dish"])
        baseline_values.append(std.suffering_days_per_serving)
    baseline_avg = sum(baseline_values) / len(baseline_values)

    fig, ax = plt.subplots(figsize=(10, max(4, len(model_avgs) * 0.6 + 1)))

    colors = ["#4CAF50" if v <= baseline_avg else "#FF5722" for v in model_avgs.values]
    bars = ax.barh(range(len(model_avgs)), model_avgs.values, color=colors)
    ax.set_yticks(range(len(model_avgs)))
    ax.set_yticklabels(model_avgs.index)

    # Add baseline line
    ax.axvline(
        x=baseline_avg,
        color="#666",
        linestyle="--",
        linewidth=1.5,
        label=f"Baseline Recipes ({baseline_avg:.2f})",
    )
    ax.legend(loc="upper right")

    ax.set_xlabel("Average Suffering-Days/Serving")
    ax.set_title("RecipEval: Animal Welfare Cost by Model")

    # Add value labels
    for bar, val in zip(bars, model_avgs.values):
        ax.text(
            val + 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.2f}",
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
