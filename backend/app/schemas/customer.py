"""
Customer Pydantic Schemas

For admin management of customers (users with account_type='customer')
"""
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, EmailStr, model_validator, field_validator
from app.core.customer_contact import normalize_phone
from datetime import datetime

VALID_PAYMENT_TERMS = Literal["cod", "prepay", "net15", "net30", "net60", "card_on_file"]
NET_TERMS = {"net15", "net30", "net60"}


# ============================================================================
# Customer Schemas
# ============================================================================

class CustomerBase(BaseModel):
    """Base customer fields"""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)

    # Billing Address
    billing_address_line1: Optional[str] = Field(None, max_length=255)
    billing_address_line2: Optional[str] = Field(None, max_length=255)
    billing_city: Optional[str] = Field(None, max_length=100)
    billing_state: Optional[str] = Field(None, max_length=50)
    billing_zip: Optional[str] = Field(None, max_length=20)
    billing_country: Optional[str] = Field("USA", max_length=100)

    # Shipping Address
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field("USA", max_length=100)


class CustomerCreate(CustomerBase):
    """Create a new customer (CRM record only)

    Note: Customer portal login is a Pro feature. In open source,
    customers are CRM records for order management only.
    """
    phone: str = Field(..., max_length=40)
    status: Optional[str] = Field("active")

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value):
        return normalize_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def optional_email(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    # Payment Terms
    payment_terms: Optional[VALID_PAYMENT_TERMS] = "cod"
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    approved_for_terms: Optional[bool] = None


class CustomerUpdate(BaseModel):
    """Update an existing customer"""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value):
        return normalize_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def optional_email(cls, value):
        return value.strip() or None if isinstance(value, str) else value
    status: Optional[str] = None  # active, inactive, suspended

    # Billing Address
    billing_address_line1: Optional[str] = Field(None, max_length=255)
    billing_address_line2: Optional[str] = Field(None, max_length=255)
    billing_city: Optional[str] = Field(None, max_length=100)
    billing_state: Optional[str] = Field(None, max_length=50)
    billing_zip: Optional[str] = Field(None, max_length=20)
    billing_country: Optional[str] = Field(None, max_length=100)

    # Shipping Address
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field(None, max_length=100)

    # Payment Terms
    payment_terms: Optional[VALID_PAYMENT_TERMS] = None
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    approved_for_terms: Optional[bool] = None

    @model_validator(mode="after")
    def net_terms_require_approval(self):
        if self.payment_terms in NET_TERMS and not self.approved_for_terms:
            raise ValueError(
                f"Payment terms '{self.payment_terms}' require approved_for_terms=true"
            )
        return self


class CustomerListResponse(BaseModel):
    """Customer list item (summary)"""
    id: int
    customer_number: Optional[str] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    status: str
    payment_terms: Optional[str] = "cod"

    # Derived fields
    full_name: Optional[str] = None

    # Shipping address for order creation
    shipping_address_line1: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None

    # Stats
    order_count: int = 0
    total_spent: float = 0.0
    total_paid: float = 0.0
    outstanding_balance: float = 0.0
    last_order_date: Optional[datetime] = None

    # PRO price level discount (None if PRO not installed)
    discount_percent: Optional[float] = None

    created_at: datetime

    class Config:
        from_attributes = True


class CustomerResponse(CustomerBase):
    """Full customer details"""
    id: int
    customer_number: Optional[str] = None
    status: str
    email_verified: bool = False

    # Payment Terms
    payment_terms: Optional[str] = "cod"
    credit_limit: Optional[Decimal] = None
    approved_for_terms: bool = False
    approved_for_terms_at: Optional[datetime] = None
    approved_for_terms_by: Optional[int] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    # Stats
    order_count: int = 0
    quote_count: int = 0
    total_spent: float = 0.0
    total_paid: float = 0.0
    outstanding_balance: float = 0.0
    last_order_date: Optional[datetime] = None

    # PRO price level discount (None if PRO not installed)
    discount_percent: Optional[float] = None

    class Config:
        from_attributes = True


class CustomerSearchResult(BaseModel):
    """Lightweight customer search result for dropdowns"""
    id: int
    customer_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None
    company_name: Optional[str] = None

    class Config:
        from_attributes = True
