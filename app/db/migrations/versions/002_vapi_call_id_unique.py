"""Unique index on call_logs.vapi_call_id

It's the de-facto key for booking/call-completion lookups and upserts;
the unique index also dedupes concurrent end-of-call inserts.

Revision ID: 002
Revises: 001
Create Date: 2026-06-22

"""
from alembic import op


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_call_logs_vapi_call_id", "call_logs", ["vapi_call_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_call_logs_vapi_call_id", table_name="call_logs")
