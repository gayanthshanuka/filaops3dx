"""Uniqueness and transaction handling for customer contact changes."""
import re
from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.customer_contact import phone_key
from app.core.utils import escape_like
from app.models.user import User


def phone_search(term: str):
    """Search formatted legacy telephone numbers using a punctuation-free query."""
    digits = phone_key(term)
    if not digits or not re.fullmatch(r"[+0-9\s().-]+", term):
        return User.phone.ilike(f"%{escape_like(term)}%", escape="\\")
    return func.regexp_replace(User.phone, "[^0-9]", "", "g").contains(digits)


def ensure_contact_available(db: Session, *, phone=None, email=None, exclude_id=None):
    """Match telephone numbers across formatting variants; email remains optional."""
    conditions = []
    if phone:
        conditions.append((User.account_type == "customer") & (
            func.regexp_replace(User.phone, "[^0-9]", "", "g") == phone_key(phone)
        ))
    if email:
        conditions.append(func.lower(User.email) == email.lower())
    if not conditions:
        return
    query = db.query(User).filter(or_(*conditions))
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    existing = query.first()
    if existing:
        if phone and existing.account_type == "customer" and phone_key(existing.phone) == phone_key(phone):
            raise HTTPException(status_code=400, detail="Telephone number already registered")
        message = "Email already in use" if exclude_id is not None else "Email already registered"
        raise HTTPException(status_code=400, detail=message)


def commit_customer(db: Session):
    """A concurrent create/update must report a conflict, rather than a server error."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
        if constraint == "uq_users_customer_phone":
            raise HTTPException(status_code=400, detail="Telephone number already registered") from exc
        if constraint in {"ix_users_email", "users_email_key"}:
            raise HTTPException(status_code=400, detail="Email already registered") from exc
        raise
