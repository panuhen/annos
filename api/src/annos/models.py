from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
#
# A native Postgres enum. Widening it later needs ALTER TYPE ... ADD VALUE, and
# the new value cannot be used in the same transaction that adds it — so a
# migration that adds a value and backfills rows with it must be split in two.
FOOD_SOURCES = ("fineli", "verified", "user", "label", "ai_estimate")
FoodSource = Enum(*FOOD_SOURCES, name="food_source")

# Finnish, Swedish, English — the three Fineli ships, complete, for every food.
# No language is the "real" one that the others translate: each name column is
# equal, each is searched, and presentation resolves against the user's
# preference. See annos.domain.language.
LANGUAGES = ("fi", "sv", "en")

MEALS = ("breakfast", "lunch", "dinner", "snack")
MealType = Enum(*MEALS, name="meal_type")

INPUT_MODES = ("text", "photo", "plan")
InputMode = Enum(*INPUT_MODES, name="input_mode")

GOAL_KINDS = ("deficit", "maintenance", "surplus")
GoalKind = Enum(*GOAL_KINDS, name="goal_kind")

DAY_TYPES = ("training", "rest")
DayType = Enum(*DAY_TYPES, name="day_type")

EXERCISE_KINDS = ("cardio", "strength", "other")
ExerciseKind = Enum(*EXERCISE_KINDS, name="exercise_kind")

# Who stated the session's facts (duration, activity): the user, or a client's
# guess. The kcal figure itself is always server arithmetic over these facts.
EXERCISE_SOURCES = ("user", "ai_estimate")
ExerciseSource = Enum(*EXERCISE_SOURCES, name="exercise_source")


class UserProfile(Base):
    """One row per user. `subject` is the Better Auth user id.

    Deliberately not a foreign key: Better Auth owns its own tables and the API's
    database role has no access to them. The subject arrives as a validated token
    claim and is treated here as an opaque external identifier.
    """

    __tablename__ = "user_profile"

    subject: Mapped[str] = mapped_column(Text, primary_key=True)

    # Annos' own data, authored here at registration (the welcome roll flow ->
    # POST /profile -> nickname.claim), never a copy of a token claim: the token
    # carries only `subject` (definePayload pins the JWT to registered claims).
    # This column IS the source of truth for the display identity everywhere.
    nickname: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # birth_year, not date of birth: Mifflin-St Jeor needs age to a year and
    # nothing needs a birthday.
    birth_year: Mapped[int | None] = mapped_column(Integer)
    height_cm: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String(16))
    activity_baseline: Mapped[str | None] = mapped_column(String(16))

    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Europe/Helsinki")
    units: Mapped[str] = mapped_column(String(8), nullable=False, server_default="metric")

    # Which of the three names a food is presented under. Search always covers
    # all three regardless — a Finnish speaker still types "banana" sometimes.
    language: Mapped[str] = mapped_column(String(2), nullable=False, server_default="fi")

    # The web UI's chrome language — labels, dates, letterhead. Separate from
    # `language` on purpose: an English app can still show foods as ruisleipä.
    # NULL means "never chosen": the web negotiates from Accept-Language.
    ui_language: Mapped[str | None] = mapped_column(String(2))

    # Whether the day sheet prints each food's macro line. Presentation only:
    # the summary payload always carries the numbers.
    show_item_macros: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

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
        CheckConstraint("language IN ('fi', 'sv', 'en')", name="ck_profile_language"),
        CheckConstraint(
            "ui_language IS NULL OR ui_language IN ('fi', 'sv', 'en')",
            name="ck_profile_ui_language",
        ),
    )


class CoachingNoteRevision(Base):
    """What the coaching notes became, every time they changed.

    Appended by `update_profile` whenever `coaching_notes` actually changes
    (a rewrite to the same text is not a revision). The current value lives on
    `user_profile` and every default read stays there — this table is only for
    the explicit "how have my instructions changed" question, so history never
    rides along uninvited. `notes` is nullable because clearing the notes is
    itself a revision worth remembering.
    """

    __tablename__ = "coaching_note_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_coaching_note_revisions_subject_created", "subject", "created_at"),)


class Food(Base):
    """One row per distinct food. Per-100g is the base convention.

    owner_id NULL means global (the Fineli seed and verified entries). A set
    owner_id makes the row private to that user, so one user's label-photo food
    never pollutes another's search.
    """

    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Three peers, all nullable, at least one required. A Fineli row has all
    # three; a food a user photographed the label of has whichever language the
    # label was printed in, and inventing the other two would be fabrication.
    name_fi: Mapped[str | None] = mapped_column(Text)
    name_sv: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)

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
        CheckConstraint("num_nonnulls(name_fi, name_sv, name_en) > 0", name="ck_foods_has_a_name"),
        # One trigram index per language. Trigram matching handles typos and
        # Finnish inflections ("rahka" -> "maitorahka") without embeddings, and
        # pg_trgm lowercases, so casing never affects a match.
        *(
            Index(
                f"ix_foods_name_{lang}_trgm",
                f"name_{lang}",
                postgresql_using="gin",
                postgresql_ops={f"name_{lang}": "gin_trgm_ops"},
            )
            for lang in LANGUAGES
        ),
        Index("ix_foods_owner_id", "owner_id"),
    )


class ServingUnit(Base):
    """How much a natural portion of this food weighs.

    `unit_code` is Fineli's own code (KPL_S, DL, RKL) rather than a word, so the
    row carries no language. `serving_unit_types` renders it. A food created
    from a label photo can carry a code Fineli never defined — hence no foreign
    key, and a missing type is displayed as the code itself.
    """

    __tablename__ = "serving_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), nullable=False)
    unit_code: Mapped[str] = mapped_column(Text, nullable=False)
    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    food: Mapped[Food] = relationship(back_populates="serving_units")
    unit_type: Mapped["ServingUnitType | None"] = relationship(
        primaryjoin="foreign(ServingUnit.unit_code) == ServingUnitType.code",
        lazy="selectin",
        viewonly=True,
    )

    __table_args__ = (UniqueConstraint("food_id", "unit_code", name="uq_serving_units_food_unit"),)


class MealLog(Base):
    """One eating event. Scoped by `subject` — never queried without it.

    `ts` is the moment the meal happened, UTC. The server defaults it to now();
    a client supplies it only when the user stated a time ("yesterday's lunch").
    Which calendar day it counts toward is decided at read time by the profile
    timezone, not stored here.

    `planned` is a planner entry not yet eaten: created true when input_mode is
    "plan", flipped false through revise_log when the user confirms.
    """

    __tablename__ = "meal_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Nullable: the client is told to ask rather than assume a meal type, and
    # "the user didn't say" is representable.
    meal: Mapped[str | None] = mapped_column(MealType)
    input_mode: Mapped[str] = mapped_column(InputMode, nullable=False, server_default="text")
    planned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # User-dictated data, stored and returned verbatim — never instructions to
    # the server.
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["MealLogItem"]] = relationship(
        back_populates="log", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        # The day view: everything a subject ate within a timestamp window.
        Index("ix_meal_logs_subject_ts", "subject", "ts"),
    )


class MealLogItem(Base):
    """One food in one meal, with the macros snapshotted at log time.

    The snapshot is per-100g, same convention as `foods` — the portion's macros
    are grams * value / 100 at read time. Copied because food definitions
    change and history must not; kept per-100g so a grams-only revision can
    rescale without touching the (possibly since-edited) food row.
    """

    __tablename__ = "meal_log_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_id: Mapped[int] = mapped_column(
        ForeignKey("meal_logs.id", ondelete="CASCADE"), nullable=False
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), nullable=False)
    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    kcal: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    protein_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    carbs_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    fat_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    fiber_g: Mapped[float | None] = mapped_column(Numeric(8, 2))

    log: Mapped[MealLog] = relationship(back_populates="items")
    food: Mapped[Food] = relationship(lazy="selectin")

    __table_args__ = (
        CheckConstraint("grams > 0", name="ck_meal_log_items_grams_positive"),
        Index("ix_meal_log_items_log_id", "log_id"),
    )


class MealTemplate(Base):
    """A meal saved as one loggable unit — "the usual breakfast".

    A recipe is the same template with a yield: `total_grams` states what the
    whole batch weighs, and logging takes a portion of it. Templates store
    foods and grams only, never macros — snapshots happen at log time, so a
    template logged next month uses that day's definitions. Names are unique
    per owner because "the usual breakfast" is how a template is referred to;
    saving the same name again replaces the contents.
    """

    __tablename__ = "meal_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    total_grams: Mapped[float | None] = mapped_column(Numeric(8, 2))

    # Bumped whenever the template is expanded into a log — "the usual" should
    # surface first wherever templates are offered. Metadata about the
    # template, never about any log: deleting the template loses it, logs
    # never reference it.
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["MealTemplateItem"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MealTemplateItem.id",
    )

    __table_args__ = (
        UniqueConstraint("subject", "name", name="uq_meal_templates_subject_name"),
        CheckConstraint(
            "total_grams IS NULL OR total_grams > 0", name="ck_meal_templates_total_grams"
        ),
    )


class MealTemplateItem(Base):
    __tablename__ = "meal_template_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("meal_templates.id", ondelete="CASCADE"), nullable=False
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), nullable=False)
    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    template: Mapped[MealTemplate] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("grams > 0", name="ck_meal_template_items_grams_positive"),
        Index("ix_meal_template_items_template_id", "template_id"),
    )


class BodyMetric(Base):
    """One row per subject per day, upserted — logging weight twice on a day
    replaces, never duplicates. The smoothed trend is computed at read time
    and never stored; the raw daily value is the only fact here.

    `date` is a calendar date in the subject's own timezone, decided by the
    domain layer at write time — the row itself carries no timezone.
    """

    __tablename__ = "body_metrics"

    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, primary_key=True)

    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2))
    waist_cm: Mapped[float | None] = mapped_column(Numeric(5, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "weight_kg IS NULL OR (weight_kg > 0 AND weight_kg < 500)",
            name="ck_body_metrics_weight_sane",
        ),
        CheckConstraint(
            "waist_cm IS NULL OR (waist_cm > 0 AND waist_cm < 500)",
            name="ck_body_metrics_waist_sane",
        ),
        # A row must say something: all-NULL measurements is a no-op, not data.
        CheckConstraint(
            "num_nonnulls(weight_kg, waist_cm, notes) > 0", name="ck_body_metrics_not_empty"
        ),
    )


class GoalPhase(Base):
    """Targets have a lifespan, not a single flat number.

    `end_date` NULL marks the current phase; setting a new phase closes the
    previous one the day before the new one starts. History always evaluates
    a day against the phase that was in force *then* — phases are appended
    and closed, never rewritten.
    """

    __tablename__ = "goal_phases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)

    kind: Mapped[str] = mapped_column(GoalKind, nullable=False)
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_type | None] = mapped_column(Date)

    # Different targets per day type: training days earn more food, and
    # protein needs vary by day type the same way energy does.
    kcal_target_training: Mapped[int] = mapped_column(Integer, nullable=False)
    kcal_target_rest: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_target_training: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_target_rest: Mapped[int] = mapped_column(Integer, nullable=False)

    # What the phase is trying to achieve; the adaptive TDEE method evaluates
    # actuals against this. Negative = losing.
    rate_target_kg_per_week: Mapped[float | None] = mapped_column(Numeric(4, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kcal_target_training > 0 AND kcal_target_rest > 0 "
            "AND protein_target_training > 0 AND protein_target_rest > 0",
            name="ck_goal_phases_targets_positive",
        ),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_goal_phases_dates"),
        Index("ix_goal_phases_subject_start", "subject", "start_date"),
    )


class DayTypeMark(Base):
    """The user's manual say on what kind of day a date is.

    A row here wins over any derivation, in both directions: marking a rest
    day rest silences a logged session, and marking training gets the training
    targets before the session is logged (the eating happens all day) or when
    the session lives outside Annos. Days without a row resolve at read time —
    exercise-derived once exercise logging exists, rest until then — so the
    table records only what the user actually said.
    """

    __tablename__ = "day_types"

    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, primary_key=True)

    day_type: Mapped[str] = mapped_column(DayType, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Activity(Base):
    """The Compendium of Physical Activities MET catalog, seeded once.

    English-only by decision (2026-08-07): the Compendium ships no
    translations, so this catalog knowingly breaks the three-language rule —
    MCP clients translate before calling, the web form leans on trigram
    tolerance. `code` is the Compendium's own 5-digit id, kept so a future
    Compendium revision can upsert instead of duplicating.
    """

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(5), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    met: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)

    __table_args__ = (
        CheckConstraint("met > 0", name="ck_activities_met_positive"),
        Index(
            "ix_activities_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class Exercise(Base):
    """A strength movement in one user's own vocabulary.

    User-grown and user-scoped (same rule as custom foods): the server creates
    a row on first mention in a set, matching case-insensitively within the
    owner's catalog, and one user's naming never leaks into another's.
    """

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    muscle_group: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_exercises_owner_lower_name",
            "owner_id",
            text("lower(name)"),
            unique=True,
        ),
    )


class ExerciseLog(Base):
    """One training session. Scoped by `subject`, like meal_logs.

    `weight_kg` is the bodyweight snapshot the estimate was computed from
    (the latest logged weight at log time) — kept so a duration revision can
    rescale from what was true then, the same discipline as macro snapshots.
    `kcal_estimate` is MET x weight x hours and NULL whenever a factor is
    honestly unknown: no weight ever logged, no duration, no MET basis.
    """

    __tablename__ = "exercise_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    kind: Mapped[str] = mapped_column(ExerciseKind, nullable=False)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    duration_min: Mapped[float | None] = mapped_column(Numeric(6, 1))

    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2))
    kcal_estimate: Mapped[float | None] = mapped_column(Numeric(8, 2))

    planned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source: Mapped[str] = mapped_column(ExerciseSource, nullable=False, server_default="user")
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    activity: Mapped[Activity | None] = relationship(lazy="selectin")
    sets: Mapped[list["StrengthSet"]] = relationship(
        back_populates="log",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="StrengthSet.set_no",
    )

    __table_args__ = (
        CheckConstraint(
            "duration_min IS NULL OR duration_min > 0", name="ck_exercise_logs_duration_positive"
        ),
        Index("ix_exercise_logs_subject_ts", "subject", "ts"),
    )


class StrengthSet(Base):
    """One set of one movement. weight_kg 0 is a bodyweight set, not missing
    data. Progression trends (e5RM, weekly volume) are queries over this
    table, never stored columns."""

    __tablename__ = "strength_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_logs.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    set_no: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    rpe: Mapped[float | None] = mapped_column(Numeric(3, 1))

    log: Mapped[ExerciseLog] = relationship(back_populates="sets")
    exercise: Mapped[Exercise] = relationship(lazy="selectin")

    __table_args__ = (
        CheckConstraint("reps > 0", name="ck_strength_sets_reps_positive"),
        CheckConstraint("weight_kg >= 0", name="ck_strength_sets_weight_not_negative"),
        CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="ck_strength_sets_rpe"),
        Index("ix_strength_sets_log_id", "log_id"),
        Index("ix_strength_sets_exercise_id", "exercise_id"),
    )


class ServingUnitType(Base):
    """Fineli's unit thesaurus: KPL_S -> "pieni (kpl)" / "litet st." / "small piece".

    Ten codes are actually used by the seed, fifteen defined. Small enough that
    it is loaded alongside every search without noticing.
    """

    __tablename__ = "serving_unit_types"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name_fi: Mapped[str | None] = mapped_column(Text)
    name_sv: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)


class NutrientComponent(Base):
    """What the keys in `foods.micros` mean, and in which unit.

    The 74 components come free with the Fineli seed and are stored now, but
    nothing surfaces them yet. Without this table they are unlabelled numbers,
    and a µg read as a mg is the kind of error that looks plausible.
    """

    __tablename__ = "nutrient_components"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    class_code: Mapped[str | None] = mapped_column(Text)
    name_fi: Mapped[str | None] = mapped_column(Text)
    name_sv: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
