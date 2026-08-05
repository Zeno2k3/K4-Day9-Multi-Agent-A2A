"""Pydantic models for input/EC_0NN.json (README §3)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerRequest(StrictModel):
    language: str
    message: str
    claimed_order_id: str


class InvestigationScope(StrictModel):
    include_customer_history: bool = True
    include_product_context: bool = True


class InputCase(StrictModel):
    case_id: str
    customer_request: CustomerRequest
    investigation_scope: InvestigationScope
    policy_version: str
