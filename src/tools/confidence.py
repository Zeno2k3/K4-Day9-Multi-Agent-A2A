"""Deterministic, penalty-based confidence score. Never an LLM-invented
number — every input here is a measurable fact or an agreement boolean
that is also written to trace.jsonl, so the score is fully reproducible."""
from __future__ import annotations

from src.schemas.handoff_models import Correction, LlmCrossCheckResult


def compute_confidence(
    cross_checks: list[LlmCrossCheckResult],
    policy_llm_agrees: bool,
    policy_llm_unavailable: bool,
    reconciled: bool | None,
    corrections: list[Correction],
) -> float:
    score = 1.0
    disagreements = sum(1 for c in cross_checks if not c.agrees and not c.llm_unavailable)
    unavailable = sum(1 for c in cross_checks if c.llm_unavailable) + (1 if policy_llm_unavailable else 0)

    score -= min(0.40, 0.15 * disagreements)
    if not policy_llm_agrees and not policy_llm_unavailable:
        score -= 0.30
    if reconciled is False:
        score -= 0.10
    score -= min(0.20, 0.05 * len(corrections))
    score -= 0.05 * unavailable

    return round(max(0.05, min(1.0, score)), 2)
