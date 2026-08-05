"""Internal agent-to-agent handoff models.

These are NOT the graded output schema (see output_models.py) — they carry
richer intermediate state (including the LLM cross-check bookkeeping used to
compute confidence and populate trace.jsonl) between agents inside a single
case run.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class HandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmCrossCheckResult(HandoffModel):
    """Result of comparing one agent's deterministic decision against its
    own LLM's independent classification of the same facts."""

    agent: str
    field: str
    deterministic_value: Any
    llm_value: Any = None
    agrees: bool = True
    llm_unavailable: bool = False
    rationale: str = ""


class OrderCore(HandoffModel):
    order_id: str
    customer_id: str
    order_status: str
    order_purchase_timestamp: Optional[str] = None
    order_approved_at: Optional[str] = None
    order_delivered_carrier_date: Optional[str] = None
    order_delivered_customer_date: Optional[str] = None
    order_estimated_delivery_date: Optional[str] = None


class OrderProductFacts(HandoffModel):
    order: OrderCore
    item_count: int
    item_ids: list[str]
    seller_ids: list[str]
    product_ids: list[str]
    category_names: list[str]
    item_total_brl: float
    freight_total_brl: float
    multi_item_order: bool
    multi_seller_order: bool
    multiple_categories: bool
    llm_cross_checks: list[LlmCrossCheckResult] = []


class CustomerFacts(HandoffModel):
    customer_unique_id: str
    related_order_ids: list[str]
    repeat_customer: bool
    llm_cross_checks: list[LlmCrossCheckResult] = []


class SellerHandoffFact(HandoffModel):
    seller_id: str
    shipping_limit_at: Optional[str] = None
    handoff_variance_hours: Optional[float] = None
    late_handoff: bool


class DeliveryFacts(HandoffModel):
    delivered_at: Optional[str] = None
    estimated_delivery_at: Optional[str] = None
    carrier_handoff_at: Optional[str] = None
    delivery_variance_hours: Optional[float] = None
    is_late_delivery: Optional[bool] = None
    seller_handoff_analysis: list[SellerHandoffFact]
    late_handoff_seller_ids: list[str]
    any_seller_late: bool
    llm_cross_checks: list[LlmCrossCheckResult] = []


class PaymentFacts(HandoffModel):
    payment_ids: list[str]
    payment_types: list[str]
    item_total_brl: float
    freight_total_brl: float
    expected_total_brl: Optional[float] = None
    payment_total_brl: float
    difference_brl: Optional[float] = None
    reconciled: Optional[bool] = None
    payment_count: int
    split_payment: bool
    llm_cross_checks: list[LlmCrossCheckResult] = []


class CaseFacts(HandoffModel):
    """Consolidated fact sheet the Coordinator builds for the Policy Agent.
    The Policy Agent never touches the DataStore directly — only this."""

    order_id: str
    order_status: str
    payment_total_brl: float
    payment_count: int
    is_late_delivery: Optional[bool]
    any_seller_late: bool
    reconciled: Optional[bool]
    item_count: int
    multi_seller_order: bool
    freight_total_brl: float
    late_handoff_seller_ids: list[str]


class ResponsiblePartyFact(HandoffModel):
    party_type: str
    party_id: str


class PolicyDecision(HandoffModel):
    primary_issue: str
    primary_issue_llm: Optional[str] = None
    llm_agrees: bool = True
    llm_unavailable: bool = False
    secondary_issues: list[str]
    root_cause_codes: list[str]
    responsible_parties: list[ResponsiblePartyFact]
    recommended_refund_brl: float
    resolution_actions: list[str]
    case_status: str
    policy_edge_case: bool = False


class Correction(HandoffModel):
    field: str
    before: Any
    after: Any
    reason: str
