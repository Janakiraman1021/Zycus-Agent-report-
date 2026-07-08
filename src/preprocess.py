"""Data normalization for project-plan workbooks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.loader import WorkbookBundle


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "task_name": ("task name", "task", "activity", "name"),
    "status": ("status", "project status"),
    "percent_complete": ("% complete", "percent complete", "completion", "complete"),
    "start_date": ("start date", "planned start", "start"),
    "end_date": ("end date", "planned finish", "finish", "finish date"),
    "baseline_start": ("baseline start", "baseline start date", "baseline start2"),
    "baseline_finish": ("baseline finish", "baseline end date", "baseline finish2"),
    "variance": ("variance", "variance2", "schedule variance"),
    "schedule_health": ("schedule health",),
    "rag": ("rag",),
    "at_risk": ("at risk?", "at risk"),
    "on_hold": ("on hold?", "on hold"),
    "not_applicable": ("not applicable?", "not applicable"),
    "duration": ("duration",),
    "predecessors": ("predecessors",),
    "total_float": ("total float", "float"),
    "critical": ("critical ?", "critical"),
    "assigned_to": ("assigned to", "owner", "ownership"),
    "comments": ("comments", "status comment", "description"),
    "phase": ("phase/milestone", "phase", "milestone"),
    "project_manager": ("project manager",),
    "project_category": ("project category",),
    "level": ("level", "ancestors"),
}


@dataclass
class ProjectDataset:
    """Cleaned project data ready for validation and scoring."""

    workbook_path: Path
    task_sheet_name: str
    summary_sheet_name: str | None
    comment_sheet_name: str | None
    project_name: str
    project_manager: str
    project_stage: str
    project_start: date | None
    project_end: date | None
    as_of_date: date
    summary: dict[str, Any]
    tasks: pd.DataFrame
    comments: list[dict[str, Any]]
    column_map: dict[str, str]


def build_project_dataset(bundle: WorkbookBundle, as_of_override: date | None = None) -> ProjectDataset:
    """Normalize one workbook into a project-level dataset."""

    task_frame = bundle.task_frame()
    column_map = infer_column_map(task_frame)
    normalized_tasks = normalize_task_frame(task_frame, column_map)
    summary = extract_summary(bundle.summary_frame())
    comments = extract_comments(bundle.comments_frame())
    comments.extend(extract_inline_comments(normalized_tasks))

    project_name = _first_text(
        summary.get("project name"),
        _first_top_level_task(normalized_tasks),
        bundle.path.stem,
    )
    project_manager = _first_text(
        summary.get("project manager"),
        _first_non_empty(normalized_tasks.get("project_manager")),
        "Unassigned",
    )
    project_stage = _first_text(summary.get("project stage"), "Unknown")
    project_start = _first_date(summary.get("project start date"), normalized_tasks.get("start_date"))
    project_end = _first_date(summary.get("project end date"), normalized_tasks.get("end_date"), use_max=True)
    as_of = as_of_override or _coerce_date(summary.get("today's date")) or date.today()

    return ProjectDataset(
        workbook_path=bundle.path,
        task_sheet_name=bundle.task_sheet_name or "",
        summary_sheet_name=bundle.summary_sheet_name,
        comment_sheet_name=bundle.comment_sheet_name,
        project_name=project_name,
        project_manager=project_manager,
        project_stage=project_stage,
        project_start=project_start,
        project_end=project_end,
        as_of_date=as_of,
        summary=summary,
        tasks=normalized_tasks,
        comments=comments,
        column_map=column_map,
    )


def infer_column_map(frame: pd.DataFrame) -> dict[str, str]:
    """Map source workbook columns to canonical field names using aliases."""

    canonical_by_alias: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            canonical_by_alias[_normalize_key(alias)] = canonical

    matches: dict[str, str] = {}
    for source_column in frame.columns:
        normalized = _normalize_key(source_column)
        canonical = canonical_by_alias.get(normalized)
        if not canonical:
            canonical = _contains_match(normalized, canonical_by_alias)
        if canonical and canonical not in matches:
            matches[canonical] = str(source_column)
    return matches


def normalize_task_frame(frame: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    """Return a task dataframe with canonical columns and parsed values."""

    result = pd.DataFrame(index=frame.index)
    result["source_row"] = frame.index + 2
    for canonical in COLUMN_ALIASES:
        source = column_map.get(canonical)
        result[canonical] = frame[source] if source in frame.columns else pd.NA

    result["task_name"] = result["task_name"].map(_clean_text)
    result["status"] = result["status"].map(_clean_text)
    result["status_normalized"] = result["status"].map(_normalize_status)
    result["schedule_health"] = result["schedule_health"].map(_normalize_rag)
    result["rag"] = result["rag"].map(_normalize_rag)
    result["assigned_to"] = result["assigned_to"].map(_clean_text)
    result["comments"] = result["comments"].map(_clean_text)
    result["phase"] = result["phase"].map(_clean_text)
    result["start_date"] = pd.to_datetime(result["start_date"], errors="coerce")
    result["end_date"] = pd.to_datetime(result["end_date"], errors="coerce")
    result["baseline_start"] = pd.to_datetime(result["baseline_start"], errors="coerce")
    result["baseline_finish"] = pd.to_datetime(result["baseline_finish"], errors="coerce")
    result["percent_complete_missing"] = result["percent_complete"].isna()
    result["percent_complete"] = result.apply(_coerce_percent_row, axis=1)
    result["duration_days"] = result["duration"].map(parse_days)
    result["variance_days"] = result["variance"].map(parse_days)
    result["total_float"] = pd.to_numeric(result["total_float"], errors="coerce")
    result["critical"] = result["critical"].map(_coerce_bool)
    result["on_hold"] = result["on_hold"].map(_coerce_bool)
    result["not_applicable"] = result["not_applicable"].map(_coerce_bool)
    result["at_risk"] = result["at_risk"].map(_coerce_bool)
    result["level"] = pd.to_numeric(result["level"], errors="coerce")
    result = result[result["task_name"].astype(str).str.strip().ne("")]
    return result.reset_index(drop=True)


def extract_summary(raw_summary: pd.DataFrame) -> dict[str, Any]:
    """Extract key/value metadata from a compact summary sheet."""

    summary: dict[str, Any] = {}
    if raw_summary.empty:
        return summary
    for _, row in raw_summary.iterrows():
        values = [_empty_to_none(value) for value in row.tolist()]
        values = [value for value in values if value is not None]
        if len(values) < 2:
            continue
        key = _normalize_key(values[0])
        summary[key] = values[1]
    return summary


def extract_comments(raw_comments: pd.DataFrame) -> list[dict[str, Any]]:
    """Extract comment rows from arbitrary comment-style sheets."""

    if raw_comments.empty:
        return []
    comments: list[dict[str, Any]] = []
    for _, row in raw_comments.iterrows():
        values = [_clean_text(value) for value in row.tolist()]
        values = [value for value in values if value]
        if len(values) < 2:
            continue
        row_ref = values[0] if values[0].lower().startswith("row") else ""
        text_index = 1 if row_ref else 0
        text = values[text_index]
        if len(text) < 8:
            continue
        comments.append(
            {
                "row_ref": row_ref,
                "text": text,
                "author": values[text_index + 1] if len(values) > text_index + 1 else "",
                "timestamp": values[text_index + 2] if len(values) > text_index + 2 else "",
                "source": "comments_sheet",
            }
        )
    return comments


def extract_inline_comments(tasks: pd.DataFrame) -> list[dict[str, Any]]:
    """Extract meaningful task-level comments from the normalized task table."""

    if "comments" not in tasks:
        return []
    inline_comments: list[dict[str, Any]] = []
    for _, row in tasks.iterrows():
        text = _clean_text(row.get("comments"))
        if len(text) < 8:
            continue
        inline_comments.append(
            {
                "row_ref": f"Row {int(row.get('source_row', 0))}",
                "task_name": row.get("task_name", ""),
                "text": text,
                "author": row.get("assigned_to", ""),
                "timestamp": "",
                "source": "task_comments",
            }
        )
    return inline_comments


def parse_days(value: Any) -> float | None:
    """Parse strings such as '170d' or '-8d' into day counts."""

    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean_text(value).lower()
    if not text or text == "#unparseable":
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _coerce_percent_row(row: pd.Series) -> float:
    value = row.get("percent_complete")
    status = _normalize_status(row.get("status"))
    if value is None or pd.isna(value):
        if status == "completed":
            return 1.0
        if status == "not_started":
            return 0.0
        if status == "not_applicable":
            return 1.0
        return 0.5 if status == "in_progress" else 0.0
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return 0.0
    if percent > 1.0:
        percent = percent / 100.0
    return max(0.0, min(1.0, percent))


def _contains_match(normalized: str, canonical_by_alias: dict[str, str]) -> str | None:
    for alias, canonical in canonical_by_alias.items():
        if len(alias) > 4 and alias in normalized:
            return canonical
    return None


def _normalize_key(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "<na>"} else text


def _normalize_status(value: object) -> str:
    text = _normalize_key(value)
    if text in {"complete", "completed", "done"}:
        return "completed"
    if text in {"in progress", "progress", "active"}:
        return "in_progress"
    if text in {"not started", "new", "pending"}:
        return "not_started"
    if text in {"on hold", "hold"}:
        return "on_hold"
    if text in {"not applicable", "na", "n a"}:
        return "not_applicable"
    return text.replace(" ", "_") if text else "unknown"


def _normalize_rag(value: object) -> str:
    text = _normalize_key(value)
    if text in {"green", "g"}:
        return "GREEN"
    if text in {"amber", "yellow", "a", "y"}:
        return "AMBER"
    if text in {"red", "r"}:
        return "RED"
    return ""


def _coerce_bool(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _normalize_key(value)
    return text in {"true", "yes", "y", "1", "critical", "high"}


def _empty_to_none(value: object) -> Any | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return None if text == "" else value


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _first_non_empty(series: pd.Series | None) -> Any | None:
    if series is None:
        return None
    for value in series.tolist():
        if _clean_text(value):
            return value
    return None


def _first_top_level_task(tasks: pd.DataFrame) -> str:
    if tasks.empty:
        return ""
    if "level" in tasks and tasks["level"].notna().any():
        candidates = tasks[tasks["level"] == tasks["level"].min()]
        if not candidates.empty:
            return _clean_text(candidates.iloc[0].get("task_name"))
    return _clean_text(tasks.iloc[0].get("task_name"))


def _first_date(value: Any, series: pd.Series | None = None, use_max: bool = False) -> date | None:
    coerced = _coerce_date(value)
    if coerced:
        return coerced
    if series is None:
        return None
    dates = pd.to_datetime(series, errors="coerce").dropna()
    if dates.empty:
        return None
    selected = dates.max() if use_max else dates.min()
    return selected.date()


def _coerce_date(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()
