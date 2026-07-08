"""Command-line interface for the Project Health Reporting Agent."""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

try:
    import typer
except ImportError:  # pragma: no cover - fallback for minimal runtimes
    typer = None  # type: ignore[assignment]

try:
    from rich.console import Console
    from rich.progress import track
except ImportError:  # pragma: no cover - fallback for minimal runtimes
    Console = None  # type: ignore[assignment]
    track = None  # type: ignore[assignment]

from src.charts import generate_charts
from src.config import AgentSettings
from src.llm_reasoning import LLMReasoner
from src.ppt_generator import generate_presentation
from src.rag_engine import PortfolioRun, evaluate_workbooks
from src.report_generator import generate_reports
from src.scheduler import write_schedule_reference


LOGGER = logging.getLogger("project_health_agent")
ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT_DIR / "config" / "default_config.json"


if typer:
    app = typer.Typer(
        add_completion=False,
        help="AI Project Health Reporting Agent",
    )
else:
    app = None


def run_agent(
    weekly: bool = False,
    monthly: bool = False,
    ppt: bool = False,
    json_output: bool = False,
    html: bool = False,
    data_dir: Path | None = None,
    as_of: str | None = None,
    llm_provider: str | None = None,
) -> dict[str, Path | str]:
    """Run the complete project health workflow."""

    settings = AgentSettings.from_root(ROOT_DIR, CONFIG_FILE)
    if data_dir:
        settings.data_dir = data_dir.resolve()
    if as_of:
        settings.as_of_date = date.fromisoformat(as_of)
    if llm_provider:
        settings.default_llm_provider = llm_provider
    settings.ensure_directories()
    _configure_logging(settings.log_dir)
    schedule_path = write_schedule_reference(settings.root_dir)

    console = Console() if Console else None
    _emit(console, "[bold blue]Project Health Reporting Agent[/bold blue]")
    LOGGER.info("Starting Project Health Reporting Agent")
    LOGGER.info("Data directory: %s", settings.data_dir)

    generate_all = not any([weekly, monthly, ppt, json_output, html])
    phases = ["evaluate workbooks", "generate charts", "generate reports", "generate presentation"]
    iterator = track(phases, description="Running agent") if track else phases

    portfolio: PortfolioRun | None = None
    chart_paths: dict[str, Path] = {}
    report_paths: dict[str, Path] = {}
    presentation_path: Path | None = None

    for phase in iterator:
        if phase == "evaluate workbooks":
            portfolio = evaluate_workbooks(settings)
            if not portfolio.projects:
                raise RuntimeError(f"No Excel workbooks found in {settings.data_dir}")
            LOGGER.info("Evaluated %s project workbooks", len(portfolio.projects))
        elif phase == "generate charts":
            assert portfolio is not None
            chart_paths = generate_charts(portfolio, settings)
            LOGGER.info("Generated %s charts", len(chart_paths))
        elif phase == "generate reports":
            assert portfolio is not None
            if generate_all or weekly or json_output or html:
                report_paths = generate_reports(portfolio, settings)
                LOGGER.info("Generated %s report artifacts", len(report_paths))
        elif phase == "generate presentation":
            assert portfolio is not None
            if generate_all or monthly or ppt:
                presentation_path = generate_presentation(portfolio, chart_paths, settings)
                LOGGER.info("Generated presentation: %s", presentation_path)

    assert portfolio is not None
    reasoner = LLMReasoner(provider=settings.default_llm_provider)
    fallback = (
        "Deterministic reasoning was used because no external LLM credentials are required. "
        "The final reports are generated from validated task-level metrics."
    )
    reasoning = reasoner.explain("Summarize the portfolio health run.", fallback)
    LOGGER.info("Reasoning provider: %s, used_llm=%s", reasoning.provider, reasoning.used_llm)

    outputs: dict[str, Path | str] = {
        "schedule_reference": schedule_path,
        "log": settings.log_dir / "sample_execution.log",
        "reasoning_provider": reasoning.provider,
    }
    outputs.update(report_paths)
    outputs.update(chart_paths)
    if presentation_path:
        outputs["presentation"] = presentation_path

    _emit_summary(console, portfolio, outputs)
    LOGGER.info("Agent run completed successfully")
    return outputs


def main(argv: list[str] | None = None) -> int:
    """Entry point used by run.py."""

    if typer and argv is None:
        try:
            app(standalone_mode=False)  # type: ignore[misc]
            return 0
        except typer.Exit as exc:  # type: ignore[union-attr]
            return int(exc.exit_code or 0)
    return _argparse_main(argv)


def _argparse_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Project Health Reporting Agent")
    parser.add_argument("--weekly", action="store_true", help="Generate weekly reports")
    parser.add_argument("--monthly", action="store_true", help="Generate monthly synthesis artifacts")
    parser.add_argument("--ppt", action="store_true", help="Generate PowerPoint")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Generate JSON outputs")
    parser.add_argument("--html", action="store_true", help="Generate HTML outputs")
    parser.add_argument("--data-dir", type=Path, default=None, help="Directory containing Excel files")
    parser.add_argument("--as-of", default=None, help="Override as-of date, YYYY-MM-DD")
    parser.add_argument("--llm-provider", default=None, help="mock, openai, groq, or ollama")
    args = parser.parse_args(argv)
    run_agent(**vars(args))
    return 0


def _configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    for handler in LOGGER.handlers[:]:
        LOGGER.removeHandler(handler)
    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    for filename in ["agent_run.log", "sample_execution.log"]:
        handler = logging.FileHandler(log_dir / filename, mode="w", encoding="utf-8")
        handler.setFormatter(formatter)
        LOGGER.addHandler(handler)


def _emit(console: object | None, message: str) -> None:
    if console:
        console.print(message)
    else:
        print(message)


def _emit_summary(console: object | None, portfolio: PortfolioRun, outputs: dict[str, Path | str]) -> None:
    lines = ["Run complete", ""]
    for project in portfolio.projects:
        lines.append(
            f"{project.evaluation.project_name}: {project.evaluation.computed_status} "
            f"({project.evaluation.health_score.final_score:.1f})"
        )
    lines.append("")
    lines.append("Key outputs:")
    for key, value in outputs.items():
        lines.append(f"- {key}: {value}")
    _emit(console, "\n".join(lines))


if typer:

    @app.callback(invoke_without_command=True)  # type: ignore[union-attr]
    def _typer_entry(
        weekly: bool = typer.Option(False, "--weekly", help="Generate weekly reports"),
        monthly: bool = typer.Option(False, "--monthly", help="Generate monthly synthesis artifacts"),
        ppt: bool = typer.Option(False, "--ppt", help="Generate PowerPoint"),
        json_output: bool = typer.Option(False, "--json", help="Generate JSON outputs"),
        html: bool = typer.Option(False, "--html", help="Generate HTML outputs"),
        data_dir: Path | None = typer.Option(None, "--data-dir", help="Directory containing Excel files"),
        as_of: str | None = typer.Option(None, "--as-of", help="Override as-of date, YYYY-MM-DD"),
        llm_provider: str | None = typer.Option(None, "--llm-provider", help="mock, openai, groq, or ollama"),
    ) -> None:
        exit_code = 0
        try:
            run_agent(
                weekly=weekly,
                monthly=monthly,
                ppt=ppt,
                json_output=json_output,
                html=html,
                data_dir=data_dir,
                as_of=as_of,
                llm_provider=llm_provider,
            )
        except Exception as exc:  # pragma: no cover - CLI error boundary
            LOGGER.exception("Agent run failed")
            if Console:
                Console().print(f"[red]Agent run failed:[/red] {exc}")
            else:
                print(f"Agent run failed: {exc}")
            exit_code = 1
        raise typer.Exit(exit_code)
