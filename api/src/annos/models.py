from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from annos.db import Base

# Provenance: every food and estimate records where its numbers came from, so
# measured and guessed data never blur.
FoodSource = Enum(
    "fineli",
    "verified",
    "user",
    "label",
    "ai_estimate",
    name="food_source",
    create_type=True,
)


class UserProfile(Base):
    """One row per user. `subject` is the Better Auth user id.

    Deliberately not a foreign key: Better Auth owns its own tables and the API's
    database role has no access to them. The subject arrives as a validated token
    claim and is treated here as an opaque external identifier.
    """

    __tablename__ = "user_profile"

    subject: Mapped[str] = mapped_column(Text, primary_key=True)

    # Denormalised from the token's `profile` claim on first contact. Safe to copy
    # because the nickname is permanent after registration (re-roll is
    # registration-only), so it cannot drift.
    nickname: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # birth_year, not date of birth: Mifflin-St Jeor needs age to a year and
    # nothing needs a birthday.
    birth_year: Mapped[int | None] = mapped_column(Integer)
    height_cm: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(16))
    activity_baseline: Mapped[str | None] = mapped_column(String(16))

    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Europe/Helsinki")
    units: Mapped[str] = mapped_column(String(8), nullable=False, server_default="metric")

    dietary_prefs: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))

    # Free text in the user's own words. Stored and returned verbatim; the server
    # never interprets it.
    coaching_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("sex IS NULL OR sex IN ('female', 'male', 'other')", name="ck_profile_sex"),
        CheckConstraint("units IN ('metric', 'imperial')", name="ck_profile_units"),
        CheckConstraint(
            "birth_year IS NULL OR (birth_year BETWEEN 1900 AND 2100)",
            name="ck_profile_birth_year",
        ),
    )


class Food(Base):
    """One row per distinct food. Per-100g is the base convention.

    owner_id NULL means global (the Fineli seed and verified entries). A set
    owner_id makes the row private to that user, so one user's label-photo food
    never pollutes another's search.
    """

    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_fi: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str] = mapped_column(FoodSource, nullable=False)
    fineli_id: Mapped[int | None] = mapped_column(Integer)
    owner_id: Mapped[str | None] = mapped_column(Text)

    kcal: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    protein_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    carbs_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    fat_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    fiber_g: Mapped[float | None] = mapped_column(Numeric(8, 2))

    # The full 74 Fineli components come free with the seed. Store them now;
    # don't build UI for them yet.
    micros: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    serving_units: Mapped[list["ServingUnit"]] = relationship(
        back_populates="food", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("fineli_id", name="uq_foods_fineli_id"),
        # Trigram search over both name columns: handles typos and Finnish
        # inflections ("rahka" -> "maitorahka") without embeddings.
        Index("ix_foods_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("ix_foods_name_fi_trgm", "name_fi", postgresql_using="gin",
              postgresql_ops={"name_fi": "gin_trgm_ops"}),
        Index("ix_foods_owner_id", "owner_id"),
    )


class ServingUnit(Base):
    """Natural logging units for a food ("slice", "kpl", "dl")."""

    __tablename__ = "serving_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    food: Mapped[Food] = relationship(back_populates="serving_units")

    __table_args__ = (
        UniqueConstraint("food_id", "name", name="uq_serving_units_food_name"),
    )
