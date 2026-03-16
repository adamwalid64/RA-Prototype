from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS
import csv
import json
import uuid
import base64
import tempfile
import traceback
import textwrap
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from threading import Lock
from HelperFunctions import parse_chatgpt_prompts, prompts_to_jsonl, count_prompts_in_jsonl, generate_prompt_wordcloud
import os
# Models imported lazily in routes to reduce startup memory (helps on 512MB free tier)


def _resolve_frontend_dist_dir() -> Path:
    """
    Resolve built frontend directory across local dev and packaged executable layouts.
    """
    env_override = os.getenv("RA_FRONTEND_DIST")
    if env_override:
        override_path = Path(env_override).resolve()
        if override_path.exists():
            return override_path

    backend_root = Path(__file__).resolve().parent
    candidate_dirs = [
        backend_root.parent / "frontend" / "RA-Project" / "dist",
        backend_root / "frontend_dist",
    ]
    for candidate in candidate_dirs:
        if candidate.exists():
            return candidate

    # Default path used during local development before frontend is built.
    return backend_root.parent / "frontend" / "RA-Project" / "dist"

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _pdf_escape(value: str) -> str:
    """Escape text for a basic PDF literal string."""
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_plain_text_pdf(text: str) -> bytes:
    """
    Build a minimal multi-page PDF from plain text without external dependencies.
    This keeps PDF export working when reportlab isn't available.
    """
    lines: List[str] = []
    for raw in (text or "").splitlines():
        wrapped = textwrap.wrap(raw, width=95) or [""]
        lines.extend(wrapped)
    if not lines:
        lines = ["No export content available."]

    lines_per_page = 48
    pages = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)]

    objects: List[str] = []
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")  # 1
    objects.append("<< /Type /Pages /Kids [] /Count 0 >>")  # 2 placeholder
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")  # 3

    page_ids: List[int] = []
    for page_lines in pages:
        content_stream = ["BT", "/F1 10 Tf", "50 760 Td", "12 TL"]
        for line in page_lines:
            content_stream.append(f"({_pdf_escape(line)}) Tj")
            content_stream.append("T*")
        content_stream.append("ET")
        stream_data = "\n".join(content_stream)

        content_obj_id = len(objects) + 1
        objects.append(f"<< /Length {len(stream_data.encode('utf-8'))} >>\nstream\n{stream_data}\nendstream")
        page_obj_id = len(objects) + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>"
        )
        page_ids.append(page_obj_id)

    kid_refs = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kid_refs}] /Count {len(page_ids)} >>"

    pdf_parts: List[bytes] = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    current_offset = len(pdf_parts[0])

    for i, obj in enumerate(objects, start=1):
        obj_bytes = f"{i} 0 obj\n{obj}\nendobj\n".encode("utf-8")
        offsets.append(current_offset)
        pdf_parts.append(obj_bytes)
        current_offset += len(obj_bytes)

    xref_offset = current_offset
    xref = [f"xref\n0 {len(objects) + 1}\n", "0000000000 65535 f \n"]
    xref.extend(f"{off:010d} 00000 n \n" for off in offsets[1:])
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    pdf_parts.append("".join(xref).encode("utf-8"))
    pdf_parts.append(trailer.encode("utf-8"))
    return b"".join(pdf_parts)


def _stringify_export_payload(export_payload: dict) -> str:
    """Create a readable plain-text report used by the fallback PDF builder."""
    lines: List[str] = []
    lines.append("Reflection & Analysis Export")
    lines.append("=" * 32)
    lines.append(f"Dataset ID: {export_payload.get('dataset_id', '')}")

    file_info = export_payload.get("file") or {}
    lines.append(f"File: {file_info.get('file_name', '')}")
    lines.append(f"Uploaded: {file_info.get('uploaded_at', '')}")
    lines.append(f"Total prompts: {export_payload.get('total_prompts', 'N/A')}")

    summary = export_payload.get("summary") or {}
    if summary:
        lines.append("")
        lines.append("Summary")
        lines.append("-" * 7)
        lines.append(
            f"Total conversations in file: {summary.get('total_conversations', 'N/A')}"
        )
        lines.append(
            f"Total user prompts in file: {summary.get('total_user_prompts', 'N/A')}"
        )

    scope = export_payload.get("analysis_scope") or {}
    if scope:
        lines.append("")
        lines.append("Analysis Scope")
        lines.append("-" * 14)
        lines.append(
            f"Conversations analyzed: {scope.get('analyzed_conversations', 0)} "
            f"(max {scope.get('max_conversations', MAX_MODEL_CONVERSATIONS)})"
        )
        lines.append(f"Prompts analyzed: {scope.get('analyzed_prompts', 0)}")

    models = export_payload.get("models") or {}
    pe = models.get("paul_elder") or {}
    if pe:
        lines.append("")
        lines.append("Paul-Elder Framework")
        lines.append("-" * 20)
        stats = pe.get("classification_stats") or {}
        lines.append(f"Conversations analyzed: {pe.get('analyzed_count', 0)}")
        lines.append(
            f"Critical thinking rate: {float(stats.get('critical_thinking_percentage', 0) or 0):.1f}%"
        )
        for category in pe.get("categories") or []:
            lines.append(
                f"  - {category.get('category', 'N/A')}: "
                f"{float(category.get('percentage', 0) or 0):.1f}% "
                f"({int(category.get('count', 0) or 0)} conversations)"
            )

    srl = models.get("srl") or {}
    if srl:
        lines.append("")
        lines.append("SRL (Zimmerman, COPES, Bloom's)")
        lines.append("-" * 31)
        lines.append(f"Conversations analyzed: {srl.get('analyzed_count', 0)}")
        lines.append(
            f"Average COPES score: {float(srl.get('copes_average', 0) or 0):.2f}/15"
        )
        lines.append(
            f"Average Bloom's level: {float(srl.get('blooms_average_level', 0) or 0):.2f}/6"
        )
        phase_distribution = srl.get("phase_distribution") or {}
        if phase_distribution:
            lines.append("Dominant phase distribution:")
            for phase, count in phase_distribution.items():
                lines.append(f"  - {phase}: {count} conversations")
        ct_summary = srl.get("critical_thinking_summary") or {}
        if ct_summary:
            lines.append("Critical thinking summary:")
            lines.append(
                f"  - Critical Thinking: {ct_summary.get('critical_thinking', 0)}"
            )
            lines.append(
                f"  - Developing Critical Thinking: {ct_summary.get('developing_critical_thinking', 0)}"
            )
            lines.append(
                f"  - Efficient Help-Seeking: {ct_summary.get('efficient_help_seeking', 0)}"
            )
            lines.append(
                f"  - Low Critical Thinking: {ct_summary.get('low_critical_thinking', 0)}"
            )
            lines.append(
                f"  - Unclassifiable: {ct_summary.get('unclassifiable', 0)}"
            )
            lines.append(
                f"  - CT rate: {ct_summary.get('critical_thinking_rate_percent', 0)}%"
            )
            lines.append(
                f"  - Non-CT rate: {ct_summary.get('non_critical_thinking_rate_percent', 0)}%"
            )
            categories_present = ct_summary.get("categories_present") or []
            lines.append(
                "  - Categories present: "
                + (", ".join(categories_present) if categories_present else "None")
            )

    grading = models.get("grading") or {}
    if grading:
        lines.append("")
        lines.append("Prompt Quality (Grading)")
        lines.append("-" * 24)
        agg = grading.get("aggregate") or {}
        lines.append(
            f"Average total score: {float(agg.get('average_total_score', 0) or 0):.2f}/15"
        )
        lines.append(f"Prompts graded: {agg.get('total_prompts', 0)}")
        dim = agg.get("dimension_averages") or {}
        if dim:
            lines.append("Dimension averages:")
            for key, value in dim.items():
                lines.append(f"  - {key}: {float(value or 0):.2f}/3")

    conversations = (export_payload.get("prompts") or {}).get("conversations") or []
    if conversations:
        lines.append("")
        lines.append("Conversation Details")
        lines.append("-" * 20)
        srl_results = (models.get("srl") or {}).get("conversation_results") or []
        srl_by_chat_id = {
            str(row.get("chat_id", "")): row for row in srl_results if row.get("chat_id")
        }
        for i, convo in enumerate(conversations, 1):
            chat_id = str(convo.get("chat_id", "unknown"))
            topic = convo.get("topic", "Untitled")
            messages = convo.get("messages") or []
            srl_row = srl_by_chat_id.get(chat_id) or (
                srl_results[i - 1] if i - 1 < len(srl_results) else {}
            )
            zimmerman = srl_row.get("zimmerman") or {}
            phase_dist = zimmerman.get("distribution_percent") or {}
            lines.append(f"[Conversation {i}] {topic} ({chat_id})")
            lines.append(f"  Message count: {len(messages)}")
            if srl_row:
                lines.append(
                    f"  Dominant SRL phase: {zimmerman.get('dominant_phase') or srl_row.get('zimmerman_phase', 'N/A')}"
                )
                lines.append(
                    "  Phase distribution: "
                    f"Forethought {phase_dist.get('forethought', 0)}%, "
                    f"Performance {phase_dist.get('performance', 0)}%, "
                    f"Self-Reflection {phase_dist.get('self_reflection', 0)}%"
                )
                copes = srl_row.get("copes_components") or {}
                lines.append(
                    f"  COPES: {int(srl_row.get('copes_score', 0) or 0)}/15 "
                    f"(Conditions {int(copes.get('C', 0) or 0)}, "
                    f"Operations {int(copes.get('O', 0) or 0)}, "
                    f"Products {int(copes.get('P', 0) or 0)}, "
                    f"Evaluations {int(copes.get('E', 0) or 0)}, "
                    f"Standards {int(copes.get('S', 0) or 0)})"
                )
                blooms = srl_row.get("blooms") or {}
                lines.append(
                    f"  Bloom's: {blooms.get('name') or srl_row.get('blooms_name', 'N/A')} "
                    f"(Level {blooms.get('level') if blooms.get('level') is not None else srl_row.get('blooms_level', 'N/A')}, "
                    f"confidence {float(blooms.get('confidence', srl_row.get('blooms_confidence', 0)) or 0):.2f})"
                )
                lines.append(
                    f"  Critical thinking classification: {srl_row.get('ct_classification', 'N/A')}"
                )
                if srl_row.get("ct_rationale"):
                    lines.append(f"  CT rationale: {srl_row.get('ct_rationale')}")
            for msg_idx, msg in enumerate(messages, 1):
                lines.append(f"  Message {msg_idx}: {msg}")
            lines.append("")

    reflection = export_payload.get("reflection") or {}
    lines.append("")
    lines.append("Reflection")
    lines.append("-" * 10)
    if reflection.get("overall_summary"):
        lines.append(f"Overall: {reflection['overall_summary']}")
    for item in reflection.get("strengths") or []:
        lines.append(f"Strength: {item}")
    for item in reflection.get("risks") or []:
        lines.append(f"Risk: {item}")
    for item in reflection.get("suggestions") or []:
        lines.append(f"Suggestion: {item}")

    return "\n".join(lines)


def _build_export_prompt_data(file_path: str) -> Dict[str, Any]:
    """
    Build canonical prompt data for exports from the same capped conversations
    used by the model analyses.
    """
    conversations = _build_capped_conversation_chats(file_path)
    flat_prompts: List[Dict[str, Any]] = []
    for convo in conversations:
        chat_id = convo.get("chat_id")
        topic = convo.get("topic")
        for idx, text in enumerate(convo.get("messages") or [], 1):
            flat_prompts.append(
                {
                    "chat_id": chat_id,
                    "topic": topic,
                    "prompt_index": idx,
                    "prompt_text": text,
                }
            )
    return {
        "conversations": conversations,
        "flat": flat_prompts,
    }


def _build_export_csv(export_payload: dict) -> str:
    """Build analytics-friendly CSV export with exhaustive row types."""
    import io

    ds_id = export_payload.get("dataset_id")
    file_info = export_payload.get("file") or {}
    models = export_payload.get("models") or {}
    prompts = export_payload.get("prompts") or {}
    conversations = prompts.get("conversations") or []

    srl_results = (models.get("srl") or {}).get("conversation_results") or []
    pe_results = (models.get("paul_elder") or {}).get("conversation_results") or []

    srl_by_chat_id = {
        str(row.get("chat_id", "")): row for row in srl_results if row.get("chat_id")
    }
    pe_by_chat_id = {
        str(row.get("chat_id", "")): row for row in pe_results if row.get("chat_id")
    }

    fieldnames = [
        "dataset_id",
        "file_name",
        "uploaded_at",
        "row_type",
        "section",
        "conversation_index",
        "chat_id",
        "topic",
        "message_count",
        "message_index",
        "message_text",
        "all_messages",
        "prompt_index",
        "prompt_text",
        "prompt_total_score",
        "prompt_strength_summary",
        "prompt_weakness_summary",
        "prompt_improvement_suggestions",
        "prompt_evaluation_json",
        "analysis_scope_json",
        "srl_summary_json",
        "pe_summary_json",
        "grading_summary_json",
        "reflection_summary_json",
        "paul_elder_category",
        "paul_elder_confidence",
        "zimmerman_dominant_phase",
        "zimmerman_phases_present",
        "zimmerman_forethought_percent",
        "zimmerman_performance_percent",
        "zimmerman_self_reflection_percent",
        "copes_total",
        "copes_conditions",
        "copes_operations",
        "copes_products",
        "copes_evaluations",
        "copes_standards",
        "blooms_level",
        "blooms_name",
        "blooms_confidence",
        "blooms_unclassifiable",
        "is_critical_thinking",
        "ct_classification",
        "ct_rationale",
    ]

    rows: List[Dict[str, Any]] = []
    rows.append(
        {
            "dataset_id": ds_id,
            "file_name": file_info.get("file_name"),
            "uploaded_at": file_info.get("uploaded_at"),
            "row_type": "summary",
            "section": "dataset",
            "conversation_index": "",
            "chat_id": "",
            "topic": "Export summary",
            "message_count": (export_payload.get("analysis_scope") or {}).get(
                "analyzed_prompts", 0
            ),
            "message_index": "",
            "message_text": "",
            "all_messages": "",
            "prompt_index": "",
            "prompt_text": "",
            "prompt_total_score": "",
            "prompt_strength_summary": "",
            "prompt_weakness_summary": "",
            "prompt_improvement_suggestions": "",
            "prompt_evaluation_json": "",
            "analysis_scope_json": json.dumps(
                export_payload.get("analysis_scope") or {}, ensure_ascii=False
            ),
            "srl_summary_json": json.dumps(
                {
                    "phase_distribution": (models.get("srl") or {}).get(
                        "phase_distribution", {}
                    ),
                    "copes_average": (models.get("srl") or {}).get("copes_average"),
                    "blooms_distribution": (models.get("srl") or {}).get(
                        "blooms_distribution", {}
                    ),
                    "blooms_average_level": (models.get("srl") or {}).get(
                        "blooms_average_level"
                    ),
                    "critical_thinking_summary": (models.get("srl") or {}).get(
                        "critical_thinking_summary", {}
                    ),
                },
                ensure_ascii=False,
            ),
            "pe_summary_json": json.dumps(
                (models.get("paul_elder") or {}).get("classification_stats", {}),
                ensure_ascii=False,
            ),
            "grading_summary_json": json.dumps(
                (models.get("grading") or {}).get("aggregate", {}), ensure_ascii=False
            ),
            "reflection_summary_json": json.dumps(
                export_payload.get("reflection") or {}, ensure_ascii=False
            ),
            "paul_elder_category": "",
            "paul_elder_confidence": "",
            "zimmerman_dominant_phase": "",
            "zimmerman_phases_present": "",
            "zimmerman_forethought_percent": "",
            "zimmerman_performance_percent": "",
            "zimmerman_self_reflection_percent": "",
            "copes_total": "",
            "copes_conditions": "",
            "copes_operations": "",
            "copes_products": "",
            "copes_evaluations": "",
            "copes_standards": "",
            "blooms_level": "",
            "blooms_name": "",
            "blooms_confidence": "",
            "blooms_unclassifiable": "",
            "is_critical_thinking": "",
            "ct_classification": "",
            "ct_rationale": "",
        }
    )

    for idx, convo in enumerate(conversations, 1):
        chat_id = str(convo.get("chat_id", "unknown"))
        topic = convo.get("topic", "Untitled")
        messages = convo.get("messages") or []
        srl_row = srl_by_chat_id.get(chat_id) or (
            srl_results[idx - 1] if idx - 1 < len(srl_results) else {}
        )
        pe_row = pe_by_chat_id.get(chat_id) or (
            pe_results[idx - 1] if idx - 1 < len(pe_results) else {}
        )

        zimmerman = srl_row.get("zimmerman") or {}
        phase_dist = zimmerman.get("distribution_percent") or {}
        phases_present = zimmerman.get("phases_present") or []
        if isinstance(phases_present, list):
            phases_present_text = "; ".join(str(p) for p in phases_present)
        else:
            phases_present_text = str(phases_present or "")

        copes = srl_row.get("copes_components") or {}
        blooms = srl_row.get("blooms") or {}

        all_messages_text = " | ".join(
            (str(msg).replace("\n", " ").strip() for msg in messages if msg)
        )

        rows.append(
            {
                "dataset_id": ds_id,
                "file_name": file_info.get("file_name"),
                "uploaded_at": file_info.get("uploaded_at"),
                "row_type": "conversation",
                "section": "conversation_summary",
                "conversation_index": idx,
                "chat_id": chat_id,
                "topic": topic,
                "message_count": srl_row.get("message_count", len(messages)),
                "message_index": "",
                "message_text": "",
                "all_messages": all_messages_text,
                "prompt_index": "",
                "prompt_text": "",
                "prompt_total_score": "",
                "prompt_strength_summary": "",
                "prompt_weakness_summary": "",
                "prompt_improvement_suggestions": "",
                "prompt_evaluation_json": "",
                "analysis_scope_json": "",
                "srl_summary_json": "",
                "pe_summary_json": "",
                "grading_summary_json": "",
                "reflection_summary_json": "",
                "paul_elder_category": pe_row.get("category", ""),
                "paul_elder_confidence": pe_row.get("confidence", ""),
                "zimmerman_dominant_phase": zimmerman.get("dominant_phase")
                or srl_row.get("zimmerman_phase", ""),
                "zimmerman_phases_present": phases_present_text,
                "zimmerman_forethought_percent": phase_dist.get("forethought", ""),
                "zimmerman_performance_percent": phase_dist.get("performance", ""),
                "zimmerman_self_reflection_percent": phase_dist.get(
                    "self_reflection", ""
                ),
                "copes_total": srl_row.get("copes_score", ""),
                "copes_conditions": copes.get("C", ""),
                "copes_operations": copes.get("O", ""),
                "copes_products": copes.get("P", ""),
                "copes_evaluations": copes.get("E", ""),
                "copes_standards": copes.get("S", ""),
                "blooms_level": blooms.get("level", srl_row.get("blooms_level", "")),
                "blooms_name": blooms.get("name", srl_row.get("blooms_name", "")),
                "blooms_confidence": blooms.get(
                    "confidence", srl_row.get("blooms_confidence", "")
                ),
                "blooms_unclassifiable": blooms.get("unclassifiable", ""),
                "is_critical_thinking": srl_row.get("is_critical_thinking", ""),
                "ct_classification": srl_row.get("ct_classification", ""),
                "ct_rationale": srl_row.get("ct_rationale", ""),
            }
        )

        for msg_idx, msg in enumerate(messages, 1):
            rows.append(
                {
                    "dataset_id": ds_id,
                    "file_name": file_info.get("file_name"),
                    "uploaded_at": file_info.get("uploaded_at"),
                    "row_type": "message",
                    "section": "conversation_message",
                    "conversation_index": idx,
                    "chat_id": chat_id,
                    "topic": topic,
                    "message_count": len(messages),
                    "message_index": msg_idx,
                    "message_text": msg,
                    "all_messages": "",
                    "prompt_index": "",
                    "prompt_text": "",
                    "prompt_total_score": "",
                    "prompt_strength_summary": "",
                    "prompt_weakness_summary": "",
                    "prompt_improvement_suggestions": "",
                    "prompt_evaluation_json": "",
                    "analysis_scope_json": "",
                    "srl_summary_json": "",
                    "pe_summary_json": "",
                    "grading_summary_json": "",
                    "reflection_summary_json": "",
                    "paul_elder_category": "",
                    "paul_elder_confidence": "",
                    "zimmerman_dominant_phase": "",
                    "zimmerman_phases_present": "",
                    "zimmerman_forethought_percent": "",
                    "zimmerman_performance_percent": "",
                    "zimmerman_self_reflection_percent": "",
                    "copes_total": "",
                    "copes_conditions": "",
                    "copes_operations": "",
                    "copes_products": "",
                    "copes_evaluations": "",
                    "copes_standards": "",
                    "blooms_level": "",
                    "blooms_name": "",
                    "blooms_confidence": "",
                    "blooms_unclassifiable": "",
                    "is_critical_thinking": "",
                    "ct_classification": "",
                    "ct_rationale": "",
                }
            )

    grading_details = (models.get("grading") or {}).get("details") or []
    for idx, row in enumerate(grading_details, 1):
        ev = row.get("evaluation") or {}
        suggestions = ev.get("improvement_suggestions") or []
        rows.append(
            {
                "dataset_id": ds_id,
                "file_name": file_info.get("file_name"),
                "uploaded_at": file_info.get("uploaded_at"),
                "row_type": "grading_prompt",
                "section": "grading_detail",
                "conversation_index": row.get("conversation_index", ""),
                "chat_id": row.get("chat_id", ""),
                "topic": row.get("topic", ""),
                "message_count": "",
                "message_index": "",
                "message_text": "",
                "all_messages": "",
                "prompt_index": row.get("prompt_index", idx),
                "prompt_text": row.get("prompt_text", ""),
                "prompt_total_score": row.get("total_score", ev.get("total_score", "")),
                "prompt_strength_summary": ev.get("strength_summary", ""),
                "prompt_weakness_summary": ev.get("weakness_summary", ""),
                "prompt_improvement_suggestions": " | ".join(
                    str(x) for x in suggestions
                ),
                "prompt_evaluation_json": json.dumps(ev, ensure_ascii=False),
                "analysis_scope_json": "",
                "srl_summary_json": "",
                "pe_summary_json": "",
                "grading_summary_json": "",
                "reflection_summary_json": "",
                "paul_elder_category": "",
                "paul_elder_confidence": "",
                "zimmerman_dominant_phase": "",
                "zimmerman_phases_present": "",
                "zimmerman_forethought_percent": "",
                "zimmerman_performance_percent": "",
                "zimmerman_self_reflection_percent": "",
                "copes_total": "",
                "copes_conditions": "",
                "copes_operations": "",
                "copes_products": "",
                "copes_evaluations": "",
                "copes_standards": "",
                "blooms_level": "",
                "blooms_name": "",
                "blooms_confidence": "",
                "blooms_unclassifiable": "",
                "is_critical_thinking": "",
                "ct_classification": "",
                "ct_rationale": "",
            }
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _build_export_pdf(export_payload: dict) -> bytes:
    """Build a PDF from the export payload. Requires reportlab."""
    import io
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    style_section = ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#1f2937"),
    )
    style_subsection = ParagraphStyle(
        name="SubSectionHeading",
        parent=styles["Heading3"],
        fontSize=11,
        spaceBefore=6,
        spaceAfter=4,
        textColor=colors.HexColor("#374151"),
    )
    style_body = ParagraphStyle(
        name="BodyTextDense",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=12,
        spaceAfter=4,
    )
    flow = []

    def para(text, style=style_body):
        if not text:
            return
        safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        flow.append(Paragraph(safe, style))
        flow.append(Spacer(1, 2))

    flow.append(Paragraph("<b>Reflection &amp; Analysis Export</b>", styles["Title"]))
    flow.append(Spacer(1, 12))
    para(f"<b>Dataset ID:</b> {export_payload.get('dataset_id', '')}", style_subsection)
    file_info = export_payload.get("file") or {}
    para(f"<b>File:</b> {file_info.get('file_name', '')} | <b>Uploaded:</b> {file_info.get('uploaded_at', '')}")
    total = export_payload.get("total_prompts")
    para(f"<b>Total prompts:</b> {total}" if total is not None else "<b>Total prompts:</b> —")
    summary = export_payload.get("summary")
    if summary:
        para("<b>Summary:</b> " + json.dumps(summary, ensure_ascii=False))
    flow.append(Spacer(1, 12))

    models = export_payload.get("models") or {}
    pe = models.get("paul_elder")
    if pe:
        flow.append(Paragraph("<u><b>Paul-Elder Framework</b></u>", style_section))
        stats = pe.get("classification_stats") or {}
        para(f"<b>Conversations analyzed:</b> {pe.get('analyzed_count', 0)}")
        para(f"<b>Critical thinking:</b> {stats.get('critical_thinking_percentage', 0):.1f}%")
        for c in (pe.get("categories") or []):
            para(
                f"• <b>{c.get('category', '')}</b>: "
                f"{c.get('percentage', 0):.1f}% ({c.get('count', 0)} conversations)"
            )
        detailed = pe.get("conversation_results") or []
        if detailed:
            flow.append(Paragraph("<b>Per-conversation analysis</b>", style_subsection))
            for i, row in enumerate(detailed, 1):
                para(
                    f"[Conversation {i}] <b>{row.get('topic', 'Untitled')}</b> "
                    f"(ID: {row.get('chat_id', 'unknown')}) | "
                    f"Category: {row.get('category', 'N/A')} | "
                    f"Confidence: {float(row.get('confidence', 0) or 0):.2f}"
                )
        flow.append(Spacer(1, 8))

    srl = models.get("srl")
    if srl:
        flow.append(Paragraph("<u><b>SRL (Zimmerman, COPES, Bloom's)</b></u>", style_section))
        para(f"<b>Conversations analyzed:</b> {srl.get('analyzed_count', 0)}")
        para(f"<b>COPES average:</b> {srl.get('copes_average', 0):.1f}/15 | <b>Bloom's avg level:</b> {srl.get('blooms_average_level', 0):.1f}/6")
        pd = srl.get("phase_distribution") or {}
        para("<b>Phase distribution:</b> " + ", ".join(f"{k}: {v}" for k, v in pd.items()))
        ct_summary = srl.get("critical_thinking_summary") or {}
        if ct_summary:
            para(
                "<b>Critical thinking summary:</b> "
                f"Critical Thinking {ct_summary.get('critical_thinking', 0)}, "
                f"Developing Critical Thinking {ct_summary.get('developing_critical_thinking', 0)}, "
                f"Efficient Help-Seeking {ct_summary.get('efficient_help_seeking', 0)}, "
                f"Low Critical Thinking {ct_summary.get('low_critical_thinking', 0)}, "
                f"Unclassifiable {ct_summary.get('unclassifiable', 0)} "
                f"(CT rate {ct_summary.get('critical_thinking_rate_percent', 0)}%, "
                f"Non-CT rate {ct_summary.get('non_critical_thinking_rate_percent', 0)}%)"
            )
            categories_present = ct_summary.get("categories_present") or []
            para(
                "<b>Categories present:</b> "
                + (", ".join(categories_present) if categories_present else "None")
            )
        detailed = srl.get("conversation_results") or []
        if detailed:
            flow.append(Paragraph("<b>Per-conversation SRL values</b>", style_subsection))
            for i, row in enumerate(detailed, 1):
                zimmerman = row.get("zimmerman") or {}
                dist = zimmerman.get("distribution_percent") or {}
                copes = row.get("copes_components") or {}
                blooms = row.get("blooms") or {}
                para(
                    f"[Conversation {i}] <b>{row.get('topic', 'Untitled')}</b> "
                    f"(ID: {row.get('chat_id', 'unknown')}, "
                    f"messages: {row.get('message_count', 0)})"
                )
                para(
                    "  Zimmerman phase distribution: "
                    f"Forethought {dist.get('forethought', 0)}%, "
                    f"Performance {dist.get('performance', 0)}%, "
                    f"Self-Reflection {dist.get('self_reflection', 0)}% "
                    f"| Dominant: {zimmerman.get('dominant_phase', row.get('zimmerman_phase', 'N/A'))}"
                )
                para(
                    "  COPES: "
                    f"{row.get('copes_score', 0)}/15 "
                    f"(Conditions {copes.get('C', 0)}, "
                    f"Operations {copes.get('O', 0)}, "
                    f"Products {copes.get('P', 0)}, "
                    f"Evaluations {copes.get('E', 0)}, "
                    f"Standards {copes.get('S', 0)})"
                )
                para(
                    "  Bloom's: "
                    f"{blooms.get('name', row.get('blooms_name', 'N/A'))} "
                    f"(Level {blooms.get('level', row.get('blooms_level', 'N/A'))}, "
                    f"confidence {float(blooms.get('confidence', row.get('blooms_confidence', 0)) or 0):.2f})"
                )
                para(
                    f"  <b>Critical Thinking:</b> {row.get('ct_classification', 'N/A')}"
                    + (
                        f" | Rationale: {row.get('ct_rationale')}"
                        if row.get("ct_rationale")
                        else ""
                    )
                )
                flow.append(Spacer(1, 4))
        flow.append(Spacer(1, 8))

    grading = models.get("grading")
    if grading:
        flow.append(Paragraph("<u><b>Prompt Quality (Grading)</b></u>", style_section))
        agg = grading.get("aggregate") or {}
        para(f"<b>Prompts graded:</b> {agg.get('total_prompts', 0)} | <b>Average total score:</b> {agg.get('average_total_score', 0):.1f}/15")
        dim = agg.get("dimension_averages") or {}
        if dim:
            para("<b>Dimension averages:</b> " + ", ".join(f"{k}: {v:.1f}" for k, v in dim.items()))
        flow.append(Spacer(1, 8))
        details = grading.get("details") or []
        if details:
            flow.append(Paragraph("<b>Per-prompt feedback (all graded prompts)</b>", style_subsection))
            for i, row in enumerate(details, 1):
                ev = row.get("evaluation") or {}
                score = row.get("total_score") or ev.get("total_score") or 0
                para(f"<b>Prompt {i} (score {score}/15)</b>: {row.get('prompt_text') or ''}")
                if ev.get("strength_summary"):
                    para("  <b>Strength:</b> " + str(ev["strength_summary"]))
                if ev.get("weakness_summary"):
                    para("  <b>Area to improve:</b> " + str(ev["weakness_summary"]))
                for s in (ev.get("improvement_suggestions") or []):
                    para("  <b>Suggestion:</b> " + str(s))
                para("  <b>Raw evaluation JSON:</b> " + json.dumps(ev, ensure_ascii=False))
                flow.append(Spacer(1, 4))
            flow.append(Spacer(1, 8))

    prompt_data = export_payload.get("prompts") or {}
    prompt_conversations = prompt_data.get("conversations") or []
    if prompt_conversations:
        flow.append(Paragraph("<u><b>All Conversation Messages</b></u>", style_section))
        for convo_idx, convo in enumerate(prompt_conversations, 1):
            topic = convo.get("topic", "Untitled")
            chat_id = convo.get("chat_id", "unknown")
            para(f"[Conversation {convo_idx}] <b>{topic}</b> ({chat_id})")
            for prompt_idx, prompt_text in enumerate(convo.get("messages") or [], 1):
                para(f"  <b>Message {prompt_idx}:</b> {prompt_text}")
        flow.append(Spacer(1, 8))

    ref = export_payload.get("reflection") or {}
    flow.append(Paragraph("<u><b>Reflection</b></u>", style_section))
    if ref.get("overall_summary"):
        para("<b>Overall:</b> " + str(ref["overall_summary"]))
    for s in ref.get("strengths") or []:
        para("<b>Strength:</b> " + str(s))
    for r in ref.get("risks") or []:
        para("<b>Risk:</b> " + str(r))
    for s in ref.get("suggestions") or []:
        para("<b>Suggestion:</b> " + str(s))

    doc.build(flow)
    return buf.getvalue()


FRONTEND_DIST_DIR = _resolve_frontend_dist_dir()
app = Flask(__name__, static_folder=str(FRONTEND_DIST_DIR), static_url_path="")
CORS(app)

# In-memory storage for uploaded files
# Structure: {dataset_id: {file_name, file_size, uploaded_at, content, file_type}}
uploaded_datasets = {}

# In-memory storage for analysis progress (per analysis type, so PE/SRL/grading are independent)
# Structure: {dataset_id: {'paul_elder': {...}, 'srl': {...}, 'grading': {...}}}
# Each slot: {current: int, total: int, message: str, status: str}
analysis_progress = {}
analysis_run_lock = Lock()
active_analysis_by_dataset: Dict[str, str] = {}
MAX_MODEL_CONVERSATIONS = 25


def _get_dataset_api_key(dataset_id: str) -> Optional[str]:
    """Return the dataset-specific OpenAI API key if present."""
    ds = uploaded_datasets.get(dataset_id) or {}
    api_key = (ds.get("openai_api_key") or "").strip()
    return api_key or None

def _progress_slot(dataset_id, analysis_type):
    """Get or create the progress dict for this dataset and analysis type."""
    if dataset_id not in analysis_progress:
        analysis_progress[dataset_id] = {}
    if analysis_type not in analysis_progress[dataset_id]:
        analysis_progress[dataset_id][analysis_type] = {
            'current': 0, 'total': MAX_MODEL_CONVERSATIONS, 'message': 'Analysis not started', 'status': 'idle'
        }
    return analysis_progress[dataset_id][analysis_type]


def _try_begin_analysis(dataset_id: str, analysis_type: str) -> Tuple[bool, Optional[str]]:
    """Allow only one analysis type at a time per dataset."""
    with analysis_run_lock:
        active = active_analysis_by_dataset.get(dataset_id)
        if active is not None:
            return False, active
        active_analysis_by_dataset[dataset_id] = analysis_type
        return True, None


def _end_analysis(dataset_id: str, analysis_type: str) -> None:
    """Release active-analysis lock for this dataset if owned by analysis_type."""
    with analysis_run_lock:
        if active_analysis_by_dataset.get(dataset_id) == analysis_type:
            del active_analysis_by_dataset[dataset_id]


def _cap_prompts_to_first_conversations(prompts: List[Any], max_conversations: int = MAX_MODEL_CONVERSATIONS) -> List[Any]:
    """Keep prompts belonging to the first N conversations encountered."""
    if max_conversations <= 0:
        return []
    seen_conversation_ids = set()
    capped_prompts = []
    for prompt in prompts:
        conversation_id = (getattr(prompt, "conversation_id", "") or "").strip() or "__unknown_conversation__"
        if conversation_id not in seen_conversation_ids:
            if len(seen_conversation_ids) >= max_conversations:
                break
            seen_conversation_ids.add(conversation_id)
        capped_prompts.append(prompt)
    return capped_prompts


def _build_capped_conversation_chats(file_path: str) -> List[Dict[str, Any]]:
    """Build chat-level records from the first MAX_MODEL_CONVERSATIONS conversations."""
    prompts, _ = parse_chatgpt_prompts(file_path)
    prompts = _cap_prompts_to_first_conversations(prompts, MAX_MODEL_CONVERSATIONS)
    chats_by_id: Dict[str, Dict[str, Any]] = {}
    for p in prompts:
        cid = p.conversation_id or "unknown"
        if cid not in chats_by_id:
            chats_by_id[cid] = {
                "chat_id": cid,
                "topic": p.conversation_title or "Untitled",
                "messages": [],
            }
        text = (p.prompt_text or "").strip()
        if text:
            chats_by_id[cid]["messages"].append(text)
    chats: List[Dict[str, Any]] = []
    for chat in chats_by_id.values():
        messages = chat.get("messages") or []
        if not messages:
            continue
        chat["num_messages"] = len(messages)
        chats.append(chat)
    return chats


def _conversation_texts_from_chats(chats: List[Dict[str, Any]]) -> List[str]:
    """Flatten each chat into one conversation string for conversation-level models."""
    conversation_texts: List[str] = []
    for c in chats:
        messages = c.get("messages") or []
        if not messages:
            continue
        joined = "\n".join(f"Message {idx + 1}: {text}" for idx, text in enumerate(messages))
        conversation_texts.append(joined)
    return conversation_texts

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# Upload file and store in memory variable
# Max upload size: 50MB (streamed)
UPLOAD_MAX_BYTES = 50 * 1024 * 1024
CHUNK_SIZE = 64 * 1024  # 64KB for streaming


def _stream_upload_to_path(file, path: str, max_bytes: int) -> int:
    """Stream upload to path in chunks. Returns bytes written. Raises if over max_bytes."""
    written = 0
    with open(path, "wb") as out:
        while True:
            chunk = file.read(CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                out.close()
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise ValueError(f"File size exceeds {max_bytes / (1024 * 1024):.0f}MB limit")
            out.write(chunk)
    return written


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Handle file upload: stream to disk (no full file in memory)."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        allowed_extensions = {".json", ".csv", ".txt"}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": "File must be JSON, CSV, or TXT format"}), 400

        api_key = (request.form.get("api_key") or "").strip()
        if file_ext == ".json" and not api_key:
            return jsonify({
                "error": "OpenAI API key is required for JSON uploads",
                "message": "Please enter your OpenAI API key before uploading your JSON file."
            }), 400

        dataset_id = str(uuid.uuid4())
        upload_id = str(uuid.uuid4())
        safe_name = secure_filename(file.filename)
        store_path = os.path.join(tempfile.gettempdir(), f"ra_upload_{dataset_id}{file_ext}")

        try:
            file_size = _stream_upload_to_path(file, store_path, UPLOAD_MAX_BYTES)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # No JSON parse at upload (would load full file into memory). Invalid JSON will fail on first use.

        uploaded_datasets[dataset_id] = {
            "upload_id": upload_id,
            "file_name": safe_name,
            "file_size": file_size,
            "uploaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "file_path": store_path,
            "file_type": file_ext,
            "openai_api_key": api_key if file_ext == ".json" else None,
        }

        return jsonify({
            "upload_id": upload_id,
            "dataset_id": dataset_id,
            "message": "File uploaded successfully",
            "file_name": safe_name,
            "file_size": file_size,
            "uploaded_at": uploaded_datasets[dataset_id]["uploaded_at"],
        }), 200
    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

# Analyze the data and generate results
@app.route("/api/results/<dataset_id>", methods=["GET"])
def get_results(dataset_id):
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404

        ds = uploaded_datasets[dataset_id]
        file_path = ds["file_path"]
        file_type = ds["file_type"]

        if file_type != ".json":
            return jsonify({"error": "Only JSON files are currently supported"}), 400

        # Parse a small prompt sample for preview while still computing full summary counts.
        prompts, summary = parse_chatgpt_prompts(file_path, max_prompts=5)

        # Create temporary JSONL file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as tmp_jsonl:
            prompts_to_jsonl(prompts, tmp_jsonl.name)
            jsonl_path = tmp_jsonl.name
        
        try:
            # Count the number of prompts
            num_prompts = count_prompts_in_jsonl(jsonl_path)
            
            # Word cloud is optional: skip if SKIP_WORDCLOUD=1 or on failure (saves ~100MB+ on free tier)
            word_cloud_base64 = None
            if not os.environ.get("SKIP_WORDCLOUD"):
                try:
                    word_cloud_path = os.path.join(tempfile.gettempdir(), f"wordcloud_{dataset_id}.png")
                    generate_prompt_wordcloud(jsonl_path, output_png=word_cloud_path)
                    if os.path.exists(word_cloud_path):
                        with open(word_cloud_path, 'rb') as img_file:
                            word_cloud_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        import time
                        for attempt in range(3):
                            try:
                                os.unlink(word_cloud_path)
                                break
                            except PermissionError:
                                if attempt < 2:
                                    time.sleep(0.1)
                except (MemoryError, Exception) as e:
                    print(f"Word cloud skipped: {e}")
            
            # Read a few prompts for preview (first 5)
            prompt_previews = []
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= 5:  # Only get first 5 prompts
                        break
                    try:
                        prompt_obj = json.loads(line.strip())
                        prompt_previews.append({
                            "prompt_text": prompt_obj.get("prompt_text", "")[:200] + ("..." if len(prompt_obj.get("prompt_text", "")) > 200 else ""),
                            "conversation_title": prompt_obj.get("conversation_title", "Untitled"),
                            "message_create_time_iso_utc": prompt_obj.get("message_create_time_iso_utc")
                        })
                    except json.JSONDecodeError:
                        continue
        finally:
            # Clean up JSONL file
            if os.path.exists(jsonl_path):
                os.unlink(jsonl_path)
        
        # Include stored grading results and reflection if available
        grading_results = uploaded_datasets[dataset_id].get("grading_results")
        reflection = {
            "strengths": [],
            "risks": [],
            "suggestions": [],
            "overall_summary": ""
        }
        if grading_results:
            agg = grading_results.get("aggregate", {})
            if agg.get("strength_summary"):
                reflection["strengths"] = [agg["strength_summary"]]
            if agg.get("weakness_summary"):
                reflection["risks"] = [agg["weakness_summary"]]
            reflection["suggestions"] = agg.get("improvement_suggestions") or []
            total_score = agg.get("average_total_score")
            dim_avg = agg.get("dimension_averages") or {}
            parts = [f"Average total score: {total_score}/15."]
            if dim_avg:
                parts.append("Dimension averages: " + ", ".join(f"{k}: {v:.1f}" for k, v in dim_avg.items()))
            reflection["overall_summary"] = " ".join(parts)

        # total_prompts: show full count from stream; preview only loads a small sample.
        total_in_file = summary.get("total_user_prompts", num_prompts)
        response = {
            "dataset_id": dataset_id,
            "analysis": {
                "dataset_id": dataset_id,
                "total_prompts": total_in_file,
                "categories": [],
                "breakdown": {},
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "classification_stats": None,
                "grading_results": grading_results
            },
            "reflection": reflection,
            # Additional data for dashboard
            "prompt_previews": prompt_previews,
            "word_cloud_image": f"data:image/png;base64,{word_cloud_base64}" if word_cloud_base64 else None,
            "summary": summary
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        # Log full traceback for debugging
        error_traceback = traceback.format_exc()
        print(f"Error in get_results: {error_traceback}")
        return jsonify({
            "error": f"Analysis failed: {str(e)}",
            "traceback": error_traceback if app.debug else None
        }), 500

# Analyze classification on-demand (conversation-level, capped at 25)
@app.route("/api/analyze-classification/<dataset_id>", methods=["POST"])
def analyze_classification(dataset_id):
    """Analyze prompts using Paul-Elder framework (capped to 25 conversations)."""
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404
        can_start, active_type = _try_begin_analysis(dataset_id, "paul_elder")
        if not can_start:
            return jsonify({
                "error": "Another analysis is already running",
                "message": f"Cannot start Paul-Elder while '{active_type}' is running. Please wait for it to finish."
            }), 409

        try:
            ds = uploaded_datasets[dataset_id]
            api_key = _get_dataset_api_key(dataset_id)
            file_path = ds["file_path"]
            file_type = ds["file_type"]
            if file_type != ".json":
                return jsonify({"error": "Only JSON files are currently supported"}), 400
            if not api_key:
                return jsonify({
                    "error": "Missing API key for this dataset",
                    "message": "Upload the JSON file again and include your OpenAI API key."
                }), 400

            chats = _build_capped_conversation_chats(file_path)
            conversation_texts = _conversation_texts_from_chats(chats)

            # Classify conversations using Paul-Elder framework
            if not conversation_texts:
                return jsonify({"error": "No conversations found to analyze"}), 400

            print(f"Classifying {len(conversation_texts)} conversations using Paul-Elder framework...")

            # Initialize progress tracking for this analysis type only
            slot = _progress_slot(dataset_id, 'paul_elder')
            slot.update({
                'current': 0,
                'total': len(conversation_texts),
                'message': f"Starting analysis of {len(conversation_texts)} conversations...",
                'status': 'running'
            })

            def update_progress(current, total, message):
                _progress_slot(dataset_id, 'paul_elder').update({
                    'current': current, 'total': total, 'message': message,
                    'status': 'running' if current < total else 'complete'
                })

            try:
                from Models.PE_classify_chats import analyze_chat_history as pe_analyze_chat_history
                classification_df, classification_stats = pe_analyze_chat_history(
                    conversation_texts,
                    progress_callback=update_progress,
                    unit_label="conversation",
                    api_key=api_key,
                )
                _progress_slot(dataset_id, 'paul_elder')['status'] = 'complete'
            except ValueError as e:
                if "OPENAI_API_KEY" in str(e):
                    return jsonify({
                        "error": "OpenAI API key is required",
                        "message": "Please upload your JSON again and provide a valid OpenAI API key.",
                        "instructions": [
                            "1. Go back to the upload page",
                            "2. Select your JSON file",
                            "3. Enter your OpenAI API key",
                            "4. Upload the file again"
                        ]
                    }), 400
                raise

            # Format classification results for frontend
            categories = []
            breakdown = {}

            if classification_stats and classification_df is not None:
                classification_stats["total_conversations_analyzed"] = len(conversation_texts)
                # Build categories array with percentages and counts
                category_breakdown = classification_stats.get('category_breakdown', {})
                total_classified = classification_stats.get('total_messages', 0)

                for category_name, count in category_breakdown.items():
                    percentage = (count / total_classified * 100) if total_classified > 0 else 0

                    # Get example messages for this category
                    category_examples = classification_df[
                        classification_df['category'] == category_name
                    ]['message'].head(3).tolist()

                    categories.append({
                        "category": category_name,
                        "percentage": round(percentage, 2),
                        "count": int(count),
                        "examples": category_examples
                    })

                # Build breakdown object (using category codes for consistency)
                # Map category names to codes
                category_code_map = {
                    'Clarity': 'CT1',
                    'Accuracy': 'CT2',
                    'Precision': 'CT3',
                    'Relevance': 'CT4',
                    'Depth': 'CT5',
                    'Breadth': 'CT6',
                    'Logicalness': 'CT7',
                    'Significance': 'CT8',
                    'Fairness': 'CT9',
                    'Non-Critical Thinking': 'Non-CT'
                }

                for category_name, count in category_breakdown.items():
                    code = category_code_map.get(category_name, category_name.lower().replace(' ', '_'))
                    breakdown[code] = round((count / total_classified * 100) if total_classified > 0 else 0, 2)

            # Return classification results
            detailed_conversation_results = []
            if classification_df is not None:
                for i, (_, row) in enumerate(classification_df.iterrows()):
                    chat = chats[i] if i < len(chats) else {}
                    detailed_conversation_results.append({
                        "chat_id": chat.get("chat_id"),
                        "topic": chat.get("topic"),
                        "message_count": len(chat.get("messages") or []),
                        "conversation_text": row.get("message"),
                        "category": row.get("category"),
                        "confidence": row.get("confidence"),
                    })

            response = {
                "dataset_id": dataset_id,
                "categories": categories,
                "breakdown": breakdown,
                "classification_stats": classification_stats,
                "conversation_results": detailed_conversation_results,
                "analyzed_count": len(conversation_texts),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            # Store for later export
            uploaded_datasets[dataset_id]["classification_results"] = response

            return jsonify(response), 200
        finally:
            _end_analysis(dataset_id, "paul_elder")
        
    except ValueError as e:
        # Handle specific ValueError for missing API key
        if "OPENAI_API_KEY" in str(e):
            return jsonify({
                "error": "OpenAI API key is required",
                "message": "Please upload your JSON again and provide a valid OpenAI API key.",
                "instructions": [
                    "1. Go back to the upload page",
                    "2. Select your JSON file",
                    "3. Enter your OpenAI API key",
                    "4. Upload the file again"
                ]
            }), 400
        raise
    except Exception as e:
        # Log full traceback for debugging
        error_traceback = traceback.format_exc()
        print(f"Error in analyze_classification: {error_traceback}")
        return jsonify({
            "error": f"Classification analysis failed: {str(e)}",
            "traceback": error_traceback if app.debug else None
        }), 500

# Analyze SRL (Self-Regulated Learning) on capped conversations
@app.route("/api/analyze-srl/<dataset_id>", methods=["POST"])
def analyze_srl(dataset_id):
    """Analyze prompts using SRL (capped to 25 conversations)."""
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404
        can_start, active_type = _try_begin_analysis(dataset_id, "srl")
        if not can_start:
            return jsonify({
                "error": "Another analysis is already running",
                "message": f"Cannot start SRL while '{active_type}' is running. Please wait for it to finish."
            }), 409
        try:
            ds = uploaded_datasets[dataset_id]
            api_key = _get_dataset_api_key(dataset_id)
            file_path = ds["file_path"]
            file_type = ds["file_type"]
            if file_type != ".json":
                return jsonify({"error": "Only JSON files are currently supported"}), 400
            if not api_key:
                return jsonify({
                    "error": "Missing API key for this dataset",
                    "message": "Upload the JSON file again and include your OpenAI API key."
                }), 400
            chats = _build_capped_conversation_chats(file_path)
            conversation_texts = _conversation_texts_from_chats(chats)
            if not conversation_texts:
                return jsonify({"error": "No conversations found to analyze"}), 400
            slot = _progress_slot(dataset_id, "srl")
            slot.update({
                'current': 0, 'total': len(conversation_texts),
                'message': f"Starting SRL analysis of {len(conversation_texts)} conversations...", 'status': 'running'
            })
            def update_progress(current, total, message):
                _progress_slot(dataset_id, 'srl').update({
                    'current': current, 'total': total, 'message': message,
                    'status': 'running' if current < total else 'complete'
                })
            from Models.SRL_classify_chats import (
                enhanced_critical_thinking_analysis_json as srl_conversation_analysis,
                classify_CT as srl_classify_ct,
            )
            df = srl_conversation_analysis(
                chats,
                progress_callback=update_progress,
                unit_label="conversation",
                api_key=api_key,
            )
            update_progress(
                len(conversation_texts),
                len(conversation_texts),
                "Computing critical thinking classifications...",
            )
            classified_df = srl_classify_ct(df)
            _progress_slot(dataset_id, 'srl')['status'] = 'complete'
            phase_counts = classified_df['zimmerman_dominant_phase'].value_counts()
            phase_distribution = {k: int(v) for k, v in phase_counts.items()}
            copes_avg = float(classified_df['copes_score'].mean())
            blooms_counts = classified_df['blooms_name'].value_counts()
            blooms_distribution = {k: int(v) for k, v in blooms_counts.items()}
            ct_counts = classified_df["ct_classification"].value_counts().to_dict()
            total_conversations = len(classified_df)
            critical_count = int(ct_counts.get("Critical Thinking", 0))
            developing_count = int(ct_counts.get("Developing Critical Thinking", 0))
            efficient_help_count = int(ct_counts.get("Efficient Help-Seeking", 0))
            low_ct_count = int(ct_counts.get("Low Critical Thinking", 0))
            unclassifiable_count = int(ct_counts.get("UNCLASSIFIABLE", 0))
            critical_total = critical_count + developing_count
            non_critical_total = efficient_help_count + low_ct_count
            ct_summary = {
                "critical_thinking": critical_count,
                "developing_critical_thinking": developing_count,
                "efficient_help_seeking": efficient_help_count,
                "low_critical_thinking": low_ct_count,
                "unclassifiable": unclassifiable_count,
                "critical_thinking_rate_percent": round(
                    (critical_total / total_conversations * 100)
                    if total_conversations > 0
                    else 0.0,
                    2,
                ),
                "non_critical_thinking_rate_percent": round(
                    (non_critical_total / total_conversations * 100)
                    if total_conversations > 0
                    else 0.0,
                    2,
                ),
                "category_percentages": {
                    "Critical Thinking": round(
                        (critical_count / total_conversations * 100)
                        if total_conversations > 0
                        else 0.0,
                        2,
                    ),
                    "Developing Critical Thinking": round(
                        (developing_count / total_conversations * 100)
                        if total_conversations > 0
                        else 0.0,
                        2,
                    ),
                    "Efficient Help-Seeking": round(
                        (efficient_help_count / total_conversations * 100)
                        if total_conversations > 0
                        else 0.0,
                        2,
                    ),
                    "Low Critical Thinking": round(
                        (low_ct_count / total_conversations * 100)
                        if total_conversations > 0
                        else 0.0,
                        2,
                    ),
                },
                "categories_present": [
                    category
                    for category in (
                        "Critical Thinking",
                        "Developing Critical Thinking",
                        "Efficient Help-Seeking",
                        "Low Critical Thinking",
                    )
                    if int(ct_counts.get(category, 0)) > 0
                ],
            }
            conversation_results = []
            for idx, (_, row) in enumerate(classified_df.iterrows()):
                level = row.get('blooms_level')
                chat = chats[idx] if idx < len(chats) else {}
                messages = chat.get("messages") or []
                sample_messages = []
                for msg in messages[:3]:
                    txt = (msg or "").strip()
                    if not txt:
                        continue
                    sample_messages.append(
                        txt[:220] + ("..." if len(txt) > 220 else "")
                    )

                phases_present_raw = row.get("zimmerman_phases_present") or ""
                phases_present = [
                    p.strip() for p in str(phases_present_raw).split(",") if p.strip()
                ]
                blooms_conf = row.get("blooms_confidence", 0.0)
                try:
                    blooms_conf = float(blooms_conf or 0.0)
                except (TypeError, ValueError):
                    blooms_conf = 0.0
                blooms_unclassifiable = bool(row.get("blooms_unclassifiable", False))

                conversation_results.append({
                    "chat_id": chat.get("chat_id"),
                    "topic": chat.get("topic"),
                    "message_count": int(row.get("num_messages", len(messages))),
                    "sample_messages": sample_messages,
                    "zimmerman_phase": row.get('zimmerman_dominant_phase'),
                    "zimmerman": {
                        "dominant_phase": row.get("zimmerman_dominant_phase"),
                        "phases_present": phases_present,
                        "distribution_percent": {
                            "forethought": int(row.get("zimmerman_forethought_pct") or 0),
                            "performance": int(row.get("zimmerman_performance_pct") or 0),
                            "self_reflection": int(row.get("zimmerman_self_reflection_pct") or 0),
                        },
                    },
                    "copes_score": int(row['copes_score']),
                    "copes_components": {
                        "C": int(row.get("copes_C") or 0),
                        "O": int(row.get("copes_O") or 0),
                        "P": int(row.get("copes_P") or 0),
                        "E": int(row.get("copes_E") or 0),
                        "S": int(row.get("copes_S") or 0),
                        "total": int(row.get("copes_score") or 0),
                    },
                    "blooms_level": int(level) if level is not None else None,
                    "blooms_name": row.get('blooms_name'),
                    "blooms_confidence": blooms_conf,
                    "blooms": {
                        "level": int(level) if level is not None else None,
                        "name": row.get("blooms_name"),
                        "confidence": blooms_conf,
                        "unclassifiable": blooms_unclassifiable,
                    },
                    "is_critical_thinking": row.get("is_critical_thinking"),
                    "ct_classification": row.get("ct_classification"),
                    "ct_rationale": row.get("ct_rationale"),
                })
            response = {
                "dataset_id": dataset_id,
                "phase_distribution": phase_distribution,
                "copes_average": round(copes_avg, 2),
                "blooms_distribution": blooms_distribution,
                "blooms_average_level": round(float(classified_df['blooms_level'].mean()), 2),
                "critical_thinking_summary": ct_summary,
                "conversation_results": conversation_results,
                # Backward-compatible alias for older clients
                "message_results": conversation_results,
                "analyzed_count": len(conversation_texts),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            # Store for later export
            uploaded_datasets[dataset_id]["srl_results"] = response

            return jsonify(response), 200
        finally:
            _end_analysis(dataset_id, "srl")
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in analyze_srl: {error_traceback}")
        return jsonify({"error": str(e), "traceback": error_traceback if app.debug else None}), 500

# Analyze prompt quality (grading) on capped conversations
@app.route("/api/analyze-grading/<dataset_id>", methods=["POST"])
def analyze_grading(dataset_id):
    """Grade prompts and store results for reflection/export (capped to 25 conversations)."""
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404
        can_start, active_type = _try_begin_analysis(dataset_id, "grading")
        if not can_start:
            return jsonify({
                "error": "Another analysis is already running",
                "message": f"Cannot start grading while '{active_type}' is running. Please wait for it to finish."
            }), 409
        try:
            ds = uploaded_datasets[dataset_id]
            api_key = _get_dataset_api_key(dataset_id)
            file_path = ds["file_path"]
            file_type = ds["file_type"]
            if file_type != ".json":
                return jsonify({"error": "Only JSON files are currently supported"}), 400
            if not api_key:
                return jsonify({
                    "error": "Missing API key for this dataset",
                    "message": "Upload the JSON file again and include your OpenAI API key."
                }), 400
            chats = _build_capped_conversation_chats(file_path)
            total_prompts = sum(len(c["messages"]) for c in chats)
            total_conversations = len(chats)
            if total_prompts == 0:
                return jsonify({"error": "No conversations found to grade"}), 400
            slot = _progress_slot(dataset_id, "grading")
            slot.update({
                'current': 0, 'total': total_conversations,
                'message': f"Grading {total_conversations} conversations ({total_prompts} prompts)...", 'status': 'running'
            })
            def update_progress(current, total, message):
                _progress_slot(dataset_id, 'grading').update({
                    'current': current, 'total': total, 'message': message,
                    'status': 'running' if current < total else 'complete'
                })
            from Models.grade_prompts import analyze_prompts_grading
            grading_df, stats = analyze_prompts_grading(
                chats=chats,
                progress_callback=update_progress,
                api_key=api_key,
            )
            _progress_slot(dataset_id, 'grading')['status'] = 'complete'
            grading_results = {
                "aggregate": {
                    "average_total_score": stats.get("average_total_score", 0),
                    "dimension_averages": stats.get("dimension_averages") or {},
                    "strength_summary": stats.get("strength_summary", ""),
                    "weakness_summary": stats.get("weakness_summary", ""),
                    "improvement_suggestions": stats.get("improvement_suggestions") or [],
                    "total_prompts": stats.get("total_prompts", total_prompts),
                },
                "details": grading_df.to_dict(orient="records"),
            }
            uploaded_datasets[dataset_id]["grading_results"] = grading_results
            response = {
                "dataset_id": dataset_id,
                "grading_results": grading_results,
                "analyzed_count": total_conversations,
                "analyzed_prompt_count": total_prompts,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            return jsonify(response), 200
        finally:
            _end_analysis(dataset_id, "grading")
    except ValueError as e:
        if "OPENAI_API_KEY" in str(e):
            return jsonify({
                "error": "OpenAI API key is required",
                "message": str(e),
                "instructions": [
                    "1. Go back to the upload page",
                    "2. Select your JSON file",
                    "3. Enter your OpenAI API key",
                    "4. Upload the file again"
                ]
            }), 400
        raise
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in analyze_grading: {error_traceback}")
        return jsonify({"error": str(e), "traceback": error_traceback if app.debug else None}), 500

# Get analysis progress (per type: paul_elder, srl, grading)
@app.route("/api/analysis-progress/<dataset_id>", methods=["GET"])
def get_analysis_progress(dataset_id):
    """Get current progress for one analysis type. Query param: type=paul_elder|srl|grading"""
    analysis_type = request.args.get("type", "paul_elder").lower()
    if analysis_type not in ("paul_elder", "srl", "grading"):
        analysis_type = "paul_elder"
    progress = _progress_slot(dataset_id, analysis_type)
    return jsonify(dict(progress)), 200


@app.route("/api/export/<dataset_id>", methods=["GET"])
def export_results(dataset_id):
    """
    Export all available analysis results for a dataset.
    - CSV: machine-readable rows with conversation-level metrics
    - PDF: human-readable report
    """
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404

        export_format = request.args.get("format", "csv").lower()
        if export_format not in ("csv", "pdf", "json"):
            return jsonify({"error": "Unsupported format"}), 400

        # Base file info
        ds = uploaded_datasets[dataset_id]
        file_info = {
            "file_name": ds.get("file_name"),
            "file_size": ds.get("file_size"),
            "uploaded_at": ds.get("uploaded_at"),
            "file_type": ds.get("file_type"),
        }

        # Recompute basic prompt stats (total prompts + summary) from stored file
        file_path = ds["file_path"]
        file_type = ds["file_type"]
        num_prompts = None
        summary = None

        if file_type == ".json":
            _, summary = parse_chatgpt_prompts(file_path, max_prompts=1)
            num_prompts = (summary or {}).get("total_user_prompts")

        # Gather model-specific results if they were run
        classification_results = ds.get("classification_results")
        srl_results = ds.get("srl_results")
        grading_results = ds.get("grading_results")
        prompt_data = _build_export_prompt_data(file_path) if file_type == ".json" else {"conversations": [], "flat": []}

        # Reflection summary (same logic as get_results)
        reflection = {
            "strengths": [],
            "risks": [],
            "suggestions": [],
            "overall_summary": ""
        }
        if grading_results:
            agg = grading_results.get("aggregate", {})
            if agg.get("strength_summary"):
                reflection["strengths"] = [agg["strength_summary"]]
            if agg.get("weakness_summary"):
                reflection["risks"] = [agg["weakness_summary"]]
            reflection["suggestions"] = agg.get("improvement_suggestions") or []
            total_score = agg.get("average_total_score")
            dim_avg = agg.get("dimension_averages") or {}
            parts = [f"Average total score: {total_score}/15."]
            if dim_avg:
                parts.append("Dimension averages: " + ", ".join(f"{k}: {v:.1f}" for k, v in dim_avg.items()))
            reflection["overall_summary"] = " ".join(parts)

        export_payload = {
            "dataset_id": dataset_id,
            "file": file_info,
            "summary": summary,
            "total_prompts": num_prompts,
            "analysis_scope": {
                "max_conversations": MAX_MODEL_CONVERSATIONS,
                "analyzed_conversations": len(prompt_data.get("conversations") or []),
                "analyzed_prompts": len(prompt_data.get("flat") or []),
            },
            "prompts": prompt_data,
            "models": {
                "paul_elder": classification_results,
                "srl": srl_results,
                "grading": grading_results,
            },
            "reflection": reflection,
        }

        if export_format == "csv":
            csv_data = _build_export_csv(export_payload)
            resp = Response(csv_data, mimetype="text/csv; charset=utf-8")
            resp.headers["Content-Disposition"] = f"attachment; filename=reflection-results-{dataset_id}.csv"
            return resp

        if export_format == "json":
            data = json.dumps(export_payload, ensure_ascii=False, indent=2)
            resp = Response(data, mimetype="application/json")
            resp.headers["Content-Disposition"] = f"attachment; filename=reflection-results-{dataset_id}.json"
            return resp

        if export_format == "pdf":
            if REPORTLAB_AVAILABLE:
                pdf_bytes = _build_export_pdf(export_payload)
            else:
                fallback_text = _stringify_export_payload(export_payload)
                pdf_bytes = _build_plain_text_pdf(fallback_text)
            resp = Response(pdf_bytes, mimetype="application/pdf")
            resp.headers["Content-Disposition"] = f"attachment; filename=reflection-results-{dataset_id}.pdf"
            return resp

    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in export_results: {error_traceback}")
        return jsonify({
            "error": f"Export failed: {str(e)}",
            "traceback": error_traceback if app.debug else None
        }), 500


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path: str):
    """
    Serve the built React app for local hosting/package mode.
    API routes remain separate under /api.
    """
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404

    if not FRONTEND_DIST_DIR.exists():
        return jsonify({
            "error": "Frontend build not found",
            "message": f"Expected built files at: {FRONTEND_DIST_DIR}",
        }), 500

    requested = FRONTEND_DIST_DIR / path
    if path and requested.exists() and requested.is_file():
        return send_from_directory(FRONTEND_DIST_DIR, path)

    return send_from_directory(FRONTEND_DIST_DIR, "index.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)