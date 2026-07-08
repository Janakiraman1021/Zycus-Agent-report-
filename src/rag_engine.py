"""End-to-end RAG engine orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.config import AgentSettings
from src.loader import WorkbookBundle, discover_workbooks, read_workbook
from src.metrics import ProjectMetrics, aggregate_portfolio_metrics, compute_project_metrics
from src.preprocess import ProjectDataset, build_project_dataset
from src.scoring import ProjectEvaluation, evaluate_project
from src.validator import ValidationResult, validate_project


@dataclass
class ProjectRun:
    """All artifacts created while evaluating one project workbook."""

    bundle: WorkbookBundle
    dataset: ProjectDataset
    validation: ValidationResult
    metrics: ProjectMetrics
    evaluation: ProjectEvaluation


@dataclass
class PortfolioRun:
    """Portfolio-level result passed to reporting and presentation generators."""

    projects: list[ProjectRun]
    portfolio_metrics: dict[str, Any]

    @property
    def evaluations(self) -> list[ProjectEvaluation]:
        return [project.evaluation for project in self.projects]

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_metrics": self.portfolio_metrics,
            "projects": [project.evaluation.to_dict() for project in self.projects],
            "sheet_profiles": {
                project.bundle.path.name: [asdict(profile) for profile in project.bundle.profiles]
                for project in self.projects
            },
        }


def evaluate_workbooks(
    settings: AgentSettings,
    workbook_paths: list[Path] | None = None,
) -> PortfolioRun:
    """Evaluate all candidate project workbooks."""

    paths = workbook_paths or discover_workbooks(settings.data_dir)
    projects: list[ProjectRun] = []
    for path in paths:
        bundle = read_workbook(path)
        dataset = build_project_dataset(bundle, settings.as_of_date)
        validation = validate_project(dataset)
        metrics = compute_project_metrics(dataset, validation, settings.lookahead_days)
        evaluation = evaluate_project(dataset, metrics, validation, settings)
        projects.append(
            ProjectRun(
                bundle=bundle,
                dataset=dataset,
                validation=validation,
                metrics=metrics,
                evaluation=evaluation,
            )
        )

    return PortfolioRun(
        projects=projects,
        portfolio_metrics=aggregate_portfolio_metrics([project.metrics for project in projects]),
    )
