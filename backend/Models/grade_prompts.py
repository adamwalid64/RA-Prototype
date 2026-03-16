# By: Adam Walid
# Prompt quality grading for LLMs (reused from classify_chats.py, repurposed for grading)
# Credit: Brandon Lyubarsky for initial code structure

import pandas as pd
import json
import re
from openai import OpenAI
import time
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = None
client_api_key = None

def get_openai_client(api_key=None):
    """Get or create OpenAI client"""
    global client, client_api_key
    effective_key = (api_key or OPENAI_API_KEY or "").strip()
    if client is None or client_api_key != effective_key:
        if not effective_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        client = OpenAI(api_key=effective_key)
        client_api_key = effective_key
    return client

# System prompt for evaluating prompt quality (0–3 per dimension, strict JSON output)
GRADING_SYSTEM_PROMPT = """You are an expert evaluator of prompt quality for large language models.

Your task is to evaluate how well a given prompt enables an LLM to generate high-quality responses by reducing uncertainty, structuring reasoning, maintaining robustness, and aligning with task context.

You must evaluate the prompt itself, not the correctness or usefulness of any hypothetical output. Do not assume missing context, user intent, prior conversation, or model capabilities beyond what is explicitly stated. If required information is absent, note this explicitly and reflect it in the score.

Goal:
Determine the quality of the prompt based on established prompt engineering principles, including clarity and precision, structural design, cognitive scaffolding, boundary management, and task–context alignment. Evaluation must be relative to the information explicitly present in the prompt.

Scoring Scale:
Score each dimension from 0 to 3 using the following rubric:

0 — Poor: The dimension is absent or severely deficient.
1 — Weak: The dimension is partially present but unclear, inconsistent, or insufficient.
2 — Adequate: The dimension is present and functional but could be improved.
3 — Strong: The dimension is explicit, well-executed, and clearly supports high-quality model behavior.

Evaluate the prompt across the following dimensions:

1. Clarity and Precision:
Assess whether the prompt clearly states the task goal, provides sufficient and relevant context, minimizes ambiguity, and constrains the model's response space appropriately.

2. Structural Design:
Assess whether the prompt is logically organized, uses clear ordering or formatting, separates concerns where appropriate, and provides guidance on the structure or form of the desired output.

3. Task Breakdown and Cognitive Scaffolding:
Assess whether complex tasks are appropriately decomposed into manageable steps, whether intermediate reasoning is scaffolded when needed, and whether cognitive load is aligned with task complexity.

4. Prompt Boundaries, Guardrails, and Robustness:
Assess whether instructions, data, and constraints are clearly separated; whether delimiters, exclusions, or scoped authority are used when appropriate; and whether the prompt is resilient to misinterpretation or unintended behavior.

5. Task–Context Alignment:
Assess whether the prompt's level of detail, structure, and constraints are appropriate given the task type and complexity, avoiding unnecessary overengineering or under-specification. If task context or assumptions are missing, reflect this explicitly.

Do not hallucinate task context or infer unstated requirements. If a dimension is not fully applicable, explain why in the justification and still assign a score.

Return your evaluation in the following strict JSON format only:

{
  "scores": {
    "clarity_precision": {
      "score": 0,
      "justification": ""
    },
    "structural_design": {
      "score": 0,
      "justification": ""
    },
    "task_breakdown_scaffolding": {
      "score": 0,
      "justification": ""
    },
    "boundaries_guardrails": {
      "score": 0,
      "justification": ""
    },
    "task_context_alignment": {
      "score": 0,
      "justification": ""
    }
  },
  "total_score": 0,
  "strength_summary": "",
  "weakness_summary": "",
  "context_limitations": "",
  "improvement_suggestions": [
    ""
  ]
}

Be concise, consistent, and evidence-based in all justifications. Do not include any text outside the JSON object."""


# Rubric for evaluating a GROUP of prompts (e.g. one assignment) as a set
GRADING_GROUP_SYSTEM_PROMPT = """You are an expert evaluator of prompt quality for large language models.

Your task is to evaluate a GROUP of related prompts (e.g. from one conversation or assignment) as a SET. Assess how well this collection, taken together, enables an LLM to support high-quality interactions—considering clarity across the set, structural coherence, scaffolding across prompts, boundaries, and alignment with the implied collective task (e.g. one assignment).

Evaluate the set of prompts as a whole. Do not assume missing context. If the group suggests a task (e.g. "Assignment 1") but individual prompts lack detail, note this and reflect it in the score.

Goal:
Determine the quality of this GROUP of prompts using the same principles as for single prompts: clarity and precision, structural design, cognitive scaffolding, boundary management, and task–context alignment—plus how coherent and appropriately varied the set is.

Scoring Scale (0–3 per dimension):
0 — Poor: The dimension is absent or severely deficient across the set.
1 — Weak: The dimension is partially present but unclear, inconsistent, or insufficient.
2 — Adequate: The dimension is present and functional across the set but could be improved.
3 — Strong: The dimension is explicit, well-executed, and clearly supports high-quality model behavior across the group.

Dimensions:

1. Clarity and Precision:
Across the set, do the prompts collectively state clear goals, provide relevant context, minimize ambiguity, and constrain the response space appropriately? Consider consistency of intent across prompts.

2. Structural Design:
Is the group logically organized (e.g. progression, consistent formatting)? Are concerns separated where appropriate? Is there guidance on structure or form of desired outputs across the set?

3. Task Breakdown and Cognitive Scaffolding:
Are complex tasks decomposed across the prompts? Is reasoning scaffolded where needed? Is cognitive load aligned with task complexity across the set?

4. Prompt Boundaries, Guardrails, and Robustness:
Across the set, are instructions, data, and constraints clearly separated? Are delimiters or scoped authority used when appropriate? Is the set resilient to misinterpretation?

5. Task–Context Alignment:
Is the level of detail and structure appropriate for the collective task (e.g. one assignment)? Avoid overengineering or under-specification. If task context is missing, reflect this.

6. Group Coherence and Variety:
Are the prompts coherent as a set (consistent goals, no conflicting instructions)? Is there appropriate variety (e.g. not redundant) without unnecessary fragmentation?

Return your evaluation in the following strict JSON format only:

{
  "scores": {
    "clarity_precision": { "score": 0, "justification": "" },
    "structural_design": { "score": 0, "justification": "" },
    "task_breakdown_scaffolding": { "score": 0, "justification": "" },
    "boundaries_guardrails": { "score": 0, "justification": "" },
    "task_context_alignment": { "score": 0, "justification": "" },
    "group_coherence_variety": { "score": 0, "justification": "" }
  },
  "total_score": 0,
  "strength_summary": "",
  "weakness_summary": "",
  "context_limitations": "",
  "improvement_suggestions": [ "" ]
}

Be concise and evidence-based. Do not include any text outside the JSON object."""


# Rubric for evaluating ALL prompts in ONE CHAT together (conversation-level)
GRADING_CHAT_SYSTEM_PROMPT = """You are an expert evaluator of prompt quality for large language models.

Your task is to evaluate a SINGLE CONVERSATION (chat) by examining ALL user prompts in that chat TOGETHER. Consider how prompts relate: context, follow-ups, coherence across the conversation, and whether later prompts build on earlier ones. Do not grade each prompt in isolation—use the full chat context to assess each prompt's clarity, structure, scaffolding, boundaries, and task-context alignment.

Goal:
Determine the quality of each prompt within this conversation using the same dimensions as single-prompt grading, but with awareness of the full thread. A prompt that is brief in isolation may be adequate in context (e.g. a follow-up); a prompt that repeats earlier context may be redundant. Score each prompt accordingly.

Scoring Scale (0–3 per dimension, same as single-prompt):
0 — Poor: The dimension is absent or severely deficient for this prompt in context.
1 — Weak: The dimension is partially present but unclear, inconsistent, or insufficient.
2 — Adequate: The dimension is present and functional but could be improved.
3 — Strong: The dimension is explicit, well-executed, and clearly supports high-quality model behavior.

Dimensions (evaluate each prompt in light of the full chat):
1. Clarity and Precision
2. Structural Design
3. Task Breakdown and Cognitive Scaffolding
4. Prompt Boundaries, Guardrails, and Robustness
5. Task–Context Alignment

You MUST return a single JSON object with this exact structure—no other text:

{
  "chat_summary": {
    "strength_summary": "",
    "weakness_summary": "",
    "context_limitations": "",
    "improvement_suggestions": [ "" ]
  },
  "prompts": [
    {
      "prompt_index": 1,
      "scores": {
        "clarity_precision": { "score": 0, "justification": "" },
        "structural_design": { "score": 0, "justification": "" },
        "task_breakdown_scaffolding": { "score": 0, "justification": "" },
        "boundaries_guardrails": { "score": 0, "justification": "" },
        "task_context_alignment": { "score": 0, "justification": "" }
      },
      "total_score": 0,
      "strength_summary": "",
      "weakness_summary": ""
    }
  ]
}

- prompt_index must match the 1-based position of the prompt in the chat (Prompt 1, Prompt 2, ...).
- Include one object in "prompts" for each user prompt in the chat, in order.
- total_score for each prompt is the sum of the five dimension scores (0–15).
- Be concise and evidence-based. Do not include any text outside the JSON object."""


def _parse_grading_json(raw: str) -> dict:
    """Parse JSON from model response, handling optional markdown code fence (same approach as SRL classifier)."""
    text = raw.strip()
    # Remove ```json ... ``` if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise


def grade_prompt_with_ai(prompt_text: str, api_key=None) -> dict:
    """Grade a single prompt using the LLM and return the evaluation object (scores, total_score, summaries, etc.)."""
    openai_client = get_openai_client(api_key=api_key)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": GRADING_SYSTEM_PROMPT},
            {"role": "user", "content": f"Evaluate the following prompt.\n\nPrompt to evaluate:\n\n{prompt_text}"}
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    raw = response.choices[0].message.content.strip()
    return _parse_grading_json(raw)


def grade_chat_prompts_with_ai(chat_id: str, topic: str, prompt_texts: list, api_key=None) -> dict:
    """
    Grade all prompts in one chat in a single LLM call. Examines the full conversation
    and returns JSON with chat_summary and per-prompt evaluations (SRL-style json_object + parsing).
    """
    if not prompt_texts:
        return {
            "chat_summary": {
                "strength_summary": "",
                "weakness_summary": "No prompts in chat.",
                "context_limitations": "",
                "improvement_suggestions": [],
            },
            "prompts": [],
        }
    lines = [
        f"Chat ID: {chat_id}",
        f"Topic / title: {topic}",
        f"Number of user prompts in this chat: {len(prompt_texts)}",
        "",
        "Evaluate each prompt in the context of the full conversation. Return JSON with 'chat_summary' and 'prompts' (one entry per prompt, in order).",
        "",
    ]
    for i, text in enumerate(prompt_texts, 1):
        excerpt = (text[:800] + "...") if len(text) > 800 else text
        lines.append(f"--- Prompt {i} ---")
        lines.append(excerpt)
        lines.append("")
    user_content = "\n".join(lines)
    openai_client = get_openai_client(api_key=api_key)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": GRADING_CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=4000,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    return _parse_grading_json(raw)


def grade_prompt_group_with_ai(group_name: str, prompt_texts: list, api_key=None) -> dict:
    """Grade a group of prompts (e.g. one assignment) as a set using the group rubric."""
    if not prompt_texts:
        return {
            "scores": {},
            "total_score": 0,
            "strength_summary": "",
            "weakness_summary": "No prompts in group.",
            "context_limitations": "",
            "improvement_suggestions": [],
        }
    # Build user message: group name + numbered prompts (truncate very long ones for context window)
    lines = [f"Group / topic: {group_name}", f"Number of prompts in this group: {len(prompt_texts)}", ""]
    for i, text in enumerate(prompt_texts, 1):
        excerpt = (text[:800] + "...") if len(text) > 800 else text
        lines.append(f"--- Prompt {i} ---")
        lines.append(excerpt)
        lines.append("")
    content = "\n".join(lines)
    openai_client = get_openai_client(api_key=api_key)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": GRADING_GROUP_SYSTEM_PROMPT},
            {"role": "user", "content": f"Evaluate the following group of prompts as a set.\n\n{content}"},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    raw = response.choices[0].message.content.strip()
    return _parse_grading_json(raw)


def analyze_grouped_prompts(groups: list, progress_callback=None, api_key=None) -> tuple:
    """
    Grade each group of prompts using the group rubric.

    Args:
        groups: List of dicts with keys "group" (str) and "prompts" (list of str). Optional "chat_ids".
        progress_callback: Optional fn(current, total, message).

    Returns:
        (df, stats): df has columns group, evaluation, total_score, prompt_count, prompts;
        stats has total_groups, dimension_averages (over groups), average_total_score, etc.
    """
    results = []
    total = len(groups)
    score_keys = [
        "clarity_precision",
        "structural_design",
        "task_breakdown_scaffolding",
        "boundaries_guardrails",
        "task_context_alignment",
        "group_coherence_variety",
    ]

    if progress_callback:
        progress_callback(0, total, f"Starting group analysis of {total} groups...")

    for i, g in enumerate(groups, 1):
        group_name = g.get("group", "Unnamed")
        prompts = g.get("prompts") or []
        msg = f"Grading group {i}/{total}: {group_name} ({len(prompts)} prompts)"
        if progress_callback:
            progress_callback(i, total, msg)
        try:
            evaluation = grade_prompt_group_with_ai(group_name, prompts, api_key=api_key)
        except (json.JSONDecodeError, KeyError) as e:
            evaluation = {
                "scores": {},
                "total_score": 0,
                "strength_summary": "",
                "weakness_summary": f"Parse error: {e}",
                "context_limitations": "",
                "improvement_suggestions": [],
            }
        results.append({
            "group": group_name,
            "evaluation": evaluation,
            "total_score": evaluation.get("total_score", 0),
            "prompt_count": len(prompts),
            "prompts": prompts,
        })

        if i % 3 == 0 and i < total:
            wait_msg = f"Rate limit: waiting 20 seconds... ({i}/{total} groups done)"
            if progress_callback:
                progress_callback(i, total, wait_msg)
            time.sleep(20)

    if progress_callback:
        progress_callback(total, total, "Group analysis complete.")

    df = pd.DataFrame(results)

    dimension_averages = {}
    for key in score_keys:
        vals = []
        for _, row in df.iterrows():
            ev = row.get("evaluation") or {}
            scores = ev.get("scores") or {}
            dim = scores.get(key)
            if isinstance(dim, dict) and "score" in dim:
                vals.append(dim["score"])
        dimension_averages[key] = sum(vals) / len(vals) if vals else 0

    total_scores = df["total_score"].tolist()
    avg_total = sum(total_scores) / len(total_scores) if total_scores else 0
    strength_summaries = [r.get("evaluation", {}).get("strength_summary", "") for _, r in df.iterrows()]
    weakness_summaries = [r.get("evaluation", {}).get("weakness_summary", "") for _, r in df.iterrows()]
    all_suggestions = []
    for _, r in df.iterrows():
        sug = (r.get("evaluation") or {}).get("improvement_suggestions") or []
        if isinstance(sug, list):
            all_suggestions.extend(sug)
    seen = set()
    unique_suggestions = []
    for s in all_suggestions:
        s = (s or "").strip()
        if s and s not in seen:
            seen.add(s)
            unique_suggestions.append(s)
    aggregate_suggestions = unique_suggestions[:15]

    stats = {
        "total_groups": total,
        "dimension_averages": dimension_averages,
        "average_total_score": round(avg_total, 2),
        "strength_summary": " ".join(s for s in strength_summaries if s).strip()[:500] or "No aggregate strength summary.",
        "weakness_summary": " ".join(s for s in weakness_summaries if s).strip()[:500] or "No aggregate weakness summary.",
        "context_limitations": "",
        "improvement_suggestions": aggregate_suggestions,
    }
    return df, stats


def _flatten_chat_grading_to_rows(chat_id: str, topic: str, messages: list, parsed: dict) -> list:
    """Convert one chat's grading JSON into per-prompt rows (prompt_text, evaluation, total_score)."""
    rows = []
    chat_summary = parsed.get("chat_summary") or {}
    prompt_evals = parsed.get("prompts") or []
    for idx, msg in enumerate(messages):
        # Match by 1-based prompt_index or by position
        ev = None
        for p in prompt_evals:
            if p.get("prompt_index") == idx + 1:
                ev = p
                break
        if ev is None and idx < len(prompt_evals):
            ev = prompt_evals[idx]
        if ev is None:
            ev = {
                "scores": {},
                "total_score": 0,
                "strength_summary": "",
                "weakness_summary": "No evaluation returned.",
            }
        # Build evaluation object in same shape as single-prompt grading for API/export compatibility
        evaluation = {
            "scores": ev.get("scores") or {},
            "total_score": ev.get("total_score", 0),
            "strength_summary": ev.get("strength_summary", ""),
            "weakness_summary": ev.get("weakness_summary", ""),
            "context_limitations": chat_summary.get("context_limitations", ""),
            "improvement_suggestions": chat_summary.get("improvement_suggestions") or [],
        }
        rows.append({
            "prompt_text": msg,
            "evaluation": evaluation,
            "total_score": evaluation.get("total_score", 0),
            "chat_id": chat_id,
            "topic": topic,
        })
    return rows


def analyze_prompts_grading(
    prompt_texts: list = None, chats: list = None, progress_callback=None, api_key=None
) -> tuple:
    """
    Grade prompts by examining each CHAT as a whole (all prompts in the chat together).

    Accepts either:
    - chats: list of {"chat_id", "topic", "messages": [str, ...]} (preferred; uses SRL-style grouping).
    - prompt_texts: flat list of strings (treated as one chat for backward compatibility).

    Returns (DataFrame of per-prompt results, aggregate stats). Each row has: prompt_text, evaluation, total_score.
    Uses one LLM call per chat and JSON parsing/grouping logic aligned with the SRL classifier.
    """
    score_keys = [
        "clarity_precision",
        "structural_design",
        "task_breakdown_scaffolding",
        "boundaries_guardrails",
        "task_context_alignment",
    ]
    if chats:
        total_prompts = sum(len(c.get("messages") or []) for c in chats)
        total_chats = len(chats)
        if progress_callback:
            progress_callback(0, total_chats, f"Starting grading of {total_prompts} prompts in {total_chats} chat(s)...")
        all_rows = []
        for i, chat in enumerate(chats, 1):
            chat_id = chat.get("chat_id", "unknown")
            topic = chat.get("topic", "Untitled")
            messages = chat.get("messages") or []
            if not messages:
                continue
            msg = f"Grading chat {i}/{total_chats}: {topic} ({len(messages)} prompts)..."
            if progress_callback:
                progress_callback(i, total_chats, msg)
            try:
                parsed = grade_chat_prompts_with_ai(chat_id, topic, messages, api_key=api_key)
                rows = _flatten_chat_grading_to_rows(chat_id, topic, messages, parsed)
                all_rows.extend(rows)
            except (json.JSONDecodeError, KeyError) as e:
                for m in messages:
                    all_rows.append({
                        "prompt_text": m,
                        "evaluation": {
                            "scores": {},
                            "total_score": 0,
                            "strength_summary": "",
                            "weakness_summary": f"Parse error: {e}",
                            "context_limitations": "",
                            "improvement_suggestions": [],
                        },
                        "total_score": 0,
                        "chat_id": chat_id,
                        "topic": topic,
                    })
            if i % 3 == 0 and i < total_chats:
                wait_msg = f"Rate limit: waiting 20 seconds... ({i}/{total_chats} chats done)"
                if progress_callback:
                    progress_callback(i, total_chats, wait_msg)
                time.sleep(20)
        if progress_callback:
            progress_callback(total_chats, total_chats, "Grading complete.")
        results = all_rows
    else:
        # Backward compatibility: flat list treated as one chat (examine all prompts together)
        prompt_texts = prompt_texts or []
        total = len(prompt_texts)
        if progress_callback:
            progress_callback(0, total, f"Starting grading of {total} prompts (as one chat)...")
        try:
            parsed = grade_chat_prompts_with_ai(
                "single", "All prompts", prompt_texts, api_key=api_key
            )
            results = _flatten_chat_grading_to_rows("single", "All prompts", prompt_texts, parsed)
        except (json.JSONDecodeError, KeyError) as e:
            results = []
            for text in prompt_texts:
                results.append({
                    "prompt_text": text,
                    "evaluation": {
                        "scores": {},
                        "total_score": 0,
                        "strength_summary": "",
                        "weakness_summary": f"Parse error: {e}",
                        "context_limitations": "",
                        "improvement_suggestions": [],
                    },
                    "total_score": 0,
                })
        if progress_callback:
            progress_callback(1, 1, "Grading complete.")
        total = len(prompt_texts)

    df = pd.DataFrame(results)

    dimension_averages = {}
    for key in score_keys:
        vals = []
        for _, row in df.iterrows():
            ev = row.get("evaluation") or {}
            scores = ev.get("scores") or {}
            dim = scores.get(key)
            if isinstance(dim, dict) and "score" in dim:
                vals.append(dim["score"])
        dimension_averages[key] = sum(vals) / len(vals) if vals else 0

    total_scores = df["total_score"].tolist()
    avg_total = sum(total_scores) / len(total_scores) if total_scores else 0

    strength_summaries = [r.get("evaluation", {}).get("strength_summary", "") for _, r in df.iterrows()]
    weakness_summaries = [r.get("evaluation", {}).get("weakness_summary", "") for _, r in df.iterrows()]
    all_suggestions = []
    for _, r in df.iterrows():
        sug = (r.get("evaluation") or {}).get("improvement_suggestions") or []
        if isinstance(sug, list):
            all_suggestions.extend(sug)
    seen = set()
    unique_suggestions = []
    for s in all_suggestions:
        s = (s or "").strip()
        if s and s not in seen:
            seen.add(s)
            unique_suggestions.append(s)
    aggregate_suggestions = unique_suggestions[:15]

    stats = {
        "total_prompts": len(df),
        "dimension_averages": dimension_averages,
        "average_total_score": round(avg_total, 2),
        "strength_summary": " ".join(s for s in strength_summaries if s).strip()[:500] or "No aggregate strength summary.",
        "weakness_summary": " ".join(s for s in weakness_summaries if s).strip()[:500] or "No aggregate weakness summary.",
        "context_limitations": "",
        "improvement_suggestions": aggregate_suggestions,
    }

    return df, stats


if __name__ == "__main__":
    from pathlib import Path
    import sys
    _backend = Path(__file__).resolve().parent.parent
    if str(_backend) not in sys.path:
        sys.path.insert(0, str(_backend))

    test_prompts = [
        "do the thing",
        "help me",
        "Write a Python function to sort a list.",
        "Explain recursion. Give examples.",
        "Summarize this article and tell me the main points.",
        "You are a helpful assistant. Answer the user's question about machine learning.",
        "You are an expert evaluator. Given a user query, first identify the intent, then list required information, then produce a step-by-step response. Query: What is 2+2?",
        "Write a short Python function that takes a list of integers and returns the list sorted in ascending order. Use a clear function name and add a one-line docstring.",
        "Review the following code for bugs. List each issue with the line number and a brief fix. Code: [paste here]",
        """You are a code review assistant. Your task is to evaluate Python code for correctness and style.
Instructions:
1. Identify the intended behavior from any docstring or comments.
2. Check for logic errors, edge cases, and style issues (PEP 8).
3. Output your review in this exact format: Summary | Issues | Suggestions
Code to review:
```python
def add(a, b): return a + b
```""",
        "You are a summarization agent. Given a text input between <text> and </text> tags, produce a summary in exactly 3 bullet points. Each bullet must be one sentence. Do not add opinions or information outside the source text. If the input is empty or not enclosed in tags, respond only with: ERROR: Invalid input.",
        """Task: Generate a JSON object with keys "name", "age", "country" from the following natural language description.
Constraints:
- Output only valid JSON; no markdown, no explanation.
- If the description omits a field, use null for that key.
- Do not infer or invent values not stated.
Description: John is 30 years old and lives in Canada.""",
    ]
    print("Grading sample prompts...")
    df, stats = analyze_prompts_grading(test_prompts)
    print("Dimension averages:", stats["dimension_averages"])
    print("Average total score:", stats["average_total_score"])
    print("Suggestions:", stats["improvement_suggestions"])

    from Models.Exports import export_grading_to_csv
    out_path = export_grading_to_csv(df)
    print(f"Results exported to: {out_path}")
