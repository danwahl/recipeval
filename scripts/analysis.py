#!/usr/bin/env python3
"""Analyze RecipEval log files and produce summary tables and charts."""

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from inspect_ai.log import read_eval_log
from matplotlib.colors import TwoSlopeNorm
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.ticker import PercentFormatter
from PIL import Image, ImageDraw, ImageFont
from tabulate import tabulate

from recipeval.models.welfare import (
    DISHES,
    compute_baseline,
    normalize_servings,
    recipe_welfare_cost,
)

matplotlib.use("Agg")

# Diverging scale centered on baseline parity: green below, red above, with
# both tails saturating so a single outlier does not flatten the rest.
RATIO_CMAP = plt.get_cmap("RdYlGn_r")
RATIO_NORM = TwoSlopeNorm(vmin=0.5, vcenter=1.0, vmax=2.0)
PLANT_CMAP = plt.get_cmap("Greens")


def simplify_model_name(model: str) -> str:
    """Extract company/model slug from a model ID (e.g. 'anthropic/claude-opus-4.6')."""
    parts = model.split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]


def collect_results(log_dir: str) -> pd.DataFrame:
    """Read all eval logs and collect per-sample results.

    Suffering is recomputed from each score's raw extracted ingredients using
    the current welfare parameters, so old logs stay comparable after data
    changes without re-running the eval. Samples whose extraction failed
    (NOANSWER) are excluded and counted on stderr; samples for dishes not in
    the benchmark, or whose baseline is not positive, are silently dropped.
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

                dish = (sample.metadata or {}).get("dish", "")
                if dish not in baselines or baselines[dish] <= 0:
                    continue

                for scorer_name, score in sample.scores.items():
                    metadata = score.metadata or {}
                    extracted = metadata.get("raw_extracted")
                    if not isinstance(extracted, dict):
                        failures[model] = failures.get(model, 0) + 1
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


def ratio_color(ratio: float) -> tuple[float, float, float]:
    """RGB for a vs-baseline ratio on the diverging scale (1.0 = parity)."""
    return RATIO_CMAP(RATIO_NORM(ratio))[:3]


def plant_color(fraction: float) -> tuple[float, float, float]:
    """RGB for a plant-based mention rate on a sequential scale."""
    return PLANT_CMAP(0.12 + 0.55 * fraction)[:3]


def text_color(rgb: tuple[float, float, float]) -> tuple[int, int, int]:
    """Black or white, whichever reads better on the given background."""
    luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    return (0, 0, 0) if luminance > 0.62 else (255, 255, 255)


def to_rgb255(rgb: tuple[float, float, float]) -> tuple[int, int, int]:
    r, g, b = (int(round(255 * c)) for c in rgb)
    return (r, g, b)


def signed_pct(ratio: float) -> str:
    """Deviation from baseline as a signed percentage (1.18 -> '+18%')."""
    points = round(100 * (ratio - 1))
    return "0%" if points == 0 else f"{points:+d}%"


def weighted_mean(pairs: list[tuple[float, float]]) -> float:
    """Weighted mean of (value, weight) pairs, renormalized over those present."""
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total


def summarize(df: pd.DataFrame) -> list[dict]:
    """Per-model summary rows, best (lowest weighted average) first.

    Each dish value is the model's average suffering as a fraction of that
    dish's baseline recipe; ``avg`` is the popularity-weighted mean across
    dishes (worldwide search-interest weights from dishes.json), renormalized
    over the dishes the model has results for.
    """
    dish_order = [d["dish"] for d in DISHES]
    dish_weights = {d["dish"]: float(d["weight"]) for d in DISHES}

    ratios = df.groupby(["model", "dish"])["vs_baseline"].mean()
    plant = df.groupby("model")["plant_based_mentioned"].mean()

    rows = []
    for model in sorted(df["model"].unique()):
        dishes = {
            dish: (ratios[(model, dish)] if (model, dish) in ratios.index else None)
            for dish in dish_order
        }
        present = [(v, dish_weights[d]) for d, v in dishes.items() if v is not None]
        rows.append(
            {
                "model": model,
                "avg": weighted_mean(present) if present else float("inf"),
                "plant": plant[model],
                "dishes": dishes,
            }
        )

    rows.sort(key=lambda r: r["avg"])
    return rows


def build_summary_table(df: pd.DataFrame) -> str:
    """Build a markdown summary table of vs-baseline percentages."""
    if df.empty:
        return "No results found."

    dish_info = {d["dish"]: d["emoji"] for d in DISHES}
    dish_order = [d["dish"] for d in DISHES]

    def dev(value: float | None) -> str:
        return "—" if value is None else signed_pct(value)

    table_data = []
    for row in summarize(df):
        cells = {"🤖": row["model"], "**⚖️**": f"**{dev(row['avg'])}**"}
        cells["🌱"] = f"{row['plant']:.0%}"
        for dish in dish_order:
            cells[dish_info[dish]] = dev(row["dishes"][dish])
        table_data.append(cells)

    return tabulate(
        table_data, headers="keys", tablefmt="github", disable_numparse=True
    )


EMOJI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto-color-emoji/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "C:/Windows/Fonts/seguiemj.ttf",
]


def find_emoji_font() -> str | None:
    """Locate a color emoji font, or None if the system has none."""
    for path in EMOJI_FONT_CANDIDATES:
        if Path(path).exists():
            return path
    try:
        found = findfont(
            FontProperties(family="Noto Color Emoji"), fallback_to_default=False
        )
    except Exception:
        return None
    return found


def render_emoji(char: str, font_path: str, size: int) -> Image.Image:
    """Rasterize one emoji to a square RGBA image of the given pixel size."""
    # Color bitmap fonts only accept their native strike size, so draw large
    # on a generous canvas, crop to ink, then scale down.
    font = ImageFont.truetype(font_path, 109)
    canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text(
        (100, 100), char, font=font, embedded_color=True, anchor="mm"
    )
    box = canvas.getbbox() or (0, 0, 200, 200)
    return canvas.crop(box).resize((size, size), Image.Resampling.LANCZOS)


def make_table_image(df: pd.DataFrame, output_path: str, scale: int = 2) -> None:
    """Render the summary table as a heatmap image with emoji column headers.

    Drawn at ``scale``x and downsampled, which keeps text crisp without
    depending on the viewer's pixel density.
    """
    if df.empty:
        return

    rows = summarize(df)
    dish_order = [d["dish"] for d in DISHES]
    dish_emoji = {d["dish"]: d["emoji"] for d in DISHES}
    emoji_font = find_emoji_font()

    s = scale
    pad, name_w, col_w, row_h, head_h = 8 * s, 250 * s, 56 * s, 30 * s, 46 * s
    gap = 10 * s  # separates the summary columns from the per-dish grid
    legend_h = 62 * s
    width = pad * 2 + name_w + col_w * (2 + len(dish_order)) + gap
    height = head_h + row_h * len(rows) + legend_h

    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    sans = findfont(FontProperties(family="DejaVu Sans"))
    sans_bold = findfont(FontProperties(family="DejaVu Sans", weight="bold"))
    f_cell = ImageFont.truetype(sans, 13 * s)
    f_bold = ImageFont.truetype(sans_bold, 14 * s)
    f_small = ImageFont.truetype(sans, 11 * s)

    columns = [("⚖️", pad + name_w), ("🌱", pad + name_w + col_w)]
    x = pad + name_w + col_w * 2 + gap
    for dish in dish_order:
        columns.append((dish_emoji[dish], x))
        x += col_w

    glyph = 22 * s
    for char, x in columns:
        if emoji_font:
            sprite = render_emoji(char, emoji_font, glyph)
            image.paste(
                sprite, (x + (col_w - glyph) // 2, (head_h - glyph) // 2), sprite
            )
        else:
            draw.text(
                (x + col_w // 2, head_h // 2),
                char,
                font=f_cell,
                fill=(30, 30, 30),
                anchor="mm",
            )

    def cell(x: int, y: int, text: str, rgb: tuple[float, float, float], font) -> None:
        fill = to_rgb255(rgb)
        draw.rectangle([x + s, y + s, x + col_w - s, y + row_h - s], fill=fill)
        draw.text(
            (x + col_w // 2, y + row_h // 2),
            text,
            font=font,
            fill=text_color(rgb),
            anchor="mm",
        )

    for i, row in enumerate(rows):
        y = head_h + i * row_h
        if i % 2:
            draw.rectangle(
                [pad, y, pad + name_w - 2 * s, y + row_h], fill=(245, 245, 245)
            )
        draw.text(
            (pad + 4 * s, y + row_h // 2),
            row["model"],
            font=f_cell,
            fill=(30, 30, 30),
            anchor="lm",
        )
        cell(columns[0][1], y, signed_pct(row["avg"]), ratio_color(row["avg"]), f_bold)
        cell(columns[1][1], y, f"{row['plant']:.0%}", plant_color(row["plant"]), f_cell)
        for j, dish in enumerate(dish_order):
            value = row["dishes"][dish]
            x = columns[2 + j][1]
            if value is None:
                cell(x, y, "—", (0.92, 0.92, 0.92), f_cell)
            else:
                cell(x, y, signed_pct(value), ratio_color(value), f_cell)

    # Gradient legend for the diverging scale
    vmin, vmax = RATIO_NORM.vmin, RATIO_NORM.vmax
    bar_x, bar_y = pad + name_w, height - legend_h + 16 * s
    bar_w, bar_h = 320 * s, 14 * s
    for px in range(bar_w):
        value = vmin + (vmax - vmin) * px / (bar_w - 1)
        draw.line(
            [(bar_x + px, bar_y), (bar_x + px, bar_y + bar_h)],
            fill=to_rgb255(ratio_color(value)),
        )
    draw.rectangle(
        [bar_x, bar_y, bar_x + bar_w - 1, bar_y + bar_h], outline=(180, 180, 180)
    )
    for value in [vmin, 0.75, 1.0, 1.5, vmax]:
        px = int((value - vmin) / (vmax - vmin) * (bar_w - 1))
        draw.line(
            [(bar_x + px, bar_y + bar_h), (bar_x + px, bar_y + bar_h + 4 * s)],
            fill=(120, 120, 120),
        )
        label = signed_pct(value)
        if value <= vmin:
            label = "≤" + label
        elif value >= vmax:
            label = "≥" + label
        draw.text(
            (bar_x + px, bar_y + bar_h + 6 * s),
            label,
            font=f_small,
            fill=(80, 80, 80),
            anchor="ma",
        )
    draw.text(
        (bar_x - 8 * s, bar_y + bar_h // 2),
        "vs. baseline recipe",
        font=f_small,
        fill=(80, 80, 80),
        anchor="rm",
    )
    draw.text(
        (bar_x + bar_w + 24 * s, bar_y + bar_h // 2),
        "plant-based column uses its own scale (darker = more mentions)",
        font=f_small,
        fill=(80, 80, 80),
        anchor="lm",
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # Palette mode cuts the file to roughly a third with no visible loss.
    image.resize((width // s, height // s), Image.Resampling.LANCZOS).quantize(
        colors=256
    ).save(output_path, optimize=True)
    print(f"Table saved to {output_path}", file=sys.stderr)


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

    colors = [ratio_color(v) for v in model_avgs.values]
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
    parser.add_argument(
        "--table", default="images/table.png", help="Output table image path"
    )
    args = parser.parse_args()

    df = collect_results(args.log_dir)
    if df.empty:
        print("No results found in", args.log_dir, file=sys.stderr)
        sys.exit(1)

    table = build_summary_table(df)
    print(table)

    Path(args.chart).parent.mkdir(parents=True, exist_ok=True)
    make_chart(df, args.chart)
    make_table_image(df, args.table)


if __name__ == "__main__":
    main()
