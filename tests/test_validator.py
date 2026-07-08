from datetime import date
from pathlib import Path

import pandas as pd

from src.preprocess import ProjectDataset, infer_column_map, normalize_task_frame
from src.validator import validate_project


def test_validator_reports_missing_dates_without_crashing() -> None:
    source = pd.DataFrame(
        {
            "Task Name": ["Kickoff", "Configuration"],
            "Status": ["Completed", "In Progress"],
            "% Complete": [1.0, None],
        }
    )
    column_map = infer_column_map(source)
    tasks = normalize_task_frame(source, column_map)
    project = ProjectDataset(
        workbook_path=Path("sample.xlsx"),
        task_sheet_name="Tasks",
        summary_sheet_name=None,
        comment_sheet_name=None,
        project_name="Sample",
        project_manager="PM",
        project_stage="Build",
        project_start=None,
        project_end=None,
        as_of_date=date(2026, 1, 10),
        summary={},
        tasks=tasks,
        comments=[],
        column_map=column_map,
    )

    result = validate_project(project)

    assert not result.is_valid
    assert "start_date" in result.missing_columns
    assert "end_date" in result.missing_columns
    assert result.quality_score > 0
