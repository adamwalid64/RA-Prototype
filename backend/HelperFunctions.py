from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from collections import Counter


@dataclass(frozen=True)
class PromptRecord:
    conversation_id: str
    conversation_title: str
    conversation_create_time: Optional[float]

    message_id: str
    message_create_time: Optional[float]

    prompt_text: str


def _utc_iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        try:
            # Handle ISO timestamps commonly found in non-ChatGPT exports.
            ts_str = str(ts).strip()
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            return datetime.fromisoformat(ts_str).astimezone(timezone.utc).isoformat()
        except Exception:
            return None


def _to_json_compatible(value: Any) -> Any:
    """
    Recursively convert values that json.dumps cannot encode by default.
    """
    if isinstance(value, Decimal):
        # Preserve numeric semantics for downstream analysis.
        return float(value)
    if isinstance(value, dict):
        return {k: _to_json_compatible(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_compatible(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_to_json_compatible(v) for v in value)
    return value


def _extract_text_from_message(message: Dict[str, Any]) -> Optional[str]:
    """
    ChatGPT exports typically store text as:
      message["content"]["content_type"] == "text"
      message["content"]["parts"] -> list[str]
    We join parts with newlines.

    Returns None if there's no usable text content.
    """
    content = message.get("content") or {}
    ctype = content.get("content_type")

    # Most common case: plain text
    if ctype == "text":
        parts = content.get("parts") or []
        # parts often looks like ["your text..."]
        text = "\n".join([p for p in parts if isinstance(p, str)]).strip()
        return text or None

    # Some exports include other content types (images, code, etc.).
    # If you later want those too, you can extend here.
    return None


def _extract_text_from_flexible_message(message: Dict[str, Any]) -> Optional[str]:
    """
    Extract text from multiple chat export schemas, including Claude-like exports.
    """
    candidates: List[str] = []

    def _append_text(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            text = value.strip()
            if text:
                candidates.append(text)
            return
        if isinstance(value, list):
            for item in value:
                _append_text(item)
            return
        if isinstance(value, dict):
            # OpenAI-style block
            if isinstance(value.get("text"), str):
                _append_text(value.get("text"))
            # Claude-export style block
            if isinstance(value.get("data"), str):
                _append_text(value.get("data"))
            # Nested content object
            if "content" in value:
                _append_text(value.get("content"))
            # Parts arrays
            if "parts" in value:
                _append_text(value.get("parts"))

    # Common direct fields
    _append_text(message.get("text"))
    _append_text(message.get("message"))
    _append_text(message.get("data"))

    # Generic content fields
    content = message.get("content")
    if isinstance(content, str):
        _append_text(content)
    elif isinstance(content, list):
        _append_text(content)
    elif isinstance(content, dict):
        ctype = content.get("content_type")
        if ctype == "text":
            _append_text(content.get("parts"))
        _append_text(content.get("text"))
        _append_text(content.get("content"))

    # Claude-export browser-script shape: {"type": "prompt/response", "message": [...]}
    _append_text(message.get("message"))

    if not candidates:
        return None
    # Preserve rough ordering while removing exact duplicates.
    seen = set()
    deduped: List[str] = []
    for part in candidates:
        if part in seen:
            continue
        seen.add(part)
        deduped.append(part)
    return "\n".join(deduped).strip() or None


def _is_user_message(message: Dict[str, Any]) -> bool:
    """
    Infer whether a message was authored by the user across export formats.
    """
    sender = message.get("sender")
    if isinstance(sender, str) and sender.lower() in {"human", "user", "person"}:
        return True

    role = message.get("role")
    if isinstance(role, str) and role.lower() in {"human", "user", "person"}:
        return True

    author = message.get("author")
    if isinstance(author, dict):
        author_role = author.get("role")
        if isinstance(author_role, str) and author_role.lower() in {"human", "user", "person"}:
            return True
    elif isinstance(author, str) and author.lower() in {"human", "user", "person"}:
        return True

    # Claude-export browser-script shape: type == prompt indicates user input.
    msg_type = message.get("type")
    if isinstance(msg_type, str) and msg_type.lower() == "prompt":
        return True

    return False


def _detect_conversation_format(conversation: Dict[str, Any]) -> str:
    """
    Detect conversation schema family.
    Returns: "chatgpt" or "generic"
    """
    if (
        isinstance(conversation.get("mapping"), dict)
        and "current_node" in conversation
    ):
        return "chatgpt"
    return "generic"


def _iter_user_prompt_messages(conversation: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """
    Yield user-authored message dicts from a conversation object.
    """
    fmt = _detect_conversation_format(conversation)
    if fmt == "chatgpt":
        for node in _walk_linear_thread(conversation):
            message = node.get("message")
            if not isinstance(message, dict):
                continue
            if _is_user_message(message):
                yield message
        return

    messages_raw = (
        conversation.get("chat_messages")
        or conversation.get("messages")
        or conversation.get("conversation")
        or []
    )
    if not isinstance(messages_raw, list):
        return
    for msg in messages_raw:
        if not isinstance(msg, dict):
            continue
        if _is_user_message(msg):
            yield msg


def _walk_linear_thread(conversation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Walks backward from conversation["current_node"] via each node's "parent"
    to reconstruct the selected branch of the conversation in chronological order.

    This pattern is widely used for ChatGPT export parsing. :contentReference[oaicite:1]{index=1}
    """
    mapping: Dict[str, Any] = conversation.get("mapping") or {}
    current_node = conversation.get("current_node")

    ordered_nodes: List[Dict[str, Any]] = []
    seen = set()

    while current_node:
        if current_node in seen:
            # safety guard against cycles / corruption
            break
        seen.add(current_node)

        node = mapping.get(current_node) or {}
        ordered_nodes.append(node)
        current_node = node.get("parent")

    ordered_nodes.reverse()
    return ordered_nodes


def _stream_prompts_from_json(
    path: Path,
    *,
    max_prompts: Optional[int] = None,
    include_empty: bool = False,
) -> Tuple[List[PromptRecord], int, int, List[Dict[str, Any]]]:
    """
    Stream JSON and collect up to max_prompts (and count total). Uses ijson so the
    full file is never loaded into memory. Returns (prompts, total_prompts, total_convos, per_convo_counts).
    """
    import ijson

    prompts: List[PromptRecord] = []
    total_prompt_count = 0
    total_convo_count = 0
    per_convo_counts: List[Dict[str, Any]] = []

    prefixes = ("item", "conversations.item", "chats.item")
    found_stream = False

    for prefix in prefixes:
        candidate_prompts: List[PromptRecord] = []
        candidate_per_convo_counts: List[Dict[str, Any]] = []
        candidate_total_prompt_count = 0
        candidate_total_convo_count = 0
        saw_any_dict = False

        with path.open("rb") as f:
            for convo in ijson.items(f, prefix):
                if not isinstance(convo, dict):
                    continue
                saw_any_dict = True
                candidate_total_convo_count += 1

                convo_id = str(
                    convo.get("id")
                    or convo.get("uuid")
                    or convo.get("chat_id")
                    or convo.get("conversation_id")
                    or ""
                )
                title = str(
                    convo.get("title")
                    or convo.get("name")
                    or convo.get("topic")
                    or convo.get("subject")
                    or ""
                )
                convo_create_time = (
                    convo.get("create_time")
                    or convo.get("created_at")
                    or convo.get("timestamp")
                )
                user_prompt_count = 0

                fmt = _detect_conversation_format(convo)
                for msg_idx, message in enumerate(_iter_user_prompt_messages(convo), 1):
                    if fmt == "chatgpt":
                        text = _extract_text_from_message(message)
                    else:
                        text = _extract_text_from_flexible_message(message)
                    if text is None and not include_empty:
                        continue
                    text = text or ""

                    user_prompt_count += 1
                    candidate_total_prompt_count += 1
                    if max_prompts is None or len(candidate_prompts) < max_prompts:
                        msg_id = str(
                            message.get("id")
                            or message.get("uuid")
                            or f"{convo_id or 'conversation'}-msg-{msg_idx}"
                        )
                        msg_time = (
                            message.get("create_time")
                            or message.get("created_at")
                            or message.get("timestamp")
                        )
                        candidate_prompts.append(
                            PromptRecord(
                                conversation_id=convo_id,
                                conversation_title=title,
                                conversation_create_time=convo_create_time,
                                message_id=msg_id,
                                message_create_time=msg_time,
                                prompt_text=text,
                            )
                        )

                candidate_per_convo_counts.append({
                    "conversation_id": convo_id,
                    "title": title,
                    "conversation_create_time": convo_create_time,
                    "conversation_create_time_iso_utc": _utc_iso(convo_create_time),
                    "user_prompt_count": user_prompt_count,
                })

        if saw_any_dict:
            prompts = candidate_prompts
            total_prompt_count = candidate_total_prompt_count
            total_convo_count = candidate_total_convo_count
            per_convo_counts = candidate_per_convo_counts
            found_stream = True
            break

    if not found_stream:
        raise ValueError(
            "Unsupported JSON structure. Expected a top-level chat list or an object containing 'conversations' or 'chats'."
        )

    return prompts, total_prompt_count, total_convo_count, per_convo_counts


def parse_chatgpt_prompts(
    conversations_json_path: str | Path,
    *,
    include_empty: bool = False,
    max_prompts: Optional[int] = None,
) -> Tuple[List[PromptRecord], Dict[str, Any]]:
    """
    Parse a chat export JSON and return:
      1) a list of PromptRecord (USER prompts only). If max_prompts is set, only the first N are loaded (saves memory).
      2) a summary dict (counts, per-conversation counts, timestamps)

    Args:
        conversations_json_path: path to exported JSON (ChatGPT or Claude-like schemas)
        include_empty: if True, keep prompts even when the text is empty/None (rare)
        max_prompts: if set (e.g. 50), stream the JSON and only load the first N prompts (much lower memory for large files)

    Returns:
        (prompts, summary)
    """
    path = Path(conversations_json_path)

    if max_prompts is not None:
        try:
            prompts, total_user_prompts, total_conversations, per_convo_counts = _stream_prompts_from_json(
                path, max_prompts=max_prompts, include_empty=include_empty
            )
            summary = {
                "total_conversations": total_conversations,
                "total_user_prompts": total_user_prompts,
                "per_conversation": per_convo_counts,
            }
            return prompts, summary
        except Exception:
            # Fallback to full parse if streaming fails (e.g. non-array JSON)
            pass

    # Full in-memory parse (original behavior)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        chats = data
    elif isinstance(data, dict) and isinstance(data.get("conversations"), list):
        chats = data.get("conversations") or []
    elif isinstance(data, dict) and isinstance(data.get("chats"), list):
        chats = data.get("chats") or []
    else:
        raise ValueError(
            "Unknown JSON format. Expected a list of conversations or an object with 'conversations' or 'chats'."
        )

    prompts = []
    per_convo_counts = []

    for convo in chats:
        if not isinstance(convo, dict):
            continue
        convo_id = str(
            convo.get("id")
            or convo.get("uuid")
            or convo.get("chat_id")
            or convo.get("conversation_id")
            or ""
        )
        title = str(
            convo.get("title")
            or convo.get("name")
            or convo.get("topic")
            or convo.get("subject")
            or ""
        )
        convo_create_time = (
            convo.get("create_time")
            or convo.get("created_at")
            or convo.get("timestamp")
        )
        user_prompt_count = 0

        fmt = _detect_conversation_format(convo)
        for msg_idx, message in enumerate(_iter_user_prompt_messages(convo), 1):
            if fmt == "chatgpt":
                text = _extract_text_from_message(message)
            else:
                text = _extract_text_from_flexible_message(message)
            if text is None and not include_empty:
                continue
            text = text or ""

            user_prompt_count += 1
            msg_id = str(
                message.get("id")
                or message.get("uuid")
                or f"{convo_id or 'conversation'}-msg-{msg_idx}"
            )
            msg_time = (
                message.get("create_time")
                or message.get("created_at")
                or message.get("timestamp")
            )
            prompts.append(
                PromptRecord(
                    conversation_id=convo_id,
                    conversation_title=title,
                    conversation_create_time=convo_create_time,
                    message_id=msg_id,
                    message_create_time=msg_time,
                    prompt_text=text,
                )
            )

        per_convo_counts.append({
            "conversation_id": convo_id,
            "title": title,
            "conversation_create_time": convo_create_time,
            "conversation_create_time_iso_utc": _utc_iso(convo_create_time),
            "user_prompt_count": user_prompt_count,
        })

    summary = {
        "total_conversations": len([c for c in chats if isinstance(c, dict)]),
        "total_user_prompts": len(prompts),
        "per_conversation": per_convo_counts,
    }
    return prompts, summary


def prompts_to_jsonl(prompts: Iterable[PromptRecord], out_path: str | Path) -> None:
    """
    Convenience helper: write prompts as JSON Lines (one prompt per line),
    great for analysis pipelines.
    """
    out_path = Path(out_path)
    with out_path.open("w", encoding="utf-8") as f:
        for p in prompts:
            row = asdict(p)
            row["conversation_create_time_iso_utc"] = _utc_iso(p.conversation_create_time)
            row["message_create_time_iso_utc"] = _utc_iso(p.message_create_time)
            safe_row = _to_json_compatible(row)
            f.write(json.dumps(safe_row, ensure_ascii=False) + "\n")

# Count the number of prompts in a JSONL file
def count_prompts_in_jsonl(path: str) -> int:
    """
    Count how many prompts (lines) are in a JSONL file.
    Each line corresponds to one prompt.
    """
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


# Analyze word frequency in prompts
def generate_prompt_wordcloud(
    jsonl_path: str,
    *,
    output_png: Optional[str] = "prompt_wordcloud.png",
    max_words: int = 200,
    min_word_len: int = 3,
) -> Tuple[int, Counter]:
    """
    Reads prompts from a JSONL file and generates a word cloud image.

    Returns:
      total_word_count: total number of words across all prompts (after basic cleaning)
      word_counts: Counter of token frequencies used in the word cloud

    Notes:
      - Requires: pip install wordcloud matplotlib
      - Expects each JSONL line to include "prompt_text"
    """
    # Lightweight stopword list (extend as you like)
    stopwords = {
        "the","a","an","and","or","but","if","then","else","so","to","of","in","on","for","with","as","at","by",
        "is","are","was","were","be","been","being","it","its","this","that","these","those",
        "i","me","my","we","our","you","your","they","them","their",
        "do","does","did","doing","can","could","should","would","will","just",
        "what","why","how","when","where","who","which",
        "please","help","make","create","write","explain",  # common prompt filler words
    }

    # Read + concatenate all prompt text
    texts = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            txt = obj.get("prompt_text", "")
            if isinstance(txt, str) and txt.strip():
                texts.append(txt)

    combined = "\n".join(texts).lower()

    # Tokenize: keep words + apostrophes, drop numbers/punct
    tokens = re.findall(r"[a-z']+", combined)

    # Filter tokens
    clean_tokens = [
        t for t in tokens
        if len(t) >= min_word_len and t not in stopwords and not t.startswith("'") and not t.endswith("'")
    ]

    total_word_count = len(clean_tokens)
    word_counts = Counter(clean_tokens)

    # Build word cloud
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend for server environments
        from wordcloud import WordCloud
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise ImportError(
            "Missing dependency. Run: pip install wordcloud matplotlib"
        ) from e

    wc = WordCloud(
        width=1200,
        height=700,
        background_color="white",
        max_words=max_words,
        collocations=False,  # prevents bigrams like "machine_learning" dominating
    ).generate_from_frequencies(word_counts)

    # Render + optionally save
    fig = plt.figure(figsize=(12, 7))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout()

    if output_png:
        plt.savefig(output_png, dpi=200, bbox_inches="tight")
    
    plt.close(fig)  # Close figure to free memory
    plt.close('all')  # Ensure all figures are closed (Windows compatibility)
    
    # Small delay to ensure file handle is released on Windows
    import time
    time.sleep(0.05)  # 50ms delay

    return total_word_count, word_counts