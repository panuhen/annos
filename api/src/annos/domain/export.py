"""Everything the caller owns, in one pass — GDPR Art. 20, and just as
deliberately the migration path out: an honest small service makes leaving easy.

The dataset is the read-side mirror of `domain/account.py`'s wipe: every table
the wipe erases appears here as a section, and `counts` uses the same
table-name keys as the wipe's receipt — export-then-delete hands the user two
receipts whose numbers match. CSV rendering and zip assembly live here too,
because they are deterministic serialisations of the dataset, not adapter
logic: the MCP tool returns the dataset as JSON, the REST route returns the
zip, and neither surface owns any shaping the other lacks.

Nothing global rides along (Fineli foods, the activity catalog, unit types are
not the user's data — log rows are self-contained through their snapshots and
resolved names), and nothing crosses the auth seam: the email lives in Better
Auth and is served from there, never joined into this payload.
"""

import csv
import io
import json
import zipfile
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from annos import servertime
from annos.domain import language as language_domain
from annos.domain import meals as meals_domain
from annos.domain import profile as profile_domain
from annos.models import (
    BodyMetric,
    CoachingNoteRevision,
    DayTypeMark,
    Exercise,
    ExerciseLog,
    Food,
    GoalPhase,
    MealLog,
    MealTemplate,
    UserProfile,
)

# Bumped only when the dataset's shape changes incompatibly; a future importer
# keys on it.
EXPORT_FORMAT = 1


def _num(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


def _name(food: Food, language: str) -> tuple[str | None, str | None]:
    names = {"fi": food.name_fi, "sv": food.name_sv, "en": food.name_en}
    return language_domain.resolve(names, language)


async def export_account(session: AsyncSession, *, subject: str) -> dict:
    """The canonical dataset: everything Annos holds for this subject.

    Sections run chronologically — an archive reads forward. Every timestamp
    carries its UTC instant and the calendar date in the profile timezone, so
    spreadsheet grouping matches what the day sheet showed. Food names resolve
    into the profile language exactly as every other read view does; the raw
    per-100g snapshots ride along untouched so nothing is lossy.
    """
    profile = await profile_domain.get_profile(session, subject=subject)
    tz = profile.timezone
    language = profile.language

    meal_logs = (
        await session.scalars(
            select(MealLog).where(MealLog.subject == subject).order_by(MealLog.ts, MealLog.id)
        )
    ).all()
    meals = []
    for log in meal_logs:
        items = []
        for item in log.items:
            name, name_language = _name(item.food, language)
            items.append(
                {
                    "food_id": item.food_id,
                    "food_name": name,
                    "food_name_language": name_language,
                    "food_source": item.food.source,
                    "grams": _num(item.grams),
                    "portion_estimated": item.estimated,
                    # Portion macros, same arithmetic as every read view …
                    "kcal": meals_domain._portion(item.kcal, item.grams),
                    "protein_g": meals_domain._portion(item.protein_g, item.grams),
                    "carbs_g": meals_domain._portion(item.carbs_g, item.grams),
                    "fat_g": meals_domain._portion(item.fat_g, item.grams),
                    "fiber_g": meals_domain._portion(item.fiber_g, item.grams),
                    # … and the raw log-time snapshot, so the export is lossless.
                    "per_100g": {
                        "kcal": _num(item.kcal),
                        "protein_g": _num(item.protein_g),
                        "carbs_g": _num(item.carbs_g),
                        "fat_g": _num(item.fat_g),
                        "fiber_g": _num(item.fiber_g),
                    },
                }
            )
        meals.append(
            {
                "log_id": log.id,
                "ts_utc": log.ts.isoformat(),
                "date_local": servertime.local_date(tz, log.ts),
                "meal": log.meal,
                "planned": log.planned,
                "input_mode": log.input_mode,
                "notes": log.notes,
                "items": items,
            }
        )

    exercise_logs = (
        await session.scalars(
            select(ExerciseLog)
            .where(ExerciseLog.subject == subject)
            .order_by(ExerciseLog.ts, ExerciseLog.id)
        )
    ).all()
    sessions = [
        {
            "log_id": log.id,
            "ts_utc": log.ts.isoformat(),
            "date_local": servertime.local_date(tz, log.ts),
            "kind": log.kind,
            "activity_id": log.activity_id,
            "activity_name": log.activity.name if log.activity is not None else None,
            "activity_met": _num(log.activity.met) if log.activity is not None else None,
            "duration_min": _num(log.duration_min),
            "bodyweight_kg": _num(log.weight_kg),
            "kcal_estimate": _num(log.kcal_estimate),
            "planned": log.planned,
            "source": log.source,
            "notes": log.notes,
            "sets": [
                {
                    "exercise_id": s.exercise_id,
                    "exercise": s.exercise.name,
                    "set_no": s.set_no,
                    "reps": s.reps,
                    "weight_kg": _num(s.weight_kg),
                    "rpe": _num(s.rpe),
                }
                for s in log.sets
            ],
        }
        for log in exercise_logs
    ]

    metrics = (
        await session.scalars(
            select(BodyMetric).where(BodyMetric.subject == subject).order_by(BodyMetric.date)
        )
    ).all()
    weights = [
        {
            "date": m.date.isoformat(),
            "weight_kg": _num(m.weight_kg),
            "waist_cm": _num(m.waist_cm),
            "notes": m.notes,
        }
        for m in metrics
    ]

    phases = (
        await session.scalars(
            select(GoalPhase).where(GoalPhase.subject == subject).order_by(GoalPhase.start_date)
        )
    ).all()
    goal_phases = [
        {
            "phase_id": p.id,
            "kind": p.kind,
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat() if p.end_date is not None else None,
            "kcal_target_training": p.kcal_target_training,
            "kcal_target_rest": p.kcal_target_rest,
            "protein_target_training": p.protein_target_training,
            "protein_target_rest": p.protein_target_rest,
            "rate_target_kg_per_week": _num(p.rate_target_kg_per_week),
        }
        for p in phases
    ]

    marks = (
        await session.scalars(
            select(DayTypeMark).where(DayTypeMark.subject == subject).order_by(DayTypeMark.date)
        )
    ).all()
    # Manual marks only: derived training days are computed at read time, and
    # exporting them would freeze a judgment the data doesn't hold.
    day_types = [{"date": m.date.isoformat(), "day_type": m.day_type} for m in marks]

    template_rows = (
        await session.scalars(
            select(MealTemplate).where(MealTemplate.subject == subject).order_by(MealTemplate.name)
        )
    ).all()
    # Template items carry no food relationship (they store ids and grams
    # only), so the names resolve through one lookup over the referenced foods.
    template_food_ids = {item.food_id for t in template_rows for item in t.items}
    template_foods = {
        f.id: f
        for f in (await session.scalars(select(Food).where(Food.id.in_(template_food_ids)))).all()
    }
    templates = []
    for t in template_rows:
        t_items = []
        for item in t.items:
            food = template_foods.get(item.food_id)
            name, name_language = _name(food, language) if food else (None, None)
            t_items.append(
                {
                    "food_id": item.food_id,
                    "food_name": name,
                    "food_name_language": name_language,
                    "grams": _num(item.grams),
                }
            )
        templates.append(
            {
                "template_id": t.id,
                "name": t.name,
                "total_grams": _num(t.total_grams),
                "use_count": t.use_count,
                "last_used_at_utc": t.last_used_at.isoformat() if t.last_used_at else None,
                "items": t_items,
            }
        )

    foods = (
        await session.scalars(select(Food).where(Food.owner_id == subject).order_by(Food.id))
    ).all()
    own_foods = [
        {
            "food_id": f.id,
            "name_fi": f.name_fi,
            "name_sv": f.name_sv,
            "name_en": f.name_en,
            "source": f.source,
            "fineli_id": f.fineli_id,
            "per_100g": {
                "kcal": _num(f.kcal),
                "protein_g": _num(f.protein_g),
                "carbs_g": _num(f.carbs_g),
                "fat_g": _num(f.fat_g),
                "fiber_g": _num(f.fiber_g),
            },
            "micros": f.micros,
            "serving_units": [
                {"unit_code": u.unit_code, "grams": _num(u.grams)} for u in f.serving_units
            ],
        }
        for f in foods
    ]

    movements = (
        await session.scalars(
            select(Exercise).where(Exercise.owner_id == subject).order_by(Exercise.name)
        )
    ).all()
    exercises = [
        {"exercise_id": e.id, "name": e.name, "muscle_group": e.muscle_group} for e in movements
    ]

    revisions = (
        await session.scalars(
            select(CoachingNoteRevision)
            .where(CoachingNoteRevision.subject == subject)
            .order_by(CoachingNoteRevision.id)
        )
    ).all()
    coaching_history = [
        {"set_at_utc": r.created_at.isoformat(), "notes": r.notes} for r in revisions
    ]

    return {
        "export_format": EXPORT_FORMAT,
        "nickname": profile.nickname,
        "profile": {
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
            "created_at_utc": profile.created_at.isoformat(),
        },
        "coaching_history": coaching_history,
        "meals": meals,
        "exercise_sessions": sessions,
        "weights": weights,
        "goal_phases": goal_phases,
        "day_types": day_types,
        "templates": templates,
        "own_foods": own_foods,
        "exercises": exercises,
        # Same keys as the deletion receipt's `erased`, deliberately: the two
        # receipts must be comparable number for number.
        "counts": {
            UserProfile.__tablename__: 1,
            MealLog.__tablename__: len(meals),
            MealTemplate.__tablename__: len(templates),
            ExerciseLog.__tablename__: len(sessions),
            Exercise.__tablename__: len(exercises),
            Food.__tablename__: len(own_foods),
            BodyMetric.__tablename__: len(weights),
            GoalPhase.__tablename__: len(goal_phases),
            DayTypeMark.__tablename__: len(day_types),
            CoachingNoteRevision.__tablename__: len(coaching_history),
        },
        "server_time": servertime.echo(tz),
    }


def _cell(value: object) -> object:
    """Booleans as lowercase words: csv would print Python's True/False."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _sheet(header: list[str], rows: list[list[object]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return out.getvalue()


def render_csvs(dataset: dict) -> dict[str, str]:
    """Flat spreadsheet views of the dataset, one file per section.

    One row per *item* where the section nests (meals, templates, sets), with
    the parent's fields denormalized onto every row — a spreadsheet reader
    filters and sums, it doesn't join. Headers are English and stable: they
    are a machine contract, like unit codes. The profile itself is deliberately
    absent — one row of JSON-stuffed cells serves nobody; it lives in data.json.
    """
    files: dict[str, str] = {}

    files["meals.csv"] = _sheet(
        [
            "log_id",
            "ts_utc",
            "date_local",
            "meal",
            "planned",
            "input_mode",
            "notes",
            "food_id",
            "food_name",
            "food_name_language",
            "food_source",
            "grams",
            "portion_estimated",
            "kcal",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
        ],
        [
            [
                m["log_id"],
                m["ts_utc"],
                m["date_local"],
                m["meal"],
                m["planned"],
                m["input_mode"],
                m["notes"],
                i["food_id"],
                i["food_name"],
                i["food_name_language"],
                i["food_source"],
                i["grams"],
                i["portion_estimated"],
                i["kcal"],
                i["protein_g"],
                i["carbs_g"],
                i["fat_g"],
                i["fiber_g"],
            ]
            for m in dataset["meals"]
            for i in m["items"]
        ],
    )

    files["exercise_sessions.csv"] = _sheet(
        [
            "log_id",
            "ts_utc",
            "date_local",
            "kind",
            "activity_id",
            "activity_name",
            "activity_met",
            "duration_min",
            "bodyweight_kg",
            "kcal_estimate",
            "planned",
            "source",
            "notes",
        ],
        [
            [
                s["log_id"],
                s["ts_utc"],
                s["date_local"],
                s["kind"],
                s["activity_id"],
                s["activity_name"],
                s["activity_met"],
                s["duration_min"],
                s["bodyweight_kg"],
                s["kcal_estimate"],
                s["planned"],
                s["source"],
                s["notes"],
            ]
            for s in dataset["exercise_sessions"]
        ],
    )

    files["strength_sets.csv"] = _sheet(
        [
            "log_id",
            "ts_utc",
            "date_local",
            "exercise_id",
            "exercise",
            "set_no",
            "reps",
            "weight_kg",
            "rpe",
        ],
        [
            [
                s["log_id"],
                s["ts_utc"],
                s["date_local"],
                x["exercise_id"],
                x["exercise"],
                x["set_no"],
                x["reps"],
                x["weight_kg"],
                x["rpe"],
            ]
            for s in dataset["exercise_sessions"]
            for x in s["sets"]
        ],
    )

    files["weights.csv"] = _sheet(
        ["date", "weight_kg", "waist_cm", "notes"],
        [[w["date"], w["weight_kg"], w["waist_cm"], w["notes"]] for w in dataset["weights"]],
    )

    files["goal_phases.csv"] = _sheet(
        [
            "phase_id",
            "kind",
            "start_date",
            "end_date",
            "kcal_target_training",
            "kcal_target_rest",
            "protein_target_training",
            "protein_target_rest",
            "rate_target_kg_per_week",
        ],
        [
            [
                p["phase_id"],
                p["kind"],
                p["start_date"],
                p["end_date"],
                p["kcal_target_training"],
                p["kcal_target_rest"],
                p["protein_target_training"],
                p["protein_target_rest"],
                p["rate_target_kg_per_week"],
            ]
            for p in dataset["goal_phases"]
        ],
    )

    files["day_types.csv"] = _sheet(
        ["date", "day_type"],
        [[d["date"], d["day_type"]] for d in dataset["day_types"]],
    )

    files["templates.csv"] = _sheet(
        [
            "template_id",
            "name",
            "total_grams",
            "use_count",
            "last_used_at_utc",
            "food_id",
            "food_name",
            "food_name_language",
            "grams",
        ],
        [
            [
                t["template_id"],
                t["name"],
                t["total_grams"],
                t["use_count"],
                t["last_used_at_utc"],
                i["food_id"],
                i["food_name"],
                i["food_name_language"],
                i["grams"],
            ]
            for t in dataset["templates"]
            for i in t["items"]
        ],
    )

    files["own_foods.csv"] = _sheet(
        [
            "food_id",
            "name_fi",
            "name_sv",
            "name_en",
            "source",
            "fineli_id",
            "kcal",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
            "micros",
            "serving_units",
        ],
        [
            [
                f["food_id"],
                f["name_fi"],
                f["name_sv"],
                f["name_en"],
                f["source"],
                f["fineli_id"],
                f["per_100g"]["kcal"],
                f["per_100g"]["protein_g"],
                f["per_100g"]["carbs_g"],
                f["per_100g"]["fat_g"],
                f["per_100g"]["fiber_g"],
                json.dumps(f["micros"], ensure_ascii=False, separators=(",", ":"))
                if f["micros"]
                else None,
                ";".join(f"{u['unit_code']}={u['grams']}" for u in f["serving_units"]) or None,
            ]
            for f in dataset["own_foods"]
        ],
    )

    files["exercises.csv"] = _sheet(
        ["exercise_id", "name", "muscle_group"],
        [[e["exercise_id"], e["name"], e["muscle_group"]] for e in dataset["exercises"]],
    )

    files["coaching_history.csv"] = _sheet(
        ["set_at_utc", "notes"],
        [[r["set_at_utc"], r["notes"]] for r in dataset["coaching_history"]],
    )

    return files


def build_zip(dataset: dict) -> tuple[bytes, str]:
    """The download artifact: manifest + lossless JSON + spreadsheet CSVs.

    CSVs are comma-separated UTF-8 with a BOM — the interoperable choice for a
    migration artifact; the BOM keeps umlauts intact in Excel (Finnish-locale
    Excel still wants File → Import, an accepted cost). The manifest repeats
    the counts so "what's in here" never requires parsing the data itself.
    """
    manifest = {key: dataset[key] for key in ("export_format", "nickname", "counts", "server_time")}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("data.json", json.dumps(dataset, ensure_ascii=False, indent=2))
        for name, text in render_csvs(dataset).items():
            archive.writestr(f"csv/{name}", "\ufeff" + text)
    filename = f"annos-export-{dataset['server_time']['local_date']}.zip"
    return buffer.getvalue(), filename
