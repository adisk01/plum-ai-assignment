"""Lightweight trace for the claims pipeline.

A Trace is a list of TraceSpans, one per stage (parse/assemble/rules/fraud/finalize).
Each span has events: LLM calls, rule evaluations, warnings. Nothing fancy —
everything is JSON-serializable so it lands straight in the final decision.

Usage:

    tracer = Tracer(claim_id="TC004")
    with tracer.span("parse"):
        tracer.event("llm_call", model="gpt-4o-mini", latency_ms=412)
        ...
    trace = tracer.finish()
"""

import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


class TraceEvent(BaseModel):
    name: str
    at: str = Field(default_factory=_now_iso)
    attrs: dict[str, Any] = Field(default_factory=dict)


class TraceSpan(BaseModel):
    stage: str
    started_at: str
    ended_at: Optional[str] = None
    duration_ms: float = 0.0
    status: str = "ok"             # "ok" | "error" | "skipped"
    error: Optional[str] = None
    events: list[TraceEvent] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    trace_id: str
    claim_id: str
    started_at: str
    ended_at: Optional[str] = None
    duration_ms: float = 0.0
    spans: list[TraceSpan] = Field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "claim_id": self.claim_id,
            "duration_ms": round(self.duration_ms, 1),
            "spans": [
                {"stage": s.stage, "status": s.status, "duration_ms": round(s.duration_ms, 1)}
                for s in self.spans
            ],
        }


class Tracer:
    """Collects spans + events for one claim run."""

    def __init__(self, claim_id: str):
        self.trace_id = uuid.uuid4().hex[:12]
        self.claim_id = claim_id
        self._start_iso = _now_iso()
        self._start_ms = _now_ms()
        self.spans: list[TraceSpan] = []
        self._stack: list[tuple[TraceSpan, float]] = []

    @contextmanager
    def span(self, stage: str, **attrs):
        sp = TraceSpan(stage=stage, started_at=_now_iso(), attrs=dict(attrs))
        self.spans.append(sp)
        t0 = _now_ms()
        self._stack.append((sp, t0))
        try:
            yield sp
        except Exception as e:
            sp.status = "error"
            sp.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            sp.ended_at = _now_iso()
            sp.duration_ms = round(_now_ms() - t0, 2)
            self._stack.pop()

    def event(self, name: str, **attrs):
        ev = TraceEvent(name=name, attrs=dict(attrs))
        if self._stack:
            self._stack[-1][0].events.append(ev)
        else:
            # No active span; attach to a synthetic root span
            if not self.spans or self.spans[-1].stage != "_root":
                self.spans.append(TraceSpan(stage="_root", started_at=_now_iso()))
            self.spans[-1].events.append(ev)
        return ev

    def annotate(self, **attrs):
        """Merge attrs into the current span."""
        if self._stack:
            self._stack[-1][0].attrs.update(attrs)

    def mark_skipped(self, stage: str, reason: str = ""):
        self.spans.append(TraceSpan(
            stage=stage,
            started_at=_now_iso(),
            ended_at=_now_iso(),
            status="skipped",
            attrs={"reason": reason} if reason else {},
        ))

    def finish(self) -> Trace:
        return Trace(
            trace_id=self.trace_id,
            claim_id=self.claim_id,
            started_at=self._start_iso,
            ended_at=_now_iso(),
            duration_ms=round(_now_ms() - self._start_ms, 2),
            spans=list(self.spans),
        )


# --- Thread-local current tracer so instrumentation can find it ---------------

_local = threading.local()


def set_tracer(tracer: Optional[Tracer]) -> None:
    _local.tracer = tracer


def get_tracer() -> Optional[Tracer]:
    return getattr(_local, "tracer", None)
