"""Markdown, HTML, JSON, and text report generation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from jinja2 import Template
except ImportError:  # pragma: no cover - exercised only in minimal runtimes
    Template = None  # type: ignore[assignment]

from src.config import AgentSettings
from src.insights import build_portfolio_insights, build_project_insights
from src.rag_engine import PortfolioRun, ProjectRun


def generate_reports(portfolio: PortfolioRun, settings: AgentSettings) -> dict[str, Path]:
    """Generate all requested weekly report formats."""

    settings.ensure_directories()
    portfolio_insights = build_portfolio_insights(portfolio)
    project_insights = {
        project.evaluation.project_name: build_project_insights(project)
        for project in portfolio.projects
    }
    context = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "portfolio": portfolio,
        "portfolio_insights": portfolio_insights,
        "project_insights": project_insights,
    }

    outputs: dict[str, Path] = {}
    markdown = _portfolio_markdown(context)
    outputs["weekly_markdown"] = _write(settings.report_dir / "weekly_report.md", markdown)
    outputs["weekly_text"] = _write(settings.report_dir / "weekly_report.txt", _plain_text(markdown))
    outputs["weekly_html"] = _write(settings.report_dir / "weekly_report.html", _html_report(context))
    outputs["weekly_json"] = _write_json(
        settings.report_dir / "weekly_report.json",
        _json_payload(portfolio, portfolio_insights, project_insights),
    )
    outputs["portfolio_json"] = _write_json(
        settings.output_dir / "portfolio_health.json",
        _json_payload(portfolio, portfolio_insights, project_insights),
    )
    outputs["execution_summary"] = _write(
        settings.output_dir / "execution_summary.txt",
        _plain_text(markdown),
    )

    for project in portfolio.projects:
        slug = slugify(project.evaluation.project_name)
        project_context = {
            "generated_at": context["generated_at"],
            "project": project,
            "insights": project_insights[project.evaluation.project_name],
        }
        project_markdown = _project_markdown(project_context)
        outputs[f"{slug}_markdown"] = _write(
            settings.report_dir / f"weekly_{slug}.md",
            project_markdown,
        )
        outputs[f"{slug}_text"] = _write(
            settings.report_dir / f"weekly_{slug}.txt",
            _plain_text(project_markdown),
        )
        outputs[f"{slug}_html"] = _write(
            settings.report_dir / f"weekly_{slug}.html",
            _project_html(project_context),
        )
        outputs[f"{slug}_json"] = _write_json(
            settings.report_dir / f"weekly_{slug}.json",
            {
                "generated_at": context["generated_at"],
                "project": project.evaluation.to_dict(),
                "insights": project_insights[project.evaluation.project_name],
            },
        )

    return outputs


def slugify(value: str) -> str:
    """Create stable file-safe names."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def _portfolio_markdown(context: dict[str, Any]) -> str:
    insights = context["portfolio_insights"]
    portfolio: PortfolioRun = context["portfolio"]
    lines = [
        "# Weekly Portfolio Health Report",
        "",
        f"Generated: {context['generated_at']}",
        "",
        "## Executive Summary",
        "",
        insights["executive_summary"],
        "",
        "## Portfolio Metrics",
        "",
        f"- Overall status: {insights['overall_status']}",
        f"- Overall score: {insights['overall_score']}",
        f"- Projects: {portfolio.portfolio_metrics.get('project_count', 0)}",
        f"- Total tasks: {portfolio.portfolio_metrics.get('total_tasks', 0)}",
        f"- Weighted completion: {portfolio.portfolio_metrics.get('weighted_completion_pct', 0.0):.0%}",
        "",
        "## Major Risks",
        "",
        *_bullets(insights["major_risks"]),
        "",
        "## Emerging Trends",
        "",
        *_bullets(insights["emerging_trends"]),
        "",
        "## Recommendations",
        "",
        *_bullets(insights["recommendations"]),
        "",
        "## Top Blockers",
        "",
        *_bullets(insights["top_blockers"]),
        "",
        "## Project Details",
        "",
    ]

    for project in portfolio.projects:
        evaluation = project.evaluation
        project_insights = context["project_insights"][evaluation.project_name]
        lines.extend(
            [
                f"### {evaluation.project_name}",
                "",
                f"- Computed RAG: {evaluation.computed_status}",
                f"- Score: {evaluation.health_score.final_score}",
                f"- Confidence: {evaluation.health_score.confidence:.0%}",
                f"- Workbook RAG: {evaluation.workbook_status}",
                f"- Discrepancy: {evaluation.discrepancy}",
                "",
                project_insights["executive_summary"],
                "",
                "Component scores:",
                "",
            ]
        )
        for component in evaluation.health_score.components:
            lines.append(f"- {component.name}: {component.score} (weight {component.weight:.0%})")
        lines.extend(["", "Risks:", "", *_bullets(project_insights["major_risks"]), ""])

    return "\n".join(lines).strip() + "\n"


def _project_markdown(context: dict[str, Any]) -> str:
    project: ProjectRun = context["project"]
    evaluation = project.evaluation
    insights = context["insights"]
    lines = [
        f"# Weekly Health Report - {evaluation.project_name}",
        "",
        f"Generated: {context['generated_at']}",
        f"As of: {evaluation.as_of_date}",
        "",
        "## Executive Summary",
        "",
        insights["executive_summary"],
        "",
        "## Health Score",
        "",
        f"- Computed RAG: {evaluation.computed_status}",
        f"- Final score: {evaluation.health_score.final_score}",
        f"- Confidence: {evaluation.health_score.confidence:.0%}",
        f"- Workbook RAG: {evaluation.workbook_status}",
        f"- RAG comparison: {evaluation.discrepancy}",
        "",
        "## Component Evidence",
        "",
    ]
    for component in evaluation.health_score.components:
        lines.append(f"### {component.name}")
        lines.append(f"Score: {component.score} | Weight: {component.weight:.0%}")
        lines.extend(_bullets(component.evidence))
        lines.append("")
    lines.extend(
        [
            "## Major Risks",
            "",
            *_bullets(insights["major_risks"]),
            "",
            "## Recommendations",
            "",
            *_bullets(insights["recommendations"]),
            "",
            "## Top Blockers",
            "",
            *_bullets(insights["top_blockers"]),
            "",
            "## Data Quality",
            "",
            f"Quality score: {project.validation.quality_score:.1f}/100",
            "",
        ]
    )
    for issue in project.validation.issues[:12]:
        lines.append(f"- {issue.severity.upper()} {issue.field}: {issue.message}")
    return "\n".join(lines).strip() + "\n"


def _html_report(context: dict[str, Any]) -> str:
    markdown = _portfolio_markdown(context)
    body = _markdown_to_html(markdown)
    return _wrap_html("Weekly Portfolio Health Report", body)


def _project_html(context: dict[str, Any]) -> str:
    markdown = _project_markdown(context)
    body = _markdown_to_html(markdown)
    return _wrap_html(f"Weekly Health Report - {context['project'].evaluation.project_name}", body)


def _wrap_html(title: str, body: str) -> str:
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; color: #1f2937; line-height: 1.45; }
    h1, h2, h3 { color: #111827; }
    h1 { border-bottom: 3px solid #2563eb; padding-bottom: 12px; }
    li { margin: 6px 0; }
    .rag { font-weight: 700; }
  </style>
</head>
<body>
{{ body }}
</body>
</html>"""
    if Template:
        return Template(template).render(title=title, body=body)
    return template.replace("{{ title }}", title).replace("{{ body }}", body)


def _markdown_to_html(markdown: str) -> str:
    html_lines: list[str] = []
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            html_lines.append(f"<h1>{_escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{_escape(line[3:])}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{_escape(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_escape(line[2:])}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{_escape(line)}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def _json_payload(
    portfolio: PortfolioRun,
    portfolio_insights: dict[str, Any],
    project_insights: dict[str, Any],
) -> dict[str, Any]:
    payload = portfolio.to_dict()
    payload["portfolio_insights"] = portfolio_insights
    payload["project_insights"] = project_insights
    return payload


def _plain_text(markdown: str) -> str:
    text = re.sub(r"^#+\s*", "", markdown, flags=re.MULTILINE)
    text = re.sub(r"(?m)^- ", "* ", text)
    return text


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
