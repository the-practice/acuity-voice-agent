"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clients table
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(50)),
        sa.Column("name", sa.String(255)),
        sa.Column("date_of_birth", sa.DateTime()),
        sa.Column("intakeq_id", sa.String(100)),
        sa.Column("acuity_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_clients_email", "clients", ["email"])
    op.create_index("ix_clients_phone", "clients", ["phone"])

    # Call logs table
    op.create_table(
        "call_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_sid", sa.String(100), unique=True),
        sa.Column("caller_phone", sa.String(50)),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("ended_at", sa.DateTime()),
        sa.Column("outcome", sa.String(50)),
        sa.Column("summary", sa.Text()),
        sa.Column("contains_phi", sa.Boolean(), server_default="false"),
        sa.Column("transcript_retention_days", sa.Integer(), server_default="0"),
        sa.Column("vapi_call_id", sa.String(100)),
    )

    # Sync jobs table
    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(20)),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("status", sa.String(20)),
        sa.Column("records_processed", sa.Integer()),
        sa.Column("records_failed", sa.Integer()),
        sa.Column("error_summary", sa.Text()),
        sa.Column("log_url", sa.String(500)),
    )

    # Review items table
    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(50)),
        sa.Column("severity", sa.String(20)),
        sa.Column("context", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("resolution", sa.Text()),
    )

    # Provider rules table
    op.create_table(
        "provider_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_name", sa.String(255)),
        sa.Column("acuity_calendar_id", sa.String(100)),
        sa.Column("accepts_new_patients", sa.Boolean()),
        sa.Column("accepted_insurance", sa.JSON()),
        sa.Column("specialties", sa.JSON()),
        sa.Column("offers_telehealth", sa.Boolean()),
        sa.Column("location", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
    )

    # Knowledge articles table
    op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(100), unique=True),
        sa.Column("title", sa.String(255)),
        sa.Column("content", sa.Text()),
        sa.Column("category", sa.String(50)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_knowledge_articles_slug", "knowledge_articles", ["slug"])


def downgrade() -> None:
    op.drop_table("knowledge_articles")
    op.drop_table("provider_rules")
    op.drop_table("review_items")
    op.drop_table("sync_jobs")
    op.drop_table("call_logs")
    op.drop_table("clients")
