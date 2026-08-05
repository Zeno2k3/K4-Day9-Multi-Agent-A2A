"""Delivery Agent.

Scoped data: the order's 5 timestamp fields, plus each item's seller_id and
shipping_limit_date only — imports only src.tools.delivery_tools.
"""
from __future__ import annotations

from src.agents.common import build_cross_checks, llm_trace_summary
from src.data.loader import DataStore
from src.llm.groq_client import GroqClient
from src.llm.prompts import DELIVERY_SYSTEM_PROMPT
from src.schemas.handoff_models import DeliveryFacts, OrderCore
from src.tools import delivery_tools
from src.tracing.trace_logger import TraceLogger


def _classify(is_late_delivery: bool | None, any_seller_late: bool) -> str:
    if is_late_delivery is None:
        return "not_applicable"
    if not is_late_delivery:
        return "on_time"
    return "late_seller" if any_seller_late else "late_logistics"


class DeliveryAgent:
    name = "delivery_agent"

    def __init__(self, ds: DataStore, llm: GroqClient):
        self.ds = ds
        self.llm = llm

    def run(self, case_id: str, order: OrderCore, trace: TraceLogger) -> DeliveryFacts:
        items = self.ds.items_by_order.get(order.order_id, [])

        variance = delivery_tools.compute_delivery_variance_hours(
            order.order_delivered_customer_date, order.order_estimated_delivery_date
        )
        is_late = delivery_tools.compute_is_late_delivery(variance)
        seller_handoffs = delivery_tools.compute_seller_handoff(
            items, order.order_delivered_carrier_date
        )
        late_seller_ids = delivery_tools.late_handoff_seller_ids(seller_handoffs)
        any_seller_late = len(late_seller_ids) > 0

        deterministic_classification = _classify(is_late, any_seller_late)
        llm_result = self.llm.call_json(
            DELIVERY_SYSTEM_PROMPT,
            {
                "order_status": order.order_status,
                "is_delivered": order.order_delivered_customer_date is not None,
                "delivery_variance_hours": variance,
                "any_seller_late": any_seller_late,
                "late_seller_count": len(late_seller_ids),
            },
        )
        cross_checks = build_cross_checks(
            self.name, {"classification": deterministic_classification}, llm_result
        )

        trace.agent_run(
            case_id,
            self.name,
            inputs_summary={
                "order_id": order.order_id,
                "order_status": order.order_status,
                "item_count": len(items),
            },
            tool_calls=[
                {"name": "compute_delivery_variance_hours", "result": variance},
                {
                    "name": "compute_seller_handoff",
                    "result": {"seller_count": len(seller_handoffs), "late_seller_ids": late_seller_ids},
                },
            ],
            llm_call=llm_trace_summary(llm_result),
            output_summary={
                "delivery_variance_hours": variance,
                "is_late_delivery": is_late,
                "any_seller_late": any_seller_late,
                "classification": deterministic_classification,
            },
        )

        return DeliveryFacts(
            delivered_at=order.order_delivered_customer_date,
            estimated_delivery_at=order.order_estimated_delivery_date,
            carrier_handoff_at=order.order_delivered_carrier_date,
            delivery_variance_hours=variance,
            is_late_delivery=is_late,
            seller_handoff_analysis=seller_handoffs,
            late_handoff_seller_ids=late_seller_ids,
            any_seller_late=any_seller_late,
            llm_cross_checks=cross_checks,
        )
