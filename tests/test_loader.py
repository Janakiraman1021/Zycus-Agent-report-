from pathlib import Path

import pandas as pd

from src.loader import read_workbook


def test_loader_discovers_task_summary_and_comment_sheets(tmp_path: Path) -> None:
    workbook = tmp_path / "sample_project.xlsx"
    tasks = pd.DataFrame(
        {
            "Task Name": ["Kickoff", "Build"],
            "Status": ["Completed", "In Progress"],
            "% Complete": [1.0, 0.5],
            "Start Date": ["2026-01-01", "2026-01-05"],
            "End Date": ["2026-01-03", "2026-01-20"],
            "Schedule Health": ["Green", "Yellow"],
        }
    )
    summary = pd.DataFrame(
        [["Project Manager", "Asha"], ["Schedule Health", "Yellow"], ["Today's Date", "2026-01-10"]]
    )
    comments = pd.DataFrame([["Row 2", "Build scope clarification is pending", "PM", "2026-01-09"]])

    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        tasks.to_excel(writer, sheet_name="Plan Export", index=False)
        summary.to_excel(writer, sheet_name="Executive Summary", index=False, header=False)
        comments.to_excel(writer, sheet_name="Notes", index=False, header=False)

    bundle = read_workbook(workbook)

    assert bundle.task_sheet_name == "Plan Export"
    assert bundle.summary_sheet_name == "Executive Summary"
    assert bundle.comment_sheet_name == "Notes"
