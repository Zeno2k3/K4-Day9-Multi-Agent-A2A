"""Lightweight raw-row records for the Olist CSVs.

Plain dataclasses (not pydantic) since these are constructed ~100k times at
load time and are internal-only — validation happens at the handoff/output
boundary, not here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderRecord:
    order_id: str
    customer_id: str
    order_status: str
    order_purchase_timestamp: str | None
    order_approved_at: str | None
    order_delivered_carrier_date: str | None
    order_delivered_customer_date: str | None
    order_estimated_delivery_date: str | None


@dataclass(frozen=True, slots=True)
class ItemRecord:
    order_id: str
    order_item_id: str
    product_id: str
    seller_id: str
    shipping_limit_date: str | None
    price: float
    freight_value: float


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    order_id: str
    payment_sequential: str
    payment_type: str
    payment_installments: int
    payment_value: float


@dataclass(frozen=True, slots=True)
class CustomerRecord:
    customer_id: str
    customer_unique_id: str
    customer_zip_code_prefix: str
    customer_city: str
    customer_state: str


@dataclass(frozen=True, slots=True)
class ProductRecord:
    product_id: str
    product_category_name: str | None


@dataclass(frozen=True, slots=True)
class SellerRecord:
    seller_id: str
    seller_zip_code_prefix: str
    seller_city: str
    seller_state: str
