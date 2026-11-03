"""Exercise the real Alembic migration against a legacy customer schema."""
import importlib.util
from pathlib import Path
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, text

from app.models.user import User


def _migration(db, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "migrations/versions/103_customer_phone_identity.py"
    spec = importlib.util.spec_from_file_location("phone_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(db.connection())))
    return module


def _legacy_schema(db):
    db.execute(text("DROP INDEX uq_users_customer_phone"))
    db.execute(text("ALTER TABLE users DROP CONSTRAINT ck_users_staff_email"))
    db.execute(text("ALTER TABLE users ALTER COLUMN email SET NOT NULL"))


def _legacy_customer(db, phone=None):
    user = User(email=f"legacy-{uuid.uuid4().hex}@example.com", phone=phone, password_hash="unused", account_type="customer")
    db.add(user)
    db.flush()
    return user


def test_upgrade_preserves_legacy_records_and_placeholders(db, monkeypatch):
    _legacy_schema(db)
    legacy = _legacy_customer(db)
    _legacy_customer(db, "N/A")
    _legacy_customer(db, "-")
    module = _migration(db, monkeypatch)
    module.upgrade()

    assert db.get(User, legacy.id).email == legacy.email
    assert db.get(User, legacy.id).phone is None
    columns = {column["name"]: column for column in inspect(db.connection()).get_columns("users")}
    assert columns["email"]["nullable"] is True
    db.add(User(email=None, phone="+94771234567", password_hash="unused", account_type="customer"))
    db.flush()


def test_upgrade_refuses_duplicate_real_numbers_without_merging(db, monkeypatch):
    _legacy_schema(db)
    first = _legacy_customer(db, "+94 (77) 123-4567")
    second = _legacy_customer(db, "94771234567")
    with pytest.raises(RuntimeError, match="duplicate customer telephone"):
        _migration(db, monkeypatch).upgrade()
    assert db.get(User, first.id) is not None
    assert db.get(User, second.id) is not None


def test_downgrade_refuses_to_discard_phone_only_customers(db, monkeypatch):
    db.add(User(email=None, phone="0771234567", password_hash="unused", account_type="customer"))
    db.flush()
    with pytest.raises(RuntimeError, match="assigned real emails"):
        _migration(db, monkeypatch).downgrade()
