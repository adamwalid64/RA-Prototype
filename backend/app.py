from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import json
import uuid
import base64
import tempfile
import traceback
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from HelperFunctions import parse_chatgpt_prompts, prompts_to_jsonl, count_prompts_in_jsonl, generate_prompt_wordcloud
import os
# Models imported lazily in routes to reduce startup memory (helps on 512MB free tier)

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _build_export_pdf(export_payload: dict) -> bytes:
    """Build a PDF from the export payload. Requires reportlab."""
    import io
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    style_heading = ParagraphStyle(name="CustomHeading", parent=styles["Heading1"], fontSize=14, spaceAfter=6)
    style_body = styles["Normal"]
    flow = []

    def para(text, style=style_body):
        if not text:
            return
        safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        flow.append(Paragraph(safe, style))
        flow.append(Spacer(1, 6))

    flow.append(Paragraph("Reflection &amp; Analysis Export", styles["Title"]))
    flow.append(Spacer(1, 12))
    para(f"Dataset ID: {export_payload.get('dataset_id', '')}", style_heading)
    file_info = export_payload.get("file") or {}
    para(f"File: {file_info.get('file_name', '')} | Uploaded: {file_info.get('uploaded_at', '')}")
    total = export_payload.get("total_prompts")
    para(f"Total prompts: {total}" if total is not None else "Total prompts: —")
    summary = export_payload.get("summary")
    if summary:
        para("Summary: " + (str(summary)[:500] + "..." if len(str(summary)) > 500 else str(summary)))
    flow.append(Spacer(1, 12))

    models = export_payload.get("models") or {}
    pe = models.get("paul_elder")
    if pe:
        flow.append(Paragraph("Paul-Elder Framework", style_heading))
        stats = pe.get("classification_stats") or {}
        para(f"Prompts analyzed: {pe.get('analyzed_count', 0)}")
        para(f"Critical thinking: {stats.get('critical_thinking_percentage', 0):.1f}%")
        for c in (pe.get("categories") or [])[:10]:
            para(f"  • {c.get('category', '')}: {c.get('percentage', 0):.1f}% ({c.get('count', 0)} prompts)")
        flow.append(Spacer(1, 8))

    srl = models.get("srl")
    if srl:
        flow.append(Paragraph("SRL (Zimmerman, COPES, Bloom's)", style_heading))
        para(f"Prompts analyzed: {srl.get('analyzed_count', 0)}")
        para(f"COPES average: {srl.get('copes_average', 0):.1f}/5 | Bloom's avg level: {srl.get('blooms_average_level', 0):.1f}/6")
        pd = srl.get("phase_distribution") or {}
        para("Phase distribution: " + ", ".join(f"{k}: {v}" for k, v in pd.items()))
        flow.append(Spacer(1, 8))

    grading = models.get("grading")
    if grading:
        flow.append(Paragraph("Prompt Quality (Grading)", style_heading))
        agg = grading.get("aggregate") or {}
        para(f"Prompts graded: {agg.get('total_prompts', 0)} | Average total score: {agg.get('average_total_score', 0):.1f}/15")
        dim = agg.get("dimension_averages") or {}
        if dim:
            para("Dimension averages: " + ", ".join(f"{k}: {v:.1f}" for k, v in dim.items()))
        flow.append(Spacer(1, 8))
        # Per-prompt feedback for all graded prompts (full 50, not just preview)
        details = grading.get("details") or []
        if details:
            flow.append(Paragraph("Per-prompt feedback (all graded prompts)", style_heading))
            for i, row in enumerate(details, 1):
                ev = row.get("evaluation") or {}
                prompt_text = (row.get("prompt_text") or "")[:200]
                if len(row.get("prompt_text") or "") > 200:
                    prompt_text += "..."
                score = row.get("total_score") or ev.get("total_score") or 0
                para(f"Prompt {i} (score {score}/15): {prompt_text}")
                if ev.get("strength_summary"):
                    para("  Strength: " + (str(ev["strength_summary"])[:350] + "..." if len(str(ev["strength_summary"])) > 350 else str(ev["strength_summary"])))
                if ev.get("weakness_summary"):
                    para("  Area to improve: " + (str(ev["weakness_summary"])[:350] + "..." if len(str(ev["weakness_summary"])) > 350 else str(ev["weakness_summary"])))
                for s in (ev.get("improvement_suggestions") or [])[:5]:
                    para("  Suggestion: " + (str(s)[:250] + "..." if len(str(s)) > 250 else str(s)))
                flow.append(Spacer(1, 4))
            flow.append(Spacer(1, 8))

    ref = export_payload.get("reflection") or {}
    flow.append(Paragraph("Reflection", style_heading))
    if ref.get("overall_summary"):
        para(ref["overall_summary"])
    for s in ref.get("strengths") or []:
        para("Strength: " + str(s)[:400])
    for r in ref.get("risks") or []:
        para("Risk: " + str(r)[:400])
    for s in ref.get("suggestions") or []:
        para("Suggestion: " + str(s)[:300])

    doc.build(flow)
    return buf.getvalue()


app = Flask(__name__)
CORS(app)

# In-memory storage for uploaded files
# Structure: {dataset_id: {file_name, file_size, uploaded_at, content, file_type}}
uploaded_datasets = {}

# In-memory storage for analysis progress (per analysis type, so PE/SRL/grading are independent)
# Structure: {dataset_id: {'paul_elder': {...}, 'srl': {...}, 'grading': {...}}}
# Each slot: {current: int, total: int, message: str, status: str}
analysis_progress = {}

def _progress_slot(dataset_id, analysis_type):
    """Get or create the progress dict for this dataset and analysis type."""
    if dataset_id not in analysis_progress:
        analysis_progress[dataset_id] = {}
    if analysis_type not in analysis_progress[dataset_id]:
        analysis_progress[dataset_id][analysis_type] = {
            'current': 0, 'total': 50, 'message': 'Analysis not started', 'status': 'idle'
        }
    return analysis_progress[dataset_id][analysis_type]

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# Upload file and store in memory variable
# Max upload size: 10MB keeps us under 512MB RAM on free tier (no full file in memory)
UPLOAD_MAX_BYTES = 10 * 1024 * 1024
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

        # Parse from stored file; only first 50 prompts loaded (streaming, low memory)
        prompts, summary = parse_chatgpt_prompts(file_path, max_prompts=50)

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

        # total_prompts: show full count from stream; we only loaded first 50 for display/analysis
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

# Analyze classification on-demand (50 sample prompts)
@app.route("/api/analyze-classification/<dataset_id>", methods=["POST"])
def analyze_classification(dataset_id):
    """Analyze 50 sample prompts using Paul-Elder framework"""
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404

        ds = uploaded_datasets[dataset_id]
        file_path = ds["file_path"]
        file_type = ds["file_type"]
        if file_type != ".json":
            return jsonify({"error": "Only JSON files are currently supported"}), 400

        prompts, _ = parse_chatgpt_prompts(file_path, max_prompts=50)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp_jsonl:
            prompts_to_jsonl(prompts, tmp_jsonl.name)
            jsonl_path = tmp_jsonl.name

        try:
            # Prompts already limited to 50 by parse_chatgpt_prompts(max_prompts=50)
            prompt_texts = []
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        prompt_obj = json.loads(line.strip())
                        prompt_text = prompt_obj.get("prompt_text", "").strip()
                        if prompt_text:
                            prompt_texts.append(prompt_text)
                    except json.JSONDecodeError:
                        continue
            
            # Classify prompts using Paul-Elder framework
            if not prompt_texts:
                return jsonify({"error": "No prompts found to analyze"}), 400
            
            print(f"Classifying {len(prompt_texts)} prompts using Paul-Elder framework...")
            
            # Initialize progress tracking for this analysis type only
            slot = _progress_slot(dataset_id, 'paul_elder')
            slot.update({
                'current': 0,
                'total': len(prompt_texts),
                'message': f"Starting analysis of {len(prompt_texts)} prompts...",
                'status': 'running'
            })
            
            def update_progress(current, total, message):
                _progress_slot(dataset_id, 'paul_elder').update({
                    'current': current, 'total': total, 'message': message,
                    'status': 'running' if current < total else 'complete'
                })
            
            try:
                from Models.PE_classify_chats import analyze_chat_history as pe_analyze_chat_history
                classification_df, classification_stats = pe_analyze_chat_history(prompt_texts, progress_callback=update_progress)
                _progress_slot(dataset_id, 'paul_elder')['status'] = 'complete'
            except ValueError as e:
                if "OPENAI_API_KEY" in str(e):
                    return jsonify({
                        "error": "OpenAI API key is not configured",
                        "message": "The classification feature requires an OpenAI API key. Please create a .env file in the backend directory with: OPENAI_API_KEY=your_key_here",
                        "instructions": [
                            "1. Create a file named '.env' in the backend directory",
                            "2. Add the line: OPENAI_API_KEY=your_actual_api_key_here",
                            "3. Get your API key from: https://platform.openai.com/api-keys",
                            "4. Restart the Flask server"
                        ]
                    }), 400
                raise
            finally:
                # Clean up progress after a delay (or keep it for a while)
                # For now, we'll keep it until next analysis
                pass
            
            # Format classification results for frontend
            categories = []
            breakdown = {}
            
            if classification_stats and classification_df is not None:
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
            response = {
                "dataset_id": dataset_id,
                "categories": categories,
                "breakdown": breakdown,
                "classification_stats": classification_stats,
                "analyzed_count": len(prompt_texts),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            # Store for later export
            uploaded_datasets[dataset_id]["classification_results"] = response

            return jsonify(response), 200
            
        finally:
            # Clean up JSONL file
            if os.path.exists(jsonl_path):
                os.unlink(jsonl_path)
        
    except ValueError as e:
        # Handle specific ValueError for missing API key
        if "OPENAI_API_KEY" in str(e):
            return jsonify({
                "error": "OpenAI API key is not configured",
                "message": "The classification feature requires an OpenAI API key. Please create a .env file in the backend directory with: OPENAI_API_KEY=your_key_here",
                "instructions": [
                    "1. Create a file named '.env' in the backend directory",
                    "2. Add the line: OPENAI_API_KEY=your_actual_api_key_here",
                    "3. Get your API key from: https://platform.openai.com/api-keys",
                    "4. Restart the Flask server"
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

# Analyze SRL (Self-Regulated Learning) on sample prompts
@app.route("/api/analyze-srl/<dataset_id>", methods=["POST"])
def analyze_srl(dataset_id):
    """Analyze up to 50 sample prompts using SRL (Zimmerman, COPES, Bloom's)"""
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404
        ds = uploaded_datasets[dataset_id]
        file_path = ds["file_path"]
        file_type = ds["file_type"]
        if file_type != ".json":
            return jsonify({"error": "Only JSON files are currently supported"}), 400
        prompts, _ = parse_chatgpt_prompts(file_path, max_prompts=50)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp_jsonl:
            prompts_to_jsonl(prompts, tmp_jsonl.name)
            jsonl_path = tmp_jsonl.name
        try:
            prompt_texts = []
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        prompt_obj = json.loads(line.strip())
                        prompt_text = prompt_obj.get("prompt_text", "").strip()
                        if prompt_text:
                            prompt_texts.append(prompt_text)
                    except json.JSONDecodeError:
                        continue
            if not prompt_texts:
                return jsonify({"error": "No prompts found to analyze"}), 400
            slot = _progress_slot(dataset_id, "srl")
            slot.update({
                'current': 0, 'total': len(prompt_texts),
                'message': f"Starting SRL analysis of {len(prompt_texts)} prompts...", 'status': 'running'
            })
            def update_progress(current, total, message):
                _progress_slot(dataset_id, 'srl').update({
                    'current': current, 'total': total, 'message': message,
                    'status': 'running' if current < total else 'complete'
                })
            from Models.SRL_classify_chats import critical_thinking_analysis as srl_critical_thinking_analysis
            df = srl_critical_thinking_analysis(prompt_texts, progress_callback=update_progress)
            _progress_slot(dataset_id, 'srl')['status'] = 'complete'
            phase_counts = df['zimmerman_phase'].value_counts()
            phase_distribution = {k: int(v) for k, v in phase_counts.items()}
            copes_avg = float(df['copes_score'].mean())
            blooms_counts = df['blooms_name'].value_counts()
            blooms_distribution = {k: int(v) for k, v in blooms_counts.items()}
            message_results = []
            for _, row in df.iterrows():
                message_results.append({
                    "message": (row['message'][:200] + "...") if len(row['message']) > 200 else row['message'],
                    "zimmerman_phase": row['zimmerman_phase'],
                    "copes_score": int(row['copes_score']),
                    "blooms_level": int(row['blooms_level']),
                    "blooms_name": row['blooms_name'],
                })
            response = {
                "dataset_id": dataset_id,
                "phase_distribution": phase_distribution,
                "copes_average": round(copes_avg, 2),
                "blooms_distribution": blooms_distribution,
                "blooms_average_level": round(float(df['blooms_level'].mean()), 2),
                "message_results": message_results,
                "analyzed_count": len(prompt_texts),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            # Store for later export
            uploaded_datasets[dataset_id]["srl_results"] = response

            return jsonify(response), 200
        finally:
            if os.path.exists(jsonl_path):
                os.unlink(jsonl_path)
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in analyze_srl: {error_traceback}")
        return jsonify({"error": str(e), "traceback": error_traceback if app.debug else None}), 500

# Analyze prompt quality (grading) on sample prompts
@app.route("/api/analyze-grading/<dataset_id>", methods=["POST"])
def analyze_grading(dataset_id):
    """Grade up to 50 sample prompts and store results for reflection/export"""
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404
        ds = uploaded_datasets[dataset_id]
        file_path = ds["file_path"]
        file_type = ds["file_type"]
        if file_type != ".json":
            return jsonify({"error": "Only JSON files are currently supported"}), 400
        prompts, _ = parse_chatgpt_prompts(file_path, max_prompts=50)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp_jsonl:
            prompts_to_jsonl(prompts, tmp_jsonl.name)
            jsonl_path = tmp_jsonl.name
        try:
            prompt_texts = []
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        prompt_obj = json.loads(line.strip())
                        prompt_text = prompt_obj.get("prompt_text", "").strip()
                        if prompt_text:
                            prompt_texts.append(prompt_text)
                    except json.JSONDecodeError:
                        continue
            if not prompt_texts:
                return jsonify({"error": "No prompts found to grade"}), 400
            slot = _progress_slot(dataset_id, "grading")
            slot.update({
                'current': 0, 'total': len(prompt_texts),
                'message': f"Grading {len(prompt_texts)} prompts...", 'status': 'running'
            })
            def update_progress(current, total, message):
                _progress_slot(dataset_id, 'grading').update({
                    'current': current, 'total': total, 'message': message,
                    'status': 'running' if current < total else 'complete'
                })
            grading_df, stats = analyze_prompts_grading(prompt_texts, progress_callback=update_progress)
            _progress_slot(dataset_id, 'grading')['status'] = 'complete'
            grading_results = {
                "aggregate": {
                    "average_total_score": stats.get("average_total_score", 0),
                    "dimension_averages": stats.get("dimension_averages") or {},
                    "strength_summary": stats.get("strength_summary", ""),
                    "weakness_summary": stats.get("weakness_summary", ""),
                    "improvement_suggestions": stats.get("improvement_suggestions") or [],
                    "total_prompts": stats.get("total_prompts", len(prompt_texts)),
                },
                "details": grading_df.to_dict(orient="records"),
            }
            uploaded_datasets[dataset_id]["grading_results"] = grading_results
            response = {
                "dataset_id": dataset_id,
                "grading_results": grading_results,
                "analyzed_count": len(prompt_texts),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            return jsonify(response), 200
        finally:
            if os.path.exists(jsonl_path):
                os.unlink(jsonl_path)
    except ValueError as e:
        if "OPENAI_API_KEY" in str(e):
            return jsonify({
                "error": "OpenAI API key is not configured",
                "message": str(e),
                "instructions": [
                    "1. Create a .env file in the backend directory",
                    "2. Add: OPENAI_API_KEY=your_key_here",
                    "3. Restart the Flask server"
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
    - JSON: machine-readable bundle of base stats + Paul-Elder + SRL + grading (if run)
    """
    try:
        if dataset_id not in uploaded_datasets:
            return jsonify({"error": "Dataset not found"}), 404

        export_format = request.args.get("format", "json").lower()
        if export_format not in ("json", "pdf"):
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
            prompts, summary = parse_chatgpt_prompts(file_path, max_prompts=50)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp_jsonl:
                prompts_to_jsonl(prompts, tmp_jsonl.name)
                jsonl_path = tmp_jsonl.name
            try:
                num_prompts = count_prompts_in_jsonl(jsonl_path)
            finally:
                if os.path.exists(jsonl_path):
                    os.unlink(jsonl_path)

        # Gather model-specific results if they were run
        classification_results = ds.get("classification_results")
        srl_results = ds.get("srl_results")
        grading_results = ds.get("grading_results")

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
            "models": {
                "paul_elder": classification_results,
                "srl": srl_results,
                "grading": grading_results,
            },
            "reflection": reflection,
        }

        if export_format == "json":
            data = json.dumps(export_payload, ensure_ascii=False, indent=2)
            resp = Response(data, mimetype="application/json")
            resp.headers["Content-Disposition"] = f"attachment; filename=reflection-results-{dataset_id}.json"
            return resp

        if export_format == "pdf":
            if not REPORTLAB_AVAILABLE:
                return jsonify({
                    "error": "PDF export requires the reportlab package",
                    "message": "Install with: pip install reportlab>=4.0.0"
                }), 503
            pdf_bytes = _build_export_pdf(export_payload)
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


if __name__ == "__main__":
    app.run(debug=True)