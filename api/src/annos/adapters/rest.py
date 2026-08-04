"""REST adapter — what the Next.js UI calls.

Mirrors the MCP tool surface, plus the three endpoints that exist only here:
nickname rolling, profile creation, and account deletion. Those are UI-only so
that a hallucinating client cannot create or destroy an account.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from annos import nickname as nickname_mod
from annos import servertime
from annos.db import get_session
from annos.domain import foods as foods_domain
from annos.domain import profile as profile_domain
from annos.identity import AuthError, Caller, resolve_caller

router = APIRouter()


async def caller(authorization: Annotated[str | None, Header()] = None) -> Caller:
    try:
        return await resolve_caller(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


CallerDep = Annotated[Caller, Depends(caller)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
) -> dict:
    candidates = await foods_domain.find_food(session, subject=who.subject, query=q, limit=limit)
    return {
        "results": [foods_domain.candidate_payload(c) for c in candidates],
        # Echoed on every response so the client is never guessing the date.
        "server_time": servertime.echo("UTC"),
    }


@router.post("/profile/nickname/roll")
async def roll_nickname(who: CallerDep) -> dict:
    """One candidate. Called repeatedly during registration; commits nothing."""
    return {"nickname": nickname_mod.roll()}


@router.post("/profile", status_code=201)
async def create_profile(session: SessionDep, who: CallerDep, body: ProfileCreate) -> dict:
    try:
        profile = await profile_domain.create_profile(
            session, subject=who.subject, nickname=body.nickname
        )
    except nickname_mod.NicknameTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _profile_payload(profile)


@router.get("/profile")
async def get_profile(session: SessionDep, who: CallerDep) -> dict:
    try:
        profile = await profile_domain.get_profile(session, subject=who.subject)
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
    return _profile_payload(profile)


@router.patch("/profile")
async def update_profile(session: SessionDep, who: CallerDep, body: ProfileUpdate) -> dict:
    try:
        profile = await profile_domain.update_profile(
            session, subject=who.subject, changes=body.changes
        )
    except profile_domain.UnknownField as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except profile_domain.ProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="no profile for this account") from exc
    return _profile_payload(profile)
