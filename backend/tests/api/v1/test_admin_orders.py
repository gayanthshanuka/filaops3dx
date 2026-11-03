"""
Tests for admin orders CSV import endpoints.

Endpoints under test:
    GET  /api/v1/admin/orders/import/template
    POST /api/v1/admin/orders/import
"""
import csv
import hashlib
import io
from decimal import Decimal

import pytest

from app.models.sales_order import SalesOrder

BASE_URL = "/api/v1/admin/orders"


# =============================================================================
# Helper
# =============================================================================

def _csv_upload(client, csv_text: str, *, filename: str = "orders.csv",
                content_type: str = "text/csv", add_phone: bool = True, **query_params):
    """POST CSV, supplying stable telephone fixtures unless deliberately omitted."""
    if add_phone:
        reader = csv.DictReader(io.StringIO(csv_text))
        headers = reader.fieldnames or []
        if headers and not any("phone" in header.lower() for header in headers):
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=[*headers, "Customer Phone"])
            writer.writeheader()
            for row in reader:
                email = next((value for key, value in row.items() if "email" in key.lower() and value), "")
                identity = email.lower() or str(row)
                row["Customer Phone"] = "0" + str(int(hashlib.sha256(identity.encode()).hexdigest(), 16))[:11]
                writer.writerow(row)
            csv_text = output.getvalue()
    params = {k: str(v) for k, v in query_params.items()}
    return client.post(
        f"{BASE_URL}/import",
        files={"file": (filename, io.BytesIO(csv_text.encode()), content_type)},
        params=params,
    )


# =============================================================================
# Authentication
# =============================================================================

class TestAdminOrdersAuth:
    """Authentication requirements for admin order endpoints."""

    def test_template_accessible_without_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/import/template")
        assert response.status_code == 200

    def test_import_returns_401_without_auth(self, unauthed_client):
        csv_text = "Customer Email,Product SKU,Quantity\nfoo@bar.com,SKU-1,1\n"
        response = _csv_upload(unauthed_client, csv_text)
        assert response.status_code == 401


# =============================================================================
# GET /import/template
# =============================================================================

class TestOrderImportTemplate:
    """Download CSV template for order import."""

    def test_returns_200(self, client):
        response = client.get(f"{BASE_URL}/import/template")
        assert response.status_code == 200

    def test_content_type_is_csv(self, client):
        response = client.get(f"{BASE_URL}/import/template")
        assert "text/csv" in response.headers.get("content-type", "")

    def test_content_disposition_header(self, client):
        response = client.get(f"{BASE_URL}/import/template")
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "order_import_template.csv" in disposition

    def test_template_contains_expected_headers(self, client):
        response = client.get(f"{BASE_URL}/import/template")
        content = response.text
        expected_headers = [
            "Order ID", "Order Date", "Customer Phone", "Customer Email", "Customer Name",
            "Product SKU", "Quantity", "Unit Price", "Shipping Cost",
            "Tax Amount", "Shipping Address Line 1", "Shipping City",
            "Shipping State", "Shipping Zip", "Shipping Country",
            "Customer Notes",
        ]
        for header in expected_headers:
            assert header in content, f"Missing template header: {header}"

    def test_template_includes_example_rows(self, client):
        response = client.get(f"{BASE_URL}/import/template")
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert rows[0]["Order ID"] == "ORD-001"
        assert rows[0]["Customer Phone"] == "+94771234567"
        assert rows[0]["Customer Email"] == ""
        assert rows[1]["Customer Phone"] == "+94712345678"
        assert rows[1]["Customer Email"] == "jane@example.com"


# =============================================================================
# POST /import  --  valid imports
# =============================================================================

class TestOrderImportValid:
    """Successful CSV import scenarios."""

    def test_single_row_import(self, client, db, make_product):
        product = make_product(sku="CSV-VALID-001", selling_price=Decimal("19.99"))
        db.flush()

        csv_text = (
            "Customer Email,Customer Name,Product SKU,Quantity,Unit Price\n"
            f"csv-valid@example.com,Jane Doe,{product.sku},3,19.99\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 1
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"
        assert data["skipped"] == 0

    def test_multi_row_import_different_orders(self, client, db, make_product):
        p1 = make_product(sku="CSV-MULTI-001", selling_price=Decimal("10.00"))
        p2 = make_product(sku="CSV-MULTI-002", selling_price=Decimal("20.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Customer Name,Product SKU,Quantity,Unit Price\n"
            f"ORD-A,multi-a@example.com,Alice,{p1.sku},1,10.00\n"
            f"ORD-B,multi-b@example.com,Bob,{p2.sku},2,20.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 2
        assert data["created"] == 2, f"Errors: {data.get('errors', [])}"

    def test_multi_line_order_grouped_by_order_id(self, client, db, make_product):
        """Multiple rows with the same Order ID become one SalesOrder."""
        p1 = make_product(sku="CSV-GRP-001", selling_price=Decimal("5.00"))
        p2 = make_product(sku="CSV-GRP-002", selling_price=Decimal("15.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Customer Name,Product SKU,Quantity,Unit Price\n"
            f"ORD-GROUPED,grp@example.com,Group User,{p1.sku},2,5.00\n"
            f"ORD-GROUPED,grp@example.com,Group User,{p2.sku},1,15.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 2
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"  # grouped into one order

    def test_import_uses_product_price_when_unit_price_absent(self, client, db, make_product):
        product = make_product(sku="CSV-NOPRICE-001", selling_price=Decimal("42.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity\n"
            f"ORD-NOPRICE,noprice@example.com,{product.sku},1\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"

    def test_import_with_shipping_and_tax(self, client, db, make_product):
        product = make_product(sku="CSV-SHIP-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity,Unit Price,Shipping Cost,Tax Amount\n"
            f"ORD-SHIP,ship@example.com,{product.sku},2,10.00,5.50,1.25\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"

    def test_import_with_currency_symbols_in_price(self, client, db, make_product):
        product = make_product(sku="CSV-DOLLAR-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity,Unit Price\n"
            f"ORD-DOLLAR,dollar@example.com,{product.sku},1,$250.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"

    def test_import_case_insensitive_sku_lookup(self, client, db, make_product):
        make_product(sku="CSV-CASE-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity,Unit Price\n"
            "ORD-CASE,case@example.com,csv-case-001,1,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"

    def test_import_with_shipping_address_fields(self, client, db, make_product):
        product = make_product(sku="CSV-ADDR-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Customer Name,Product SKU,Quantity,Unit Price,"
            "Shipping Address Line 1,Shipping City,Shipping State,Shipping Zip,Shipping Country\n"
            f"ORD-ADDR,addr@example.com,Addr User,{product.sku},1,10.00,"
            "123 Main St,Springfield,IL,62701,USA\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"

    def test_import_source_query_param(self, client, db, make_product):
        product = make_product(sku="CSV-SRC-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity,Unit Price\n"
            f"ORD-SRC-001,src@example.com,{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text, source="squarespace")

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"


# =============================================================================
# POST /import  --  invalid data / error handling
# =============================================================================

class TestOrderImportErrors:
    """Error handling and edge cases."""

    def test_non_csv_file_rejected(self, client):
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("orders.txt", io.BytesIO(b"not csv"), "text/plain")},
        )
        assert response.status_code == 400

    def test_non_csv_extension_rejected(self, client):
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("data.xlsx", io.BytesIO(b"binary"), "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_empty_csv_returns_zero_counts(self, client):
        csv_text = "Customer Email,Product SKU,Quantity,Unit Price\n"
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 0
        assert data["created"] == 0
        assert data["skipped"] == 0

    def test_missing_sku_skips_row_with_error(self, client):
        csv_text = (
            "Customer Email,Product SKU,Quantity,Unit Price\n"
            "nosku@example.com,,5,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 1
        assert data["created"] == 0
        assert len(data["errors"]) >= 1

    def test_unknown_sku_reports_error(self, client):
        csv_text = (
            "Customer Email,Product SKU,Quantity,Unit Price\n"
            "unknownsku@example.com,DOES-NOT-EXIST-999,1,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        errors_text = str(data["errors"])
        assert "DOES-NOT-EXIST-999" in errors_text

    def test_inactive_product_reports_error(self, client, db, make_product):
        product = make_product(sku="CSV-INACTIVE-001", selling_price=Decimal("10.00"), active=False)
        db.flush()

        csv_text = (
            "Customer Email,Product SKU,Quantity,Unit Price\n"
            f"inactive@example.com,{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        errors_text = str(data["errors"])
        assert "inactive" in errors_text.lower()

    def test_telephone_only_customer_has_no_placeholder_email(self, client, db, make_product):
        """A telephone customer can place an imported order without an email."""
        from app.models.user import User

        product = make_product(sku="CSV-NOEMAIL-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Phone,Product SKU,Quantity,Unit Price\n"
            f"ORD-NOEMAIL,+94771234567,{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"
        order = db.query(SalesOrder).filter(SalesOrder.source_order_id == "ORD-NOEMAIL").one()
        customer = db.get(User, order.user_id)
        assert customer.email is None
        assert customer.phone == "+94771234567"

    def test_new_customer_without_telephone_is_skipped(self, client, db, make_product):
        product = make_product(sku="CSV-NOPHONE-001", selling_price=Decimal("10.00"))
        db.flush()
        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity,Unit Price\n"
            f"ORD-NOPHONE,no-phone@example.com,{product.sku},1,10.00\n"
        )

        response = _csv_upload(client, csv_text, add_phone=False)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        assert data["skipped"] == 1
        assert "Telephone number is required" in data["errors"][0]["error"]

    def test_missing_email_skipped_when_create_customers_false(self, client, db, make_product):
        product = make_product(sku="CSV-NOEML2-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Customer Email,Product SKU,Quantity,Unit Price\n"
            f",{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text, create_customers="false")

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        assert data["skipped"] >= 1

    def test_product_with_zero_price_and_no_csv_price_reports_error(self, client, db, make_product):
        product = make_product(sku="CSV-ZPRICE-001", selling_price=Decimal("0.00"))
        db.flush()

        csv_text = (
            "Customer Email,Product SKU,Quantity\n"
            f"zprice@example.com,{product.sku},1\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        errors_text = str(data["errors"])
        assert "no price" in errors_text.lower() or "no valid products" in errors_text.lower()


# =============================================================================
# POST /import  --  duplicate detection
# =============================================================================

class TestOrderImportDuplicates:
    """Duplicate order_id detection via source_order_id."""

    def test_duplicate_order_id_skipped(self, client, db, make_product):
        product = make_product(sku="CSV-DUP-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity,Unit Price\n"
            f"ORD-DUP-TEST,dup@example.com,{product.sku},1,10.00\n"
        )

        # First import should succeed
        resp1 = _csv_upload(client, csv_text)
        assert resp1.status_code == 200
        assert resp1.json()["created"] == 1, f"Errors: {resp1.json().get('errors', [])}"

        # Second import with the same Order ID should skip
        resp2 = _csv_upload(client, csv_text)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["created"] == 0
        assert data2["skipped"] == 1
        errors_text = str(data2["errors"])
        assert "already exists" in errors_text.lower()


# =============================================================================
# POST /import  --  customer creation
# =============================================================================

class TestOrderImportCustomerCreation:
    """Customer find-or-create behaviour."""

    def test_existing_customer_reused(self, client, db, make_product):
        """When the customer email already exists, no duplicate is created."""
        from app.models.user import User

        product = make_product(sku="CSV-REUSE-001", selling_price=Decimal("10.00"))
        db.flush()

        email = "reuse-customer@example.com"
        csv_text = (
            "Order ID,Customer Email,Customer Name,Product SKU,Quantity,Unit Price\n"
            f"ORD-REUSE-1,{email},Reuse User,{product.sku},1,10.00\n"
        )

        # First import creates the customer
        resp1 = _csv_upload(client, csv_text)
        assert resp1.status_code == 200
        assert resp1.json()["created"] == 1, f"Errors: {resp1.json().get('errors', [])}"

        count_before = db.query(User).filter(User.email.ilike(email)).count()

        # Second import with a different order ID but same email
        csv_text2 = (
            "Order ID,Customer Email,Customer Name,Product SKU,Quantity,Unit Price\n"
            f"ORD-REUSE-2,{email},Reuse User,{product.sku},1,10.00\n"
        )
        resp2 = _csv_upload(client, csv_text2)
        assert resp2.status_code == 200
        assert resp2.json()["created"] == 1, f"Errors: {resp2.json().get('errors', [])}"

        count_after = db.query(User).filter(User.email.ilike(email)).count()
        assert count_after == count_before  # no duplicate customer

    def test_create_customers_false_skips_unknown_email(self, client, db, make_product):
        product = make_product(sku="CSV-NOCREATE-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Customer Email,Product SKU,Quantity,Unit Price\n"
            f"ORD-NOCREATE,brand-new@example.com,{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text, create_customers="false")

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 0
        assert data["skipped"] >= 1


# =============================================================================
# POST /import  --  column name variations
# =============================================================================

class TestOrderImportColumnVariations:
    """The endpoint accepts several column name aliases."""

    def test_alternative_column_names(self, client, db, make_product):
        product = make_product(sku="CSV-ALT-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "order_id,email,sku,qty,price\n"
            f"ORD-ALT-001,alt@example.com,{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, data

    def test_standard_aliases_email_and_sku(self, client, db, make_product):
        """'Email' and 'SKU' are valid column aliases."""
        product = make_product(sku="CSV-ALIAS-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "Order ID,Email,SKU,Quantity,Price\n"
            f"ORD-ALIAS,alias@example.com,{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"


# =============================================================================
# POST /import  --  BOM-encoded CSV
# =============================================================================

class TestOrderImportEncoding:
    """UTF-8 BOM and Latin-1 encoding handling."""

    def test_utf8_bom_handled(self, client, db, make_product):
        product = make_product(sku="CSV-BOM-001", selling_price=Decimal("10.00"))
        db.flush()

        csv_text = (
            "\ufeffOrder ID,Customer Email,Product SKU,Quantity,Unit Price\n"
            f"ORD-BOM,bom@example.com,{product.sku},1,10.00\n"
        )
        response = _csv_upload(client, csv_text)

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1, f"Errors: {data.get('errors', [])}"
