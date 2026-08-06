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

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from annos import nickname as nickname_mod
from annos import servertime
from annos.db import get_session
from annos.domain import body as body_domain
from annos.domain import foods as foods_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.domain import summary as summary_domain
from annos.identity import AuthError, Caller, resolve_caller

router = APIRouter()


async def caller(authorization: Annotated[str | None, Header()] = None) -> Caller:
    try:
        return await resolve_caller(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CallerDep = Annotated[Caller, Depends(caller)]
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
    dietary_prefs: dict[str, Any]
    coaching_notes: str | None
    server_time: ServerTime


class LoggedItemOut(BaseModel):
    food_id: int
    grams: float
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
    kcal: float | None


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


class DailySummaryResponse(BaseModel):
    date: str
    day_type: str
    totals: DayTotals
    target: TargetOut | None
    remaining: RemainingOut | None
    meals: list[SummaryMealOut]
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
    protein_target_g: int
    rate_target_kg_per_week: float | None
    server_time: ServerTime
    closed_previous: ClosedPhaseOut | None = None


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
    except profile_domain.UnknownField as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
    return _profile_payload(profile)


class MealItem(BaseModel):
    food_id: int
    grams: float = Field(gt=0)


class MealLogCreate(BaseModel):
    items: list[MealItem] = Field(min_length=1)
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
            items=[item.model_dump() for item in body.items],
            meal=body.meal,
            ts=body.ts,
            input_mode=body.input_mode,
            notes=body.notes,
        )
    except meals_domain.InvalidLog as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except meals_domain.UnknownFood as exc:
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
    protein_g: int
    rate_target: float | None = None
    start_date: str | None = None


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
            protein_g=body.protein_g,
            rate_target=body.rate_target,
            start_date=body.start_date,
        )
    except body_domain.InvalidPhase as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    except (meals_domain.UnknownFood, meals_domain.LogNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
