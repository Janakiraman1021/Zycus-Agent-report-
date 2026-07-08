"""Portfolio and project metric calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from src.preprocess import ProjectDataset
from src.validator import ValidationResult


BLOCKER_TERMS = {
    "blocked",
    "blocker",
    "delay",
    "delayed",
    "pending",
    "impacted",
    "issue",
    "risk",
    "need",
    "tbd",
    "incomplete",
    "remain",
    "waiting",
    "hold",
}
POSITIVE_TERMS = {"complete", "completed", "covered", "done", "approved", "signed"}
NEGATIVE_TERMS = {"pending", "impacted", "delay", "delayed", "issue", "risk", "need", "repeating"}


@dataclass(frozen=True)
class ProjectMetrics:
    """Calculated signals for one project."""

    total_tasks: int
    active_tasks: int
    status_counts: dict[str, int]
    completion_pct: float
    elapsed_pct: float
    expected_completion_pct: float
    schedule_gap_pct: float
    overdue_incomplete: int
    due_soon_incomplete: int
    red_task_signals: int
    amber_task_signals: int
    critical_tasks: int
    critical_incomplete: int
    zero_float_incomplete: int
    on_hold_tasks: int
    blocker_comment_count: int
    total_comments: int
    missing_owner_active: int
    data_quality_score: float
    workbook_status: str
    budget_fields_present: bool
    trend_points: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key, value in payload.items():
            if isinstance(value, float):
                payload[key] = round(value, 4)
        return payload


def compute_project_metrics(
    project: ProjectDataset,
    validation: ValidationResult,
    lookahead_days: int,
) -> ProjectMetrics:
    """Compute health signals for a normalized project."""

    tasks = project.tasks.copy()
    if tasks.empty:
        return _empty_metrics(validation.quality_score)

    active = tasks[~tasks["status_normalized"].eq("not_applicable")].copy()
    incomplete = active[active["percent_complete"] < 0.999].copy()
    as_of = pd.Timestamp(project.as_of_date)
    due_soon_limit = as_of + pd.Timedelta(days=lookahead_days)

    status_counts = {
        str(status): int(count)
        for status, count in active["status_normalized"].value_counts().sort_index().items()
    }
    completion_pct = float(active["percent_complete"].mean()) if not active.empty else 0.0
    elapsed_pct = _elapsed_percent(project)
    expected_completion = elapsed_pct
    schedule_gap = completion_pct - expected_completion

    overdue = incomplete[
        incomplete["end_date"].notna() & (incomplete["end_date"] < as_of)
    ]
    due_soon = incomplete[
        incomplete["end_date"].notna()
        & (incomplete["end_date"] >= as_of)
        & (incomplete["end_date"] <= due_soon_limit)
    ]

    red_task_signals = _count_rag_signals(active, "RED")
    amber_task_signals = _count_rag_signals(active, "AMBER")
    critical = active[active["critical"]]
    critical_incomplete = critical[critical["percent_complete"] < 0.999]
    zero_float_incomplete = incomplete[
        incomplete["total_float"].notna() & (incomplete["total_float"] <= 0)
    ]
    on_hold = active[active["on_hold"] | active["status_normalized"].eq("on_hold")]
    blocker_comment_count = _count_blocker_comments(project.comments)
    missing_owner_active = int(
        incomplete["assigned_to"].fillna("").astype(str).str.strip().eq("").sum()
    )

    return ProjectMetrics(
        total_tasks=int(len(tasks)),
        active_tasks=int(len(active)),
        status_counts=status_counts,
        completion_pct=completion_pct,
        elapsed_pct=elapsed_pct,
        expected_completion_pct=expected_completion,
        schedule_gap_pct=schedule_gap,
        overdue_incomplete=int(len(overdue)),
        due_soon_incomplete=int(len(due_soon)),
        red_task_signals=int(red_task_signals),
        amber_task_signals=int(amber_task_signals),
        critical_tasks=int(len(critical)),
        critical_incomplete=int(len(critical_incomplete)),
        zero_float_incomplete=int(len(zero_float_incomplete)),
        on_hold_tasks=int(len(on_hold)),
        blocker_comment_count=int(blocker_comment_count),
        total_comments=int(len(project.comments)),
        missing_owner_active=missing_owner_active,
        data_quality_score=validation.quality_score,
        workbook_status=_workbook_status(project),
        budget_fields_present=False,
        trend_points=_build_trend_points(project, completion_pct, expected_completion),
    )


def sentiment_score(comments: list[dict[str, Any]]) -> tuple[float, float, str]:
    """Score comment sentiment with a deterministic keyword method."""

    if not comments:
        return 75.0, 0.35, "No stakeholder comments were available, so sentiment is neutral."

    positive = 0
    negative = 0
    for comment in comments:
        text = str(comment.get("text", "")).lower()
        positive += sum(term in text for term in POSITIVE_TERMS)
        negative += sum(term in text for term in NEGATIVE_TERMS)

    score = 75.0 + min(12.0, positive * 3.0) - min(35.0, negative * 4.0)
    if negative > positive:
        explanation = "Stakeholder comments contain more unresolved or risk-oriented language."
    elif positive > negative:
        explanation = "Stakeholder comments are generally constructive or completion-oriented."
    else:
        explanation = "Stakeholder comments are balanced with no strong sentiment skew."
    return max(0.0, min(100.0, score)), 0.7, explanation


def aggregate_portfolio_metrics(metrics: list[ProjectMetrics]) -> dict[str, Any]:
    """Aggregate project metrics for portfolio reporting."""

    if not metrics:
        return {}
    total_tasks = sum(item.total_tasks for item in metrics)
    weighted_completion = _weighted_average(
        [(item.completion_pct, item.active_tasks) for item in metrics]
    )
    return {
        "project_count": len(metrics),
        "total_tasks": total_tasks,
        "weighted_completion_pct": weighted_completion,
        "overdue_incomplete": sum(item.overdue_incomplete for item in metrics),
        "critical_incomplete": sum(item.critical_incomplete for item in metrics),
        "blocker_comment_count": sum(item.blocker_comment_count for item in metrics),
        "red_task_signals": sum(item.red_task_signals for item in metrics),
        "amber_task_signals": sum(item.amber_task_signals for item in metrics),
    }


def _elapsed_percent(project: ProjectDataset) -> float:
    if not project.project_start or not project.project_end:
        return 0.5
    start = pd.Timestamp(project.project_start)
    end = pd.Timestamp(project.project_end)
    as_of = pd.Timestamp(project.as_of_date)
    total = max((end - start).days, 1)
    elapsed = (as_of - start).days
    return float(np.clip(elapsed / total, 0.0, 1.0))


def _count_rag_signals(tasks: pd.DataFrame, status: str) -> int:
    signal_frame = tasks[["schedule_health", "rag"]].fillna("")
    return int(((signal_frame == status).any(axis=1)).sum())


def _count_blocker_comments(comments: list[dict[str, Any]]) -> int:
    count = 0
    for comment in comments:
        text = str(comment.get("text", "")).lower()
        if any(term in text for term in BLOCKER_TERMS):
            count += 1
    return count


def _workbook_status(project: ProjectDataset) -> str:
    summary_status = project.summary.get("schedule health")
    if summary_status:
        return _normalize_status_label(summary_status)
    task_statuses = (
        project.tasks[["schedule_health", "rag"]].fillna("").to_numpy().flatten().tolist()
    )
    task_statuses = [_normalize_status_label(value) for value in task_statuses if value]
    if "RED" in task_statuses:
        return "RED"
    if "AMBER" in task_statuses:
        return "AMBER"
    if "GREEN" in task_statuses:
        return "GREEN"
    return "UNKNOWN"


def _normalize_status_label(value: Any) -> str:
    text = str(value).strip().upper()
    if text == "YELLOW":
        return "AMBER"
    if text in {"GREEN", "AMBER", "RED"}:
        return text
    return "UNKNOWN"


def _build_trend_points(
    project: ProjectDataset,
    completion_pct: float,
    expected_completion_pct: float,
) -> list[dict[str, Any]]:
    if not project.project_start or not project.project_end:
        return []
    return [
        {
            "label": "Start",
            "date": project.project_start.isoformat(),
            "planned": 0.0,
            "actual": 0.0,
        },
        {
            "label": "As of",
            "date": project.as_of_date.isoformat(),
            "planned": round(expected_completion_pct, 4),
            "actual": round(completion_pct, 4),
        },
        {
            "label": "Finish",
            "date": project.project_end.isoformat(),
            "planned": 1.0,
            "actual": 1.0 if completion_pct >= 0.999 else None,
        },
    ]


def _weighted_average(values: list[tuple[float, int]]) -> float:
    numerator = sum(value * weight for value, weight in values)
    denominator = sum(weight for _, weight in values)
    return numerator / denominator if denominator else 0.0


def _empty_metrics(data_quality_score: float) -> ProjectMetrics:
    return ProjectMetrics(
        total_tasks=0,
        active_tasks=0,
        status_counts={},
        completion_pct=0.0,
        elapsed_pct=0.0,
        expected_completion_pct=0.0,
        schedule_gap_pct=0.0,
        overdue_incomplete=0,
        due_soon_incomplete=0,
        red_task_signals=0,
        amber_task_signals=0,
        critical_tasks=0,
        critical_incomplete=0,
        zero_float_incomplete=0,
        on_hold_tasks=0,
        blocker_comment_count=0,
        total_comments=0,
        missing_owner_active=0,
        data_quality_score=data_quality_score,
        workbook_status="UNKNOWN",
        budget_fields_present=False,
        trend_points=[],
    )
