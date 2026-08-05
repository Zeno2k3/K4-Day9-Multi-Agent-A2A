"""Pydantic models for output/EC_0NN.json (README §6). Mirrors the schema
and array limits exactly; `extra="forbid"` so a typo'd field fails loudly
instead of silently shipping a wrong schema.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.config import (
    MAX_CATEGORY_NAMES,
    MAX_EVIDENCE_IDS,
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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


PrimaryIssue = Literal[
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]

SecondaryIssue = Literal[
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
]

CaseStatus = Literal["action_required", "no_action"]

RootCauseCode = Literal[
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
]

PartyType = Literal["platform", "seller", "logistics_provider"]

ResolutionAction = Literal[
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


class CaseAssessment(StrictModel):
    primary_issue: PrimaryIssue
    secondary_issues: list[SecondaryIssue] = Field(default_factory=list, max_length=5)
    case_status: CaseStatus
    confidence: float = Field(ge=0.0, le=1.0)


class AffectedEntities(StrictModel):
    order_ids: list[str] = Field(default_factory=list, max_length=MAX_ORDER_IDS)
    item_ids: list[str] = Field(default_factory=list, max_length=MAX_ITEM_IDS)
    seller_ids: list[str] = Field(default_factory=list, max_length=MAX_SELLER_IDS)
    payment_ids: list[str] = Field(default_factory=list, max_length=MAX_PAYMENT_IDS)


class CustomerContext(StrictModel):
    customer_unique_id: str
    related_order_ids: list[str] = Field(default_factory=list, max_length=MAX_RELATED_ORDER_IDS)


class ProductContext(StrictModel):
    product_ids: list[str] = Field(default_factory=list, max_length=MAX_PRODUCT_IDS)
    category_names: list[str] = Field(default_factory=list, max_length=MAX_CATEGORY_NAMES)


class SellerHandoffAnalysis(StrictModel):
    seller_id: str
    shipping_limit_at: Optional[str] = None
    handoff_variance_hours: Optional[float] = None
    late_handoff: bool


class DeliveryAnalysis(StrictModel):
    delivered_at: Optional[str] = None
    estimated_delivery_at: Optional[str] = None
    carrier_handoff_at: Optional[str] = None
    delivery_variance_hours: Optional[float] = None
    seller_handoff_analysis: list[SellerHandoffAnalysis] = Field(
        default_factory=list, max_length=MAX_SELLER_IDS
    )
    late_handoff_seller_ids: list[str] = Field(default_factory=list, max_length=MAX_SELLER_IDS)


class PaymentReconciliation(StrictModel):
    currency: Literal["BRL"] = "BRL"
    item_total_brl: float
    freight_total_brl: float
    expected_total_brl: Optional[float] = None
    payment_total_brl: float
    difference_brl: Optional[float] = None
    reconciled: Optional[bool] = None
    payment_types: list[str] = Field(default_factory=list)


class RankedCause(StrictModel):
    cause_code: RootCauseCode
    rank: int


class ResponsibleParty(StrictModel):
    party_type: PartyType
    party_id: str


class RootCauseAnalysis(StrictModel):
    ranked_causes: list[RankedCause] = Field(default_factory=list, max_length=MAX_ROOT_CAUSES)
    responsible_parties: list[ResponsibleParty] = Field(
        default_factory=list, max_length=MAX_RESPONSIBLE_PARTIES
    )


class FinancialResolution(StrictModel):
    currency: Literal["BRL"] = "BRL"
    recommended_refund_brl: float


class CaseOutput(StrictModel):
    case_id: str
    case_assessment: CaseAssessment
    affected_entities: AffectedEntities
    customer_context: CustomerContext
    product_context: ProductContext
    delivery_analysis: DeliveryAnalysis
    payment_reconciliation: PaymentReconciliation
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS)
    financial_resolution: FinancialResolution
    resolution_actions: list[ResolutionAction] = Field(
        default_factory=list, max_length=MAX_RESOLUTION_ACTIONS
    )
