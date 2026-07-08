# Project Health RAG Methodology

This methodology computes project health independently from workbook-entered status fields. Workbook `Schedule Health` or `RAG` values are treated as comparison signals, not as the final answer.

## Weighted Score

Final health is a weighted score from 0 to 100:

`Final Score = Schedule * 0.30 + Budget * 0.20 + Milestones * 0.20 + Risks * 0.10 + Blockers * 0.10 + Sentiment * 0.05 + Data Quality * 0.05`

RAG mapping:

- `GREEN`: 85 to 100
- `AMBER`: 60 to 84
- `RED`: 0 to 59

## Component Formulas

### Schedule Health - 30%

Schedule health measures whether actual progress matches elapsed time and whether incomplete work is already late.

`Expected Completion = elapsed calendar days / total planned project days`

`Schedule Gap = Actual Completion - Expected Completion`

The score starts at 100 and subtracts penalties for negative schedule gap, overdue incomplete tasks, Red task-level health signals, and incomplete zero-float tasks.

### Budget Burn - 20%

Budget burn uses budget, cost, spend, or burn-rate fields when present. The supplied workbooks do not include financial fields, so the score is neutral at 70 with low confidence. This avoids falsely marking a project Green or Red when the source data cannot support a financial conclusion.

### Milestone Health - 20%

Milestone health combines incomplete tasks due soon, incomplete critical tasks, and schedule gap. When explicit milestone fields are sparse, the agent falls back to task hierarchy, date, completion, and critical-path fields.

### Risks - 10%

Risk score penalizes Red and Amber task-level signals, incomplete critical work, and on-hold tasks. This makes risk visible even when the workbook summary says the project is healthy.

### Blockers - 10%

Blocker score is based on stakeholder comments, on-hold tasks, and incomplete zero-float work. Comments are scanned for operational blocker terms such as pending, impacted, issue, need, remain, waiting, delay, and hold.

### Stakeholder Sentiment - 5%

Sentiment is deterministic and keyword based. Positive completion-oriented language improves the score. Risk-oriented or unresolved language reduces it. If no comments exist, sentiment is neutral with low confidence.

### Data Quality - 5%

Data quality starts at 100 and is reduced for missing required columns, missing optional signals, invalid dates, inferred completion values, and unknown statuses. The agent continues to run when columns are absent and reports the confidence impact.

## Assumptions

- Completion values may be stored as `0.44`, `44`, or blank. Blank completion is inferred from status.
- `Yellow` workbook values are normalized to `AMBER`.
- Missing budget data should reduce confidence, not force a Red score.
- Critical tasks, zero-float tasks, overdue tasks, comments, and schedule gap are stronger signals than workbook summary status.
- The workbook's `Today's Date` is used when available so generated reports are reproducible.
