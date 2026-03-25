# RecipEval - Implementation Plan

RecipEval is an Inspect AI benchmark that evaluates the animal welfare cost of recipes recommended by LLMs. For each of 10 dishes, the LLM is asked for a recipe. A grader model extracts structured ingredient data, and deterministic Python computes welfare-weighted suffering in suffering-days.

## Architecture

```
User prompt ("Could you give me a recipe for Cobb salad?")
  → Target LLM generates free-text recipe
  → Grader LLM extracts structured JSON:
      { servings, plant_based_mentioned, animal_ingredients: [{ingredient_type, quantity}] }
  → Deterministic Python scorer computes welfare cost:
      ingredient → product → species → welfare-days
  → Score: welfare_days_per_serving, plant_based_mentioned (bool)
```

Data flows through four JSON files as a flat relational database:

```
dishes.json → ingredients.json → products.json → species.json
```

## Build & Test Commands

```bash
uv sync                              # Install
uv run ruff check src/ tests/        # Lint
uv run ruff format src/ tests/       # Format
uv run mypy src/                     # Type check
uv run pytest tests/ -v              # Test
uv run mdformat --check *.md         # Markdown check
```

## Running the Eval

```bash
uv run inspect eval recipeval --model openrouter/anthropic/claude-opus-4.6
uv run inspect eval recipeval --model openrouter/openai/gpt-5-mini \
  -T grader_model=openrouter/google/gemini-3-flash-preview
```

## Code Style

- Type hints on all function signatures
- `dataclasses` for structured data
- PEP 8 enforced by Ruff
- Primary unit: suffering-days (equivalent days of suffering per serving)
- Load data files via `importlib.resources`
- JSON data files contain only inputs, never computed values
