"""EC_POLICY_V2 decision engine (README §4) — the single highest-leverage
module for scoring accuracy. `classify_primary_issue` mirrors the README
policy table row order EXACTLY as a sequential if/elif: first matching row
wins, never reordered, never "best fit".
"""
from __future__ import annotations

from src.config import MAX_RESPONSIBLE_PARTIES, MAX_RESOLUTION_ACTIONS
from src.schemas.handoff_models import CaseFacts, ResponsiblePartyFact

ACTION_REQUIRED_ISSUES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
}

PRIMARY_ISSUE_ROOT_CAUSE = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}

PRIMARY_ISSUE_ACTION = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}

# Canonical orderings used by the Verifier to re-sort upstream output rather
# than trust whatever order an LLM-influenced step produced.
SECONDARY_ISSUE_ORDER = [
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
]

RESOLUTION_ACTION_ORDER = [
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
    "review_seller_handoff",
    "review_carrier_delay",
    "verify_refund_completion",
    "coordinate_multi_seller_case",
    "verify_payment_allocation",
]


def classify_primary_issue(f: CaseFacts) -> tuple[str, bool]:
    """Returns (primary_issue, matched_a_defined_row). If no row matches
    (not observed in the real 50-case input set, but must not crash on an
    unseen case), falls back to unsupported_late_claim/no_action and the
    caller logs a policy_edge_case trace flag."""
    if f.order_status == "canceled" and f.payment_total_brl > 0:
        return "canceled_order_paid", True
    if f.order_status == "unavailable" and f.payment_total_brl > 0:
        return "unavailable_order_paid", True
    if f.is_late_delivery and f.any_seller_late:
        return "late_delivery_seller", True
    if f.is_late_delivery and not f.any_seller_late:
        return "late_delivery_logistics", True
    if f.payment_count >= 2 and f.reconciled is True:
        return "valid_split_payment", True
    if f.is_late_delivery is False and f.reconciled is True:
        return "unsupported_late_claim", True
    return "unsupported_late_claim", False


def compute_secondary_issues(
    multi_item_order: bool,
    multi_seller_order: bool,
    split_payment: bool,
    repeat_customer: bool,
    multiple_categories: bool,
) -> list[str]:
    issues: list[str] = []
    if multi_item_order:
        issues.append("multi_item_order")
    if multi_seller_order:
        issues.append("multi_seller_order")
    if split_payment:
        issues.append("split_payment")
    if repeat_customer:
        issues.append("repeat_customer")
    if multiple_categories:
        issues.append("multiple_categories")
    return issues


def compute_case_status(primary_issue: str) -> str:
    return "action_required" if primary_issue in ACTION_REQUIRED_ISSUES else "no_action"


def compute_recommended_refund_brl(
    primary_issue: str, payment_total_brl: float, freight_total_brl: float
) -> float:
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        return round(payment_total_brl, 2)
    if primary_issue in ("late_delivery_seller", "late_delivery_logistics"):
        return round(freight_total_brl, 2)
    return 0.0


def compute_responsible_parties(
    primary_issue: str, late_handoff_seller_ids: list[str]
) -> list[ResponsiblePartyFact]:
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        return [ResponsiblePartyFact(party_type="platform", party_id="OLIST_PLATFORM")]
    if primary_issue == "late_delivery_seller":
        return [
            ResponsiblePartyFact(party_type="seller", party_id=sid)
            for sid in late_handoff_seller_ids[:MAX_RESPONSIBLE_PARTIES]
        ]
    if primary_issue == "late_delivery_logistics":
        return [ResponsiblePartyFact(party_type="logistics_provider", party_id="LOGISTICS_PROVIDER")]
    return []


def compute_resolution_actions(
    primary_issue: str,
    multi_seller_order: bool,
    split_payment: bool,
) -> list[str]:
    actions = [PRIMARY_ISSUE_ACTION[primary_issue]]
    if primary_issue == "late_delivery_seller":
        actions.append("review_seller_handoff")
    elif primary_issue == "late_delivery_logistics":
        actions.append("review_carrier_delay")
    # verify_refund_completion follows a FULL refund only, not a freight refund.
    # Ground truth for this is the README §6 worked example, which is a real
    # order (eb09635680fadffb33358e40b05c9029): late_delivery_seller with
    # recommended_refund_brl=18.27 > 0, yet its expected resolution_actions are
    # exactly [refund_freight, review_seller_handoff, verify_payment_allocation]
    # — no verify_refund_completion. Keying off "refund > 0" added a spurious
    # action to all 20 late-delivery cases.
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        actions.append("verify_refund_completion")
    if multi_seller_order:
        actions.append("coordinate_multi_seller_case")
    if split_payment and primary_issue != "valid_split_payment":
        actions.append("verify_payment_allocation")
    return actions[:MAX_RESOLUTION_ACTIONS]
