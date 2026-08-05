"""Shared helpers for turning an LLM classification call into logged
cross-check records. Used by every domain agent so the "LLM proposes,
deterministic value always wins" pattern is implemented in exactly one
place (see architecture.md, "design tension")."""
from __future__ import annotations

from typing import Any

from src.llm.groq_client import LlmCallResult
from src.schemas.handoff_models import LlmCrossCheckResult


def build_cross_checks(
    agent_name: str, deterministic: dict[str, Any], llm_result: LlmCallResult
) -> list[LlmCrossCheckResult]:
    rationale = (
        str((llm_result.parsed or {}).get("rationale", ""))[:240]
        if llm_result.success
        else (llm_result.error or "")
    )
    checks: list[LlmCrossCheckResult] = []
    for field, det_value in deterministic.items():
        if llm_result.success and llm_result.parsed is not None and field in llm_result.parsed:
            llm_value = llm_result.parsed.get(field)
            checks.append(
                LlmCrossCheckResult(
                    agent=agent_name,
                    field=field,
                    deterministic_value=det_value,
                    llm_value=llm_value,
                    agrees=(llm_value == det_value),
                    rationale=rationale,
                )
            )
        else:
            checks.append(
                LlmCrossCheckResult(
                    agent=agent_name,
                    field=field,
                    deterministic_value=det_value,
                    llm_unavailable=True,
                    agrees=True,
                    rationale=rationale,
                )
            )
    return checks


def llm_trace_summary(llm_result: LlmCallResult) -> dict[str, Any]:
    return {
        "provider": "groq",
        "success": llm_result.success,
        "prompt_excerpt": llm_result.prompt_excerpt,
        "response_excerpt": llm_result.response_excerpt,
        "attempt": llm_result.attempt,
        "latency_ms": llm_result.latency_ms,
        "error": llm_result.error,
    }
