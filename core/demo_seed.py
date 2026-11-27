"""
core/demo_seed.py - Jeu de données de démonstration réaliste (5 élèves tests)
pour visualiser immédiatement l'ensemble des graphiques (ACWR, EWMA, Monotonie,
Stress tendineux, Dérive technique, Perte de vitesse) en local et sur Streamlit Cloud.
"""

from datetime import datetime, timedelta, timezone
import random
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.auth import hash_password
from core.load_quantification import compute_set_load_bundle


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


DEMO_ATHLETES_PROFILES: List[Dict[str, Any]] = [
    {
        "username": "eleve_demo",
        "legacy_aliases": ["lve_dmo", "Élève Démo"],
        "full_name": "Élève Démo",
        "bodyweight_kg": 70.0,
        "freq": "4x / semaine",
        "goal": "Progression Muscle-up & Planche",
        "profile_kind": "demo_21d",
    },
    {
        "username": "lucas_martin",
        "full_name": "Lucas Martin",
        "bodyweight_kg": 71.5,
        "freq": "4x / semaine",
        "goal": "Full Planche 8s & Straddle Press (Profil Sweet Spot)",
        "profile_kind": "sweet_spot",
    },
    {
        "username": "sarah_benali",
        "full_name": "Sarah Benali",
        "bodyweight_kg": 58.0,
        "freq": "4x / semaine",
        "goal": "Muscle-ups stricts & Streetlifting lesté (Profil Force Dynamique)",
        "profile_kind": "dynamic_strength",
    },
    {
        "username": "theo_moreau",
        "full_name": "Théo Moreau",
        "bodyweight_kg": 78.0,
        "freq": "6x / semaine",
        "goal": "Maltese & Iron Cross (Profil Surcharge / Pic d'intensité)",
        "profile_kind": "overreaching",
    },
    {
        "username": "chloe_bernard",
        "full_name": "Chloé Bernard",
        "bodyweight_kg": 61.5,
        "freq": "2-3x / semaine",
        "goal": "Reprise progressive & Front Lever (Profil Sous-charge)",
        "profile_kind": "underload",
    },
    {
        "username": "karim_haddad",
        "full_name": "Karim Haddad",
        "bodyweight_kg": 74.0,
        "freq": "5x / semaine",
        "goal": "Endurance de force Tractions / Dips (Profil Haute Monotonie)",
        "profile_kind": "high_monotony",
    },
]

DEMO_USERNAMES = {p["username"] for p in DEMO_ATHLETES_PROFILES} | {"lve_dmo"}


def _generate_logs_for_profile(
    profile_kind: str,
    bodyweight_kg: float,
    now: datetime,
) -> List[Dict[str, Any]]:
    """Génère un historique cohérent sur 35 jours adapté à chaque profil physiologique."""
    rng = random.Random(hash(profile_kind) & 0xFFFFFFFF)
    logs: List[Dict[str, Any]] = []

    def add_log(
        days_ago: int,
        hour: int,
        exercise: str,
        exo_type: str,
        reps: int,
        tut: float,
        added_kg: float,
        rpe: float,
        drift_deg: float = None,
        vel_loss: float = None,
        notes: str = "",
    ) -> None:
        dt = (now - timedelta(days=days_ago)).replace(hour=hour, minute=rng.choice([0, 15, 30, 45]), second=0, microsecond=0)
        bundle = compute_set_load_bundle(
            exercise=exercise,
            exo_type=exo_type,
            tut_effective_sec=tut,
            reps=reps,
            added_load_kg=added_kg,
            bodyweight_kg=bodyweight_kg,
            rpe=rpe,
        )
        logs.append(
            {
                "date": dt,
                "exercise": exercise,
                "exercise_type": exo_type,
                "reps": reps,
                "tut_effective_sec": round(tut, 2),
                "added_load_kg": round(added_kg, 1),
                "bodyweight_kg": bodyweight_kg,
                "difficulty_coef": bundle["difficulty_coef"],
                "external_load_au": bundle["external_load_au"],
                "rpe": round(rpe, 1),
                "srpe_load": bundle["srpe_load"],
                "fatigue_drift_deg": round(drift_deg, 2) if drift_deg is not None else None,
                "velocity_loss_pct": round(vel_loss, 2) if vel_loss is not None else None,
                "notes": notes,
            }
        )

    if profile_kind == "demo_21d":
        # 15 séances réalistes réparties sur 21 jours pour Élève Démo
        demo_schedule = [21, 19, 18, 16, 15, 13, 12, 10, 9, 7, 6, 4, 3, 2, 1]
        for idx, d in enumerate(demo_schedule):
            prog = idx / max(1, len(demo_schedule) - 1)
            if idx % 3 == 0:
                add_log(
                    d, 18, "Straddle Planche", "isometric", 0,
                    tut=round(7.5 + prog * 4.0 + rng.uniform(-0.4, 0.5), 1),
                    added_kg=0.0,
                    rpe=7.5 + rng.uniform(-0.3, 0.4),
                    drift_deg=4.0 - prog * 1.1,
                    notes="Tenue propre, gainage verrouillé",
                )
            elif idx % 3 == 1:
                add_log(
                    d, 18, "Muscle-ups", "dynamic",
                    reps=4 + (idx % 3),
                    tut=round(14.0 + prog * 3.5, 1),
                    added_kg=0.0 if idx < 7 else 2.5,
                    rpe=7.8,
                    vel_loss=14.0 + rng.uniform(-2.0, 4.0),
                    notes="Tirage haut explosif",
                )
            else:
                add_log(
                    d, 19, "Front Lever", "isometric", 0,
                    tut=round(9.0 + prog * 4.5, 1),
                    added_kg=0.0,
                    rpe=7.2 + rng.uniform(-0.3, 0.4),
                    drift_deg=3.5 - prog * 0.8,
                    notes="Épaules déprimées, alignement propre",
                )

    elif profile_kind == "sweet_spot":
        # Progression régulière dans la zone optimale ACWR (0.95 - 1.20)
        training_days = [34, 32, 30, 28, 26, 24, 22, 20, 18, 16, 14, 12, 10, 8, 6, 4, 2, 1]
        for idx, d in enumerate(training_days):
            prog = idx / max(1, len(training_days) - 1)
            add_log(
                d, 18, "Straddle Planche", "isometric", 0,
                tut=9.0 + prog * 4.5 + rng.uniform(-0.8, 0.8),
                added_kg=0.0,
                rpe=7.2 + rng.uniform(-0.4, 0.6),
                drift_deg=4.2 - prog * 1.4 + rng.uniform(-0.5, 0.5),
                notes="Tenue propre, protraction stable",
            )
            add_log(
                d, 18, "Planche Push-ups", "dynamic",
                reps=4 + int(prog * 2),
                tut=14.0 + prog * 4.0,
                added_kg=0.0,
                rpe=7.5 + rng.uniform(-0.3, 0.5),
                vel_loss=14.0 + rng.uniform(-3.0, 4.0),
                notes="Contrôle excentrique 2s",
            )
            if idx % 2 == 0:
                add_log(
                    d, 19, "Full Planche", "isometric", 0,
                    tut=4.0 + prog * 2.5,
                    added_kg=0.0,
                    rpe=8.3 + rng.uniform(-0.3, 0.4),
                    drift_deg=5.1 - prog * 1.5,
                    notes="Tentative max en début de bloc",
                )

    elif profile_kind == "dynamic_strength":
        # Streetlifting lesté et mouvements dynamiques avec suivi de perte de vitesse
        training_days = [33, 31, 29, 27, 24, 22, 20, 17, 15, 13, 10, 8, 6, 4, 1]
        for idx, d in enumerate(training_days):
            prog = idx / max(1, len(training_days) - 1)
            add_log(
                d, 17, "Muscle-ups", "dynamic",
                reps=5 + (idx % 3),
                tut=16.0 + rng.uniform(-1.5, 2.0),
                added_kg=round(2.5 + prog * 5.0, 1),
                rpe=7.8 + rng.uniform(-0.4, 0.6),
                vel_loss=15.0 + rng.uniform(-4.0, 6.0),
                notes="Passage explosif sans kipping",
            )
            add_log(
                d, 18, "Tractions", "dynamic",
                reps=6,
                tut=18.0 + rng.uniform(-1.0, 2.0),
                added_kg=round(15.0 + prog * 10.0, 1),
                rpe=8.2 + rng.uniform(-0.3, 0.5),
                vel_loss=21.0 + rng.uniform(-4.0, 7.0),
                notes="Série lestée lourde",
            )
            add_log(
                d, 18, "Dips", "dynamic",
                reps=8,
                tut=20.0 + rng.uniform(-1.0, 2.0),
                added_kg=round(20.0 + prog * 12.5, 1),
                rpe=7.6 + rng.uniform(-0.4, 0.5),
                vel_loss=18.0 + rng.uniform(-3.0, 5.0),
                notes="Amplitude complète épaules sous coudes",
            )

    elif profile_kind == "overreaching":
        # Base modérée semaines 1-3, puis pic brutal sur les 7 derniers jours (ACWR > 1.5 + Stress tendineux élevé)
        base_days = [34, 31, 28, 25, 22, 19, 16, 13, 10]
        for d in base_days:
            add_log(
                d, 18, "Full Planche", "isometric", 0,
                tut=7.5 + rng.uniform(-0.5, 1.0),
                added_kg=0.0,
                rpe=7.5,
                drift_deg=4.5 + rng.uniform(-0.5, 0.8),
                notes="Volume d'entretien",
            )
        spike_days = [7, 6, 5, 4, 3, 2, 1, 0]
        for idx, d in enumerate(spike_days):
            add_log(
                d, 17, "Maltese", "isometric", 0,
                tut=12.0 + rng.uniform(1.0, 4.0),
                added_kg=2.5,
                rpe=9.2 + rng.uniform(-0.2, 0.6),
                drift_deg=8.4 + idx * 0.35,
                notes="Fatigue accumulée sur les biceps distaux",
            )
            add_log(
                d, 18, "Iron Cross", "isometric", 0,
                tut=11.0 + rng.uniform(0.5, 3.0),
                added_kg=0.0,
                rpe=9.0 + rng.uniform(-0.2, 0.5),
                drift_deg=7.9 + rng.uniform(0.0, 2.0),
                notes="Anneaux - dérive notable en fin de tenue",
            )
            add_log(
                d, 19, "Hefesto", "dynamic",
                reps=5,
                tut=20.0,
                added_kg=0.0,
                rpe=9.4,
                vel_loss=38.0 + rng.uniform(-2.0, 5.0),
                notes="Grosse perte de vitesse sur les 2 dernières reps",
            )

    elif profile_kind == "underload":
        # Volume soutenu il y a 3-4 semaines, puis très peu de séances récentes (ACWR < 0.75)
        early_days = [34, 32, 30, 28, 26, 24, 22, 20, 18, 16]
        for d in early_days:
            add_log(
                d, 18, "Front Lever", "isometric", 0,
                tut=11.0 + rng.uniform(-1.0, 1.5),
                added_kg=0.0,
                rpe=7.8 + rng.uniform(-0.3, 0.4),
                drift_deg=3.8 + rng.uniform(-0.5, 0.7),
                notes="Bloc volume initial",
            )
            add_log(
                d, 19, "Back Lever", "isometric", 0,
                tut=14.0 + rng.uniform(-1.0, 2.0),
                added_kg=0.0,
                rpe=6.8,
                drift_deg=2.4,
                notes="Gainage fluide",
            )
        recent_days = [11, 5]
        for d in recent_days:
            add_log(
                d, 17, "Pompes", "dynamic",
                reps=12,
                tut=22.0,
                added_kg=0.0,
                rpe=5.5,
                vel_loss=8.0,
                notes="Séance de reprise légère",
            )

    elif profile_kind == "high_monotony":
        # Séances quasi quotidiennes avec charges très similaires (haute monotonie / strain)
        for d in range(28, 0, -1):
            if d % 7 == 0:
                continue  # 6j/7 quasi identiques
            add_log(
                d, 19, "Tractions", "dynamic",
                reps=10,
                tut=24.0 + rng.uniform(-0.4, 0.4),
                added_kg=5.0,
                rpe=7.5,
                vel_loss=24.0 + rng.uniform(-1.0, 1.5),
                notes="Routine quotidienne fixe",
            )
            add_log(
                d, 19, "Dips", "dynamic",
                reps=12,
                tut=25.0 + rng.uniform(-0.4, 0.4),
                added_kg=5.0,
                rpe=7.5,
                vel_loss=22.0 + rng.uniform(-1.0, 1.5),
                notes="Même volume chaque séance",
            )

    return logs


def seed_demo_athletes_and_logs(session: Session, coach_user: Any) -> int:
    """
    Crée les élèves de démonstration (dont Élève Démo avec 15 séances sur 21 jours)
    et insère leurs séances fictives si chacun n'a pas encore de logs d'entraînement.
    Retourne le nombre de logs insérés.
    """
    from core.database import TrainingLog, User

    now = _utcnow()
    inserted_logs = 0

    for prof in DEMO_ATHLETES_PROFILES:
        uname = prof["username"]
        aliases = [uname] + [a.lower() for a in prof.get("legacy_aliases", [])]
        athlete = (
            session.query(User)
            .filter(func.lower(User.username).in_(aliases) | (func.lower(User.full_name) == prof["full_name"].lower()))
            .first()
        )
        if athlete is None:
            athlete = User(
                username=uname,
                full_name=prof["full_name"],
                role="athlete",
                password_hash=hash_password("caliperf123"),
                coach_id=int(coach_user.id),
                invite_code=None,
                bodyweight_kg=float(prof["bodyweight_kg"]),
                freq=prof["freq"],
                goal=prof["goal"],
                is_demo=True,
            )
            session.add(athlete)
            session.flush()
        else:
            if not getattr(athlete, "is_demo", False):
                athlete.is_demo = True
            if athlete.coach_id is None:
                athlete.coach_id = int(coach_user.id)

        ath_logs = session.query(func.count(TrainingLog.id)).filter(TrainingLog.athlete_id == int(athlete.id)).scalar() or 0
        if ath_logs > 0:
            continue

        entries = _generate_logs_for_profile(prof["profile_kind"], float(athlete.bodyweight_kg), now)
        for item in entries:
            session.add(
                TrainingLog(
                    athlete_id=int(athlete.id),
                    coach_id=int(coach_user.id),
                    date=item["date"],
                    exercise=item["exercise"],
                    exercise_type=item["exercise_type"],
                    reps=item["reps"],
                    tut_effective_sec=item["tut_effective_sec"],
                    added_load_kg=item["added_load_kg"],
                    bodyweight_kg=item["bodyweight_kg"],
                    difficulty_coef=item["difficulty_coef"],
                    external_load_au=item["external_load_au"],
                    rpe=item["rpe"],
                    srpe_load=item["srpe_load"],
                    fatigue_drift_deg=item["fatigue_drift_deg"],
                    velocity_loss_pct=item["velocity_loss_pct"],
                    notes=item["notes"],
                )
            )
            inserted_logs += 1

    session.flush()
    return inserted_logs
