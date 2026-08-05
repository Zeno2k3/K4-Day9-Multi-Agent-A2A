"""Loads and indexes the Olist CSVs exactly once per process.

olist_order_reviews_dataset.csv and olist_geolocation_dataset.csv are
intentionally NOT loaded: no formula in README §4/§6 references them, and
geolocation alone is a 1M-row file that would cost real load time for zero
benefit to any graded field. Documented decision, see architecture.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.schemas.records import (
    CustomerRecord,
    ItemRecord,
    OrderRecord,
    PaymentRecord,
    ProductRecord,
    SellerRecord,
)


def _blank_to_none(value: str) -> str | None:
    return value if value != "" else None


def _to_float(value: str) -> float:
    return float(value) if value else 0.0


def _to_int(value: str) -> int:
    return int(value) if value else 0


@dataclass(frozen=True)
class DataStore:
    orders: dict[str, OrderRecord]
    items_by_order: dict[str, list[ItemRecord]]
    payments_by_order: dict[str, list[PaymentRecord]]
    customers_by_id: dict[str, CustomerRecord]
    orders_by_unique_id: dict[str, list[tuple[str, str]]]  # unique_id -> [(order_id, purchase_ts)]
    products_by_id: dict[str, ProductRecord]
    sellers_by_id: dict[str, SellerRecord]
    category_translation: dict[str, str]

    def order_exists(self, order_id: str) -> bool:
        return order_id in self.orders

    def item_exists(self, order_id: str, order_item_id: str) -> bool:
        return any(
            i.order_item_id == str(order_item_id) for i in self.items_by_order.get(order_id, [])
        )

    def payment_exists(self, order_id: str, payment_sequential: str) -> bool:
        return any(
            p.payment_sequential == str(payment_sequential)
            for p in self.payments_by_order.get(order_id, [])
        )

    def seller_exists(self, seller_id: str) -> bool:
        return seller_id in self.sellers_by_id

    def translate_category(self, pt_name: str | None) -> str | None:
        if not pt_name:
            return None
        return self.category_translation.get(pt_name, pt_name)


def load_data_store(data_dir: Path) -> DataStore:
    orders_df = pd.read_csv(data_dir / "olist_orders_dataset.csv", dtype=str, keep_default_na=False)
    items_df = pd.read_csv(
        data_dir / "olist_order_items_dataset.csv", dtype=str, keep_default_na=False
    )
    payments_df = pd.read_csv(
        data_dir / "olist_order_payments_dataset.csv", dtype=str, keep_default_na=False
    )
    customers_df = pd.read_csv(
        data_dir / "olist_customers_dataset.csv", dtype=str, keep_default_na=False
    )
    products_df = pd.read_csv(
        data_dir / "olist_products_dataset.csv", dtype=str, keep_default_na=False
    )
    sellers_df = pd.read_csv(data_dir / "olist_sellers_dataset.csv", dtype=str, keep_default_na=False)
    category_df = pd.read_csv(
        data_dir / "product_category_name_translation.csv",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    orders: dict[str, OrderRecord] = {}
    for row in orders_df.itertuples(index=False):
        orders[row.order_id] = OrderRecord(
            order_id=row.order_id,
            customer_id=row.customer_id,
            order_status=row.order_status,
            order_purchase_timestamp=_blank_to_none(row.order_purchase_timestamp),
            order_approved_at=_blank_to_none(row.order_approved_at),
            order_delivered_carrier_date=_blank_to_none(row.order_delivered_carrier_date),
            order_delivered_customer_date=_blank_to_none(row.order_delivered_customer_date),
            order_estimated_delivery_date=_blank_to_none(row.order_estimated_delivery_date),
        )

    items_by_order: dict[str, list[ItemRecord]] = {}
    for row in items_df.itertuples(index=False):
        rec = ItemRecord(
            order_id=row.order_id,
            order_item_id=row.order_item_id,
            product_id=row.product_id,
            seller_id=row.seller_id,
            shipping_limit_date=_blank_to_none(row.shipping_limit_date),
            price=_to_float(row.price),
            freight_value=_to_float(row.freight_value),
        )
        items_by_order.setdefault(rec.order_id, []).append(rec)
    for order_id, item_list in items_by_order.items():
        item_list.sort(key=lambda i: _to_int(i.order_item_id))

    payments_by_order: dict[str, list[PaymentRecord]] = {}
    for row in payments_df.itertuples(index=False):
        rec = PaymentRecord(
            order_id=row.order_id,
            payment_sequential=row.payment_sequential,
            payment_type=row.payment_type,
            payment_installments=_to_int(row.payment_installments),
            payment_value=_to_float(row.payment_value),
        )
        payments_by_order.setdefault(rec.order_id, []).append(rec)
    for order_id, payment_list in payments_by_order.items():
        payment_list.sort(key=lambda p: _to_int(p.payment_sequential))

    customers_by_id: dict[str, CustomerRecord] = {}
    for row in customers_df.itertuples(index=False):
        customers_by_id[row.customer_id] = CustomerRecord(
            customer_id=row.customer_id,
            customer_unique_id=row.customer_unique_id,
            customer_zip_code_prefix=row.customer_zip_code_prefix,
            customer_city=row.customer_city,
            customer_state=row.customer_state,
        )

    products_by_id: dict[str, ProductRecord] = {}
    for row in products_df.itertuples(index=False):
        products_by_id[row.product_id] = ProductRecord(
            product_id=row.product_id,
            product_category_name=_blank_to_none(row.product_category_name),
        )

    sellers_by_id: dict[str, SellerRecord] = {}
    for row in sellers_df.itertuples(index=False):
        sellers_by_id[row.seller_id] = SellerRecord(
            seller_id=row.seller_id,
            seller_zip_code_prefix=row.seller_zip_code_prefix,
            seller_city=row.seller_city,
            seller_state=row.seller_state,
        )

    category_translation: dict[str, str] = {}
    for row in category_df.itertuples(index=False):
        category_translation[row.product_category_name] = row.product_category_name_english

    orders_by_unique_id: dict[str, list[tuple[str, str]]] = {}
    for order_id, order in orders.items():
        customer = customers_by_id.get(order.customer_id)
        if customer is None:
            continue
        orders_by_unique_id.setdefault(customer.customer_unique_id, []).append(
            (order_id, order.order_purchase_timestamp or "")
        )

    return DataStore(
        orders=orders,
        items_by_order=items_by_order,
        payments_by_order=payments_by_order,
        customers_by_id=customers_by_id,
        orders_by_unique_id=orders_by_unique_id,
        products_by_id=products_by_id,
        sellers_by_id=sellers_by_id,
        category_translation=category_translation,
    )
