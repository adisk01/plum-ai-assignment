"""Tracing / observability.

Two independent layers:

1. `Tracer` — claim-level audit log, attached to `FinalDecision.trace`.
   Always on. Deterministic, serializable, surfaces to the ops reviewer.
2. LangSmith — engineering-level tracing of LLM calls and graph-node runs.
   Activated by env vars (`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY=...`);
   applied via `@langsmith.traceable` directly in the callsites.
"""

from claims_processor.observability.trace import (
    Trace,
    TraceEvent,
    TraceSpan,
    Tracer,
    get_tracer,
    set_tracer,
)

__all__ = [
    "Trace",
    "TraceEvent",
    "TraceSpan",
    "Tracer",
    "get_tracer",
    "set_tracer",
]
