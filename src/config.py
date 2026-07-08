"""Configuration models and repository path handling."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class HealthWeights(BaseModel):
    """Weighted scoring model used to produce the final health score."""

    schedule: float = 0.30
    budget: float = 0.20
    milestones: float = 0.20
    risks: float = 0.10
    blockers: float = 0.10
    sentiment: float = 0.05
    data_quality: float = 0.05

    @field_validator("*")
    @classmethod
    def validate_weight(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Weights must be non-negative")
        return value

    def normalized(self) -> dict[str, float]:
        total = sum(self.model_dump().values())
        if total <= 0:
            raise ValueError("At least one weight must be greater than zero")
        return {name: value / total for name, value in self.model_dump().items()}


class RagThresholds(BaseModel):
    """Numerical cutoffs for Green, Amber, and Red ratings."""

    green_min: int = 85
    amber_min: int = 60

    def label_for_score(self, score: float) -> str:
        if score >= self.green_min:
            return "GREEN"
        if score >= self.amber_min:
            return "AMBER"
        return "RED"


class AgentSettings(BaseModel):
    """Runtime settings for a local repository execution."""

    root_dir: Path
    data_dir: Path
    output_dir: Path
    report_dir: Path
    presentation_dir: Path
    log_dir: Path
    weights: HealthWeights = Field(default_factory=HealthWeights)
    thresholds: RagThresholds = Field(default_factory=RagThresholds)
    lookahead_days: int = 14
    default_llm_provider: str = "mock"
    as_of_date: date | None = None

    @classmethod
    def from_root(cls, root_dir: Path, config_file: Path | None = None) -> "AgentSettings":
        root = root_dir.resolve()
        payload: dict[str, Any] = {}
        if config_file and config_file.exists():
            payload = json.loads(config_file.read_text(encoding="utf-8"))

        return cls(
            root_dir=root,
            data_dir=root / "data",
            output_dir=root / "outputs",
            report_dir=root / "reports",
            presentation_dir=root / "presentations",
            log_dir=root / "logs",
            weights=HealthWeights(**payload.get("weights", {})),
            thresholds=RagThresholds(**payload.get("thresholds", {})),
            lookahead_days=int(payload.get("lookahead_days", 14)),
            default_llm_provider=str(payload.get("default_llm_provider", "mock")),
        )

    def ensure_directories(self) -> None:
        for path in [
            self.data_dir,
            self.output_dir,
            self.output_dir / "charts",
            self.report_dir,
            self.presentation_dir,
            self.log_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)
