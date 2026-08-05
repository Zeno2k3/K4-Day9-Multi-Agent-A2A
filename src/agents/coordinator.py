"""Coordinator Agent.

Holds the DataStore reference and orchestrates the 6 other agents in
sequence: Order & Product -> Customer -> Payment -> Delivery -> Policy ->
Verifier. Merges their handoffs into the draft output and computes the
final confidence score. Makes no LLM call of its own — pure orchestration
and structural assembly.
"""
from __future__ import annotations

from typing import Any

from src.agents.customer_agent import CustomerAgent
from src.agents.delivery_agent import DeliveryAgent
from src.agents.order_product_agent import OrderProductAgent
from src.agents.payment_agent import PaymentAgent
from src.agents.policy_agent import PolicyAgent
from src.agents.verifier_agent import VerifierAgent
from src.data.loader import DataStore
from src.llm.groq_client import GroqClient
from src.schemas.handoff_models import CaseFacts
from src.schemas.input_models import InputCase
from src.schemas.output_models import CaseOutput
from src.tools import evidence as evidence_tools
from src.tools.confidence import compute_confidence
from src.tracing.trace_logger import TraceLogger


class Coordinator:
    name = "coordinator"

    def __init__(self, ds: DataStore, llm: GroqClient):
        self.ds = ds
        self.order_product_agent = OrderProductAgent(ds, llm)
        self.customer_agent = CustomerAgent(ds, llm)
        self.payment_agent = PaymentAgent(ds, llm)
        self.delivery_agent = DeliveryAgent(ds, llm)
        self.policy_agent = PolicyAgent(llm)
        self.verifier_agent = VerifierAgent(ds, llm)

    def run_case(self, case: InputCase, trace: TraceLogger) -> CaseOutput:
        case_id = case.case_id
        order_id = case.customer_request.claimed_order_id
        trace.case_start(case_id, order_id=order_id)

        op_facts = self.order_product_agent.run(case_id, order_id, trace)
        if op_facts is None:
            output = build_minimal_fallback_output(case_id, order_id)
            trace.case_end(case_id, status="order_not_found")
            return output

        customer_facts = self.customer_agent.run(
            case_id,
            op_facts.order.customer_id,
            order_id,
            case.investigation_scope.include_customer_history,
            trace,
        )
        payment_facts = self.payment_agent.run(
            case_id, order_id, op_facts.item_total_brl, op_facts.freight_total_brl, op_facts.item_count > 0, trace
        )
        delivery_facts = self.delivery_agent.run(case_id, op_facts.order, trace)

        case_facts = CaseFacts(
            order_id=order_id,
            order_status=op_facts.order.order_status,
            payment_total_brl=payment_facts.payment_total_brl,
            payment_count=payment_facts.payment_count,
            is_late_delivery=delivery_facts.is_late_delivery,
            any_seller_late=delivery_facts.any_seller_late,
            reconciled=payment_facts.reconciled,
            item_count=op_facts.item_count,
            multi_seller_order=op_facts.multi_seller_order,
            freight_total_brl=op_facts.freight_total_brl,
            late_handoff_seller_ids=delivery_facts.late_handoff_seller_ids,
        )
        policy_decision = self.policy_agent.run(
            case_id,
            case_facts,
            op_facts.multi_item_order,
            op_facts.multi_seller_order,
            payment_facts.split_payment,
            customer_facts.repeat_customer,
            op_facts.multiple_categories,
            trace,
        )

        responsible_seller_ids = [
            p.party_id for p in policy_decision.responsible_parties if p.party_type == "seller"
        ]
        evidence_ids = evidence_tools.build_evidence_ids(
            order_id,
            op_facts.item_ids,
            payment_facts.payment_ids,
            responsible_seller_ids,
            policy_decision.root_cause_codes,
        )

        all_cross_checks = (
            op_facts.llm_cross_checks
            + customer_facts.llm_cross_checks
            + payment_facts.llm_cross_checks
            + delivery_facts.llm_cross_checks
        )
        preliminary_confidence = compute_confidence(
            all_cross_checks, policy_decision.llm_agrees, policy_decision.llm_unavailable,
            payment_facts.reconciled, [],
        )

        draft = _assemble_draft(
            case_id, order_id, op_facts, customer_facts, payment_facts, delivery_facts,
            policy_decision, evidence_ids, preliminary_confidence,
        )

        final_draft, corrections = self.verifier_agent.run(case_id, draft, trace)

        final_confidence = compute_confidence(
            all_cross_checks, policy_decision.llm_agrees, policy_decision.llm_unavailable,
            payment_facts.reconciled, corrections,
        )
        final_draft["case_assessment"]["confidence"] = final_confidence

        output = CaseOutput.model_validate(final_draft)
        trace.case_end(
            case_id,
            primary_issue=output.case_assessment.primary_issue,
            confidence=output.case_assessment.confidence,
            corrections=len(corrections),
            policy_edge_case=policy_decision.policy_edge_case,
        )
        return output


def _assemble_draft(
    case_id: str,
    order_id: str,
    op: Any,
    customer: Any,
    payment: Any,
    delivery: Any,
    policy: Any,
    evidence_ids: list[str],
    confidence: float,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_assessment": {
            "primary_issue": policy.primary_issue,
            "secondary_issues": policy.secondary_issues,
            "case_status": policy.case_status,
            "confidence": confidence,
        },
        "affected_entities": {
            "order_ids": [order_id],
            "item_ids": op.item_ids,
            "seller_ids": op.seller_ids,
            "payment_ids": payment.payment_ids,
        },
        "customer_context": {
            "customer_unique_id": customer.customer_unique_id,
            "related_order_ids": customer.related_order_ids,
        },
        "product_context": {
            "product_ids": op.product_ids,
            "category_names": op.category_names,
        },
        "delivery_analysis": {
            "delivered_at": delivery.delivered_at,
            "estimated_delivery_at": delivery.estimated_delivery_at,
            "carrier_handoff_at": delivery.carrier_handoff_at,
            "delivery_variance_hours": delivery.delivery_variance_hours,
            "seller_handoff_analysis": [s.model_dump() for s in delivery.seller_handoff_analysis],
            "late_handoff_seller_ids": delivery.late_handoff_seller_ids,
        },
        "payment_reconciliation": {
            "currency": "BRL",
            "item_total_brl": payment.item_total_brl,
            "freight_total_brl": payment.freight_total_brl,
            "expected_total_brl": payment.expected_total_brl,
            "payment_total_brl": payment.payment_total_brl,
            "difference_brl": payment.difference_brl,
            "reconciled": payment.reconciled,
            "payment_types": payment.payment_types,
        },
        "root_cause_analysis": {
            "ranked_causes": [
                {"cause_code": code, "rank": i + 1} for i, code in enumerate(policy.root_cause_codes)
            ],
            "responsible_parties": [p.model_dump() for p in policy.responsible_parties],
        },
        "evidence_ids": evidence_ids,
        "financial_resolution": {
            "currency": "BRL",
            "recommended_refund_brl": policy.recommended_refund_brl,
        },
        "resolution_actions": policy.resolution_actions,
    }


def build_minimal_fallback_output(case_id: str, order_id: str | None) -> CaseOutput:
    """Used both when the claimed order can't be found and, at the runner
    level, when a case raises an uncaught exception. Guarantees the zip
    always contains exactly 50 files even in a worst-case failure."""
    return CaseOutput.model_validate(
        {
            "case_id": case_id,
            "case_assessment": {
                "primary_issue": "unsupported_late_claim",
                "secondary_issues": [],
                "case_status": "no_action",
                "confidence": 0.05,
            },
            "affected_entities": {
                "order_ids": [order_id] if order_id else [],
                "item_ids": [],
                "seller_ids": [],
                "payment_ids": [],
            },
            "customer_context": {"customer_unique_id": "", "related_order_ids": []},
            "product_context": {"product_ids": [], "category_names": []},
            "delivery_analysis": {
                "delivered_at": None,
                "estimated_delivery_at": None,
                "carrier_handoff_at": None,
                "delivery_variance_hours": None,
                "seller_handoff_analysis": [],
                "late_handoff_seller_ids": [],
            },
            "payment_reconciliation": {
                "currency": "BRL",
                "item_total_brl": 0.0,
                "freight_total_brl": 0.0,
                "expected_total_brl": None,
                "payment_total_brl": 0.0,
                "difference_brl": None,
                "reconciled": None,
                "payment_types": [],
            },
            "root_cause_analysis": {"ranked_causes": [], "responsible_parties": []},
            "evidence_ids": [f"order:{order_id}"] if order_id else [],
            "financial_resolution": {"currency": "BRL", "recommended_refund_brl": 0.0},
            "resolution_actions": [],
        }
    )
