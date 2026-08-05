"""Customer Agent.

Scoped data: customers.csv + the orders->customer_unique_id index only.
No items/payments/products access — imports only src.tools.customer_tools.
"""
from __future__ import annotations

from src.agents.common import build_cross_checks, llm_trace_summary
from src.data.loader import DataStore
from src.llm.groq_client import GroqClient
from src.llm.prompts import CUSTOMER_SYSTEM_PROMPT
from src.schemas.handoff_models import CustomerFacts
from src.tools import customer_tools
from src.tracing.trace_logger import TraceLogger


class CustomerAgent:
    name = "customer_agent"

    def __init__(self, ds: DataStore, llm: GroqClient):
        self.ds = ds
        self.llm = llm

    def run(
        self,
        case_id: str,
        customer_id: str,
        claimed_order_id: str,
        include_customer_history: bool,
        trace: TraceLogger,
    ) -> CustomerFacts:
        customer_unique_id = customer_tools.resolve_customer_unique_id(self.ds, customer_id)
        if customer_unique_id is None:
            customer_unique_id = ""

        related_order_ids: list[str] = []
        if include_customer_history and customer_unique_id:
            related_order_ids = customer_tools.fetch_related_order_ids(
                self.ds, customer_unique_id, claimed_order_id
            )
        repeat_customer = customer_tools.is_repeat_customer(related_order_ids)

        deterministic = {"repeat_customer": repeat_customer}
        llm_result = self.llm.call_json(
            CUSTOMER_SYSTEM_PROMPT, {"related_order_count": len(related_order_ids)}
        )
        cross_checks = build_cross_checks(self.name, deterministic, llm_result)

        trace.agent_run(
            case_id,
            self.name,
            inputs_summary={
                "customer_id": customer_id,
                "include_customer_history": include_customer_history,
            },
            tool_calls=[
                {"name": "resolve_customer_unique_id", "result": customer_unique_id},
                {"name": "fetch_related_order_ids", "result_count": len(related_order_ids)},
            ],
            llm_call=llm_trace_summary(llm_result),
            output_summary={
                "customer_unique_id": customer_unique_id,
                "related_order_ids": related_order_ids,
                **deterministic,
            },
        )

        return CustomerFacts(
            customer_unique_id=customer_unique_id,
            related_order_ids=related_order_ids,
            repeat_customer=repeat_customer,
            llm_cross_checks=cross_checks,
        )
