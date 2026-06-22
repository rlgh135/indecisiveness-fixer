"""init decidoctor schema

Revision ID: 0001
Revises:
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS decidoctor")

    op.create_table(
        "question_type",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("keywords", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        schema="decidoctor",
    )

    op.create_table(
        "persona",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("stance_directive", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_persona_name_version"),
        schema="decidoctor",
    )

    op.create_table(
        "persona_type",
        sa.Column("persona_id", sa.BigInteger(), nullable=False),
        sa.Column("type_id", sa.BigInteger(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.ForeignKeyConstraint(["persona_id"], ["decidoctor.persona.id"]),
        sa.ForeignKeyConstraint(["type_id"], ["decidoctor.question_type.id"]),
        sa.PrimaryKeyConstraint("persona_id", "type_id"),
        schema="decidoctor",
    )


def downgrade() -> None:
    op.drop_table("persona_type", schema="decidoctor")
    op.drop_table("persona", schema="decidoctor")
    op.drop_table("question_type", schema="decidoctor")
    op.execute("DROP SCHEMA IF EXISTS decidoctor")
