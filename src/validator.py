"""Validation and data-quality scoring for normalized project plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from src.preprocess import COLUMN_ALIASES, ProjectDataset


REQUIRED_COLUMNS = {"task_name", "status", "percent_complete", "start_date", "end_date"}
IMPORTANT_OPTIONAL_COLUMNS = {
    "schedule_health",
    "rag",
    "critical",
    "total_float",
    "variance",
    "assigned_to",
    "comments",
    "phase",
}
KNOWN_STATUSES = {"completed", "in_progress", "not_started", "on_hold", "not_applicable", "unknown"}


@dataclass(frozen=True)
class ValidationIssue:
    """One validation finding."""

    severity: str
    field: str
    message: str
    affected_rows: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationResult:
    """Validation summary used by reporting and scoring."""

    is_valid: bool
    quality_score: float
    issues: list[ValidationIssue]
    missing_columns: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "quality_score": round(self.quality_score, 2),
            "missing_columns": self.missing_columns,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def validate_project(project: ProjectDataset) -> ValidationResult:
    """Validate a project dataset without raising for recoverable schema issues."""

    issues: list[ValidationIssue] = []
    tasks = project.tasks
    missing_required = sorted(REQUIRED_COLUMNS - set(project.column_map))
    missing_optional = sorted(IMPORTANT_OPTIONAL_COLUMNS - set(project.column_map))

    if tasks.empty:
        issues.append(
            ValidationIssue(
                severity="error",
                field="task_sheet",
                message="No task rows were discovered in the inferred task sheet.",
            )
        )

    for column in missing_required:
        issues.append(
            ValidationIssue(
                severity="error",
                field=column,
                message=f"Required field '{column}' was not found; fallback defaults were used.",
            )
        )

    for column in missing_optional:
        issues.append(
            ValidationIssue(
                severity="warning",
                field=column,
                message=f"Optional signal '{column}' was not found; the score uses other signals.",
            )
        )

    if not tasks.empty:
        _append_value_quality_issues(tasks, issues)

    quality_score = _calculate_quality_score(tasks, missing_required, missing_optional, issues)
    return ValidationResult(
        is_valid=not any(issue.severity == "error" for issue in issues) and not tasks.empty,
        quality_score=quality_score,
        issues=issues,
        missing_columns=missing_required + missing_optional,
    )


def available_canonical_fields() -> list[str]:
    """Return the canonical schema for documentation and tests."""

    return sorted(COLUMN_ALIASES)


def _append_value_quality_issues(tasks: pd.DataFrame, issues: list[ValidationIssue]) -> None:
    invalid_start = int(tasks["start_date"].isna().sum()) if "start_date" in tasks else 0
    invalid_end = int(tasks["end_date"].isna().sum()) if "end_date" in tasks else 0
    missing_task_name = int(tasks["task_name"].astype(str).str.strip().eq("").sum())
    missing_percent = int(tasks["percent_complete_missing"].sum())
    unknown_status = int((~tasks["status_normalized"].isin(KNOWN_STATUSES)).sum())

    if invalid_start:
        issues.append(
            ValidationIssue(
                severity="warning",
                field="start_date",
                message="Some rows have blank or invalid start dates.",
                affected_rows=invalid_start,
            )
        )
    if invalid_end:
        issues.append(
            ValidationIssue(
                severity="warning",
                field="end_date",
                message="Some rows have blank or invalid end dates.",
                affected_rows=invalid_end,
            )
        )
    if missing_task_name:
        issues.append(
            ValidationIssue(
                severity="warning",
                field="task_name",
                message="Some task rows have blank names and were excluded.",
                affected_rows=missing_task_name,
            )
        )
    if missing_percent:
        issues.append(
            ValidationIssue(
                severity="info",
                field="percent_complete",
                message="Missing completion values were inferred from task status.",
                affected_rows=missing_percent,
            )
        )
    if unknown_status:
        issues.append(
            ValidationIssue(
                severity="warning",
                field="status",
                message="Some rows contain status values outside the known status set.",
                affected_rows=unknown_status,
            )
        )


def _calculate_quality_score(
    tasks: pd.DataFrame,
    missing_required: list[str],
    missing_optional: list[str],
    issues: list[ValidationIssue],
) -> float:
    if tasks.empty:
        return 0.0

    score = 100.0
    score -= 12.0 * len(missing_required)
    score -= 2.0 * len(missing_optional)

    row_count = max(len(tasks), 1)
    invalid_date_rate = (
        tasks["start_date"].isna().sum() + tasks["end_date"].isna().sum()
    ) / (row_count * 2)
    missing_percent_rate = float(tasks["percent_complete_missing"].sum()) / row_count
    unknown_status_rate = float((~tasks["status_normalized"].isin(KNOWN_STATUSES)).sum()) / row_count

    score -= min(18.0, invalid_date_rate * 35.0)
    score -= min(10.0, missing_percent_rate * 18.0)
    score -= min(8.0, unknown_status_rate * 18.0)

    for issue in issues:
        if issue.severity == "error":
            score -= 6.0
        elif issue.severity == "warning":
            score -= 1.5

    return max(0.0, min(100.0, score))
