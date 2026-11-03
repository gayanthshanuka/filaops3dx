"""Phone-first CRM customer creation, uniqueness, and legacy compatibility."""
import io
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user import User

BASE_URL = "/api/v1/admin/customers"


def _phone():
    return f"07{uuid.uuid4().int % 1000000000000:012d}"


def _create(client, **fields):
    response = client.post(BASE_URL, json={"phone": _phone(), **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_two_customers_can_be_created_without_email(client):
    first = _create(client, phone="077 123 4567")
    second = _create(client, phone="+94 (71) 234-5678")
    assert first["email"] is None
    assert second["email"] is None
    assert first["phone"] == "0771234567"
    assert second["phone"] == "+94712345678"
    assert first["id"] != second["id"]


@pytest.mark.parametrize("phone", [None, "", "   ", "123", "1234567890123456", "CALL-ME", "０７７１２３４５６７"])
def test_invalid_phone_is_rejected(client, phone):
    response = client.post(BASE_URL, json={"phone": phone})
    assert response.status_code == 422


def test_omitting_phone_is_rejected_even_when_email_present(client):
    response = client.post(BASE_URL, json={"email": "needs-phone@example.com"})
    assert response.status_code == 422


def test_empty_optional_email_is_stored_as_null(client):
    customer = _create(client, email="   ")
    assert customer["email"] is None


def test_formatted_duplicate_phone_is_rejected(client):
    _create(client, phone="+94 (77) 123-4567")
    response = client.post(BASE_URL, json={"phone": "94771234567"})
    assert response.status_code == 400
    assert "phone" in response.json()["detail"].lower() or "telephone" in response.json()["detail"].lower()


def test_phone_change_cannot_reuse_another_customers_number(client):
    first = _create(client)
    second = _create(client)
    response = client.patch(f"{BASE_URL}/{second['id']}", json={"phone": first["phone"]})
    assert response.status_code == 400
    unchanged = client.get(f"{BASE_URL}/{second['id']}")
    assert unchanged.json()["phone"] == second["phone"]


@pytest.mark.parametrize("phone", [None, "", "  "])
def test_explicitly_clearing_phone_is_rejected(client, phone):
    customer = _create(client)
    response = client.patch(f"{BASE_URL}/{customer['id']}", json={"phone": phone})
    assert response.status_code == 422


def test_email_can_be_cleared_without_changing_phone(client):
    customer = _create(client, email=f"optional-{uuid.uuid4().hex[:8]}@example.com")
    response = client.patch(f"{BASE_URL}/{customer['id']}", json={"email": None})
    assert response.status_code == 200, response.text
    assert response.json()["email"] is None
    assert response.json()["phone"] == customer["phone"]


def test_phone_search_returns_phone_only_customer(client):
    customer = _create(client, phone="+94 (77) 123-4567")
    search = client.get(f"{BASE_URL}/search", params={"q": "77 123-4567"})
    assert search.status_code == 200, search.text
    assert customer["id"] in [row["id"] for row in search.json()]
    assert next(row for row in search.json() if row["id"] == customer["id"])["phone"] == "+94771234567"
    listing = client.get(BASE_URL, params={"search": "77 123-4567"})
    assert listing.status_code == 200, listing.text
    assert customer["id"] in [row["id"] for row in listing.json()]


def test_legacy_email_only_customer_can_still_be_read_and_edited(client, db):
    legacy = User(email=f"legacy-{uuid.uuid4().hex[:8]}@example.com", password_hash="unused", account_type="customer", status="active", phone=None)
    db.add(legacy)
    db.commit()
    response = client.get(f"{BASE_URL}/{legacy.id}")
    assert response.status_code == 200, response.text
    assert response.json()["phone"] is None
    changed = client.patch(f"{BASE_URL}/{legacy.id}", json={"company_name": "Legacy company"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["company_name"] == "Legacy company"
    assert changed.json()["phone"] is None


def test_staff_accounts_still_require_email(db):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(User(email=None, password_hash="unused", account_type="admin", status="active"))
            db.flush()


def test_legacy_customer_cannot_lose_their_only_contact(client, db):
    legacy = User(email=f"legacy-{uuid.uuid4().hex[:8]}@example.com", password_hash="unused", account_type="customer", status="active")
    db.add(legacy)
    db.flush()
    response = client.patch(f"{BASE_URL}/{legacy.id}", json={"email": None})
    assert response.status_code == 400
    assert "telephone" in response.json()["detail"].lower()


@pytest.mark.parametrize("path", ["/api/v1/auth/register", "/api/v1/auth/portal/register"])
def test_registration_duplicate_crm_phone_returns_conflict(client, unauthed_client, monkeypatch, path):
    from app.core.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    phone = _phone()
    _create(client, phone=phone)
    response = unauthed_client.post(path, json={
        "email": f"register-{uuid.uuid4().hex[:8]}@example.com",
        "password": "ValidPassword123!",
        "phone": phone[:3] + " " + phone[3:],
    })
    assert response.status_code == 400
    assert "telephone" in response.json()["detail"].lower()


def test_phone_only_csv_preview_and_import_are_consistent(client):
    phone = _phone()
    contents = f"phone,first_name\n{phone},Telephone customer\n".encode()
    preview = client.post(f"{BASE_URL}/import/preview", files={"file": ("customers.csv", io.BytesIO(contents), "text/csv")})
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 1
    imported = client.post(f"{BASE_URL}/import", files={"file": ("customers.csv", io.BytesIO(contents), "text/csv")})
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1
    duplicate = client.post(f"{BASE_URL}/import/preview", files={"file": ("customers.csv", io.BytesIO(contents), "text/csv")})
    assert duplicate.json()["error_rows"] == 1


def test_phone_uniqueness_is_enforced_by_database(db):
    first = User(email=None, phone="+94 (77) 123-4567", password_hash="unused", account_type="customer", status="active")
    db.add(first)
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(User(email=None, phone="94771234567", password_hash="unused", account_type="customer", status="active"))
            db.flush()


def test_staff_phone_does_not_block_customer_creation(client, db):
    phone = _phone()
    db.add(User(email=f"staff-{uuid.uuid4().hex[:8]}@example.com", phone=phone, password_hash="unused", account_type="operator", status="active"))
    db.commit()
    customer = _create(client, phone=phone)
    assert customer["phone"] == phone


def test_csv_detects_duplicate_phone_with_different_presentation(client):
    contents = b"phone,first_name\n+94 (77) 123-4567,First\n94771234567,Second\n"
    preview = client.post(f"{BASE_URL}/import/preview", files={"file": ("customers.csv", io.BytesIO(contents), "text/csv")})
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 1
    assert preview.json()["error_rows"] == 1
    imported = client.post(f"{BASE_URL}/import", files={"file": ("customers.csv", io.BytesIO(contents), "text/csv")})
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1
    assert imported.json()["skipped"] == 1
