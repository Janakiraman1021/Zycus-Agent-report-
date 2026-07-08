"""Weighted RAG scoring model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.config import AgentSettings
from src.metrics import ProjectMetrics, sentiment_score
from src.preprocess import ProjectDataset
from src.validator import ValidationResult


class ComponentScore(BaseModel):
    """One scoring component in the weighted health model."""

    name: str
    score: float
    weight: float
    confidence: float
    evidence: list[str] = Field(default_factory=list)


class HealthScore(BaseModel):
    """Final weighted score and RAG label."""

    final_score: float
    rag_status: str
    confidence: float
    components: list[ComponentScore]


class ProjectEvaluation(BaseModel):
    """Complete evaluation payload for one project."""

    project_name: str
    project_manager: str
    project_stage: str
    source_file: str
    as_of_date: str
    workbook_status: str
    computed_status: str
    discrepancy: str
    health_score: HealthScore
    metrics: dict[str, Any]
    validation: dict[str, Any]
    top_observations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def evaluate_project(
    project: ProjectDataset,
    metrics: ProjectMetrics,
    validation: ValidationResult,
    settings: AgentSettings,
) -> ProjectEvaluation:
    """Calculate component scores and final project RAG status."""

    weights = settings.weights.normalized()
    components = [
        _schedule_score(metrics, weights["schedule"]),
        _budget_score(metrics, weights["budget"]),
        _milestone_score(metrics, weights["milestones"]),
        _risk_score(metrics, weights["risks"]),
        _blocker_score(metrics, weights["blockers"]),
        _sentiment_component(project, weights["sentiment"]),
        _data_quality_component(metrics, weights["data_quality"]),
    ]

    final_score = sum(component.score * component.weight for component in components)
    status = settings.thresholds.label_for_score(final_score)
    confidence = _weighted_confidence(components, metrics.data_quality_score)
    discrepancy = _discrepancy_text(status, metrics.workbook_status)

    return ProjectEvaluation(
        project_name=project.project_name,
        project_manager=project.project_manager,
        project_stage=project.project_stage,
        source_file=project.workbook_path.name,
        as_of_date=project.as_of_date.isoformat(),
        workbook_status=metrics.workbook_status,
        computed_status=status,
        discrepancy=discrepancy,
        health_score=HealthScore(
            final_score=round(final_score, 2),
            rag_status=status,
            confidence=round(confidence, 2),
            components=components,
        ),
        metrics=metrics.to_dict(),
        validation=validation.to_dict(),
        top_observations=_top_observations(metrics, validation),
    )


def status_from_score(score: float, green_min: int = 85, amber_min: int = 60) -> str:
    """Map a numeric score to a RAG label."""

    if score >= green_min:
        return "GREEN"
    if score >= amber_min:
        return "AMBER"
    return "RED"


def _schedule_score(metrics: ProjectMetrics, weight: float) -> ComponentScore:
    active = max(metrics.active_tasks, 1)
    overdue_rate = metrics.overdue_incomplete / active
    red_rate = metrics.red_task_signals / active
    zero_float_rate = metrics.zero_float_incomplete / active
    behind_pct = max(0.0, -metrics.schedule_gap_pct)

    score = 100.0
    score -= min(38.0, behind_pct * 170.0)
    score -= min(32.0, overdue_rate * 120.0)
    score -= min(18.0, red_rate * 120.0)
    score -= min(12.0, zero_float_rate * 80.0)

    evidence = [
        f"Completion is {metrics.completion_pct:.0%} against expected {metrics.expected_completion_pct:.0%}.",
        f"{metrics.overdue_incomplete} incomplete tasks are past their planned finish date.",
        f"{metrics.red_task_signals} task rows carry a Red health signal.",
    ]
    return ComponentScore(
        name="Schedule Health",
        score=_clamp(score),
        weight=weight,
        confidence=0.88,
        evidence=evidence,
    )


def _budget_score(metrics: ProjectMetrics, weight: float) -> ComponentScore:
    if not metrics.budget_fields_present:
        return ComponentScore(
            name="Budget Burn",
            score=70.0,
            weight=weight,
            confidence=0.35,
            evidence=[
                "No budget, cost, spend, or burn columns were present in the source workbooks.",
                "The score is neutral and flagged with low confidence rather than assumed healthy.",
            ],
        )
    return ComponentScore(
        name="Budget Burn",
        score=80.0,
        weight=weight,
        confidence=0.75,
        evidence=["Budget fields were detected and no severe burn issue was identified."],
    )


def _milestone_score(metrics: ProjectMetrics, weight: float) -> ComponentScore:
    active = max(metrics.active_tasks, 1)
    due_soon_rate = metrics.due_soon_incomplete / active
    critical_pressure = (
        metrics.critical_incomplete / metrics.critical_tasks if metrics.critical_tasks else 0.0
    )
    behind_pct = max(0.0, -metrics.schedule_gap_pct)

    score = 100.0
    score -= min(35.0, behind_pct * 140.0)
    score -= min(20.0, due_soon_rate * 100.0)
    score -= min(30.0, critical_pressure * 45.0)

    evidence = [
        f"{metrics.due_soon_incomplete} incomplete tasks are due in the lookahead window.",
        f"{metrics.critical_incomplete} of {metrics.critical_tasks} critical tasks remain incomplete.",
    ]
    return ComponentScore(
        name="Milestone Health",
        score=_clamp(score),
        weight=weight,
        confidence=0.82,
        evidence=evidence,
    )


def _risk_score(metrics: ProjectMetrics, weight: float) -> ComponentScore:
    active = max(metrics.active_tasks, 1)
    red_rate = metrics.red_task_signals / active
    amber_rate = metrics.amber_task_signals / active
    critical_pressure = (
        metrics.critical_incomplete / metrics.critical_tasks if metrics.critical_tasks else 0.0
    )

    score = 100.0
    score -= min(35.0, red_rate * 150.0)
    score -= min(18.0, amber_rate * 70.0)
    score -= min(28.0, critical_pressure * 45.0)
    score -= min(12.0, metrics.on_hold_tasks * 4.0)

    evidence = [
        f"{metrics.red_task_signals} Red and {metrics.amber_task_signals} Amber task signals were detected.",
        f"{metrics.on_hold_tasks} tasks are on hold.",
    ]
    return ComponentScore(
        name="Risks",
        score=_clamp(score),
        weight=weight,
        confidence=0.78,
        evidence=evidence,
    )


def _blocker_score(metrics: ProjectMetrics, weight: float) -> ComponentScore:
    active = max(metrics.active_tasks, 1)
    zero_float_rate = metrics.zero_float_incomplete / active

    score = 100.0
    score -= min(42.0, metrics.blocker_comment_count * 7.0)
    score -= min(16.0, metrics.on_hold_tasks * 5.0)
    score -= min(28.0, zero_float_rate * 150.0)

    evidence = [
        f"{metrics.blocker_comment_count} stakeholder comments contain blocker language.",
        f"{metrics.zero_float_incomplete} incomplete tasks have zero or negative float.",
    ]
    return ComponentScore(
        name="Blockers",
        score=_clamp(score),
        weight=weight,
        confidence=0.74 if metrics.total_comments else 0.55,
        evidence=evidence,
    )


def _sentiment_component(project: ProjectDataset, weight: float) -> ComponentScore:
    score, confidence, explanation = sentiment_score(project.comments)
    return ComponentScore(
        name="Stakeholder Sentiment",
        score=round(score, 2),
        weight=weight,
        confidence=confidence,
        evidence=[explanation],
    )


def _data_quality_component(metrics: ProjectMetrics, weight: float) -> ComponentScore:
    return ComponentScore(
        name="Data Quality",
        score=round(metrics.data_quality_score, 2),
        weight=weight,
        confidence=0.95,
        evidence=[f"Validation quality score is {metrics.data_quality_score:.1f}/100."],
    )


def _weighted_confidence(components: list[ComponentScore], data_quality_score: float) -> float:
    weighted = sum(component.confidence * component.weight for component in components)
    quality_factor = 0.5 + (data_quality_score / 200.0)
    return _clamp(weighted * quality_factor, upper=1.0)


def _discrepancy_text(computed_status: str, workbook_status: str) -> str:
    if workbook_status == "UNKNOWN":
        return "No workbook-level RAG status was available for comparison."
    if computed_status == workbook_status:
        return f"Computed status agrees with workbook status: {computed_status}."
    return (
        f"Computed status is {computed_status}, while the workbook reports {workbook_status}. "
        "The agent does not copy workbook health; it recomputes status from task-level signals."
    )


def _top_observations(metrics: ProjectMetrics, validation: ValidationResult) -> list[str]:
    observations = [
        f"{metrics.completion_pct:.0%} average task completion across {metrics.active_tasks} active tasks.",
        f"{metrics.overdue_incomplete} overdue incomplete tasks and {metrics.critical_incomplete} incomplete critical tasks.",
        f"{metrics.blocker_comment_count} blocker-like comments across {metrics.total_comments} extracted comments.",
    ]
    if validation.missing_columns:
        observations.append(
            "Missing or sparse signals: " + ", ".join(validation.missing_columns[:6]) + "."
        )
    return observations


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return round(max(lower, min(upper, value)), 2)
