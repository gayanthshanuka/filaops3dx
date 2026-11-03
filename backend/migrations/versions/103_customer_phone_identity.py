"""Allow telephone-based customer records while retaining staff email requirements.

Revision ID: 103
Revises: 102

Existing email-only customers are retained. Duplicate legacy telephone numbers
must be reconciled explicitly before upgrading; this migration never deletes or
merges customers. National and international dialing prefixes are not inferred.
"""
from alembic import op
import sqlalchemy as sa

revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    duplicate_groups = bind.execute(sa.text("""
        SELECT count(*) FROM (
            SELECT regexp_replace(phone, '[^0-9]', '', 'g')
            FROM users
            WHERE account_type = 'customer' AND regexp_replace(phone, '[^0-9]', '', 'g') <> ''
            GROUP BY regexp_replace(phone, '[^0-9]', '', 'g') HAVING count(*) > 1
        ) duplicates
    """)).scalar()
    if duplicate_groups:
        raise RuntimeError(
            f"Reconcile {duplicate_groups} duplicate customer telephone groups before migration 103"
        )
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)
    op.create_check_constraint("ck_users_staff_email", "users", "account_type = 'customer' OR email IS NOT NULL")
    op.create_index(
        "uq_users_customer_phone", "users",
        [sa.text("regexp_replace(phone, '[^0-9]', '', 'g')")],
        unique=True,
        postgresql_where=sa.text("account_type = 'customer' AND regexp_replace(phone, '[^0-9]', '', 'g') <> ''"),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM users WHERE email IS NULL")).scalar():
        raise RuntimeError("Customers without email must be assigned real emails before downgrading migration 103")
    op.drop_index("uq_users_customer_phone", table_name="users")
    op.drop_constraint("ck_users_staff_email", "users", type_="check")
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
