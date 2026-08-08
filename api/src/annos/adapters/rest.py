"""REST adapter — what the Next.js UI calls.

Mirrors the MCP tool surface, plus the three endpoints that exist only here:
nickname rolling, profile creation, and account deletion. Those are UI-only so
that a hallucinating client cannot create or destroy an account.

Every route declares a response model: the web client is generated from the
OpenAPI schema (`openapi-typescript`), so an untyped response would turn
contract drift back into a runtime bug — the exact failure codegen exists to
prevent. The models mirror the domain payloads field for field; a field added
in the domain without being added here disappears from REST responses, which
the route tests and the cross-surface parity tests then catch.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from annos import nickname as nickname_mod
from annos import servertime
from annos.config import settings
from annos.db import get_session
from annos.domain import account as account_domain
from annos.domain import body as body_domain
from annos.domain import days as days_domain
from annos.domain import exercise as exercise_domain
from annos.domain import export as export_domain
from annos.domain import foods as foods_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import stats as stats_domain
from annos.domain import summary as summary_domain
from annos.domain import templates as templates_domain
from annos.identity import AuthError, Caller, resolve_caller

router = APIRouter()


async def caller(authorization: Annotated[str | None, Header()] = None) -> Caller:
    try:
        return await resolve_caller(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def web_caller(authorization: Annotated[str | None, Header()] = None) -> Caller:
    """A caller wearing the web UI's credential shape — a JWT, never an
    opaque OAuth token.

    Account destruction is web-only in *mechanism*, not just by absence from
    the tool list: an MCP client's opaque token is refused by shape before
    any validation, so no chain of tool calls can reach this route with the
    credentials MCP clients hold. (The dev bypass passes, as everywhere.)
    """
    if not settings.dev_subject:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() == "bearer" and token and token.count(".") != 2:
            raise HTTPException(
                status_code=403, detail="this endpoint accepts web credentials only"
            )
    return await caller(authorization)


CallerDep = Annotated[Caller, Depends(caller)]
WebCallerDep = Annotated[Caller, Depends(web_caller)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ServerTime(BaseModel):
    utc: str
    timezone: str
    local_date: str


class ServingUnitOut(BaseModel):
    code: str
    name: str
    grams: float


class Per100g(BaseModel):
    kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None


class FoodCandidateOut(BaseModel):
    id: int
    name: str
    name_language: str
    source: str
    owned: bool
    per_100g: Per100g
    serving_units: list[ServingUnitOut]


class FoodSearchResponse(BaseModel):
    results: list[FoodCandidateOut]
    language: str
    server_time: ServerTime


class NicknameRollResponse(BaseModel):
    nickname: str


class ProfileResponse(BaseModel):
    nickname: str
    birth_year: int | None
    height_cm: int | None
    sex: str | None
    activity_baseline: str | None
    timezone: str
    units: str
    language: str
    ui_language: str | None
    show_item_macros: bool
    dietary_prefs: dict[str, Any]
    coaching_notes: str | None
    server_time: ServerTime


class LoggedItemOut(BaseModel):
    food_id: int
    grams: float
    estimated: bool
    kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None


class DayTotals(BaseModel):
    local_date: str
    items_logged: int
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float


class MealLogResponse(BaseModel):
    log_id: int
    ts: str
    meal: str | None
    input_mode: str
    planned: bool
    notes: str | None
    items: list[LoggedItemOut]
    day_totals: DayTotals
    server_time: ServerTime


class SummaryItemOut(BaseModel):
    food_id: int
    name: str | None
    source: str | None
    grams: float
    estimated: bool
    kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None


class SummaryMealOut(BaseModel):
    log_id: int
    ts: str
    meal: str | None
    planned: bool
    notes: str | None
    kcal: float
    items: list[SummaryItemOut]


class TargetOut(BaseModel):
    kind: str
    kcal: int
    protein_g: int
    rate_kg_per_week: float | None


class RemainingOut(BaseModel):
    kcal: float
    protein_g: float


class ProfileContextOut(BaseModel):
    dietary_prefs: dict[str, Any]
    coaching_notes: str | None


class ActivityOut(BaseModel):
    id: int
    name: str
    category: str
    met: float


class StrengthSetOut(BaseModel):
    set_no: int
    exercise: str | None
    reps: int
    weight_kg: float
    rpe: float | None


class SummaryExerciseOut(BaseModel):
    log_id: int
    ts: str
    kind: str
    activity: ActivityOut | None
    duration_min: float | None
    kcal_estimate: float | None
    planned: bool
    source: str
    notes: str | None
    sets: list[StrengthSetOut]


class DailySummaryResponse(BaseModel):
    date: str
    day_type: str
    day_type_source: str
    totals: DayTotals
    target: TargetOut | None
    remaining: RemainingOut | None
    meals: list[SummaryMealOut]
    exercise: list[SummaryExerciseOut]
    profile_context: ProfileContextOut
    server_time: ServerTime


class WeightLogResponse(BaseModel):
    date: str
    weight_kg: float | None
    waist_cm: float | None
    notes: str | None
    server_time: ServerTime


class ClosedPhaseOut(BaseModel):
    phase_id: int
    end_date: str


class GoalPhaseResponse(BaseModel):
    phase_id: int
    kind: str
    start_date: str
    end_date: str | None
    kcal_target_training: int
    kcal_target_rest: int
    protein_target_training: int
    protein_target_rest: int
    rate_target_kg_per_week: float | None
    server_time: ServerTime
    closed_previous: ClosedPhaseOut | None = None


class CoachingRevisionOut(BaseModel):
    notes: str | None
    set_at: str


class CoachingHistoryResponse(BaseModel):
    revisions: list[CoachingRevisionOut]
    server_time: ServerTime


class GoalPhaseOut(BaseModel):
    phase_id: int
    kind: str
    start_date: str
    end_date: str | None
    kcal_target_training: int
    kcal_target_rest: int
    protein_target_training: int
    protein_target_rest: int
    rate_target_kg_per_week: float | None


class GoalHistoryResponse(BaseModel):
    phases: list[GoalPhaseOut]
    server_time: ServerTime


class GoalPhaseDeletedResponse(BaseModel):
    deleted_phase_id: int
    kind: str
    start_date: str
    end_date: str | None
    server_time: ServerTime


class ProfileCreate(BaseModel):
    nickname: str | None = Field(
        default=None,
        description="A candidate previously returned by /profile/nickname/roll. "
        "Omitted means take whatever the generator produces.",
    )


class ProfileUpdate(BaseModel):
    changes: dict[str, Any]


def _profile_payload(profile) -> dict:
    return {
        "nickname": profile.nickname,
        "birth_year": profile.birth_year,
        "height_cm": profile.height_cm,
        "sex": profile.sex,
        "activity_baseline": profile.activity_baseline,
        "timezone": profile.timezone,
        "units": profile.units,
        "language": profile.language,
        "ui_language": profile.ui_language,
        "show_item_macros": profile.show_item_macros,
        "dietary_prefs": profile.dietary_prefs,
        "coaching_notes": profile.coaching_notes,
        "server_time": servertime.echo(profile.timezone),
    }


@router.get("/foods/search")
async def search_foods(
    session: SessionDep,
    who: CallerDep,
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> FoodSearchResponse:
    language = await foods_domain.reading_language(session, subject=who.subject)
    candidates = await foods_domain.find_food(session, subject=who.subject, query=q, limit=limit)
    return {
        "results": [foods_domain.candidate_payload(c, language) for c in candidates],
        "language": language,
        # Echoed on every response so the client is never guessing the date.
        "server_time": servertime.echo("UTC"),
    }


@router.post("/profile/nickname/roll")
async def roll_nickname(who: CallerDep) -> NicknameRollResponse:
    """One candidate. Called repeatedly during registration; commits nothing."""
    return {"nickname": nickname_mod.roll()}


@router.post("/profile", status_code=201)
async def create_profile(
    session: SessionDep, who: CallerDep, body: ProfileCreate
) -> ProfileResponse:
    try:
        profile = await profile_domain.create_profile(
            session, subject=who.subject, nickname=body.nickname
        )
    except nickname_mod.NicknameTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except profile_domain.AlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail="already registered") from exc
    return _profile_payload(profile)


@router.get("/profile")
async def get_profile(session: SessionDep, who: CallerDep) -> ProfileResponse:
    try:
        profile = await profile_domain.get_profile(session, subject=who.subject)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
    return _profile_payload(profile)


@router.patch("/profile")
async def update_profile(
    session: SessionDep, who: CallerDep, body: ProfileUpdate
) -> ProfileResponse:
    try:
        profile = await profile_domain.update_profile(
            session, subject=who.subject, changes=body.changes
        )
    except (profile_domain.UnknownField, profile_domain.InvalidValue) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
    return _profile_payload(profile)


@router.get("/profile/coaching-history")
async def coaching_history(session: SessionDep, who: CallerDep) -> CoachingHistoryResponse:
    try:
        return await profile_domain.coaching_notes_history(session, subject=who.subject)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class MealItem(BaseModel):
    food_id: int
    grams: float = Field(gt=0)
    estimated: bool = Field(
        default=False,
        description="True when the grams are a guess (eyeballed from a photo, or a "
        "vague amount like 'a bowl' turned into grams); false when they trace to a "
        "measurement, a package figure, or a serving-unit conversion.",
    )


class TemplateRef(BaseModel):
    """A template standing in for its foods; expanded server-side at log time."""

    template_id: int
    portions: float | None = Field(default=None, gt=0)
    grams: float | None = Field(default=None, gt=0)


class MealLogCreate(BaseModel):
    items: list[MealItem | TemplateRef] = Field(min_length=1)
    meal: str | None = None
    ts: str | None = Field(
        default=None,
        description="Only when the user stated a time. Omitted means server now(). "
        "Naive timestamps are read in the profile timezone.",
    )
    input_mode: str = "text"
    notes: str | None = None


class MealLogRevise(BaseModel):
    changes: dict[str, Any]


@router.post("/logs/meals", status_code=201)
async def log_meal(session: SessionDep, who: CallerDep, body: MealLogCreate) -> MealLogResponse:
    try:
        return await meals_domain.log_meal(
            session,
            subject=who.subject,
            items=[item.model_dump(exclude_none=True) for item in body.items],
            meal=body.meal,
            ts=body.ts,
            input_mode=body.input_mode,
            notes=body.notes,
        )
    except meals_domain.InvalidLog as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (meals_domain.UnknownFood, templates_domain.TemplateNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.get("/summary/daily")
async def daily_summary(
    session: SessionDep, who: CallerDep, date: Annotated[str | None, Query()] = None
) -> DailySummaryResponse:
    try:
        return await summary_domain.daily_summary(session, subject=who.subject, date=date)
    except meals_domain.InvalidLog as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class DayTypeSet(BaseModel):
    day_type: str
    date: str | None = Field(
        default=None, description="Only when the user stated a day; defaults to today."
    )


class DayTypeResponse(BaseModel):
    date: str
    day_type: str
    server_time: ServerTime


class WeightLogCreate(BaseModel):
    weight_kg: float | None = None
    date: str | None = Field(
        default=None, description="Only when the user stated a day; defaults to today."
    )
    waist_cm: float | None = None
    notes: str | None = None


class GoalPhaseCreate(BaseModel):
    kind: str
    kcal_training: int
    kcal_rest: int
    protein_training: int
    protein_rest: int
    rate_target: float | None = None
    start_date: str | None = None


@router.put("/days/type")
async def set_day_type(session: SessionDep, who: CallerDep, body: DayTypeSet) -> DayTypeResponse:
    try:
        return await days_domain.set_day_type(
            session, subject=who.subject, day_type=body.day_type, date=body.date
        )
    except days_domain.InvalidDayType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.post("/logs/weight", status_code=201)
async def log_weight(
    session: SessionDep, who: CallerDep, body: WeightLogCreate
) -> WeightLogResponse:
    try:
        return await body_domain.log_weight(
            session,
            subject=who.subject,
            weight_kg=body.weight_kg,
            date=body.date,
            waist_cm=body.waist_cm,
            notes=body.notes,
        )
    except body_domain.InvalidMetric as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.post("/goals/phase", status_code=201)
async def set_goal_phase(
    session: SessionDep, who: CallerDep, body: GoalPhaseCreate
) -> GoalPhaseResponse:
    try:
        return await body_domain.set_goal_phase(
            session,
            subject=who.subject,
            kind=body.kind,
            kcal_training=body.kcal_training,
            kcal_rest=body.kcal_rest,
            protein_training=body.protein_training,
            protein_rest=body.protein_rest,
            rate_target=body.rate_target,
            start_date=body.start_date,
        )
    except body_domain.InvalidPhase as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class GoalPhaseRevise(BaseModel):
    changes: dict[str, Any]


@router.patch("/goals/phase")
async def revise_goal_phase(
    session: SessionDep, who: CallerDep, body: GoalPhaseRevise
) -> GoalPhaseResponse:
    try:
        return await body_domain.revise_goal_phase(
            session, subject=who.subject, changes=body.changes
        )
    except body_domain.InvalidPhase as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except body_domain.NoOpenPhase as exc:
        raise HTTPException(status_code=404, detail="no open phase to revise") from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.delete("/goals/phase/{phase_id}")
async def delete_goal_phase(
    session: SessionDep, who: CallerDep, phase_id: int
) -> GoalPhaseDeletedResponse:
    try:
        return await body_domain.delete_goal_phase(session, subject=who.subject, phase_id=phase_id)
    except body_domain.PhaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.get("/goals/phases")
async def list_goal_phases(session: SessionDep, who: CallerDep) -> GoalHistoryResponse:
    try:
        return await body_domain.list_goal_phases(session, subject=who.subject)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class ActivitySearchResponse(BaseModel):
    results: list[ActivityOut]
    server_time: ServerTime


@router.get("/activities/search")
async def search_activities(
    session: SessionDep,
    who: CallerDep,
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ActivitySearchResponse:
    results = await exercise_domain.find_activity(
        session, subject=who.subject, query=q, limit=limit
    )
    return {"results": results, "server_time": servertime.echo("UTC")}


class StrengthSetIn(BaseModel):
    exercise: str
    reps: int = Field(gt=0)
    weight_kg: float = Field(ge=0, description="0 is a bodyweight set.")
    rpe: float | None = Field(default=None, ge=1, le=10)


class ExerciseLogCreate(BaseModel):
    kind: str
    activity_id: int | None = None
    duration_min: float | None = Field(default=None, gt=0)
    sets: list[StrengthSetIn] | None = None
    ts: str | None = Field(
        default=None,
        description="Only when the user stated a time. Omitted means server now().",
    )
    planned: bool = False
    source: str = "user"
    notes: str | None = None


class ExerciseLogRevise(BaseModel):
    changes: dict[str, Any]


class ExerciseLogResponse(BaseModel):
    log_id: int
    ts: str
    kind: str
    activity: ActivityOut | None
    duration_min: float | None
    kcal_estimate: float | None
    planned: bool
    source: str
    notes: str | None
    sets: list[StrengthSetOut]
    date: str
    day_type: str
    day_type_source: str
    server_time: ServerTime


class ExerciseDeletedResponse(BaseModel):
    deleted_log_id: int
    date: str
    day_type: str
    day_type_source: str
    server_time: ServerTime


@router.post("/logs/exercise", status_code=201)
async def log_exercise(
    session: SessionDep, who: CallerDep, body: ExerciseLogCreate
) -> ExerciseLogResponse:
    try:
        return await exercise_domain.log_exercise(
            session,
            subject=who.subject,
            kind=body.kind,
            activity_id=body.activity_id,
            duration_min=body.duration_min,
            sets=[s.model_dump() for s in body.sets] if body.sets is not None else None,
            ts=body.ts,
            planned=body.planned,
            source=body.source,
            notes=body.notes,
        )
    except exercise_domain.InvalidExercise as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (exercise_domain.UnknownActivity, meals_domain.InvalidLog) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.patch("/logs/exercise/{log_id}")
async def revise_exercise(
    session: SessionDep, who: CallerDep, log_id: int, body: ExerciseLogRevise
) -> ExerciseLogResponse:
    try:
        return await exercise_domain.revise_exercise(
            session, subject=who.subject, log_id=log_id, changes=body.changes
        )
    except (exercise_domain.InvalidExercise, meals_domain.InvalidLog) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except exercise_domain.UnknownActivity as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except exercise_domain.ExerciseLogNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.delete("/logs/exercise/{log_id}")
async def delete_exercise(
    session: SessionDep, who: CallerDep, log_id: int
) -> ExerciseDeletedResponse:
    try:
        return await exercise_domain.delete_exercise(session, subject=who.subject, log_id=log_id)
    except exercise_domain.ExerciseLogNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class RecentMealOut(BaseModel):
    log_id: int
    date: str
    ts: str
    meal: str | None
    planned: bool
    notes: str | None
    kcal: float
    items: list[SummaryItemOut]


class RecentMealsResponse(BaseModel):
    days: int
    meals: list[RecentMealOut]
    language: str
    server_time: ServerTime


@router.get("/logs/meals")
async def recent_meals(
    session: SessionDep,
    who: CallerDep,
    days: Annotated[int, Query(ge=1, le=summary_domain.MAX_RECENT_DAYS)] = 7,
) -> RecentMealsResponse:
    try:
        return await summary_domain.recent_meals(session, subject=who.subject, days=days)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class LogDeletedResponse(BaseModel):
    deleted_log_id: int
    day_totals: DayTotals
    server_time: ServerTime


@router.delete("/logs/meals/{log_id}")
async def delete_log(session: SessionDep, who: CallerDep, log_id: int) -> LogDeletedResponse:
    try:
        return await meals_domain.delete_log(session, subject=who.subject, log_id=log_id)
    except meals_domain.LogNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.patch("/logs/meals/{log_id}")
async def revise_log(
    session: SessionDep, who: CallerDep, log_id: int, body: MealLogRevise
) -> MealLogResponse:
    try:
        return await meals_domain.revise_log(
            session, subject=who.subject, log_id=log_id, changes=body.changes
        )
    except meals_domain.InvalidLog as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        meals_domain.UnknownFood,
        meals_domain.LogNotFound,
        templates_domain.TemplateNotFound,
    ) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class TemplateItemIn(BaseModel):
    food_id: int
    grams: float = Field(gt=0)


class TemplateCreate(BaseModel):
    name: str
    items: list[TemplateItemIn] = Field(min_length=1)
    total_grams: float | None = Field(default=None, gt=0)


class TemplateItemOut(BaseModel):
    food_id: int
    grams: float


class TemplateSavedResponse(BaseModel):
    template_id: int
    name: str
    total_grams: float | None
    created: bool
    items: list[TemplateItemOut]
    server_time: ServerTime


class TemplateListItemOut(BaseModel):
    food_id: int
    name: str | None
    grams: float
    per_100g: Per100g
    kcal: float | None


class TemplateOut(BaseModel):
    template_id: int
    name: str
    total_grams: float | None
    kcal: float | None
    use_count: int
    last_used_at: str | None
    items: list[TemplateListItemOut]


class TemplatesResponse(BaseModel):
    templates: list[TemplateOut]
    language: str
    server_time: ServerTime


@router.post("/templates", status_code=201)
async def save_template(
    session: SessionDep, who: CallerDep, body: TemplateCreate
) -> TemplateSavedResponse:
    try:
        return await templates_domain.save_template(
            session,
            subject=who.subject,
            name=body.name,
            items=[item.model_dump() for item in body.items],
            total_grams=body.total_grams,
        )
    except templates_domain.InvalidTemplate as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class TemplateRevise(BaseModel):
    changes: dict[str, Any]


@router.patch("/templates/{template_id}")
async def revise_template(
    session: SessionDep, who: CallerDep, template_id: int, body: TemplateRevise
) -> TemplateSavedResponse:
    try:
        return await templates_domain.revise_template(
            session, subject=who.subject, template_id=template_id, changes=body.changes
        )
    except templates_domain.InvalidTemplate as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except templates_domain.TemplateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class TemplateDeletedResponse(BaseModel):
    deleted_template_id: int
    server_time: ServerTime


@router.delete("/templates/{template_id}")
async def delete_template(
    session: SessionDep, who: CallerDep, template_id: int
) -> TemplateDeletedResponse:
    try:
        return await templates_domain.delete_template(
            session, subject=who.subject, template_id=template_id
        )
    except templates_domain.TemplateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


@router.get("/templates")
async def list_templates(session: SessionDep, who: CallerDep) -> TemplatesResponse:
    try:
        return await templates_domain.list_templates(session, subject=who.subject)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class WeightPointOut(BaseModel):
    date: str
    weight_kg: float | None
    waist_cm: float | None
    notes: str | None


class SmoothedPointOut(BaseModel):
    date: str
    weight_kg: float


class WeightHistoryResponse(BaseModel):
    days: int
    points: list[WeightPointOut]
    smoothed: list[SmoothedPointOut]
    rate_kg_per_week: float | None
    server_time: ServerTime


@router.get("/logs/weight")
async def weight_history(
    session: SessionDep,
    who: CallerDep,
    days: Annotated[int, Query(ge=1, le=stats_domain.MAX_WEIGHT_DAYS)] = 30,
) -> WeightHistoryResponse:
    try:
        return await stats_domain.weight_history(session, subject=who.subject, days=days)
    except stats_domain.InvalidQuery as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class TdeeWindowOut(BaseModel):
    start: str
    end: str
    days: int


class TdeeCoverageOut(BaseModel):
    logged_days: int
    required_days: int
    weigh_in_days: int


class TdeeInputsOut(BaseModel):
    intake_avg_kcal: float | None
    weight_trend_start_kg: float | None
    weight_trend_end_kg: float | None
    weight_change_kg: float | None


class TdeeBlock(BaseModel):
    tdee_kcal: int | None
    confidence: str | None
    reasons: list[str]
    window: TdeeWindowOut
    coverage: TdeeCoverageOut
    inputs: TdeeInputsOut


class TdeeResponse(TdeeBlock):
    server_time: ServerTime


@router.get("/stats/tdee")
async def get_tdee(session: SessionDep, who: CallerDep) -> TdeeResponse:
    try:
        return await stats_domain.get_tdee(session, subject=who.subject)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class ReviewWeekOut(BaseModel):
    week_start: str
    week_end: str
    partial: bool
    days_logged: int
    days_in_week: int
    kcal_avg: float | None
    kcal_target_avg: float | None
    kcal_delta_avg: float | None
    targeted_days: int
    protein_avg_g: float | None
    protein_target_avg_g: float | None
    weight_trend_start_kg: float | None
    weight_trend_end_kg: float | None
    weight_change_kg: float | None
    sessions: int
    cardio_min: float
    exercise_kcal: float
    strength_sets: int
    strength_volume_kg: float


class WeeklyReviewResponse(BaseModel):
    weeks: list[ReviewWeekOut]
    tdee: TdeeBlock
    active_phase: GoalPhaseOut | None
    profile_context: ProfileContextOut
    server_time: ServerTime


@router.get("/stats/review")
async def weekly_review(
    session: SessionDep,
    who: CallerDep,
    weeks: Annotated[int, Query(ge=1, le=stats_domain.MAX_WEEKS)] = 4,
) -> WeeklyReviewResponse:
    try:
        return await stats_domain.weekly_review(session, subject=who.subject, weeks=weeks)
    except stats_domain.InvalidQuery as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class TrainingWeekOut(BaseModel):
    week_start: str
    week_end: str
    partial: bool
    sessions: int
    cardio_min: float
    exercise_kcal: float
    strength_sets: int
    strength_volume_kg: float


class TopSetOut(BaseModel):
    reps: int
    weight_kg: float
    rpe: float | None


class ProgressionSessionOut(BaseModel):
    date: str
    log_id: int
    sets: int
    top_set: TopSetOut | None
    e5rm_kg: float | None


class TrainingExerciseOut(BaseModel):
    name: str
    sessions: list[ProgressionSessionOut]


class TrainingHistoryResponse(BaseModel):
    weeks: list[TrainingWeekOut]
    exercises: list[str]
    exercise: TrainingExerciseOut | None
    server_time: ServerTime


@router.get("/stats/training")
async def training_history(
    session: SessionDep,
    who: CallerDep,
    exercise: Annotated[str | None, Query()] = None,
    weeks: Annotated[int, Query(ge=1, le=stats_domain.MAX_WEEKS)] = 8,
) -> TrainingHistoryResponse:
    try:
        return await stats_domain.training_history(
            session, subject=who.subject, exercise=exercise, weeks=weeks
        )
    except stats_domain.InvalidQuery as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except stats_domain.UnknownExercise as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc


class AccountDeleteRequest(BaseModel):
    nickname: str = Field(
        description="The account's nickname, typed by the user as confirmation. "
        "Checked server-side; a mismatch deletes nothing."
    )


class AccountDeletedResponse(BaseModel):
    deleted: bool
    nickname: str
    erased: dict[str, int]
    server_time: ServerTime


@router.get("/export")
async def export_account(session: SessionDep, who: CallerDep) -> Response:
    """The whole account as a zip: manifest, lossless data.json, and CSVs.

    The one deliberately untyped response in this file: it is a binary
    download, excluded from the generated client by nature — the profile page
    fetches it by hand with the same bearer header. The MCP twin
    `export_my_data` returns the identical dataset as JSON; both are
    renderings of `domain/export.py`'s one dataset. Read-only, so unlike
    DELETE /account there is no credential-shape guard: either surface's
    credential may export.
    """
    try:
        dataset = await export_domain.export_account(session, subject=who.subject)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
    content, filename = export_domain.build_zip(dataset)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/account")
async def delete_account(
    session: SessionDep, who: WebCallerDep, body: AccountDeleteRequest
) -> AccountDeletedResponse:
    """The Annos half of account deletion — the web page calls this first,
    then has Better Auth delete the identity (user, sessions, OAuth grants)
    on its own side. Web-only by credential shape; no MCP tool exists."""
    try:
        return await account_domain.delete_account(
            session, subject=who.subject, nickname=body.nickname
        )
    except account_domain.NicknameMismatch as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
