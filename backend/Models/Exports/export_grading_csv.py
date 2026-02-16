"""
Export grading results (DataFrame from analyze_prompts_grading) to CSV.
Output is written to the Models/Exports folder.
"""

import os
import csv
from pathlib import Path

# Directory for export files (this package's folder)
EXPORTS_DIR = Path(__file__).resolve().parent

# Dimension keys matching grade_prompts.py
SCORE_KEYS = [
    "clarity_precision",
    "structural_design",
    "task_breakdown_scaffolding",
    "boundaries_guardrails",
    "task_context_alignment",
]
# Group-level rubric adds this dimension
GROUP_SCORE_KEYS = SCORE_KEYS + ["group_coherence_variety"]


def _flatten_row(row):
    """Turn one grading result row into a flat dict for CSV."""
    ev = row.get("evaluation") or {}
    scores = ev.get("scores") or {}
    flat = {
        "prompt_text": (row.get("prompt_text") or "").replace("\r\n", " ").replace("\n", " "),
        "total_score": row.get("total_score", 0),
    }
    for key in SCORE_KEYS:
        dim = scores.get(key) or {}
        flat[f"{key}_score"] = dim.get("score", "")
        flat[f"{key}_justification"] = (dim.get("justification") or "").replace("\r\n", " ").replace("\n", " ")
    flat["strength_summary"] = (ev.get("strength_summary") or "").replace("\r\n", " ").replace("\n", " ")
    flat["weakness_summary"] = (ev.get("weakness_summary") or "").replace("\r\n", " ").replace("\n", " ")
    flat["context_limitations"] = (ev.get("context_limitations") or "").replace("\r\n", " ").replace("\n", " ")
    sugs = ev.get("improvement_suggestions") or []
    flat["improvement_suggestions"] = " | ".join(str(s) for s in sugs).replace("\r\n", " ").replace("\n", " ")
    return flat


def _flatten_group_row(row):
    """Turn one group grading result row into a flat dict for CSV."""
    ev = row.get("evaluation") or {}
    scores = ev.get("scores") or {}
    flat = {
        "group": (row.get("group") or "").replace("\r\n", " ").replace("\n", " "),
        "prompt_count": row.get("prompt_count", 0),
        "total_score": row.get("total_score", 0),
    }
    for key in GROUP_SCORE_KEYS:
        dim = scores.get(key) or {}
        flat[f"{key}_score"] = dim.get("score", "")
        flat[f"{key}_justification"] = (dim.get("justification") or "").replace("\r\n", " ").replace("\n", " ")
    flat["strength_summary"] = (ev.get("strength_summary") or "").replace("\r\n", " ").replace("\n", " ")
    flat["weakness_summary"] = (ev.get("weakness_summary") or "").replace("\r\n", " ").replace("\n", " ")
    flat["context_limitations"] = (ev.get("context_limitations") or "").replace("\r\n", " ").replace("\n", " ")
    sugs = ev.get("improvement_suggestions") or []
    flat["improvement_suggestions"] = " | ".join(str(s) for s in sugs).replace("\r\n", " ").replace("\n", " ")
    prompts = row.get("prompts") or []
    flat["prompts_preview"] = " | ".join((p[:100] + "..." if len(p) > 100 else p for p in prompts[:5])).replace("\r\n", " ").replace("\n", " ")
    return flat


def export_group_grading_to_csv(df, filename=None):
    """
    Export group-level grading DataFrame to CSV in Models/Exports.

    Args:
        df: DataFrame from analyze_grouped_prompts (columns: group, evaluation, total_score, prompt_count, prompts).
        filename: Base filename (e.g. 'group_grading_results.csv'). If None, uses 'group_grading_results.csv'.

    Returns:
        Path to the written CSV file.
    """
    if filename is None:
        filename = "group_grading_results.csv"
    if not filename.lower().endswith(".csv"):
        filename = filename + ".csv"

    out_path = EXPORTS_DIR / filename

    if df is None or df.empty:
        out_path.write_text("group,prompt_count,total_score\n", encoding="utf-8")
        return out_path

    rows = [_flatten_group_row(row) for _, row in df.iterrows()]
    fieldnames = list(rows[0].keys()) if rows else ["group", "prompt_count", "total_score"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out_path


def export_grading_to_csv(df, filename=None):
    """
    Export grading DataFrame to CSV in Models/Exports.

    Args:
        df: DataFrame from analyze_prompts_grading (columns: prompt_text, evaluation, total_score).
        filename: Base filename (e.g. 'grading_results.csv'). If None, uses 'grading_results.csv'.

    Returns:
        Path to the written CSV file.
    """
    if filename is None:
        filename = "grading_results.csv"
    if not filename.lower().endswith(".csv"):
        filename = filename + ".csv"

    out_path = EXPORTS_DIR / filename

    if df is None or df.empty:
        out_path.write_text("prompt_text,total_score\n", encoding="utf-8")
        return out_path

    rows = [_flatten_row(row) for _, row in df.iterrows()]
    fieldnames = list(rows[0].keys()) if rows else ["prompt_text", "total_score"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out_path
