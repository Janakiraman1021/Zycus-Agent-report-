"""Chart generation for reports and presentations."""

from __future__ import annotations

from pathlib import Path

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:  # pragma: no cover - fallback for minimal runtimes
    matplotlib = None  # type: ignore[assignment]
    plt = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

from PIL import Image, ImageDraw, ImageFont

from src.config import AgentSettings
from src.rag_engine import PortfolioRun


STATUS_COLORS = {"GREEN": "#16a34a", "AMBER": "#f59e0b", "RED": "#dc2626", "UNKNOWN": "#64748b"}
BLUE = "#2563eb"
INK = "#111827"
GRID = "#e5e7eb"


def generate_charts(portfolio: PortfolioRun, settings: AgentSettings) -> dict[str, Path]:
    """Generate all required chart PNGs."""

    chart_dir = settings.output_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    charts = {
        "health_pie": chart_dir / "portfolio_health_pie.png",
        "score_bar": chart_dir / "project_comparison_bar.png",
        "trend_line": chart_dir / "portfolio_trend_line.png",
        "risk_heatmap": chart_dir / "risk_heatmap.png",
        "completion_chart": chart_dir / "completion_chart.png",
        "portfolio_comparison": chart_dir / "portfolio_comparison.png",
    }

    if plt is None:
        for title, path in charts.items():
            _fallback_chart(path, title.replace("_", " ").title())
        return charts

    _health_pie(portfolio, charts["health_pie"])
    _score_bar(portfolio, charts["score_bar"])
    _trend_line(portfolio, charts["trend_line"])
    _risk_heatmap(portfolio, charts["risk_heatmap"])
    _completion_chart(portfolio, charts["completion_chart"])
    _portfolio_comparison(portfolio, charts["portfolio_comparison"])
    return charts


def _health_pie(portfolio: PortfolioRun, path: Path) -> None:
    statuses = [project.evaluation.computed_status for project in portfolio.projects]
    labels = sorted(set(statuses)) or ["UNKNOWN"]
    sizes = [statuses.count(label) for label in labels]
    colors = [STATUS_COLORS.get(label, STATUS_COLORS["UNKNOWN"]) for label in labels]
    fig, axis = plt.subplots(figsize=(7, 4.5))
    axis.pie(sizes, labels=labels, autopct="%1.0f%%", colors=colors, startangle=90)
    axis.set_title("Computed Portfolio Health Mix", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _score_bar(portfolio: PortfolioRun, path: Path) -> None:
    names = [_short_name(project.evaluation.project_name) for project in portfolio.projects]
    scores = [project.evaluation.health_score.final_score for project in portfolio.projects]
    colors = [STATUS_COLORS[project.evaluation.computed_status] for project in portfolio.projects]
    fig, axis = plt.subplots(figsize=(8, 4.5))
    bars = axis.bar(names, scores, color=colors)
    axis.axhline(85, color=STATUS_COLORS["GREEN"], linewidth=1, linestyle="--", label="Green")
    axis.axhline(60, color=STATUS_COLORS["AMBER"], linewidth=1, linestyle="--", label="Amber")
    axis.set_ylim(0, 100)
    axis.set_ylabel("Health Score")
    axis.set_title("Project Health Score Comparison", fontsize=14, fontweight="bold")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    for bar, score in zip(bars, scores):
        axis.text(bar.get_x() + bar.get_width() / 2, score + 2, f"{score:.0f}", ha="center")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _trend_line(portfolio: PortfolioRun, path: Path) -> None:
    fig, axis = plt.subplots(figsize=(8, 4.5))
    for project in portfolio.projects:
        points = project.metrics.trend_points
        if not points:
            continue
        x = [point["label"] for point in points]
        planned = [point["planned"] * 100 for point in points]
        actual = [None if point["actual"] is None else point["actual"] * 100 for point in points]
        axis.plot(x, planned, linestyle="--", marker="o", label=f"{_short_name(project.evaluation.project_name)} planned")
        axis.plot(x, actual, marker="o", label=f"{_short_name(project.evaluation.project_name)} actual")
    axis.set_ylim(0, 105)
    axis.set_ylabel("Completion %")
    axis.set_title("Planned vs Actual Completion Trend", fontsize=14, fontweight="bold")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _risk_heatmap(portfolio: PortfolioRun, path: Path) -> None:
    labels = ["Overdue", "Critical", "Red", "Blockers"]
    project_names = [_short_name(project.evaluation.project_name) for project in portfolio.projects]
    values = []
    for project in portfolio.projects:
        metrics = project.metrics
        values.append(
            [
                metrics.overdue_incomplete,
                metrics.critical_incomplete,
                metrics.red_task_signals,
                metrics.blocker_comment_count,
            ]
        )
    matrix = np.array(values, dtype=float) if values else np.zeros((1, len(labels)))
    normalized = matrix.copy()
    for column_index in range(matrix.shape[1]):
        column = matrix[:, column_index]
        max_value = max(float(column.max()), 1.0)
        normalized[:, column_index] = column / max_value

    fig, axis = plt.subplots(figsize=(8, 4.5))
    image = axis.imshow(normalized, cmap="YlOrRd", vmin=0, vmax=1)
    axis.set_xticks(range(len(labels)), labels=labels)
    axis.set_yticks(range(len(project_names)), labels=project_names)
    axis.set_title("Risk Heatmap", fontsize=14, fontweight="bold")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            axis.text(j, i, f"{int(matrix[i, j])}", ha="center", va="center", color=INK)
    fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _completion_chart(portfolio: PortfolioRun, path: Path) -> None:
    names = [_short_name(project.evaluation.project_name) for project in portfolio.projects]
    actual = [project.metrics.completion_pct * 100 for project in portfolio.projects]
    expected = [project.metrics.expected_completion_pct * 100 for project in portfolio.projects]
    x = np.arange(len(names))
    width = 0.34
    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(x - width / 2, expected, width, label="Expected", color="#94a3b8")
    axis.bar(x + width / 2, actual, width, label="Actual", color=BLUE)
    axis.set_xticks(x, labels=names)
    axis.set_ylim(0, 105)
    axis.set_ylabel("Completion %")
    axis.set_title("Completion vs Expected Progress", fontsize=14, fontweight="bold")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _portfolio_comparison(portfolio: PortfolioRun, path: Path) -> None:
    names = [_short_name(project.evaluation.project_name) for project in portfolio.projects]
    red = [project.metrics.red_task_signals for project in portfolio.projects]
    amber = [project.metrics.amber_task_signals for project in portfolio.projects]
    green = [
        max(project.metrics.active_tasks - red_value - amber_value, 0)
        for project, red_value, amber_value in zip(portfolio.projects, red, amber)
    ]
    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(names, green, label="Green/No issue", color=STATUS_COLORS["GREEN"])
    axis.bar(names, amber, bottom=green, label="Amber", color=STATUS_COLORS["AMBER"])
    axis.bar(
        names,
        red,
        bottom=[green_value + amber_value for green_value, amber_value in zip(green, amber)],
        label="Red",
        color=STATUS_COLORS["RED"],
    )
    axis.set_ylabel("Task Count")
    axis.set_title("Task Health Signal Mix by Project", fontsize=14, fontweight="bold")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _fallback_chart(path: Path, title: str) -> None:
    image = Image.new("RGB", (1280, 720), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((48, 48), title, fill=INK, font=font)
    draw.rectangle((48, 110, 1230, 660), outline=GRID, width=3)
    draw.text((80, 150), "Install matplotlib to render the full analytical chart.", fill=INK, font=font)
    image.save(path)


def _short_name(name: str) -> str:
    cleaned = name.replace("Zycus - ", "").replace(" Implementation", "")
    return cleaned[:28]
