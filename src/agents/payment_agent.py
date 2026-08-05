"""Payment Agent.

Scoped data: order_payments.csv rows for the claimed order only, plus the
item_total_brl/freight_total_brl numbers handed off by the Coordinator from
the Order & Product Agent's step (this agent never re-derives items itself
and never touches order_items.csv directly) — imports only
src.tools.payment_tools.
"""
from __future__ import annotations

from src.agents.common import build_cross_checks, llm_trace_summary
from src.data.loader import DataStore
from src.llm.groq_client import GroqClient
from src.llm.prompts import PAYMENT_SYSTEM_PROMPT
from src.schemas.handoff_models import PaymentFacts
from src.tools import payment_tools
from src.tracing.trace_logger import TraceLogger


class PaymentAgent:
    name = "payment_agent"

    def __init__(self, ds: DataStore, llm: GroqClient):
        self.ds = ds
        self.llm = llm

    def run(
        self,
        case_id: str,
        order_id: str,
        item_total_brl: float,
        freight_total_brl: float,
        has_items: bool,
        trace: TraceLogger,
    ) -> PaymentFacts:
        payments = self.ds.payments_by_order.get(order_id, [])
        payment_ids = payment_tools.build_payment_ids(order_id, payments)
        payment_types = payment_tools.build_payment_types(payments)
        payment_total = payment_tools.compute_payment_total_brl(payments)
        expected_total, difference, reconciled = payment_tools.compute_reconciliation(
            item_total_brl, freight_total_brl, payment_total, has_items
        )

        deterministic = {
            "split_payment": len(payments) >= 2,
            "valid_split_payment_candidate": len(payments) >= 2 and reconciled is True,
        }
        llm_result = self.llm.call_json(
            PAYMENT_SYSTEM_PROMPT,
            {"payment_row_count": len(payments), "reconciled": reconciled},
        )
        cross_checks = build_cross_checks(self.name, deterministic, llm_result)

        trace.agent_run(
            case_id,
            self.name,
            inputs_summary={"order_id": order_id, "payment_row_count": len(payments)},
            tool_calls=[
                {"name": "compute_payment_total_brl", "result": payment_total},
                {
                    "name": "compute_reconciliation",
                    "result": {
                        "expected_total_brl": expected_total,
                        "difference_brl": difference,
                        "reconciled": reconciled,
                    },
                },
            ],
            llm_call=llm_trace_summary(llm_result),
            output_summary={"payment_ids": payment_ids, "payment_types": payment_types, **deterministic},
        )

        return PaymentFacts(
            payment_ids=payment_ids,
            payment_types=payment_types,
            item_total_brl=item_total_brl,
            freight_total_brl=freight_total_brl,
            expected_total_brl=expected_total,
            payment_total_brl=payment_total,
            difference_brl=difference,
            reconciled=reconciled,
            payment_count=len(payments),
            split_payment=deterministic["split_payment"],
            llm_cross_checks=cross_checks,
        )
