"""PowerPoint generation for monthly executive synthesis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from src.config import AgentSettings
from src.insights import build_portfolio_insights
from src.rag_engine import PortfolioRun


NAVY = RGBColor(17, 24, 39)
MUTED = RGBColor(75, 85, 99)
BLUE = RGBColor(37, 99, 235)
GREEN = RGBColor(22, 163, 74)
AMBER = RGBColor(245, 158, 11)
RED = RGBColor(220, 38, 38)
LIGHT = RGBColor(248, 250, 252)
WHITE = RGBColor(255, 255, 255)


def generate_presentation(
    portfolio: PortfolioRun,
    chart_paths: dict[str, Path],
    settings: AgentSettings,
) -> Path:
    """Create the final 5-7 slide executive presentation."""

    settings.ensure_directories()
    insights = build_portfolio_insights(portfolio)
    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)

    _slide_title(deck, insights, portfolio)
    _slide_portfolio_health(deck, insights, portfolio, chart_paths)
    _slide_project_comparison(deck, portfolio, chart_paths)
    _slide_risks(deck, insights, chart_paths)
    _slide_recommendations(deck, insights)
    _slide_charts(deck, chart_paths)
    _slide_next_steps(deck, insights)

    output_path = settings.presentation_dir / "monthly_portfolio_health.pptx"
    deck.save(output_path)
    return output_path


def _slide_title(deck: Presentation, insights: dict[str, Any], portfolio: PortfolioRun) -> None:
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    _background(slide)
    _textbox(
        slide,
        "Project Health Synthesis",
        0.75,
        1.35,
        11.8,
        0.8,
        font_size=52,
        bold=True,
        color=NAVY,
    )
    _textbox(
        slide,
        f"Monthly portfolio review | Status: {insights['overall_status']} | Score: {insights['overall_score']:.1f}",
        0.8,
        2.35,
        9.8,
        0.45,
        font_size=24,
        color=_status_color(insights["overall_status"]),
    )
    project_names = ", ".join(project.evaluation.project_name for project in portfolio.projects)
    _textbox(
        slide,
        f"Projects reviewed: {project_names}",
        0.8,
        3.0,
        9.8,
        0.6,
        font_size=18,
        color=MUTED,
    )
    _textbox(
        slide,
        f"Generated {datetime.now().strftime('%d %b %Y')}",
        0.8,
        6.45,
        4.0,
        0.35,
        font_size=16,
        color=MUTED,
    )
    _status_band(slide, insights["overall_status"], 10.5, 1.5)


def _slide_portfolio_health(
    deck: Presentation,
    insights: dict[str, Any],
    portfolio: PortfolioRun,
    chart_paths: dict[str, Path],
) -> None:
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    _background(slide)
    _header(slide, "Portfolio health needs targeted governance focus")
    _textbox(slide, insights["executive_summary"], 0.75, 1.2, 7.2, 1.4, font_size=18, color=NAVY)
    _add_picture(slide, chart_paths["health_pie"], 8.1, 1.1, 4.4, 2.8)
    metrics = portfolio.portfolio_metrics
    metric_lines = [
        f"{metrics.get('total_tasks', 0)} total tasks",
        f"{metrics.get('weighted_completion_pct', 0):.0%} weighted completion",
        f"{metrics.get('overdue_incomplete', 0)} overdue incomplete tasks",
        f"{metrics.get('critical_incomplete', 0)} incomplete critical tasks",
    ]
    _bullets(slide, metric_lines, 0.9, 3.1, 6.6, 2.0, font_size=18)
    _add_picture(slide, chart_paths["completion_chart"], 7.2, 4.0, 5.4, 2.7)
    _footer(slide, "Portfolio Health")


def _slide_project_comparison(
    deck: Presentation,
    portfolio: PortfolioRun,
    chart_paths: dict[str, Path],
) -> None:
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    _background(slide)
    _header(slide, "Project comparison shows different risk profiles")
    _add_picture(slide, chart_paths["score_bar"], 0.65, 1.05, 6.5, 3.8)
    _add_picture(slide, chart_paths["portfolio_comparison"], 6.95, 1.05, 5.8, 3.8)
    lines = [
        f"{project.evaluation.project_name}: {project.evaluation.computed_status}, "
        f"score {project.evaluation.health_score.final_score:.1f}, "
        f"{project.metrics.overdue_incomplete} overdue tasks."
        for project in portfolio.projects
    ]
    _bullets(slide, lines, 0.9, 5.15, 11.6, 1.0, font_size=17)
    _footer(slide, "Project Comparison")


def _slide_risks(
    deck: Presentation,
    insights: dict[str, Any],
    chart_paths: dict[str, Path],
) -> None:
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    _background(slide)
    _header(slide, "Emerging risks are concentrated in schedule execution")
    _add_picture(slide, chart_paths["risk_heatmap"], 0.7, 1.0, 6.5, 3.7)
    _textbox(slide, "Highest priority risks", 7.55, 1.15, 4.8, 0.4, font_size=24, bold=True)
    _bullets(slide, insights["major_risks"][:5], 7.55, 1.75, 4.8, 3.2, font_size=18)
    _textbox(slide, "Trend signal", 0.9, 5.25, 2.2, 0.35, font_size=22, bold=True)
    _bullets(slide, insights["emerging_trends"][:3], 3.1, 5.15, 9.3, 1.0, font_size=17)
    _footer(slide, "Emerging Risks")


def _slide_recommendations(deck: Presentation, insights: dict[str, Any]) -> None:
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    _background(slide)
    _header(slide, "Recommendations drive management action")
    recommendations = insights["recommendations"][:4]
    y = 1.45
    for index, recommendation in enumerate(recommendations, start=1):
        _textbox(slide, f"{index}", 0.85, y, 0.45, 0.45, font_size=22, bold=True, color=BLUE)
        _textbox(slide, recommendation, 1.45, y - 0.02, 10.7, 0.55, font_size=20, color=NAVY)
        y += 1.05
    _textbox(
        slide,
        "Management intent: move from descriptive status reporting to exception-based governance.",
        0.9,
        6.05,
        11.5,
        0.5,
        font_size=18,
        color=MUTED,
    )
    _footer(slide, "Recommendations")


def _slide_charts(deck: Presentation, chart_paths: dict[str, Path]) -> None:
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    _background(slide)
    _header(slide, "The evidence base combines completion, trend, and risk views")
    _add_picture(slide, chart_paths["trend_line"], 0.7, 1.05, 6.0, 3.55)
    _add_picture(slide, chart_paths["completion_chart"], 6.95, 1.05, 5.7, 3.55)
    _add_picture(slide, chart_paths["health_pie"], 0.95, 4.75, 4.7, 2.25)
    _textbox(
        slide,
        "These views are generated from task-level data and can be refreshed automatically from updated workbooks.",
        6.3,
        5.05,
        5.8,
        0.9,
        font_size=18,
        color=NAVY,
    )
    _footer(slide, "Charts")


def _slide_next_steps(deck: Presentation, insights: dict[str, Any]) -> None:
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    _background(slide)
    _header(slide, "Next steps tighten cadence, ownership, and data quality")
    next_steps = [
        "Run the weekly agent refresh after project plan updates.",
        "Review Red, overdue, critical, and blocker items with project owners.",
        "Update budget and owner fields so future scoring has higher confidence.",
        "Use workbook discrepancy findings to calibrate PM status reporting.",
    ]
    _bullets(slide, next_steps, 0.9, 1.25, 7.2, 2.8, font_size=21)
    _textbox(slide, "Leadership decision", 8.2, 1.25, 3.8, 0.45, font_size=24, bold=True)
    _textbox(
        slide,
        "Adopt independent computed health as the standard exception signal, while keeping PM-entered workbook status as supporting context.",
        8.2,
        1.95,
        3.9,
        1.8,
        font_size=18,
        color=NAVY,
    )
    _textbox(
        slide,
        "Primary outcome: faster escalation on schedule risk with less manual follow-up.",
        0.9,
        5.8,
        10.8,
        0.5,
        font_size=20,
        color=BLUE,
        bold=True,
    )
    _footer(slide, "Next Steps")


def _background(slide: Any) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = WHITE
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0),
        Inches(0),
        Inches(13.333),
        Inches(0.16),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = BLUE
    shape.line.color.rgb = BLUE


def _header(slide: Any, title: str) -> None:
    _textbox(slide, title, 0.7, 0.42, 11.8, 0.48, font_size=36, bold=True, color=NAVY)


def _footer(slide: Any, section: str) -> None:
    _textbox(slide, section, 0.7, 7.0, 5.0, 0.25, font_size=12, color=MUTED)
    _textbox(slide, "Project Health Reporting Agent", 9.0, 7.0, 3.6, 0.25, font_size=12, color=MUTED)


def _status_band(slide: Any, status: str, x: float, y: float) -> None:
    color = _status_color(status)
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(x),
        Inches(y),
        Inches(1.9),
        Inches(1.9),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.color.rgb = color
    text_frame = shape.text_frame
    text_frame.clear()
    paragraph = text_frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = status
    run.font.size = Pt(22)
    run.font.bold = True
    run.font.color.rgb = WHITE


def _textbox(
    slide: Any,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: int,
    color: RGBColor = NAVY,
    bold: bool = False,
) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = Inches(0.02)
    frame.margin_right = Inches(0.02)
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    paragraph.font.size = Pt(font_size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = color


def _bullets(
    slide: Any,
    items: list[str],
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: int = 18,
) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = Inches(0.05)
    frame.margin_right = Inches(0.05)
    frame.clear()
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = item
        paragraph.level = 0
        paragraph.font.size = Pt(font_size)
        paragraph.font.color.rgb = NAVY
        paragraph.space_after = Pt(6)


def _add_picture(slide: Any, path: Path, x: float, y: float, width: float, height: float) -> None:
    if not path.exists():
        return
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(width), height=Inches(height))


def _status_color(status: str) -> RGBColor:
    return {"GREEN": GREEN, "AMBER": AMBER, "RED": RED}.get(status, MUTED)
