from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

SCHEMA = "decidoctor"


class QuestionType(Base):
    __tablename__ = "question_type"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    persona_types: Mapped[list["PersonaType"]] = relationship(back_populates="question_type")


class Persona(Base):
    __tablename__ = "persona"
    __table_args__ = (
        sa.UniqueConstraint("name", "version", name="uq_persona_name_version"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    stance_directive: Mapped[str] = mapped_column(sa.Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )

    persona_types: Mapped[list["PersonaType"]] = relationship(back_populates="persona")


class PersonaType(Base):
    __tablename__ = "persona_type"
    __table_args__ = {"schema": SCHEMA}

    persona_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey(f"{SCHEMA}.persona.id"), primary_key=True
    )
    type_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey(f"{SCHEMA}.question_type.id"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(sa.Float, nullable=False, server_default="1.0")

    persona: Mapped["Persona"] = relationship(back_populates="persona_types")
    question_type: Mapped["QuestionType"] = relationship(back_populates="persona_types")
