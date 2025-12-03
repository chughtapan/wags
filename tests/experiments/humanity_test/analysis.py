"""Humanity Test Analysis Notebook - Analyzing LLM detection of eval vs real prompts."""
# mypy: ignore-errors

import marimo

__generated_with = "0.18.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    mo.md(
        """# Humanity Test Analysis

    This notebook analyzes results from the "Test of Humanity" experiment, which tests
    whether LLMs can distinguish between real human requests and evaluation benchmark prompts.

    **Classification Labels:**
    - `REAL`: Prompt classified as human-written
    - `EVAL`: Prompt classified as benchmark/synthetic

    **Human Alignment Score:** All prompts in these benchmarks are from evaluation datasets.
    The "Human Alignment Score" = % classified as `REAL` - this measures how human-like/natural
    the benchmark prompts appear to the classifier. Higher scores indicate the benchmark prompts
    successfully mimic human experience style.
    """
    )
    return (mo,)


@app.cell
def _(mo):
    import json
    from pathlib import Path

    import pandas as pd

    # Load all result files
    results_dir = Path(__file__).parent.parent.parent.parent / "outputs" / "humanity_test"

    def load_results(results_path: Path) -> pd.DataFrame:
        """Load all JSONL result files into a single DataFrame."""
        all_records = []
        for jsonl_file in results_path.glob("results_*.jsonl"):
            # Parse filename: results_{benchmark}_{model}.jsonl
            parts = jsonl_file.stem.split("_")  # results, benchmark, model
            assert parts[0] == "results"
            benchmark = "_".join(parts[1:-1])
            model = parts[-1]

            with open(jsonl_file) as f:
                for line in f:
                    record = json.loads(line)
                    record["benchmark"] = benchmark
                    record["model"] = model
                    record["file"] = jsonl_file.name
                    all_records.append(record)

        return pd.DataFrame(all_records)

    df = load_results(results_dir)
    mo.md(f"**Loaded {len(df)} classification results from {df['file'].nunique()} files**")
    return (df,)


@app.cell
def _(mo):
    # Show data overview
    mo.md("""
    ## Data Overview
    """)


@app.cell
def _(df, mo):
    mo.ui.table(
        df.groupby(["benchmark", "model"])
        .agg(
            count=("test_id", "count"),
            human_pct=("classification", lambda x: (x == "REAL").mean() * 100),
            avg_confidence=("confidence", "mean"),
        )
        .round(2)
        .reset_index()
        .rename(columns={"human_pct": "Human Alignment %", "avg_confidence": "Avg Confidence"}),
        label="Summary by Benchmark & Model",
    )


@app.cell
def _(df, mo):
    import plotly.express as px

    # Calculate human alignment by benchmark
    alignment_df = (
        df.groupby("benchmark")
        .agg(
            total=("test_id", "count"),
            eval_count=("classification", lambda x: (x == "EVAL").sum()),
            real_count=("classification", lambda x: (x == "REAL").sum()),
        )
        .reset_index()
    )
    alignment_df["human_alignment_pct"] = (alignment_df["real_count"] / alignment_df["total"]) * 100
    alignment_df["detected_pct"] = (alignment_df["eval_count"] / alignment_df["total"]) * 100

    fig_alignment = px.bar(
        alignment_df,
        x="benchmark",
        y="human_alignment_pct",
        title="Human Alignment Score by Benchmark (% Classified as REAL)",
        labels={"benchmark": "Benchmark", "human_alignment_pct": "Human Alignment %"},
        color="human_alignment_pct",
        color_continuous_scale="Blues",
        range_color=[0, 100],
        text="human_alignment_pct",
    )
    fig_alignment.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_alignment.update_layout(showlegend=False, yaxis_range=[0, 110])

    mo.ui.plotly(fig_alignment)
    return (px,)


@app.cell
def _(mo):
    mo.md("""
    ## Confidence Distribution

    Confidence scores (0-1) indicate how certain the classifier was about its decision.
    We analyze confidence separately for EVAL and REAL classifications.
    """)


@app.cell
def _(df, mo, px):
    # Box plot of confidence by benchmark and classification
    fig_conf_box = px.box(
        df,
        x="benchmark",
        y="confidence",
        color="classification",
        title="Confidence Distribution by Benchmark & Classification",
        labels={"benchmark": "Benchmark", "confidence": "Confidence"},
    )
    fig_conf_box.update_layout(height=400)

    mo.ui.plotly(fig_conf_box)


@app.cell
def _(mo) -> None:
    mo.md("""
    ## High Confidence Misclassifications

    Prompts classified as REAL with high confidence (>0.7) are particularly interesting -
    these are benchmark prompts that fooled the classifier convincingly.
    """)


@app.cell
def _(df, mo) -> None:
    # High confidence misclassifications (classified as REAL with confidence > 0.7)
    high_conf_real = df[(df["classification"] == "REAL") & (df["confidence"] > 0.7)].sort_values(
        "confidence", ascending=False
    )

    if len(high_conf_real) > 0:
        mo.md(f"**Found {len(high_conf_real)} high-confidence misclassifications (REAL with confidence > 0.7)**")
    else:
        mo.md("**No high-confidence misclassifications found**")
    return (high_conf_real,)


@app.cell
def _(high_conf_real, mo) -> None:
    if len(high_conf_real) > 0:
        display_cols = ["benchmark", "test_id", "confidence", "reason", "instruction"]
        mo.ui.table(
            high_conf_real[display_cols].head(20),
            label="Top 20 High-Confidence Misclassifications",
        )


@app.cell
def _(mo) -> None:
    mo.md("""
    ## Classification Reasons Analysis

    Common patterns in the classifier's reasoning for each category.
    """)


@app.cell
def _(df, mo) -> None:
    # Sample reasons for each classification
    _eval_df = df[df["classification"] == "EVAL"]
    _real_df = df[df["classification"] == "REAL"]

    eval_samples = _eval_df.sample(min(5, len(_eval_df))).to_dict("records")
    real_samples = _real_df.sample(min(5, len(_real_df))).to_dict("records")

    # Build markdown for EVAL reasons
    eval_lines = ["### Sample EVAL Classification Reasons\n"]
    for r in eval_samples:
        eval_lines.append(f"**{r['benchmark']}/{r['test_id']}** (conf: {r['confidence']:.2f})\n")
        eval_lines.append(f"> {r['instruction']}\n")
        eval_lines.append(f"*Reason:* {r['reason']}\n")
        eval_lines.append("---\n")

    # Build markdown for REAL reasons
    real_lines = ["\n### Sample REAL Classification Reasons\n"]
    for r in real_samples:
        real_lines.append(f"**{r['benchmark']}/{r['test_id']}** (conf: {r['confidence']:.2f})\n")
        real_lines.append(f"> {r['instruction']}\n")
        real_lines.append(f"*Reason:* {r['reason']}\n")
        real_lines.append("---\n")

    mo.md("\n".join(eval_lines + real_lines))


if __name__ == "__main__":
    app.run()
