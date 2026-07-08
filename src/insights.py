"""Deterministic executive insights for project and portfolio reports."""

from __future__ import annotations

from statistics import mean
from typing import Any

from src.metrics import BLOCKER_TERMS
from src.rag_engine import PortfolioRun, ProjectRun
from src.scoring import status_from_score


def build_project_insights(project: ProjectRun) -> dict[str, Any]:
    """Create weekly project narrative from computed evaluation signals."""

    evaluation = project.evaluation
    metrics = project.metrics
    score = evaluation.health_score.final_score
    status = evaluation.computed_status

    summary = (
        f"{evaluation.project_name} is rated {status} with a computed score of {score:.1f}. "
        f"The project is {metrics.completion_pct:.0%} complete against an expected "
        f"{metrics.expected_completion_pct:.0%}, with {metrics.overdue_incomplete} overdue "
        f"incomplete tasks and {metrics.critical_incomplete} incomplete critical tasks."
    )

    risks = _project_risks(project)
    recommendations = _project_recommendations(project)
    blockers = _project_blockers(project)
    resource_constraints = _resource_constraints(project)

    return {
        "executive_summary": summary,
        "major_risks": risks,
        "recommendations": recommendations,
        "top_blockers": blockers,
        "resource_constraints": resource_constraints,
        "emerging_trends": _project_trends(project),
    }


def build_portfolio_insights(portfolio: PortfolioRun) -> dict[str, Any]:
    """Create VP-level portfolio narrative from all evaluated projects."""

    evaluations = portfolio.evaluations
    if not evaluations:
        return {
            "overall_status": "UNKNOWN",
            "overall_score": 0.0,
            "executive_summary": "No project workbooks were found.",
            "major_risks": [],
            "recommendations": [],
            "emerging_trends": [],
            "top_blockers": [],
            "resource_constraints": [],
        }

    scores = [evaluation.health_score.final_score for evaluation in evaluations]
    overall_score = mean(scores)
    overall_status = status_from_score(overall_score)
    red_or_amber = [item for item in evaluations if item.computed_status != "GREEN"]
    portfolio_metrics = portfolio.portfolio_metrics

    executive_summary = (
        f"The portfolio is rated {overall_status} with an average health score of "
        f"{overall_score:.1f} across {len(evaluations)} projects. Completion is "
        f"{portfolio_metrics.get('weighted_completion_pct', 0.0):.0%} across "
        f"{portfolio_metrics.get('total_tasks', 0)} tasks. Leadership attention should focus on "
        f"{portfolio_metrics.get('overdue_incomplete', 0)} overdue incomplete tasks, "
        f"{portfolio_metrics.get('critical_incomplete', 0)} incomplete critical tasks, and "
        f"{portfolio_metrics.get('blocker_comment_count', 0)} blocker-like stakeholder comments."
    )

    return {
        "overall_status": overall_status,
        "overall_score": round(overall_score, 2),
        "executive_summary": executive_summary,
        "major_risks": _portfolio_risks(portfolio, red_or_amber),
        "recommendations": _portfolio_recommendations(portfolio),
        "emerging_trends": _portfolio_trends(portfolio),
        "top_blockers": _portfolio_blockers(portfolio),
        "resource_constraints": _portfolio_resource_constraints(portfolio),
    }


def _project_risks(project: ProjectRun) -> list[str]:
    metrics = project.metrics
    risks: list[str] = []
    if metrics.overdue_incomplete:
        risks.append(f"{metrics.overdue_incomplete} incomplete tasks are already past due.")
    if metrics.critical_incomplete:
        risks.append(f"{metrics.critical_incomplete} critical tasks remain incomplete.")
    if metrics.red_task_signals:
        risks.append(f"{metrics.red_task_signals} task-level Red signals require review.")
    if metrics.blocker_comment_count:
        risks.append(f"{metrics.blocker_comment_count} comments indicate blockers or open decisions.")
    if project.evaluation.discrepancy and "Computed status is" in project.evaluation.discrepancy:
        risks.append(project.evaluation.discrepancy)
    if not risks:
        risks.append("No severe project risks were detected, but schedule and data quality should be monitored.")
    return risks


def _project_recommendations(project: ProjectRun) -> list[str]:
    metrics = project.metrics
    recommendations = [
        "Review overdue and zero-float tasks in the next project governance meeting.",
        "Ask the project manager to confirm baseline dates and update workbook health fields after review.",
    ]
    if metrics.missing_owner_active:
        recommendations.append(
            f"Assign owners for {metrics.missing_owner_active} incomplete tasks without clear ownership."
        )
    if not metrics.budget_fields_present:
        recommendations.append("Add budget or burn-rate fields so financial health can be scored with confidence.")
    if metrics.blocker_comment_count:
        recommendations.append("Convert blocker comments into dated actions with accountable owners.")
    return recommendations


def _project_blockers(project: ProjectRun) -> list[str]:
    comments = []
    for comment in project.dataset.comments:
        text = str(comment.get("text", "")).strip()
        if _is_blocker_text(text):
            comments.append(text)
    return comments[:5] or ["No explicit blocker comments were captured in the workbook."]


def _resource_constraints(project: ProjectRun) -> list[str]:
    metrics = project.metrics
    constraints = []
    if metrics.missing_owner_active:
        constraints.append(f"{metrics.missing_owner_active} active tasks do not show an assigned owner.")
    if metrics.critical_incomplete:
        constraints.append("Critical work needs dedicated owner review because schedule float is limited.")
    if not constraints:
        constraints.append("No major resource ownership gaps were detected from available fields.")
    return constraints


def _project_trends(project: ProjectRun) -> list[str]:
    metrics = project.metrics
    trend = "ahead of plan" if metrics.schedule_gap_pct >= 0 else "behind plan"
    return [
        f"Progress is {abs(metrics.schedule_gap_pct):.0%} {trend} versus linear elapsed schedule.",
        f"Task health mix shows {metrics.red_task_signals} Red and {metrics.amber_task_signals} Amber signals.",
    ]


def _portfolio_risks(portfolio: PortfolioRun, red_or_amber: list[Any]) -> list[str]:
    risks = [
        f"{len(red_or_amber)} of {len(portfolio.projects)} projects are not computed Green.",
        f"{portfolio.portfolio_metrics.get('overdue_incomplete', 0)} overdue incomplete tasks exist across the portfolio.",
        f"{portfolio.portfolio_metrics.get('critical_incomplete', 0)} incomplete critical tasks may constrain delivery.",
    ]
    if portfolio.portfolio_metrics.get("blocker_comment_count", 0):
        risks.append("Stakeholder comments show unresolved mapping, workshop, and calendar coordination issues.")
    return risks


def _portfolio_recommendations(portfolio: PortfolioRun) -> list[str]:
    return [
        "Create a weekly exception review for overdue, critical, and zero-float tasks.",
        "Normalize workbook hygiene across projects, especially owner, milestone, budget, and comment fields.",
        "Separate self-reported workbook health from independently computed health in leadership reporting.",
        "Add budget burn data to the standard project plan export so health is not schedule-only.",
    ]


def _portfolio_trends(portfolio: PortfolioRun) -> list[str]:
    trends = []
    for project in portfolio.projects:
        direction = "ahead of" if project.metrics.schedule_gap_pct >= 0 else "behind"
        trends.append(
            f"{project.evaluation.project_name}: {project.metrics.completion_pct:.0%} complete, "
            f"{abs(project.metrics.schedule_gap_pct):.0%} {direction} expected progress."
        )
    return trends


def _portfolio_blockers(portfolio: PortfolioRun) -> list[str]:
    blockers: list[str] = []
    for project in portfolio.projects:
        for comment in project.dataset.comments:
            text = str(comment.get("text", "")).strip()
            if _is_blocker_text(text):
                blockers.append(f"{project.evaluation.project_name}: {text}")
    return blockers[:8] or ["No explicit blocker comments were captured across the portfolio."]


def _portfolio_resource_constraints(portfolio: PortfolioRun) -> list[str]:
    constraints = []
    for project in portfolio.projects:
        if project.metrics.missing_owner_active:
            constraints.append(
                f"{project.evaluation.project_name}: {project.metrics.missing_owner_active} active tasks lack owners."
            )
    return constraints or ["No major owner gaps were detected from the available workbook fields."]


def _is_blocker_text(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in BLOCKER_TERMS)
