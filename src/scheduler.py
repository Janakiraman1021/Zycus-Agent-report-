"""Scheduling helpers for weekly and monthly agent runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SchedulePlan:
    """Portable schedule plan that can be translated into cron or Task Scheduler."""

    name: str
    cadence: str
    command: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def build_schedule_plans(root_dir: Path) -> list[SchedulePlan]:
    """Return suggested weekly and monthly automation commands."""

    run_py = root_dir / "run.py"
    return [
        SchedulePlan(
            name="weekly-project-health",
            cadence="Every Friday at 17:00 local time",
            command=f"python {run_py} --weekly --json --html",
            description="Refresh weekly project health reports after PM workbook updates.",
        ),
        SchedulePlan(
            name="monthly-portfolio-synthesis",
            cadence="First business day of each month at 09:00 local time",
            command=f"python {run_py} --monthly --ppt",
            description="Create the VP-level portfolio synthesis deck.",
        ),
    ]


def write_schedule_reference(root_dir: Path) -> Path:
    """Write a human-readable schedule reference file."""

    path = root_dir / "config" / "schedule_reference.txt"
    lines = ["Project Health Agent Schedule Reference", ""]
    for plan in build_schedule_plans(root_dir):
        lines.extend(
            [
                f"Name: {plan.name}",
                f"Cadence: {plan.cadence}",
                f"Command: {plan.command}",
                f"Purpose: {plan.description}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
