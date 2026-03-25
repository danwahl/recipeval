---
name: run-model
description: Run eval on a model, update analysis/plots, and update README
disable-model-invocation: true
argument-hint: [openrouter-model-id]
---

# Run Model Evaluation

Run the full evaluation pipeline for a model and update all artifacts.

The argument should be an OpenRouter model ID (e.g., `google/gemini-3-flash-preview`).

## Steps

### 1. Run the evaluation

```bash
uv run inspect eval recipeval --model openrouter/$ARGUMENTS
```

This will take a while. Wait for it to complete and verify it succeeded (check for errors in the output).

### 2. Generate updated analysis

Run the analysis script and capture the results table output:

```bash
uv run scripts/analysis.py
```

This reads all log files from `logs/`, regenerates the chart image at `images/chart.png`, and prints the results table to stdout.

### 3. Update README.md

Replace the results table in README.md. The table sits between the "## Results" heading and the "### Interpretation Guide" heading. Replace everything between those two markers with the fresh output from the analysis script, keeping the `![Results Chart](images/chart.png)` image link right after `## Results`.

### 4. Suggest a commit

Show the user a suggested commit command in the style:

```
feat: add <Model Display Name>
```

For example: `feat: add Gemini 3 Flash`

Use the model's common display name rather than the raw model ID. Stage the following files:
- `images/chart.png`
- `README.md`

Do NOT commit automatically — just suggest the command and let the user decide.
