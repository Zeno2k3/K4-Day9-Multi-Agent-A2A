"""Order & Product Agent.

Scoped data: the claimed order's own row, its items, and the products/
sellers/categories referenced by those items. No customer or payment
access — imports only src.tools.order_tools.
"""
from __future__ import annotations

from src.agents.common import build_cross_checks, llm_trace_summary
from src.data.loader import DataStore
from src.llm.groq_client import GroqClient
from src.llm.prompts import ORDER_PRODUCT_SYSTEM_PROMPT
from src.schemas.handoff_models import OrderProductFacts
from src.tools import order_tools
from src.tracing.trace_logger import TraceLogger


class OrderProductAgent:
    name = "order_product_agent"

    def __init__(self, ds: DataStore, llm: GroqClient):
        self.ds = ds
        self.llm = llm

    def run(self, case_id: str, order_id: str, trace: TraceLogger) -> OrderProductFacts | None:
        order_core = order_tools.fetch_order_core(self.ds, order_id)
        if order_core is None:
            trace.agent_run(case_id, self.name, error="order_not_found", order_id=order_id)
            return None

        items = order_tools.fetch_items(self.ds, order_id)
        item_ids = order_tools.build_item_ids(order_id, items)
        seller_ids = order_tools.build_seller_ids(items)
        product_ids = order_tools.build_product_ids(items)
        category_names = order_tools.build_category_names(self.ds, items)
        item_total = order_tools.compute_item_total_brl(items)
        freight_total = order_tools.compute_freight_total_brl(items)
        seller_count = order_tools.distinct_seller_count(items)
        category_count = order_tools.distinct_category_count(self.ds, items)

        deterministic = {
            "multi_item_order": len(items) >= 2,
            "multi_seller_order": seller_count >= 2,
            "multiple_categories": category_count >= 2,
        }

        llm_result = self.llm.call_json(
            ORDER_PRODUCT_SYSTEM_PROMPT,
            {
                "item_count": len(items),
                "distinct_seller_count": seller_count,
                "distinct_category_count": category_count,
            },
        )
        cross_checks = build_cross_checks(self.name, deterministic, llm_result)

        trace.agent_run(
            case_id,
            self.name,
            inputs_summary={"order_id": order_id, "item_count": len(items)},
            tool_calls=[
                {"name": "compute_item_total_brl", "result": item_total},
                {"name": "compute_freight_total_brl", "result": freight_total},
            ],
            llm_call=llm_trace_summary(llm_result),
            output_summary={
                "item_ids": item_ids,
                "seller_ids": seller_ids,
                "product_ids": product_ids,
                "category_names": category_names,
                "item_total_brl": item_total,
                "freight_total_brl": freight_total,
                **deterministic,
            },
        )

        return OrderProductFacts(
            order=order_core,
            item_count=len(items),
            item_ids=item_ids,
            seller_ids=seller_ids,
            product_ids=product_ids,
            category_names=category_names,
            item_total_brl=item_total,
            freight_total_brl=freight_total,
            multi_item_order=deterministic["multi_item_order"],
            multi_seller_order=deterministic["multi_seller_order"],
            multiple_categories=deterministic["multiple_categories"],
            llm_cross_checks=cross_checks,
        )
