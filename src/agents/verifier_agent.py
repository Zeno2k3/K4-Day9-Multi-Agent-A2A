"""Verifier Agent.

Runs deterministic checks first (auto-correcting in place, logging one
Correction per fix), then a single advisory LLM pass over the finalized
output. The LLM here can only flag inconsistencies into the trace — it
never mutates a value. Failure of any single check must never raise; a
run_one_case-level try/except in runner.py is the last-resort safety net,
but the Verifier itself is written to degrade a field rather than crash.
"""
from __future__ import annotations

from typing import Any

from src.agents.common import llm_trace_summary
from src.config import (
    MAX_CATEGORY_NAMES,
    MAX_ITEM_IDS,
    MAX_ORDER_IDS,
    MAX_PAYMENT_IDS,
    MAX_PRODUCT_IDS,
    MAX_RELATED_ORDER_IDS,
    MAX_RESOLUTION_ACTIONS,
    MAX_RESPONSIBLE_PARTIES,
    MAX_ROOT_CAUSES,
    MAX_SELLER_IDS,
)
from src.data.loader import DataStore
from src.llm.groq_client import GroqClient
from src.llm.prompts import VERIFIER_ADVISORY_SYSTEM_PROMPT
from src.schemas.handoff_models import Correction
from src.tools import evidence as evidence_tools
from src.tools.policy_tools import ACTION_REQUIRED_ISSUES, RESOLUTION_ACTION_ORDER, SECONDARY_ISSUE_ORDER
from src.tracing.trace_logger import TraceLogger

_ARRAY_CAPS: dict[tuple[str, str], int] = {
    ("affected_entities", "order_ids"): MAX_ORDER_IDS,
    ("affected_entities", "item_ids"): MAX_ITEM_IDS,
    ("affected_entities", "seller_ids"): MAX_SELLER_IDS,
    ("affected_entities", "payment_ids"): MAX_PAYMENT_IDS,
    ("customer_context", "related_order_ids"): MAX_RELATED_ORDER_IDS,
    ("product_context", "product_ids"): MAX_PRODUCT_IDS,
    ("product_context", "category_names"): MAX_CATEGORY_NAMES,
}


def _round(value: Any) -> Any:
    return round(value, 2) if isinstance(value, float) else value


class VerifierAgent:
    name = "verifier_agent"

    def __init__(self, ds: DataStore, llm: GroqClient):
        self.ds = ds
        self.llm = llm

    def run(
        self, case_id: str, draft: dict[str, Any], trace: TraceLogger
    ) -> tuple[dict[str, Any], list[Correction]]:
        corrections: list[Correction] = []

        self._cap_arrays(draft, corrections)
        self._enforce_itemless_nulls(draft, corrections)
        self._canonical_ordering(draft, corrections)
        self._case_status_consistency(draft, corrections)
        evidence_dropped = self._filter_evidence(draft, corrections)
        self._round_all_floats(draft)

        llm_result = self.llm.call_json(VERIFIER_ADVISORY_SYSTEM_PROMPT, _slim_for_llm(draft))

        trace.agent_run(
            case_id,
            self.name,
            inputs_summary={"corrections_needed": len(corrections)},
            tool_calls=[{"name": "filter_valid_evidence", "dropped": evidence_dropped}],
            llm_call=llm_trace_summary(llm_result),
            output_summary={
                "corrections_count": len(corrections),
                "llm_flags": (llm_result.parsed or {}).get("flags") if llm_result.success else None,
            },
        )
        for c in corrections:
            trace.correction(case_id, self.name, c.field, c.before, c.after, c.reason)

        return draft, corrections

    def _cap_arrays(self, draft: dict[str, Any], corrections: list[Correction]) -> None:
        for (section, field), cap in _ARRAY_CAPS.items():
            values = draft[section][field]
            if len(values) > cap:
                corrections.append(
                    Correction(field=f"{section}.{field}", before=len(values), after=cap, reason="array_limit_exceeded")
                )
                draft[section][field] = values[:cap]

        ranked = draft["root_cause_analysis"]["ranked_causes"]
        if len(ranked) > MAX_ROOT_CAUSES:
            corrections.append(
                Correction(
                    field="root_cause_analysis.ranked_causes",
                    before=len(ranked),
                    after=MAX_ROOT_CAUSES,
                    reason="array_limit_exceeded",
                )
            )
            draft["root_cause_analysis"]["ranked_causes"] = ranked[:MAX_ROOT_CAUSES]

        parties = draft["root_cause_analysis"]["responsible_parties"]
        if len(parties) > MAX_RESPONSIBLE_PARTIES:
            corrections.append(
                Correction(
                    field="root_cause_analysis.responsible_parties",
                    before=len(parties),
                    after=MAX_RESPONSIBLE_PARTIES,
                    reason="array_limit_exceeded",
                )
            )
            draft["root_cause_analysis"]["responsible_parties"] = parties[:MAX_RESPONSIBLE_PARTIES]

        actions = draft["resolution_actions"]
        if len(actions) > MAX_RESOLUTION_ACTIONS:
            corrections.append(
                Correction(
                    field="resolution_actions",
                    before=len(actions),
                    after=MAX_RESOLUTION_ACTIONS,
                    reason="array_limit_exceeded",
                )
            )
            draft["resolution_actions"] = actions[:MAX_RESOLUTION_ACTIONS]

    def _enforce_itemless_nulls(self, draft: dict[str, Any], corrections: list[Correction]) -> None:
        """README §4: for an order with zero item rows, expected_total_brl,
        difference_brl and reconciled must be null, and item/seller/product/
        category/seller-handoff arrays must be empty. This is a defensive
        re-assertion — it should already hold by construction (payment
        fields are never LLM-touched), but the Verifier is the structural
        safety net so it re-checks rather than trusts upstream."""
        order_ids = draft["affected_entities"]["order_ids"]
        order_id = order_ids[0] if order_ids else None
        has_items = bool(order_id and self.ds.items_by_order.get(order_id))
        if has_items:
            return

        pr = draft["payment_reconciliation"]
        for field in ("expected_total_brl", "difference_brl", "reconciled"):
            if pr[field] is not None:
                corrections.append(
                    Correction(
                        field=f"payment_reconciliation.{field}",
                        before=pr[field],
                        after=None,
                        reason="null_required_for_itemless_order",
                    )
                )
                pr[field] = None

        for section, field in (
            ("affected_entities", "item_ids"),
            ("affected_entities", "seller_ids"),
            ("product_context", "product_ids"),
            ("product_context", "category_names"),
        ):
            if draft[section][field]:
                corrections.append(
                    Correction(
                        field=f"{section}.{field}",
                        before=draft[section][field],
                        after=[],
                        reason="empty_required_for_itemless_order",
                    )
                )
                draft[section][field] = []

        if draft["delivery_analysis"]["seller_handoff_analysis"]:
            corrections.append(
                Correction(
                    field="delivery_analysis.seller_handoff_analysis",
                    before=len(draft["delivery_analysis"]["seller_handoff_analysis"]),
                    after=0,
                    reason="empty_required_for_itemless_order",
                )
            )
            draft["delivery_analysis"]["seller_handoff_analysis"] = []

    def _canonical_ordering(self, draft: dict[str, Any], corrections: list[Correction]) -> None:
        secondary = draft["case_assessment"]["secondary_issues"]
        reordered = [s for s in SECONDARY_ISSUE_ORDER if s in secondary]
        if reordered != secondary:
            corrections.append(
                Correction(
                    field="case_assessment.secondary_issues",
                    before=secondary,
                    after=reordered,
                    reason="reordered_to_canonical_sequence",
                )
            )
            draft["case_assessment"]["secondary_issues"] = reordered

        actions = draft["resolution_actions"]
        reordered_actions = [a for a in RESOLUTION_ACTION_ORDER if a in actions]
        if reordered_actions != actions:
            corrections.append(
                Correction(
                    field="resolution_actions",
                    before=actions,
                    after=reordered_actions,
                    reason="reordered_to_canonical_sequence",
                )
            )
            draft["resolution_actions"] = reordered_actions

    def _case_status_consistency(self, draft: dict[str, Any], corrections: list[Correction]) -> None:
        primary = draft["case_assessment"]["primary_issue"]
        expected_status = "action_required" if primary in ACTION_REQUIRED_ISSUES else "no_action"
        current = draft["case_assessment"]["case_status"]
        if current != expected_status:
            corrections.append(
                Correction(
                    field="case_assessment.case_status",
                    before=current,
                    after=expected_status,
                    reason="case_status_primary_issue_mismatch",
                )
            )
            draft["case_assessment"]["case_status"] = expected_status

    def _filter_evidence(self, draft: dict[str, Any], corrections: list[Correction]) -> list[str]:
        evidence_ids = draft["evidence_ids"]
        kept, dropped = evidence_tools.filter_valid_evidence(self.ds, evidence_ids)
        if dropped:
            corrections.append(
                Correction(
                    field="evidence_ids",
                    before=evidence_ids,
                    after=kept,
                    reason=f"evidence_not_found_in_source: {dropped}",
                )
            )
            draft["evidence_ids"] = kept
        return dropped

    def _round_all_floats(self, draft: dict[str, Any]) -> None:
        pr = draft["payment_reconciliation"]
        for field in ("item_total_brl", "freight_total_brl", "expected_total_brl", "payment_total_brl", "difference_brl"):
            pr[field] = _round(pr[field])
        draft["financial_resolution"]["recommended_refund_brl"] = _round(
            draft["financial_resolution"]["recommended_refund_brl"]
        )
        draft["delivery_analysis"]["delivery_variance_hours"] = _round(
            draft["delivery_analysis"]["delivery_variance_hours"]
        )
        for entry in draft["delivery_analysis"]["seller_handoff_analysis"]:
            entry["handoff_variance_hours"] = _round(entry["handoff_variance_hours"])
        draft["case_assessment"]["confidence"] = _round(draft["case_assessment"]["confidence"])


def _slim_for_llm(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_assessment": draft["case_assessment"],
        "payment_reconciliation": draft["payment_reconciliation"],
        "delivery_analysis": {
            "delivery_variance_hours": draft["delivery_analysis"]["delivery_variance_hours"],
            "late_handoff_seller_ids": draft["delivery_analysis"]["late_handoff_seller_ids"],
        },
        "financial_resolution": draft["financial_resolution"],
        "resolution_actions": draft["resolution_actions"],
    }
