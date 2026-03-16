import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


# ============================================================================
# OPENAI CLIENT SETUP (ENV-BASED, SHARED WITH REST OF BACKEND)
# ============================================================================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_client: Optional[OpenAI] = None
_client_api_key: Optional[str] = None


def get_openai_client(api_key: Optional[str] = None) -> OpenAI:
    """Get or create OpenAI client (prefers passed key, falls back to env key)."""
    global _client, _client_api_key
    effective_key = (api_key or OPENAI_API_KEY or "").strip()
    if _client is None or _client_api_key != effective_key:
        if not effective_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is not set. "
                "Please set it in your backend .env file."
            )
        _client = OpenAI(api_key=effective_key)
        _client_api_key = effective_key
    return _client


# ============================================================================
# LOW-LEVEL CALL TO GPT-4O-MINI
# ============================================================================
def classify_with_openai(prompt: str, json_mode: bool = False, api_key: Optional[str] = None) -> Any:
    """
    Helper for calling GPT-4o-mini with a standard SRL system prompt.

    If json_mode=True, enforces JSON-only responses and returns a parsed object.
    Otherwise returns a plain string.
    """
    messages = [
        {
            "role": "system",
            "content": "You are an expert in self-regulated learning, "
            "educational psychology, and cognitive psychology.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        api = get_openai_client(api_key=api_key)

        if json_mode:
            response = api.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3,
                max_tokens=200,  # JSON needs extra formatting characters
                response_format={"type": "json_object"},
            )
        else:
            response = api.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3,
                max_tokens=100,
            )

        result = response.choices[0].message.content.strip()

        if json_mode:
            return json.loads(result)
        return result

    except Exception as e:
        # Surface errors to logs but keep the caller alive
        print(f"API Error in classify_with_openai: {e}")
        return None


# ============================================================================
# SRL FRAMEWORK CODE CLASSIFICATION (CONVERSATION-LEVEL)
# ============================================================================
def classify_zimmerman_phase(full_conversation: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Analyze an entire conversation and identify ALL Zimmerman SRL phases present
    with their percentage distribution.

    Returns a dict like:
        {
          "forethought": int,
          "performance": int,
          "self_reflection": int,
          "phases_present": [...],
          "dominant_phase": "..."
        }
    or None on API failure.
    """
    prompt = f"""Analyze this conversation and identify ALL Zimmerman SRL phases present with their percentage distribution.

    FORETHOUGHT: Task analysis - goal setting/strategic planning. 
                 Self-motivation beliefs - self-efficacy, outcome expectations, intrinsic interest/value, goal orientation
                - Indicators: "I want to learn", "My goal is", "I should start by", future tense planning

    PERFORMANCE: self control - self-instruction, imagery, attention focusing, task strategies. 
                 Self-observation - self-recording, self-experimentation
                - Indicators: "I'm implementing", "I'm trying", asking clarifying questions during work

    SELF_REFLECTION: Self-judgment - self-evaluation, casual attribution. 
                     Self-reaction - self-satisfaction/affect, adaptive defensive
                    - Indicators: "That didn't work", "I understand now", "I should have", past tense reflection

    Full Conversation: "{full_conversation}"

    Analyze the ENTIRE conversation and identify what percentage of the conversation shows each phase. 
    Consider:
    - Multiple phases can be present in one conversation
    - Percentages must add up to 100
    - Base percentages on the proportion of messages/content showing each phase
    - A phase with 0% means it's completely absent
    
    You MUST return JSON format: {{"forethought": X, "performance": Y, "self_reflection": Z, "phases_present": ["phase1", "phase2"], "dominant_phase": "phase_name"}}
    
    Where X, Y, Z are percentages (integers 0-100 that sum to 100), phases_present lists all phases with >0%, and dominant_phase is the highest percentage phase.
    """

    result = classify_with_openai(prompt, json_mode=True, api_key=api_key)
    if not isinstance(result, dict):
        return None
    return result


def analyze_copes_components(message: str, zimmerman_phase: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Analyze a conversation/message for COPES components using frequency scoring (0–3).

    Returns:
        {"C": 0-3, "O": 0-3, "P": 0-3, "E": 0-3, "S": 0-3, "total": sum}
    or None on API failure.
    """
    prompt = f"""Analyze this conversation for COPES components from Winne and Hadwin's model of SRL within the {zimmerman_phase} phase of Zimmerman's SRL model.

    Use FREQUENCY SCORING (0-3) for each component based on how consistently it appears:

    0 = ABSENT - Not present at all in the conversation
    1 = MINIMAL - Present once or very briefly mentioned
    2 = MODERATE - Present multiple times or in multiple messages
    3 = CONSISTENT - Present throughout most/all of the conversation

    BE INCLUSIVE - Look for both explicit and implicit indicators.

    C - CONDITIONS: Resources, constraints, or context mentioned?
        - IMPLICIT: Providing equations/code (context), mentioning specific problems, stating initial conditions
        - 0: No context provided
        - 1: Brief mention of problem context
        - 2: Multiple contextual details provided
        - 3: Rich, detailed context throughout conversation

    O - OPERATIONS: Cognitive processes, tactics, or strategies shown?
        - IMPLICIT: Asking questions, requesting explanations, seeking alternatives, analyzing
        - 0: No cognitive processes evident
        - 1: Single question or basic inquiry
        - 2: Multiple questions or some strategic thinking
        - 3: Consistent questioning, analysis, exploration throughout

    P - PRODUCTS: Creating outputs or building new understanding?
        - IMPLICIT: Requesting practice problems (to create knowledge), asking for examples (to build understanding)
        - 0: No product creation or learning focus
        - 1: Brief mention of wanting to learn/create
        - 2: Active engagement in building understanding
        - 3: Consistent focus on creating outputs/knowledge throughout

    E - EVALUATIONS: Self-monitoring, assessment, or feedback?
        - IMPLICIT: "That's wrong", "Make them simpler" (evaluating difficulty), requesting clarification (monitoring comprehension)
        - 0: No evaluation or monitoring
        - 1: Single instance of self-monitoring
        - 2: Multiple checks or evaluations
        - 3: Consistent self-monitoring throughout conversation

    S - STANDARDS: Success criteria or expectations referenced?
        - IMPLICIT: "in depth" (depth standard), "simpler" (clarity standard), "similar to" (consistency standard)
        - 0: No standards mentioned
        - 1: Single standard or expectation stated
        - 2: Multiple standards referenced
        - 3: Clear, consistent standards maintained throughout

    Conversation: {message}

    You MUST return JSON: {{"C": 0-3, "O": 0-3, "P": 0-3, "E": 0-3, "S": 0-3, "total": sum}}
    
    The 'total' should be the sum of all five components (max 15)."""

    result = classify_with_openai(prompt, json_mode=True, api_key=api_key)
    if not isinstance(result, dict):
        return None
    return result


def classify_blooms_level(
    message: str, zimmerman_phase: Dict[str, Any], api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Classify a conversation using Bloom's Taxonomy (1956), using SRL phase context.

    Returns:
        {"level": 1-6, "level_name": "...", "confidence": 0.0-1.0, "rationale": "..."}
    or None on API failure.
    """
    phases_present = ", ".join(zimmerman_phase.get("phases_present", []))
    dominant_phase = zimmerman_phase.get("dominant_phase")
    forethought_pct = zimmerman_phase.get("forethought")
    performance_pct = zimmerman_phase.get("performance")
    reflection_pct = zimmerman_phase.get("self_reflection")

    prompt = f"""Classify this conversation using Bloom's Taxonomy (1956). Return JSON.

    CONTEXT: This conversation shows the following SRL phases:
    - Phases present: {phases_present}
    - Dominant phase: {dominant_phase}
    - Distribution: Forethought {forethought_pct}%, Performance {performance_pct}%, Self-Reflection {reflection_pct}%
    
    Use this context to better understand the cognitive level. For example:
    - Forethought-heavy conversations may show planning (Application/Analysis)
    - Performance-heavy may show problem-solving (Application/Analysis)
    - Reflection-heavy may show evaluation (Synthesis/Evaluation)

    Bloom's Levels:
    1. KNOWLEDGE: Remembering, recognition or recall of ideas, material, or phenomena
       - Indicators: define, list, name, state, recall, identify
    2. COMPREHENSION: Understanding the literal message in communication
       - Indicators: explain, describe, summarize, interpret, paraphrase
    3. APPLICATION: Using abstractions in particular situations without being told which to use
       - Indicators: apply, solve, use, demonstrate, implement
    4. ANALYSIS: Breaking down material into parts and detecting relationships
       - Indicators: analyze, compare, contrast, examine, categorize
    5. SYNTHESIS: Drawing from many sources to create new structures/patterns
       - Indicators: create, design, formulate, integrate, combine
    6. EVALUATION: Making judgments about value using criteria and standards
       - Indicators: judge, critique, assess, evaluate, justify

    Conversation:
    {message}

    You MUST return JSON: {{"level": 1-6, "level_name": "...", "confidence": 0.0-1.0, "rationale": "..."}}"""

    result = classify_with_openai(prompt, json_mode=True, api_key=api_key)
    if not isinstance(result, dict):
        return None
    return result


# ============================================================================
# FLEXIBLE CHAT HISTORY LOADER (JSON FILE)
# ============================================================================
def load_chat_history_flexible(filepath: str) -> List[Dict[str, Any]]:
    """
    Load chat history from JSON supporting several shapes:

    - Per-user JSON:
        {"netid": "...", "conversations": [...]}
        or [{"netid": "...", "conversations": [...]}, ...]
    - Flat chats:
        [{"chat": ...}, {"chat": ...}]
    - Wrapped:
        {"chats": [...]}
        {"conversations": [...]}

    Returns list of normalized chats:
        {
          "chat_id": ...,
          "topic": ...,
          "messages": [user_message_str, ...],
          "num_messages": int,
          "updated_at": optional timestamp
        }
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    processed_chats: List[Dict[str, Any]] = []

    # Handle per-user JSON format from CSV conversion
    if isinstance(data, dict) and "netid" in data:
        users_data = [data]
    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict) and "netid" in data[0]:
        users_data = data
    elif isinstance(data, list):
        chats = data
        users_data = None
    elif isinstance(data, dict) and "chats" in data:
        chats = data["chats"]
        users_data = None
    elif isinstance(data, dict) and "conversations" in data:
        chats = data["conversations"]
        users_data = None
    else:
        raise ValueError(
            "Unknown JSON format. Expected list of chats, per-user format, "
            "or object with 'chats'/'conversations' key."
        )

    # Per-user format (netid + conversations)
    if users_data:
        for user_data in users_data:
            conversations = user_data.get("conversations", [])
            for chat in conversations:
                chat_id = chat.get("conversation_id", chat.get("uuid", "unknown"))
                topic = chat.get("topic", "Unknown Topic")
                messages_raw = chat.get("messages", [])

                messages: List[str] = []
                for msg in messages_raw:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        messages.append((msg.get("content") or "").strip())
                    elif isinstance(msg, str):
                        messages.append(msg)

                if messages:
                    processed_chats.append(
                        {
                            "chat_id": chat_id,
                            "topic": topic,
                            "messages": messages,
                            "num_messages": len(messages),
                        }
                    )

        return processed_chats

    # Generic chat list formats
    for chat in chats:
        chat_id = (
            chat.get("uuid")
            or chat.get("id")
            or chat.get("chat_id")
            or chat.get("conversation_id")
            or "unknown"
        )
        topic = (
            chat.get("name")
            or chat.get("title")
            or chat.get("topic")
            or chat.get("subject")
            or "Untitled Chat"
        )
        messages_raw = (
            chat.get("chat_messages")
            or chat.get("messages")
            or chat.get("conversation")
            or []
        )

        user_messages: List[str] = []
        for msg in messages_raw:
            sender = (
                (msg.get("sender") or msg.get("role") or msg.get("author") or "")
                .lower()
            )
            if sender in ("human", "user", "person"):
                text = (
                    msg.get("text")
                    or msg.get("content")
                    or msg.get("message")
                    or ""
                )
                if text:
                    user_messages.append(text)

        if not user_messages:
            continue

        processed_chats.append(
            {
                "chat_id": chat_id,
                "topic": topic,
                "updated_at": chat.get("updated_at")
                or chat.get("timestamp")
                or chat.get("created_at"),
                "num_messages": len(user_messages),
                "messages": user_messages,
            }
        )

    return processed_chats


# ============================================================================
# CONVERSATION-LEVEL ENHANCED SRL + BLOOM'S ANALYSIS (FROM CHAT HISTORY JSON)
# ============================================================================
def enhanced_critical_thinking_analysis_json(
    chats: List[Dict[str, Any]],
    progress_callback: Optional[Any] = None,
    unit_label: str = "conversation",
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Analyze CHATS loaded from JSON (not individual messages).
    Each chat contains multiple user messages treated as one conversation.
    """
    print("\n" + "=" * 80, flush=True)
    print("ENHANCED SRL + CRITICAL THINKING ANALYSIS (FROM CHAT HISTORY)", flush=True)
    print("=" * 80, flush=True)
    print(f"Analyzing {len(chats)} conversations", flush=True)

    total = len(chats)
    label_plural = f"{unit_label}s" if not unit_label.endswith("s") else unit_label
    if progress_callback:
        progress_callback(0, total, f"Starting SRL analysis of {total} {label_plural}...")

    chat_results: List[Dict[str, Any]] = []

    for i, chat in enumerate(chats):
        if progress_callback:
            progress_callback(i, total, f"Analyzing {unit_label} {i+1}/{total}: {chat['topic']}")

        print(f"\nChat {i+1}/{len(chats)}: {chat['topic']}", flush=True)
        print(f"  User messages: {len(chat['messages'])}", flush=True)

        full_conversation = "\n".join(
            [f"Message {j+1}: {msg}" for j, msg in enumerate(chat["messages"])]
        )

        # Zimmerman SRL phases
        zimmerman_phase = classify_zimmerman_phase(full_conversation, api_key=api_key) or {}

        # COPES (frequency-based 0–3 per component, total 0–15)
        copes_analysis = analyze_copes_components(
            full_conversation, zimmerman_phase.get("dominant_phase", "unknown"), api_key=api_key
        ) or {"C": 0, "O": 0, "P": 0, "E": 0, "S": 0, "total": 0}

        # Bloom's classification (with unclassifiable handling)
        blooms_result = classify_blooms_level(full_conversation, zimmerman_phase, api_key=api_key)
        if blooms_result is None:
            print("  ⚠️  Bloom's API call failed, marking as unclassifiable")
            blooms_result = {
                "level": None,
                "level_name": "UNCLASSIFIABLE",
                "confidence": 0.0,
                "rationale": "API error - unable to classify",
                "unclassifiable": True,
            }
        else:
            blooms_result["unclassifiable"] = False

        print(
            f"  Zimmerman Phases: {zimmerman_phase.get('phases_present', [])}"
        )
        print(f"    Forethought: {zimmerman_phase.get('forethought')}%")
        print(f"    Performance: {zimmerman_phase.get('performance')}%")
        print(
            f"    Self-Reflection: {zimmerman_phase.get('self_reflection')}%"
        )
        print(
            f"    Dominant: {zimmerman_phase.get('dominant_phase', 'N/A')}"
        )

        chat_results.append(
            {
                "chat_id": chat["chat_id"],
                "topic": chat["topic"],
                "updated_at": chat.get("updated_at"),
                "num_messages": chat["num_messages"],
                "zimmerman_dominant_phase": zimmerman_phase.get(
                    "dominant_phase"
                ),
                "zimmerman_phases_present": ", ".join(
                    zimmerman_phase.get("phases_present", [])
                ),
                "zimmerman_forethought_pct": zimmerman_phase.get("forethought"),
                "zimmerman_performance_pct": zimmerman_phase.get("performance"),
                "zimmerman_self_reflection_pct": zimmerman_phase.get(
                    "self_reflection"
                ),
                "copes_score": copes_analysis.get("total"),
                "copes_C": copes_analysis.get("C"),
                "copes_O": copes_analysis.get("O"),
                "copes_P": copes_analysis.get("P"),
                "copes_E": copes_analysis.get("E"),
                "copes_S": copes_analysis.get("S"),
                "blooms_level": blooms_result.get("level"),
                "blooms_name": blooms_result.get("level_name"),
                "blooms_confidence": blooms_result.get("confidence"),
                "blooms_unclassifiable": blooms_result.get("unclassifiable", False),
                "first_message": (
                    chat["messages"][0][:100] + "..."
                    if len(chat["messages"][0]) > 100
                    else chat["messages"][0]
                ),
            }
        )
        if progress_callback:
            progress_callback(i + 1, total, f"Completed {unit_label} {i+1}/{total}.")

        if (i + 1) % 3 == 0 and i < len(chats) - 1:
            print(
                f"  Rate limit: Waiting 20 seconds... ({i+1}/{len(chats)} done)"
            )
            if progress_callback:
                progress_callback(
                    i + 1,
                    total,
                    f"Rate limit: Waiting 20 seconds... ({i+1}/{total} {label_plural} done)",
                )
            time.sleep(20)

    df = pd.DataFrame(chat_results)

    # === Summary statistics (conversation-level) ===
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Total conversations: {len(df)}")

    print("\nDominant Phase per Conversation:")
    dominant_counts = df["zimmerman_dominant_phase"].value_counts()
    for phase, count in dominant_counts.items():
        print(f"  {phase.upper()}: {count} conversations ({count/len(df)*100:.1f}%)")

    print("\nAverage Phase Distribution Across All Conversations:")
    print(f"  Forethought: {df['zimmerman_forethought_pct'].mean():.1f}%")
    print(f"  Performance: {df['zimmerman_performance_pct'].mean():.1f}%")
    print(f"  Self-Reflection: {df['zimmerman_self_reflection_pct'].mean():.1f}%")

    multi_phase = df[
        df["zimmerman_phases_present"].str.contains(",", na=False)
    ]
    print(
        f"\nConversations showing multiple phases: {len(multi_phase)} "
        f"({len(multi_phase)/len(df)*100:.1f}%)"
    )

    full_cycle = df[
        (df["zimmerman_forethought_pct"] > 0)
        & (df["zimmerman_performance_pct"] > 0)
        & (df["zimmerman_self_reflection_pct"] > 0)
    ]
    print(
        f"Conversations showing full SRL cycle: {len(full_cycle)} "
        f"({len(full_cycle)/len(df)*100:.1f}%)"
    )

    print("\n" + "=" * 80)
    print("COPES QUALITY SCORES (Frequency-Based: 0-15 scale)")
    print("=" * 80)
    print(f"Average Total Score: {df['copes_score'].mean():.2f}/15")
    print(f"Average per Component: {df['copes_score'].mean()/5:.2f}/3")
    print()
    print("Score Distribution:")
    print(
        f"  Excellent (12-15): {len(df[df['copes_score'] >= 12])} "
        f"({len(df[df['copes_score'] >= 12])/len(df)*100:.1f}%) "
        "- Consistent SRL throughout"
    )
    print(
        f"  Good (9-11): "
        f"{len(df[(df['copes_score'] >= 9) & (df['copes_score'] < 12)])} "
        f"({len(df[(df['copes_score'] >= 9) & (df['copes_score'] < 12)])/len(df)*100:.1f}%) "
        "- Moderate SRL engagement"
    )
    print(
        f"  Fair (5-8): "
        f"{len(df[(df['copes_score'] >= 5) & (df['copes_score'] < 9)])} "
        f"({len(df[(df['copes_score'] >= 5) & (df['copes_score'] < 9)])/len(df)*100:.1f}%) "
        "- Minimal SRL present"
    )
    print(
        f"  Poor (0-4): {len(df[df['copes_score'] < 5])} "
        f"({len(df[df['copes_score'] < 5])/len(df)*100:.1f}%) - Little to no SRL"
    )
    print()
    print("Component Averages:")
    print(f"  Conditions (C): {df['copes_C'].mean():.2f}/3")
    print(f"  Operations (O): {df['copes_O'].mean():.2f}/3")
    print(f"  Products (P): {df['copes_P'].mean():.2f}/3")
    print(f"  Evaluations (E): {df['copes_E'].mean():.2f}/3")
    print(f"  Standards (S): {df['copes_S'].mean():.2f}/3")

    print("\n" + "=" * 80)
    print("BLOOM'S TAXONOMY DISTRIBUTION")
    print("=" * 80)

    blooms_unclassifiable = df[df["blooms_unclassifiable"] == True]
    if len(blooms_unclassifiable) > 0:
        print("\n⚠️  UNCLASSIFIABLE CONVERSATIONS")
        print("-" * 80)
        print(
            f"Bloom's unclassifiable: {len(blooms_unclassifiable)} "
            f"({len(blooms_unclassifiable)/len(df)*100:.1f}%)"
        )
        print("  Reasons: API parsing errors, malformed responses")
        print()

    classifiable_blooms = df[df["blooms_unclassifiable"] == False]
    if len(classifiable_blooms) > 0:
        blooms_counts = classifiable_blooms["blooms_name"].value_counts()
        for level, count in blooms_counts.items():
            print(f"{level}: {count} ({count/len(classifiable_blooms)*100:.1f}%)")
        print(
            f"\nAverage Cognitive Depth (classifiable only): "
            f"{classifiable_blooms['blooms_level'].mean():.2f}/6"
        )
    else:
        print("⚠️  No classifiable Bloom's results")

    print("\n" + "=" * 80)
    print("DETAILED CHAT ANALYSIS")
    print("=" * 80)
    for idx, row in df.iterrows():
        print(f"\n[Chat {idx+1}] {row['topic']}")
        print(f"  ID: {row['chat_id']}")
        print(f"  Messages: {row['num_messages']}")
        print(f"  Zimmerman Phases: {row['zimmerman_phases_present']}")
        print(
            "    Distribution: "
            f"Forethought {row['zimmerman_forethought_pct']}% "
            f"Performance {row['zimmerman_performance_pct']}% "
            f"Self-Reflection {row['zimmerman_self_reflection_pct']}%"
        )
        print(
            f"    Dominant: {str(row['zimmerman_dominant_phase']).upper()}"
        )
        print(
            f"  COPES: {row['copes_score']}/15 "
            f"(C:{row['copes_C']} O:{row['copes_O']} P:{row['copes_P']} "
            f"E:{row['copes_E']} S:{row['copes_S']}) "
            "[0=absent, 1=minimal, 2=moderate, 3=consistent]"
        )
        if row["blooms_unclassifiable"]:
            print("  Bloom's: [UNCLASSIFIABLE] - API error")
        else:
            conf = row["blooms_confidence"] or 0.0
            try:
                conf_val = float(conf)
            except (TypeError, ValueError):
                conf_val = 0.0
            print(
                f"  Bloom's: Level {row['blooms_level']} - {row['blooms_name']} "
                f"(confidence: {conf_val:.2f})"
            )
        print(f"  First message: {row['first_message']}")

    if progress_callback:
        progress_callback(total, total, "SRL analysis complete.")

    return df


# ============================================================================
# CRITICAL THINKING CLASSIFICATION (CONVERSATION-LEVEL)
# ============================================================================
def classify_CT(chat_results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Classifies each chat into 4 categories:
    1. CRITICAL THINKING - Clear evidence of CT
    2. DEVELOPING CRITICAL THINKING - Emerging CT behaviors
    3. EFFICIENT HELP-SEEKING - Context-appropriate questions (not CT deficit)
    4. LOW CRITICAL THINKING - Clear lack of CT
    """
    classifications: List[Dict[str, Any]] = []

    for _, row in chat_results_df.iterrows():
        blooms_unclassifiable = row.get("blooms_unclassifiable", False)

        if blooms_unclassifiable:
            classifications.append(
                {
                    "is_critical_thinking": None,
                    "ct_classification": "UNCLASSIFIABLE",
                    "ct_rationale": (
                        "Unable to classify due to API errors. Bloom's: failed."
                    ),
                }
            )
            continue

        zimmerman_dominant = row["zimmerman_dominant_phase"]
        zimmerman_forethought = row["zimmerman_forethought_pct"]
        zimmerman_performance = row["zimmerman_performance_pct"]
        zimmerman_reflection = row["zimmerman_self_reflection_pct"]
        copes_score = row["copes_score"]
        blooms_level = row["blooms_level"]
        num_messages = row["num_messages"]
        has_evaluations = row["copes_E"] >= 2

        has_progression = (
            (zimmerman_forethought > 0 and zimmerman_performance > 0)
            or (zimmerman_performance > 0 and zimmerman_reflection > 0)
            or (zimmerman_forethought > 0 and zimmerman_reflection > 0)
        )
        has_full_cycle = (
            zimmerman_forethought > 0
            and zimmerman_performance > 0
            and zimmerman_reflection > 0
        )

        # Branch 1: Bloom's ≥ 4 (Analysis/Synthesis/Evaluation)
        if blooms_level is not None and blooms_level >= 4:
            if copes_score >= 9 and has_evaluations:
                classification = "Critical Thinking"
                is_ct = True
                rationale = (
                    f"Deep cognitive engagement (Bloom's {blooms_level}) with "
                    f"self-regulation (COPES {copes_score}/15) and metacognitive "
                    "monitoring."
                )
                if has_full_cycle:
                    rationale += (
                        " Shows full SRL cycle "
                        f"(Forethought {zimmerman_forethought}%, "
                        f"Performance {zimmerman_performance}%, "
                        f"Self-Reflection {zimmerman_reflection}%)."
                    )
            elif zimmerman_dominant == "performance" and num_messages == 1:
                classification = "Efficient Help-Seeking"
                is_ct = False
                rationale = (
                    f"High-level question (Bloom's {blooms_level}) during active "
                    "work. Context-appropriate question, not a CT deficit."
                )
            else:
                classification = "Low Critical Thinking"
                is_ct = False
                rationale = (
                    f"Asking analytical questions (Bloom's {blooms_level}) without "
                    f"self-regulation (COPES {copes_score}/15)."
                )

        # Branch 2: Bloom's = 3 (Application)
        elif blooms_level == 3:
            if copes_score >= 6:
                classification = "Critical Thinking"
                is_ct = True
                rationale = (
                    f"Applying knowledge (Bloom's {blooms_level}) with "
                    f"self-regulation (COPES {copes_score}/15)."
                )
                if has_progression:
                    rationale += " Shows SRL progression across phases."
            elif zimmerman_dominant == "performance" and num_messages == 1:
                classification = "Efficient Help-Seeking"
                is_ct = False
                rationale = (
                    "Application-level question during active work. "
                    "Efficient help-seeking."
                )
            else:
                classification = "Low Critical Thinking"
                is_ct = False
                rationale = (
                    f"Limited self-regulation (COPES {copes_score}/15) during "
                    "application."
                )

        # Branch 3: Bloom's ≤ 2 (Knowledge/Comprehension or missing)
        else:
            if (
                zimmerman_dominant in ["forethought", "self_reflection"]
                and copes_score >= 6
            ):
                classification = "Developing Critical Thinking"
                is_ct = True
                rationale = (
                    f"Metacognitive engagement in {zimmerman_dominant} phase "
                    f"(COPES {copes_score}/15). Planning or reflection "
                    "demonstrates emerging CT."
                )
                if has_progression:
                    rationale += " Shows phase transitions in SRL."
            elif copes_score >= 9 and has_evaluations:
                classification = "Developing Critical Thinking"
                is_ct = True
                rationale = (
                    f"Self-monitoring (COPES {copes_score}/15) with metacognitive "
                    "awareness. Process quality compensates for cognitive depth."
                )
            elif copes_score <= 4 and not has_evaluations:
                classification = "Low Critical Thinking"
                is_ct = False
                rationale = (
                    f"Surface-level engagement (Bloom's {blooms_level}) with "
                    f"minimal self-regulation (COPES {copes_score}/15)."
                )
            elif zimmerman_dominant == "performance" and num_messages == 1:
                classification = "Efficient Help-Seeking"
                is_ct = False
                rationale = (
                    "Basic question during active work. Efficient help-seeking."
                )
            else:
                classification = "Low Critical Thinking"
                is_ct = False
                rationale = (
                    f"Limited evidence of deep thinking (Bloom's {blooms_level}) "
                    f"or self-regulation (COPES {copes_score}/15)."
                )

        classifications.append(
            {
                "is_critical_thinking": is_ct,
                "ct_classification": classification,
                "ct_rationale": rationale,
            }
        )

    ct_df = pd.DataFrame(classifications)
    result_df = pd.concat([chat_results_df.reset_index(drop=True), ct_df], axis=1)
    return result_df


def generate_critical_thinking_report(
    classified_df: pd.DataFrame,
) -> pd.DataFrame:
    print("\n" + "=" * 80)
    print("CRITICAL THINKING ASSESSMENT REPORT")
    print("=" * 80)

    total_chats = len(classified_df)
    ct_chats = len(classified_df[classified_df["is_critical_thinking"] == True])
    ct_percentage = (ct_chats / total_chats * 100) if total_chats > 0 else 0

    print(f"\nTotal Conversations Analyzed: {total_chats}")
    print(f"Critical Thinking Demonstrated: {ct_chats} ({ct_percentage:.1f}%)")
    print(
        f"Non-Critical Thinking: {total_chats - ct_chats} "
        f"({100 - ct_percentage:.1f}%)"
    )

    print("\n" + "=" * 80)
    print("CLASSIFICATION BREAKDOWN (4 Categories)")
    print("=" * 80)

    ct_count = len(classified_df[classified_df["ct_classification"] == "Critical Thinking"])
    dev_ct_count = len(
        classified_df[
            classified_df["ct_classification"] == "Developing Critical Thinking"
        ]
    )
    help_count = len(
        classified_df[
            classified_df["ct_classification"] == "Efficient Help-Seeking"
        ]
    )
    low_ct_count = len(
        classified_df[
            classified_df["ct_classification"] == "Low Critical Thinking"
        ]
    )
    unclassifiable_count = len(
        classified_df[classified_df["ct_classification"] == "UNCLASSIFIABLE"]
    )

    print(f"✅ Critical Thinking: {ct_count} ({ct_count/total_chats*100:.1f}%)")
    print(
        f"✅ Developing Critical Thinking: {dev_ct_count} "
        f"({dev_ct_count/total_chats*100:.1f}%)"
    )
    print(
        f"❌ Efficient Help-Seeking: {help_count} "
        f"({help_count/total_chats*100:.1f}%)"
    )
    print(
        f"❌ Low Critical Thinking: {low_ct_count} "
        f"({low_ct_count/total_chats*100:.1f}%)"
    )
    if unclassifiable_count > 0:
        print(
            f"⚠️  UNCLASSIFIABLE: {unclassifiable_count} "
            f"({unclassifiable_count/total_chats*100:.1f}%)"
        )

    low_ct = classified_df[classified_df["ct_classification"] == "Low Critical Thinking"]
    if len(low_ct) > 0:
        print("\n" + "=" * 80)
        print("AREAS FOR IMPROVEMENT")
        print("=" * 80)

        avg_blooms_low = low_ct["blooms_level"].mean()
        avg_copes_low = low_ct["copes_score"].mean()

        print("\nIn conversations showing low critical thinking:")
        print(f"  Average Bloom's Level: {avg_blooms_low:.1f}/6")
        print(f"  Average COPES Score: {avg_copes_low:.1f}/15")

        print(f"\n  Most Common Missing Components:")
        if low_ct["copes_E"].sum() / len(low_ct) < 0.3:
            print(
                f"    ⚠️  Evaluations (E): Only {low_ct['copes_E'].sum()}/{len(low_ct)} chats"
            )
            print(
                "        → Practice self-monitoring: "
                "'Does this make sense? Am I understanding correctly?'"
            )
        if low_ct["copes_S"].sum() / len(low_ct) < 0.3:
            print(
                f"    ⚠️  Standards (S): Only {low_ct['copes_S'].sum()}/{len(low_ct)} chats"
            )
            print(
                "        → Set learning goals: "
                "'I want to understand X well enough to Y'"
            )
        if low_ct["copes_P"].sum() / len(low_ct) < 0.3:
            print(
                f"    ⚠️  Products (P): Only {low_ct['copes_P'].sum()}/{len(low_ct)} chats"
            )
            print(
                "        → Try solving problems yourself before asking for solutions"
            )

    print("\n" + "=" * 80)
    print("CRITICAL THINKING BY DOMINANT SRL PHASE")
    print("=" * 80)
    for phase in ["forethought", "performance", "self_reflection"]:
        phase_df = classified_df[classified_df["zimmerman_dominant_phase"] == phase]
        if len(phase_df) > 0:
            phase_ct_rate = (
                len(phase_df[phase_df["is_critical_thinking"] == True])
                / len(phase_df)
                * 100
            )
            print(f"{phase.upper()}: {len(phase_df)} chats, {phase_ct_rate:.1f}% show CT")

    print("\n" + "=" * 80)
    print("SRL PROGRESSION & CRITICAL THINKING")
    print("=" * 80)
    multi_phase = classified_df[
        classified_df["zimmerman_phases_present"].str.contains(",", na=False)
    ]
    if len(multi_phase) > 0:
        multi_phase_ct_rate = (
            len(multi_phase[multi_phase["is_critical_thinking"] == True])
            / len(multi_phase)
            * 100
        )
        print(
            f"Multi-phase conversations: {len(multi_phase)}, "
            f"{multi_phase_ct_rate:.1f}% show CT"
        )

    full_cycle = classified_df[
        (classified_df["zimmerman_forethought_pct"] > 0)
        & (classified_df["zimmerman_performance_pct"] > 0)
        & (classified_df["zimmerman_self_reflection_pct"] > 0)
    ]
    if len(full_cycle) > 0:
        full_cycle_ct_rate = (
            len(full_cycle[full_cycle["is_critical_thinking"] == True])
            / len(full_cycle)
            * 100
        )
        print(
            f"Full SRL cycle conversations: {len(full_cycle)}, "
            f"{full_cycle_ct_rate:.1f}% show CT"
        )

    print("\n" + "=" * 80)
    print("DETAILED CHAT CLASSIFICATIONS")
    print("=" * 80)

    for category in [
        "Critical Thinking",
        "Developing Critical Thinking",
        "Efficient Help-Seeking",
        "Low Critical Thinking",
        "UNCLASSIFIABLE",
    ]:
        category_chats = classified_df[
            classified_df["ct_classification"] == category
        ]
        if len(category_chats) == 0:
            continue

        if category == "UNCLASSIFIABLE":
            ct_indicator = "⚠️ "
        else:
            ct_indicator = (
                "✅"
                if category in ["Critical Thinking", "Developing Critical Thinking"]
                else "❌"
            )
        print(f"\n{ct_indicator} {category.upper()} ({len(category_chats)} chats)")
        print("-" * 80)
        for _, row in category_chats.iterrows():
            print(f"  • {row['topic']}")
            if category != "UNCLASSIFIABLE":
                phases_display = (
                    f"Forethought {row['zimmerman_forethought_pct']}% "
                    f"Performance {row['zimmerman_performance_pct']}% "
                    f"Self-Reflection {row['zimmerman_self_reflection_pct']}%"
                )
                print(
                    f"    Bloom's: {row['blooms_level']} | COPES: {row['copes_score']}/15 "
                    f"| Phases: {phases_display}"
                )
            print(f"    {row['ct_rationale']}")

    return classified_df


# ============================================================================
# MESSAGE-LEVEL SRL ANALYSIS (USED BY FLASK /api/analyze-srl ENDPOINT)
# ============================================================================
def critical_thinking_analysis(
    messages: List[str],
    progress_callback: Optional[Any] = None,
    unit_label: str = "message",
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Backwards-compatible message-level SRL analysis used by the Flask API.

    - messages: list of texts to analyze (prompts or conversation strings)
    - progress_callback: optional callable(current, total, message)

    Returns a DataFrame with columns used by backend.app.analyze_srl:
        - message
        - zimmerman_phase (dominant phase label)
        - copes_score (0–15)
        - copes_components (dict)
        - blooms_level (1–6 or None)
        - blooms_name (str)
        - blooms_confidence (float 0–1)
    """
    print("\n" + "=" * 80)
    print("ENHANCED SRL + CRITICAL THINKING ANALYSIS: from sample chats list")
    print("=" * 80)

    srl_results: List[Dict[str, Any]] = []
    total = len(messages)

    label_plural = f"{unit_label}s" if not unit_label.endswith("s") else unit_label

    for i, msg in enumerate(messages):
        if progress_callback:
            progress_callback(i + 1, total, f"Analyzing {unit_label} {i+1}/{total}...")
        print(f"\nAnalyzing {unit_label} {i+1}/{len(messages)}...")

        # Conversation so far (for phase/bloom context), but the COPES focus is the current message.
        full_conversation = "\n".join(
            [f"Message {j+1}: {m}" for j, m in enumerate(messages[: i + 1])]
        )

        # Zimmerman phases for conversation-so-far
        zimmerman_result = classify_zimmerman_phase(full_conversation, api_key=api_key) or {}
        zimmerman_phase_label = (
            zimmerman_result.get("dominant_phase") or "unknown"
        )

        # COPES on the current message (frequency 0–3, total 0–15)
        copes_analysis = analyze_copes_components(
            msg, zimmerman_phase_label, api_key=api_key
        ) or {"C": 0, "O": 0, "P": 0, "E": 0, "S": 0, "total": 0}

        # Bloom's on conversation-so-far
        blooms_result = classify_blooms_level(msg, zimmerman_result or {}, api_key=api_key)
        if blooms_result is None:
            blooms_result = {
                "level": None,
                "level_name": "UNCLASSIFIABLE",
                "confidence": 0.0,
                "rationale": "API error - unable to classify",
            }

        conf_raw = blooms_result.get("confidence")
        try:
            blooms_conf = float(conf_raw) if conf_raw is not None else 0.0
        except (TypeError, ValueError):
            blooms_conf = 0.0

        srl_results.append(
            {
                "message": msg,
                "zimmerman_phase": zimmerman_phase_label,
                "copes_score": copes_analysis.get("total", 0),
                "copes_components": copes_analysis,
                "blooms_level": blooms_result.get("level"),
                "blooms_name": blooms_result.get("level_name"),
                "blooms_confidence": blooms_conf,
            }
        )

        if (i + 1) % 3 == 0 and i < len(messages) - 1:
            wait_msg = (
                f"Rate limit: Waiting 20 seconds... ({i+1}/{len(messages)} {label_plural} done)"
            )
            print(wait_msg)
            if progress_callback:
                progress_callback(i + 1, total, wait_msg)
            time.sleep(20)

    if progress_callback:
        progress_callback(total, total, "SRL analysis complete.")

    df = pd.DataFrame(srl_results)

    print("\n" + "=" * 80)
    print("ZIMMERMAN PHASE DISTRIBUTION")
    print("=" * 80)
    phase_counts = df["zimmerman_phase"].value_counts()
    for phase, count in phase_counts.items():
        print(f"{phase.upper()}: {count} ({count/len(df)*100:.1f}%)")

    print("\n" + "=" * 80)
    print("COPES QUALITY SCORES (0–15)")
    print("=" * 80)
    print(f"Average COPES Score: {df['copes_score'].mean():.2f}/15")
    print(f"High Quality (12–15): {len(df[df['copes_score'] >= 12])} messages")
    print(f"Moderate (8–11): {len(df[(df['copes_score'] >= 8) & (df['copes_score'] < 12)])} messages")
    print(f"Low (0–7): {len(df[df['copes_score'] < 8])} messages")

    print("\n" + "=" * 80)
    print("BLOOM'S TAXONOMY DISTRIBUTION")
    print("=" * 80)
    blooms_counts = df["blooms_name"].value_counts()
    for level, count in blooms_counts.items():
        print(f"{level}: {count} ({count/len(df)*100:.1f}%)")

    print(f"\nAverage Cognitive Depth: {df['blooms_level'].mean():.2f}/6")

    print("\n" + "=" * 80)
    print("DETAILED MESSAGE ANALYSIS")
    print("=" * 80)
    for idx, row in df.iterrows():
        text = (
            row["message"][:100] + "..."
            if len(row["message"]) > 100
            else row["message"]
        )
        print(f"\n[Message {idx+1}]")
        print(f"Text: {text}")
        cc = row["copes_components"]
        print(f"  → Phase: {str(row['zimmerman_phase']).upper()}")
        print(
            f"  → COPES: {row['copes_score']}/15 "
            f"(C:{cc.get('C')} O:{cc.get('O')} P:{cc.get('P')} "
            f"E:{cc.get('E')} S:{cc.get('S')})"
        )
        conf = row["blooms_confidence"] or 0.0
        try:
            conf_val = float(conf)
        except (TypeError, ValueError):
            conf_val = 0.0
        print(
            f"  → Bloom's: Level {row['blooms_level']} - {row['blooms_name']} "
            f"(confidence: {conf_val:.2f})"
        )

    return df


