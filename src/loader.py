"""Excel discovery and sheet profiling utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


TASK_COLUMN_HINTS = {
    "task name",
    "status",
    "% complete",
    "start date",
    "end date",
    "schedule health",
    "rag",
    "critical ?",
    "total float",
    "predecessors",
}

SUMMARY_HINTS = {
    "project manager",
    "project start date",
    "project end date",
    "project stage",
    "schedule health",
    "% complete",
    "today's date",
}


@dataclass(frozen=True)
class SheetProfile:
    """Compact metadata profile for one workbook sheet."""

    sheet_name: str
    rows: int
    columns: list[str]
    missing_counts: dict[str, int]
    dtypes: dict[str, str]
    task_score: int
    summary_score: int
    comment_score: int


@dataclass
class WorkbookBundle:
    """All loaded data and profiles for a workbook."""

    path: Path
    sheets: dict[str, pd.DataFrame]
    raw_sheets: dict[str, pd.DataFrame]
    profiles: list[SheetProfile]
    task_sheet_name: str | None
    summary_sheet_name: str | None
    comment_sheet_name: str | None

    def task_frame(self) -> pd.DataFrame:
        if not self.task_sheet_name:
            return pd.DataFrame()
        return self.sheets[self.task_sheet_name].copy()

    def summary_frame(self) -> pd.DataFrame:
        if not self.summary_sheet_name:
            return pd.DataFrame()
        return self.raw_sheets[self.summary_sheet_name].copy()

    def comments_frame(self) -> pd.DataFrame:
        if not self.comment_sheet_name:
            return pd.DataFrame()
        return self.raw_sheets[self.comment_sheet_name].copy()


def discover_workbooks(data_dir: Path, patterns: Iterable[str] = ("*.xlsx", "*.xlsm")) -> list[Path]:
    """Find candidate Excel files under a data directory."""

    workbooks: list[Path] = []
    for pattern in patterns:
        workbooks.extend(data_dir.glob(pattern))
    return sorted(path for path in workbooks if not path.name.startswith("~$"))


def read_workbook(path: Path) -> WorkbookBundle:
    """Load every sheet in a workbook and infer the business role of each sheet."""

    excel = pd.ExcelFile(path, engine="openpyxl")
    sheets: dict[str, pd.DataFrame] = {}
    raw_sheets: dict[str, pd.DataFrame] = {}
    profiles: list[SheetProfile] = []

    for sheet_name in excel.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
        raw = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl", header=None)
        sheets[sheet_name] = frame
        raw_sheets[sheet_name] = raw
        profiles.append(_profile_sheet(sheet_name, frame, raw))

    task_sheet = _best_sheet(profiles, "task_score")
    summary_sheet = _best_sheet(profiles, "summary_score")
    comment_sheet = _best_sheet(profiles, "comment_score")

    return WorkbookBundle(
        path=path,
        sheets=sheets,
        raw_sheets=raw_sheets,
        profiles=profiles,
        task_sheet_name=task_sheet,
        summary_sheet_name=summary_sheet,
        comment_sheet_name=comment_sheet,
    )


def _profile_sheet(sheet_name: str, frame: pd.DataFrame, raw: pd.DataFrame) -> SheetProfile:
    columns = [str(column).strip() for column in frame.columns]
    normalized_columns = {_normalize(column) for column in columns}
    task_score = len(normalized_columns & TASK_COLUMN_HINTS)
    if len(frame) > 20:
        task_score += 2
    if "task name" in normalized_columns:
        task_score += 4

    raw_values = {
        _normalize(value)
        for value in raw.fillna("").astype(str).to_numpy().flatten().tolist()
        if str(value).strip()
    }
    summary_score = len(raw_values & SUMMARY_HINTS)
    if "summary" in sheet_name.lower():
        summary_score += 2
    if 1 <= raw.shape[1] <= 4 and raw.shape[0] <= 50:
        summary_score += 1

    comment_score = 0
    if "comment" in sheet_name.lower():
        comment_score += 4
    non_empty_rows = raw.dropna(how="all")
    text_cells = raw.fillna("").astype(str).map(lambda value: len(value.strip()) > 12).sum().sum()
    row_ref_cells = raw.fillna("").astype(str).map(
        lambda value: value.strip().lower().startswith("row ")
    ).sum().sum()
    if len(non_empty_rows) > 0 and text_cells >= 3:
        comment_score += 2
    if len(non_empty_rows) > 0 and row_ref_cells >= 1 and text_cells >= 1:
        comment_score += 3

    return SheetProfile(
        sheet_name=sheet_name,
        rows=len(frame),
        columns=columns,
        missing_counts={str(key): int(value) for key, value in frame.isna().sum().items()},
        dtypes={str(key): str(value) for key, value in frame.dtypes.items()},
        task_score=task_score,
        summary_score=summary_score,
        comment_score=comment_score,
    )


def _best_sheet(profiles: list[SheetProfile], score_field: str) -> str | None:
    if not profiles:
        return None
    scored = sorted(
        profiles,
        key=lambda profile: (getattr(profile, score_field), profile.rows),
        reverse=True,
    )
    best = scored[0]
    return best.sheet_name if getattr(best, score_field) > 0 else None


def _normalize(value: object) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())
