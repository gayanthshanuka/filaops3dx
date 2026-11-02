"""Order imports must reuse telephone customers without inventing email addresses."""
import uuid

import pytest

from app.models.sales_order import SalesOrder
from app.models.user import User
from app.services.order_import_service import find_or_create_customer, import_orders_from_csv


def _phone():
    return "0" + str(uuid.uuid4().int)[:9]


def test_order_customer_created_with_phone_and_no_email(db):
    phone = _phone()
    customer = find_or_create_customer(db, None, "Phone Customer", {"phone": phone})

    assert customer.email is None
    assert customer.phone == phone
    assert customer.customer_number.startswith("CUST-")


def test_order_customer_reuses_formatted_phone_only_record(db):
    phone = _phone()
    customer = find_or_create_customer(db, None, shipping_address={"phone": phone})
    formatted = phone[:3] + "-" + phone[3:]

    found = find_or_create_customer(db, None, shipping_address={"phone": formatted}, create=False)

    assert found.id == customer.id


def test_order_customer_rejects_email_only_creation_but_allows_legacy_lookup(db):
    email = f"legacy-{uuid.uuid4().hex}@example.com"
    with pytest.raises(ValueError, match="Telephone number is required"):
        find_or_create_customer(db, email)

    legacy = User(email=email, password_hash="unused", account_type="customer")
    db.add(legacy)
    db.flush()
    assert find_or_create_customer(db, email).id == legacy.id


def test_order_csv_telephone_only_customer_reused_without_creation(db, make_product):
    phone = _phone()
    customer = find_or_create_customer(db, None, shipping_address={"phone": phone})
    sku = "PHONE-" + uuid.uuid4().hex[:8]
    source_id = "PHONE-ORDER-" + uuid.uuid4().hex[:8]
    make_product(sku=sku, name="Phone order item")
    text = f"Order ID,Telephone,SKU,Quantity,Unit Price\n{source_id},{phone},{sku},1,10.00\n"

    result = import_orders_from_csv(db, text, create_customers=False, current_user_id=1)

    assert result["created"] == 1, result
    order = db.query(SalesOrder).filter(SalesOrder.source_order_id == source_id).one()
    assert order.user_id == customer.id
    assert customer.email is None


def test_order_csv_missing_phone_reports_clear_error(db, make_product):
    sku = "PHONE-" + uuid.uuid4().hex[:8]
    source_id = "PHONE-ORDER-" + uuid.uuid4().hex[:8]
    make_product(sku=sku, name="Missing telephone item")
    email = f"missing-{uuid.uuid4().hex}@example.com"
    text = f"Order ID,Email,SKU,Quantity,Unit Price\n{source_id},{email},{sku},1,10.00\n"

    result = import_orders_from_csv(db, text, current_user_id=1)

    assert result["created"] == 0
    assert "Telephone number is required" in result["errors"][0]["error"]
