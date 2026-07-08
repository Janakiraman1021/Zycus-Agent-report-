# Architecture

The agent is organized as a small production-style pipeline. Each module has one clear responsibility, and generated reports are based on normalized task-level evidence rather than workbook summary status alone.

```mermaid
flowchart LR
    A["Excel workbooks in data/"] --> B["loader.py - discover sheets and schemas"]
    B --> C["preprocess.py - canonical task model"]
    C --> D["validator.py - data quality checks"]
    D --> E["metrics.py - schedule, blockers, risk, sentiment signals"]
    E --> F["scoring.py - weighted RAG score"]
    F --> G["rag_engine.py - project and portfolio run object"]
    G --> H["insights.py - executive narrative"]
    G --> I["charts.py - visuals"]
    H --> J["report_generator.py - Markdown, HTML, JSON, TXT"]
    I --> K["ppt_generator.py - VP presentation"]
    J --> L["reports/ and outputs/"]
    K --> M["presentations/monthly_portfolio_health.pptx"]
```

## Design Decisions

- Workbook sheets are profiled automatically using column evidence, row counts, and compact key/value patterns.
- Canonical fields are mapped through aliases, so variants such as `RAG`, `Schedule Health`, `% Complete`, and `Critical ?` can be handled without fixed column positions.
- Missing columns are reported as data quality findings instead of causing runtime failure.
- LLM reasoning is optional. OpenAI, Groq, and Ollama are supported through a small adapter, while mock mode always produces deterministic reasoning.
- Reports and the PowerPoint are regenerated from the same evaluation object to keep numbers consistent across all outputs.
