"""Deterministic evidence_ids construction (README §5).

Every evidence string is a formatted reference to an ID that was already
obtained from a DataStore dict key elsewhere in the pipeline — never typed
out by an LLM — so fabricated evidence is structurally impossible here.
"""
from __future__ import annotations

from src.config import MAX_EVIDENCE_IDS
from src.data.loader import DataStore

VALID_ROOT_CAUSE_CODES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}


def build_evidence_ids(
    order_id: str,
    item_ids: list[str],
    payment_ids: list[str],
    responsible_seller_ids: list[str],
    root_cause_codes: list[str],
) -> list[str]:
    evidence = [f"order:{order_id}"]
    evidence += [f"item:{item_id}" for item_id in item_ids]
    evidence += [f"payment:{payment_id}" for payment_id in payment_ids]
    evidence += [f"seller:{seller_id}" for seller_id in responsible_seller_ids]
    evidence += [f"policy:{code}" for code in root_cause_codes]
    return evidence[:MAX_EVIDENCE_IDS]


def _evidence_exists(ds: DataStore, evidence_id: str) -> bool:
    prefix, _, rest = evidence_id.partition(":")
    if prefix == "order":
        return ds.order_exists(rest)
    if prefix == "item":
        order_id, _, item_id = rest.rpartition(":")
        return bool(order_id) and ds.item_exists(order_id, item_id)
    if prefix == "payment":
        order_id, _, seq = rest.rpartition(":")
        return bool(order_id) and ds.payment_exists(order_id, seq)
    if prefix == "seller":
        return ds.seller_exists(rest)
    if prefix == "policy":
        return rest in VALID_ROOT_CAUSE_CODES
    return False


def filter_valid_evidence(ds: DataStore, evidence_ids: list[str]) -> tuple[list[str], list[str]]:
    """Verifier-side safety net: drops any evidence string that doesn't
    resolve to a real row/ID in the loaded CSVs (README §5 "false
    positive"). Returns (kept, dropped)."""
    kept: list[str] = []
    dropped: list[str] = []
    for evidence_id in evidence_ids:
        if _evidence_exists(ds, evidence_id):
            kept.append(evidence_id)
        else:
            dropped.append(evidence_id)
    return kept, dropped
