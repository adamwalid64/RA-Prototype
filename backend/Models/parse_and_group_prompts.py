"""
Parse chat history JSON and organize prompts by group (e.g. by topic/assignment).
Extracted and adapted from colleague's code for use with prompt quality grading.
"""

import json
from pathlib import Path
from typing import Any


def load_chat_history_flexible(filepath: str | Path) -> list[dict[str, Any]]:
    """
    Load chat history from a JSON file with flexible structure.

    Handles:
    - data as list: [{"chat": 1}, {"chat": 2}]
    - data as object: {"chats": [...]} or {"conversations": [...]}

    Each chat is normalized to:
    - chat_id, topic, updated_at, num_messages, messages (list of user message strings)

    Uses common field name variants for id, title, and message content.
    """
    path = Path(filepath)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        chats = data
    elif isinstance(data, dict) and "chats" in data:
        chats = data["chats"]
    elif isinstance(data, dict) and "conversations" in data:
        chats = data["conversations"]
    else:
        raise ValueError(
            "Unknown JSON format. Expected a list of chats or an object with 'chats' or 'conversations'."
        )

    processed_chats = []

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

        user_messages = []
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

        processed_chats.append({
            "chat_id": chat_id,
            "topic": topic,
            "updated_at": chat.get("updated_at") or chat.get("timestamp") or chat.get("created_at"),
            "num_messages": len(user_messages),
            "messages": user_messages,
        })

    return processed_chats


def group_chats_by_topic(processed_chats: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Group parsed chats by topic (e.g. assignment name, conversation title).

    Returns a dict: topic -> list of chat dicts.
    Chats with the same topic are in one group for reviewing quality by assignment/topic.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for chat in processed_chats:
        topic = (chat.get("topic") or "Untitled").strip() or "Untitled"
        if topic not in groups:
            groups[topic] = []
        groups[topic].append(chat)
    return groups


def prompts_by_group(
    processed_chats: list[dict[str, Any]],
    *,
    group_by_topic: bool = True,
    one_prompt_per_chat: bool = False,
) -> list[dict[str, Any]]:
    """
    Turn parsed chats into a list of groups, each with a group label and list of prompt texts.

    Args:
        processed_chats: Result of load_chat_history_flexible().
        group_by_topic: If True, group chats by topic; else one group per chat.
        one_prompt_per_chat: If True, each chat becomes one prompt (all messages joined);
            if False, each user message is a separate prompt (with same group/topic).

    Returns:
        List of {"group": str, "prompts": [str, ...], "chat_ids": [str, ...]}.
    """
    if group_by_topic:
        topic_to_chats = group_chats_by_topic(processed_chats)
        result = []
        for topic, chats in topic_to_chats.items():
            prompts = []
            chat_ids = []
            for c in chats:
                chat_ids.append(c.get("chat_id", ""))
                if one_prompt_per_chat:
                    prompts.append(" ".join(c["messages"]))
                else:
                    prompts.extend(c["messages"])
            result.append({"group": topic, "prompts": prompts, "chat_ids": chat_ids})
        return result

    # One group per chat (use topic as label per chat)
    result = []
    for chat in processed_chats:
        topic = chat.get("topic", "Untitled")
        if one_prompt_per_chat:
            prompts = [" ".join(chat["messages"])]
        else:
            prompts = list(chat["messages"])
        result.append({
            "group": topic,
            "prompts": prompts,
            "chat_ids": [chat.get("chat_id", "")],
        })
    return result
