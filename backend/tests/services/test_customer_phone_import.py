"""Phone-first customer import validation and persistence regressions."""
import uuid

from app.models.user import User
from app.services.customer_import_service import (
    import_customers,
    preview_customer_import,
)


def _phone():
    return "0" + str(uuid.uuid4().int)[:9]


def test_phone_only_preview_normalizes_international_number(db):
    phone = "+94 " + str(uuid.uuid4().int)[:9]
    result = preview_customer_import(db, f"telephone,first_name\n{phone},Sam\n")

    assert result["valid_rows"] == 1
    assert result["rows"][0]["data"]["email"] is None
    assert result["rows"][0]["data"]["phone"] == phone.replace(" ", "")


def test_preview_requires_phone_even_with_email(db):
    result = preview_customer_import(db, "email,first_name\nsam@example.com,Sam\n")

    assert result["valid_rows"] == 0
    assert "phone" in result["rows"][0]["errors"][0].lower()


def test_preview_rejects_formatted_duplicate_phones_in_csv(db):
    phone = _phone()
    formatted = phone[:3] + "-" + phone[3:]
    result = preview_customer_import(db, f"phone\n{phone}\n{formatted}\n")

    assert result["valid_rows"] == 1
    assert result["rows"][1]["errors"] == ["Duplicate phone number in CSV"]


def test_import_phone_only_rows_and_preview_agree(db):
    phone = _phone()
    other_phone = _phone()
    text = f"phone,first_name\n{phone},First\n{phone},Duplicate\n{other_phone},Second\n"

    preview = preview_customer_import(db, text)
    result = import_customers(db, text, admin_id=1)

    assert preview["valid_rows"] == result["imported"] == 2
    assert preview["error_rows"] == result["skipped"] == 1
    users = db.query(User).filter(User.phone.in_([phone, other_phone])).all()
    assert len(users) == 2
    assert all(user.email is None for user in users)
    assert all(user.customer_number.startswith("CUST-") for user in users)


def test_preview_handles_null_email_and_legacy_phone_format(db):
    phone = _phone()
    db.add(User(
        email=None,
        phone=phone[:3] + " " + phone[3:],
        password_hash="unused",
        account_type="customer",
    ))
    db.flush()

    result = preview_customer_import(db, f"phone\n{phone}\n")

    assert result["valid_rows"] == 0
    assert result["rows"][0]["errors"] == ["Phone number already exists in database"]


def test_invalid_email_does_not_reserve_phone_for_later_valid_row(db):
    phone = _phone()
    text = f"phone,email\n{phone},invalid\n{phone},\n"

    preview = preview_customer_import(db, text)
    result = import_customers(db, text, admin_id=1)

    assert preview["rows"][0]["errors"] == ["Invalid email format"]
    assert preview["rows"][1]["valid"] is True
    assert result["imported"] == result["skipped"] == 1
