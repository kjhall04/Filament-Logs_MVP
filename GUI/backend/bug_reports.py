import json
import os
import uuid
from datetime import datetime, timezone

from backend.config import DATA_DIR

SEVERITY_OPTIONS = ("critical", "high", "medium", "low")
DEFAULT_BUG_REPORTS_PATH = os.path.join(DATA_DIR, "bug_reports.jsonl")


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_multiline_text(value, max_length):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > max_length:
        return text[:max_length]
    return text


def _normalize_text(value, max_length):
    text = " ".join(str(value or "").split()).strip()
    if len(text) > max_length:
        return text[:max_length]
    return text


def get_bug_reports_path():
    configured = str(os.getenv("BUG_REPORTS_PATH", "")).strip()
    if configured:
        return configured
    return DEFAULT_BUG_REPORTS_PATH


def get_external_bug_report_url():
    return str(os.getenv("BUG_REPORT_URL", "")).strip()


def normalize_bug_report_form(form_data):
    source = form_data if isinstance(form_data, dict) else {}
    severity = _normalize_text(source.get("severity"), 16).lower()
    if severity not in SEVERITY_OPTIONS:
        severity = "medium"

    return {
        "severity": severity,
        "title": _normalize_text(source.get("title"), 180),
        "description": _normalize_multiline_text(source.get("description"), 8000),
        "steps_to_reproduce": _normalize_multiline_text(source.get("steps_to_reproduce"), 8000),
        "expected_behavior": _normalize_multiline_text(source.get("expected_behavior"), 4000),
        "actual_behavior": _normalize_multiline_text(source.get("actual_behavior"), 4000),
        "contact": _normalize_text(source.get("contact"), 250),
    }


def validate_bug_report_form(form_data):
    errors = []
    if not form_data.get("title"):
        errors.append("Title is required.")
    if not form_data.get("description"):
        errors.append("Description is required.")
    return errors


def build_bug_report_payload(form_data, app_version="", user_agent="", source_page=""):
    normalized = normalize_bug_report_form(form_data)
    errors = validate_bug_report_form(normalized)
    if errors:
        return None, errors

    payload = dict(normalized)
    payload["id"] = str(uuid.uuid4())
    payload["submitted_at"] = _utc_now_iso()
    payload["app_version"] = _normalize_text(app_version, 64)
    payload["user_agent"] = _normalize_text(user_agent, 400)
    payload["source_page"] = _normalize_text(source_page, 400)
    payload["source"] = "web_form"
    return payload, []


def save_bug_report(report_payload, destination_path=None):
    payload = report_payload if isinstance(report_payload, dict) else {}
    target_path = destination_path or get_bug_reports_path()

    parent = os.path.dirname(target_path) or "."
    os.makedirs(parent, exist_ok=True)

    with open(target_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True))
        handle.write("\n")

    return {"id": payload.get("id", ""), "path": target_path}
