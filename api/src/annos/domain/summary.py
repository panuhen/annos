"""The day view: what was eaten, against what target.

A call with no date means *today, server-defined* — the client asking "how am
I doing?" can never be off by a day. The response is arithmetic and facts:
totals, the active phase's target, what remains. Whether the number is good
news is the client's judgment, fed by `profile_context`.

Until exercise logging exists (Phase 2), every day is a rest day and the
payload says so explicitly — a wrong-but-labelled assumption beats a hidden
one.
"""

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import body as body_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.models import MealLog


def _parse_date(value: str | date_type | None, tz: str) -> date_type:
    if value is None:
        return date_type.fromisoformat(servertime.local_date(tz))
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(value)
    except ValueError as exc:
        raise meals_domain.InvalidLog(f"not an ISO 8601 date: {value!r}") from exc


async def daily_summary(
    session: AsyncSession, *, subject: str, date: str | date_type | None = None
) -> dict:
    """One call, the whole day: totals, target, remaining, and the day's logs.

    The `meals` list is compact on purpose — enough for the client to name a
    log ("your 12:40 lunch") and revise it by id without another lookup.
    Planned entries appear in the list but count toward no totals.
    """
    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    day = _parse_date(date, tz)

    totals = await meals_domain.day_totals(
        session, subject=subject, local_date=day.isoformat(), tz=tz
    )

    start, end = meals_domain._day_window(day.isoformat(), tz)
    logs = (
        (
            await session.execute(
                select(MealLog)
                .where(MealLog.subject == subject, MealLog.ts >= start, MealLog.ts < end)
                .order_by(MealLog.ts)
            )
        )
        .scalars()
        .all()
    )

    phase = await body_domain.active_phase(session, subject=subject, on=day)

    # No exercise logging yet, so every day is a rest day — labelled, not
    # hidden, so the client knows why the training target was not used.
    day_type = "rest"

    if phase is not None:
        kcal_target = (
            phase.kcal_target_training if day_type == "training" else phase.kcal_target_rest
        )
        target = {
            "kind": phase.kind,
            "kcal": kcal_target,
            "protein_g": phase.protein_target_g,
            "rate_kg_per_week": (
                float(phase.rate_target_kg_per_week)
                if phase.rate_target_kg_per_week is not None
                else None
            ),
        }
        remaining = {
            "kcal": round(kcal_target - totals["kcal"], 2),
            "protein_g": round(phase.protein_target_g - totals["protein_g"], 2),
        }
    else:
        target = None
        remaining = None

    return {
        "date": day.isoformat(),
        "day_type": day_type,
        "totals": totals,
        "target": target,
        "remaining": remaining,
        "meals": [
            {
                "log_id": log.id,
                "ts": log.ts.isoformat(),
                "meal": log.meal,
                "planned": log.planned,
                "kcal": round(
                    sum(
                        float(item.kcal) * float(item.grams) / 100
                        for item in log.items
                        if item.kcal is not None
                    ),
                    2,
                ),
                "items": len(log.items),
            }
            for log in logs
        ],
        "profile_context": {
            "dietary_prefs": profile.dietary_prefs,
            "coaching_notes": profile.coaching_notes,
        },
        "server_time": servertime.echo(tz),
    }
