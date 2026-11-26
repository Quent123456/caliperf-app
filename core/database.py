"""
core/database.py - Persistance relationnelle SQLAlchemy (PostgreSQL Cloud / SQLite local)
pour CaliPerf. Zéro dépendance à Google Sheets / Google Forms.

Tables relationnelles :
- users (coachs & athlètes liés par coach_id et invite_code)
- baselines_3d (bibliothèque 3D scopée par owner_id / is_shared + quality_score)
- training_logs (journal de charge pondérée AU, sRPE, dérive fatigue, vitesse)
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

from core.auth import (
    create_session_token,
    generate_invite_code,
    hash_password,
    is_modern_password_hash,
    normalize_role,
    sanitize_username,
    verify_password,
    verify_session_token,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DIR = os.path.join(PROJECT_ROOT, "data")
SQLITE_DB_PATH = os.path.join(SQLITE_DIR, "caliperf.db")
LEGACY_DB_JSON = os.path.join(PROJECT_ROOT, "caliperf_db.json")
LEGACY_BASELINES_JSON = os.path.join(PROJECT_ROOT, "config", "baselines_3d.json")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==============================================================================
# MODÈLES SQLALCHEMY
# ==============================================================================

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    role = Column(String(20), nullable=False, index=True, default="athlete")  # "coach" | "athlete"
    password_hash = Column(String(256), nullable=False)
    coach_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    invite_code = Column(String(32), unique=True, nullable=True, index=True)
    bodyweight_kg = Column(Float, nullable=False, default=70.0)
    avatar_b64 = Column(Text, nullable=True, default="")
    freq = Column(String(64), nullable=True, default="4x / semaine")
    goal = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class Baseline3D(Base):
    __tablename__ = "baselines_3d"
    __table_args__ = (
        UniqueConstraint("owner_id", "exercise", "camera_view", name="uq_baseline_owner_exo_view"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    is_shared = Column(Boolean, nullable=False, default=True, index=True)
    exercise = Column(String(120), nullable=False, index=True)
    camera_view = Column(String(16), nullable=False)  # "Face" | "3/4" | "Profil"
    type = Column(String(16), nullable=False, default="isometric")  # "isometric" | "dynamic"
    status = Column(String(16), nullable=False, default="empty", index=True)  # "empty" | "calibrated"
    mean_features_json = Column(Text, nullable=True)
    std_features_json = Column(Text, nullable=True)
    rom_bounds_json = Column(Text, nullable=True)
    quality_score = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class TrainingLog(Base):
    __tablename__ = "training_logs"
    __table_args__ = (
        Index("ix_tlogs_athlete_date", "athlete_id", "date"),
        Index("ix_tlogs_coach_date", "coach_id", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    athlete_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    coach_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    date = Column(DateTime, nullable=False, index=True, default=_utcnow)
    exercise = Column(String(120), nullable=False, index=True)
    exercise_type = Column(String(16), nullable=False, default="isometric")
    reps = Column(Integer, nullable=False, default=0)
    tut_effective_sec = Column(Float, nullable=False, default=0.0)
    added_load_kg = Column(Float, nullable=False, default=0.0)
    bodyweight_kg = Column(Float, nullable=False, default=70.0)
    difficulty_coef = Column(Float, nullable=False, default=1.0)
    external_load_au = Column(Float, nullable=False, default=0.0)
    rpe = Column(Float, nullable=False, default=7.0)
    srpe_load = Column(Float, nullable=False, default=0.0)
    fatigue_drift_deg = Column(Float, nullable=True)
    velocity_loss_pct = Column(Float, nullable=True)
    notes = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, nullable=False, default=_utcnow)


# ==============================================================================
# CONNEXION HYBRIDE POSTGRESQL / SQLITE & INITIALISATION
# ==============================================================================

_ENGINE_CACHE: Dict[str, Any] = {}
_INITIALIZED_URLS: set = set()


def resolve_database_url(override_url: Optional[str] = None) -> str:
    """
    Lit DATABASE_URL depuis override/st.secrets/env pour PostgreSQL Cloud (Supabase/Neon),
    avec repli automatique transparent vers sqlite:///data/caliperf.db.
    """
    raw_url = (override_url or "").strip()
    if not raw_url and HAS_STREAMLIT:
        try:
            if hasattr(st, "secrets") and "DATABASE_URL" in st.secrets:
                raw_url = str(st.secrets["DATABASE_URL"]).strip()
        except Exception:
            pass
    if not raw_url:
        raw_url = os.getenv("DATABASE_URL", "").strip()

    if raw_url:
        if raw_url.startswith("postgres://"):
            raw_url = "postgresql+psycopg2://" + raw_url[len("postgres://"):]
        elif raw_url.startswith("postgresql://") and "+psycopg" not in raw_url:
            raw_url = "postgresql+psycopg2://" + raw_url[len("postgresql://"):]
        return raw_url

    os.makedirs(SQLITE_DIR, exist_ok=True)
    sqlite_uri = os.path.abspath(SQLITE_DB_PATH).replace("\\", "/")
    return f"sqlite:///{sqlite_uri}"


def get_engine(db_url: Optional[str] = None):
    """Crée ou récupère le moteur SQLAlchemy configuré (pool_pre_ping pour Cloud DB)."""
    resolved = resolve_database_url(db_url)
    if resolved in _ENGINE_CACHE:
        return _ENGINE_CACHE[resolved]

    is_sqlite = resolved.startswith("sqlite:")
    if is_sqlite:
        engine = create_engine(
            resolved,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    else:
        engine = create_engine(
            resolved,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=5,
            future=True,
        )

    _ENGINE_CACHE[resolved] = engine
    return engine


@contextmanager
def get_db_session(db_url: Optional[str] = None) -> Iterator[Session]:
    """Context manager transactionnel sûr pour toutes les opérations SQL."""
    resolved = resolve_database_url(db_url)
    engine = get_engine(resolved)
    ensure_database_initialized(resolved)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _user_to_dict(u: User) -> Dict[str, Any]:
    return {
        "id": int(u.id),
        "username": str(u.username),
        "full_name": str(u.full_name),
        "role": normalize_role(u.role),
        "coach_id": int(u.coach_id) if u.coach_id is not None else None,
        "invite_code": str(u.invite_code) if u.invite_code else None,
        "bodyweight_kg": float(u.bodyweight_kg or 70.0),
        "avatar_b64": str(u.avatar_b64 or ""),
        "avatar": str(u.avatar_b64 or ""),  # Alias compatibilité UI
        "freq": str(u.freq or "4x / semaine"),
        "goal": str(u.goal or ""),
        "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
    }


def _log_to_dict(log: TrainingLog) -> Dict[str, Any]:
    return {
        "id": int(log.id),
        "athlete_id": int(log.athlete_id),
        "coach_id": int(log.coach_id) if log.coach_id is not None else None,
        "date": log.date.strftime("%Y-%m-%d %H:%M") if log.date else "",
        "date_dt": log.date,
        "exercise": str(log.exercise),
        "exercise_type": str(log.exercise_type),
        "reps": int(log.reps or 0),
        "tut_effective_sec": float(log.tut_effective_sec or 0.0),
        "added_load_kg": float(log.added_load_kg or 0.0),
        "bodyweight_kg": float(log.bodyweight_kg or 70.0),
        "difficulty_coef": float(log.difficulty_coef or 1.0),
        "external_load_au": float(log.external_load_au or 0.0),
        "rpe": float(log.rpe or 7.0),
        "srpe_load": float(log.srpe_load or 0.0),
        "fatigue_drift_deg": float(log.fatigue_drift_deg) if log.fatigue_drift_deg is not None else None,
        "velocity_loss_pct": float(log.velocity_loss_pct) if log.velocity_loss_pct is not None else None,
        "notes": str(log.notes or ""),
        "created_at": log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else "",
    }


def _load_legacy_json_seed() -> Dict[str, Any]:
    """Charge d'éventuelles données historiques locales (utilisateurs / figures) pour migration unique."""
    data: Dict[str, Any] = {}
    if os.path.exists(LEGACY_DB_JSON):
        try:
            with open(LEGACY_DB_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    if (not data.get("baselines_3d")) and os.path.exists(LEGACY_BASELINES_JSON):
        try:
            with open(LEGACY_BASELINES_JSON, "r", encoding="utf-8") as bf:
                b_raw = json.load(bf)
            data["baselines_3d"] = b_raw.get("prototypes", [])
        except Exception:
            pass
    return data


def _unique_invite_code(session: Session) -> str:
    for _ in range(25):
        cand = generate_invite_code()
        exists = session.query(User.id).filter(User.invite_code == cand).first()
        if not exists:
            return cand
    return generate_invite_code("CP")


def ensure_database_initialized(db_url: Optional[str] = None) -> None:
    """Crée le schéma SQL s'il n'existe pas et migre les comptes/baselines initiaux une seule fois."""
    resolved = resolve_database_url(db_url)
    if resolved in _INITIALIZED_URLS:
        return

    engine = get_engine(resolved)
    Base.metadata.create_all(engine)

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    try:
        user_count = session.query(func.count(User.id)).scalar() or 0
        if user_count == 0:
            legacy = _load_legacy_json_seed()
            legacy_users = legacy.get("users", {})
            admin_pwd_raw = str(legacy.get("settings", {}).get("admin_pwd", "admin") or "admin")

            # 1. Créer ou migrer le coach principal 'admin'
            admin_rec = legacy_users.get("admin", {})
            admin_hash = str(admin_rec.get("password_hash", "") or "")
            if not admin_hash or (len(admin_hash) != 64 and not is_modern_password_hash(admin_hash)):
                admin_hash = hash_password(admin_pwd_raw)

            admin_user = User(
                username="admin",
                full_name=str(admin_rec.get("full_name") or "Coach Principal"),
                role="coach",
                password_hash=admin_hash,
                coach_id=None,
                invite_code=_unique_invite_code(session),
                bodyweight_kg=72.0,
                avatar_b64=str(admin_rec.get("avatar") or ""),
                freq="5x / semaine",
                goal="Coaching & Calibration 3D",
            )
            session.add(admin_user)
            session.flush()

            user_map: Dict[str, User] = {"admin": admin_user}

            # 2. Migrer les autres utilisateurs du JSON éventuel
            for uname, udata in legacy_users.items():
                clean_u = sanitize_username(uname)
                if not clean_u or clean_u in user_map:
                    continue
                norm_role = normalize_role(udata.get("role", "athlete"))
                p_hash = str(udata.get("password_hash", "") or "")
                if not p_hash:
                    p_hash = hash_password("caliperf123")
                new_u = User(
                    username=clean_u,
                    full_name=str(udata.get("full_name") or clean_u.capitalize()),
                    role=norm_role,
                    password_hash=p_hash,
                    coach_id=admin_user.id if norm_role == "athlete" else None,
                    invite_code=_unique_invite_code(session) if norm_role == "coach" else None,
                    bodyweight_kg=70.0,
                    avatar_b64=str(udata.get("avatar") or ""),
                )
                session.add(new_u)
                session.flush()
                user_map[clean_u] = new_u

            # 3. Migrer les fiches élèves historiques sans URL Google Forms
            for s_name, s_info in (legacy.get("students", {}) or {}).items():
                base_u = sanitize_username(re.sub(r"\s+", "_", str(s_name))) or "athlete_demo"
                cand_u = base_u
                suffix = 1
                while cand_u in user_map or session.query(User.id).filter(User.username == cand_u).first():
                    cand_u = f"{base_u}_{suffix}"
                    suffix += 1
                stud_u = User(
                    username=cand_u,
                    full_name=str(s_name).strip() or "Élève Démo",
                    role="athlete",
                    password_hash=hash_password("caliperf123"),
                    coach_id=admin_user.id,
                    invite_code=None,
                    bodyweight_kg=70.0,
                    freq=str((s_info or {}).get("freq", "4x / semaine")),
                    goal=str((s_info or {}).get("goal", "")),
                )
                session.add(stud_u)
                session.flush()
                user_map[cand_u] = stud_u

            # 4. Migrer les prototypes/emplacements 3D existants
            seen_slots = set()
            for item in (legacy.get("baselines_3d", []) or []):
                ex_name = str(item.get("exercise", "")).strip()
                c_view = str(item.get("camera_view", "Profil")).strip()
                if not ex_name or c_view not in ("Face", "3/4", "Profil"):
                    continue
                owner_name = sanitize_username(str(item.get("owner", "admin")))
                owner_obj = user_map.get(owner_name, admin_user)
                key_t = (owner_obj.id, ex_name.lower(), c_view)
                if key_t in seen_slots:
                    continue
                seen_slots.add(key_t)

                mf = item.get("mean_features")
                sf = item.get("std_features")
                rb = item.get("rom_bounds")
                mf_json = json.dumps(mf) if isinstance(mf, list) and mf else (str(mf) if str(mf or "").strip() else None)
                sf_json = json.dumps(sf) if isinstance(sf, list) and sf else (str(sf) if str(sf or "").strip() else None)
                rb_json = json.dumps(rb) if isinstance(rb, dict) and rb else (str(rb) if str(rb or "").strip() else None)

                session.add(Baseline3D(
                    owner_id=owner_obj.id,
                    is_shared=bool(item.get("is_master", True)),
                    exercise=ex_name,
                    camera_view=c_view,
                    type="dynamic" if "dyn" in str(item.get("type", "")).lower() else "isometric",
                    status="calibrated" if item.get("status") == "calibrated" and mf_json else "empty",
                    mean_features_json=mf_json,
                    std_features_json=sf_json,
                    rom_bounds_json=rb_json,
                    quality_score=item.get("quality_score"),
                ))

            # 5. Alimenter les 5 élèves tests et leurs historiques d'entraînement
            from core.demo_seed import seed_demo_athletes_and_logs
            seed_demo_athletes_and_logs(session, admin_user)

            session.commit()
        else:
            # Si la base existe déjà sans les 5 élèves tests (ex: migration initiale),
            # injecter les 5 élèves tests manquants pour le coach principal.
            from core.demo_seed import DEMO_ATHLETES_PROFILES, seed_demo_athletes_and_logs
            demo_usernames = [p["username"] for p in DEMO_ATHLETES_PROFILES]
            existing_demo = (
                session.query(func.count(User.id))
                .filter(func.lower(User.username).in_(demo_usernames))
                .scalar()
                or 0
            )
            if existing_demo < len(demo_usernames):
                coach_u = (
                    session.query(User)
                    .filter(User.role == "coach")
                    .order_by(User.id.asc())
                    .first()
                )
                if coach_u is not None:
                    if seed_demo_athletes_and_logs(session, coach_u) > 0:
                        session.commit()

        _INITIALIZED_URLS.add(resolved)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ==============================================================================
# AUTHENTIFICATION, SÉLECTEUR ATHLÈTE & GESTION DES COMPTES SQL
# ==============================================================================

def get_user_by_id(user_id: int, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with get_db_session(db_url) as s:
        u = s.query(User).filter(User.id == int(user_id)).first()
        return _user_to_dict(u) if u else None


def get_user_by_username(username: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    clean_u = sanitize_username(username)
    if not clean_u:
        return None
    with get_db_session(db_url) as s:
        u = s.query(User).filter(func.lower(User.username) == clean_u).first()
        return _user_to_dict(u) if u else None


def authenticate_user_sql(
    username: str,
    password: str,
    db_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Authentifie un utilisateur SQL et met à jour automatiquement un hash legacy en PBKDF2-HMAC."""
    clean_u = sanitize_username(username)
    if not clean_u or not password:
        return None
    with get_db_session(db_url) as s:
        u = s.query(User).filter(func.lower(User.username) == clean_u).first()
        if not u:
            return None
        if not verify_password(password, u.password_hash):
            return None
        if not is_modern_password_hash(u.password_hash):
            u.password_hash = hash_password(password)
            s.flush()
        return _user_to_dict(u)


def register_user_sql(
    username: str,
    password: str,
    role: str,
    full_name: str,
    avatar_b64: str = "",
    invite_code_input: str = "",
    bodyweight_kg: float = 70.0,
    db_url: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Enregistre un nouveau coach ou élève en SQL avec rattachement optionnel via code d'invitation."""
    clean_u = sanitize_username(username)
    if len(clean_u) < 3:
        return False, "L'identifiant doit contenir au moins 3 caractères alphanumériques.", None
    if len((password or "").strip()) < 4:
        return False, "Le mot de passe doit contenir au moins 4 caractères.", None

    norm_role = normalize_role(role)
    clean_full = (full_name or "").strip() or clean_u.capitalize()
    bw = max(25.0, min(250.0, float(bodyweight_kg or 70.0)))

    with get_db_session(db_url) as s:
        existing = s.query(User.id).filter(func.lower(User.username) == clean_u).first()
        if existing:
            return False, f"L'identifiant '{clean_u}' est déjà utilisé.", None

        coach_id: Optional[int] = None
        clean_code = (invite_code_input or "").strip().upper()
        if norm_role == "athlete" and clean_code:
            coach = (
                s.query(User)
                .filter(func.upper(User.invite_code) == clean_code, User.role == "coach")
                .first()
            )
            if not coach:
                return False, f"Code d'invitation coach '{clean_code}' introuvable.", None
            coach_id = coach.id

        new_user = User(
            username=clean_u,
            full_name=clean_full,
            role=norm_role,
            password_hash=hash_password(password),
            coach_id=coach_id,
            invite_code=_unique_invite_code(s) if norm_role == "coach" else None,
            bodyweight_kg=bw,
            avatar_b64=avatar_b64 or "",
        )
        s.add(new_user)
        s.flush()
        return True, f"Compte '{clean_u}' créé avec succès !", _user_to_dict(new_user)


def get_coach_athletes(coach_id: int, db_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retourne exclusivement les élèves rattachés au coach_id (isolation stricte)."""
    with get_db_session(db_url) as s:
        rows = (
            s.query(User)
            .filter(User.coach_id == int(coach_id), User.role == "athlete")
            .order_by(User.full_name.asc())
            .all()
        )
        return [_user_to_dict(r) for r in rows]


def create_athlete_for_coach(
    coach_id: int,
    full_name: str,
    username: str = "",
    password: str = "caliperf123",
    bodyweight_kg: float = 70.0,
    freq: str = "4x / semaine",
    goal: str = "",
    db_url: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Permet à un coach de créer directement un compte élève rattaché à son espace."""
    clean_name = (full_name or "").strip()
    if not clean_name:
        return False, "Le nom de l'athlète est obligatoire.", None

    base_u = sanitize_username(username) if username.strip() else sanitize_username(re.sub(r"\s+", "_", clean_name))
    if len(base_u) < 3:
        base_u = f"athlete_{base_u}"

    with get_db_session(db_url) as s:
        coach = s.query(User).filter(User.id == int(coach_id), User.role == "coach").first()
        if not coach:
            return False, "Seul un coach peut créer un élève dans son espace.", None

        cand_u = base_u
        suffix = 1
        while s.query(User.id).filter(func.lower(User.username) == cand_u).first():
            cand_u = f"{base_u}_{suffix}"
            suffix += 1

        new_ath = User(
            username=cand_u,
            full_name=clean_name,
            role="athlete",
            password_hash=hash_password(password or "caliperf123"),
            coach_id=coach.id,
            invite_code=None,
            bodyweight_kg=max(25.0, min(250.0, float(bodyweight_kg or 70.0))),
            freq=freq or "4x / semaine",
            goal=(goal or "").strip() or "Progression Callisthénie",
        )
        s.add(new_ath)
        s.flush()
        return True, f"Athlète '{clean_name}' (@{cand_u}) créé et rattaché à votre compte !", _user_to_dict(new_ath)


def link_athlete_to_coach_by_code(
    athlete_id: int,
    invite_code: str,
    db_url: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Permet à un élève de rejoindre un coach via son code d'invitation."""
    clean_code = (invite_code or "").strip().upper()
    if not clean_code:
        return False, "Veuillez saisir un code d'invitation coach.", None
    with get_db_session(db_url) as s:
        coach = (
            s.query(User)
            .filter(func.upper(User.invite_code) == clean_code, User.role == "coach")
            .first()
        )
        if not coach:
            return False, "Code d'invitation coach invalide.", None
        ath = s.query(User).filter(User.id == int(athlete_id), User.role == "athlete").first()
        if not ath:
            return False, "Compte élève introuvable.", None
        ath.coach_id = coach.id
        s.flush()
        return True, f"Rattaché avec succès au coach {coach.full_name} !", _user_to_dict(ath)


def update_user_profile_sql(
    user_id: int,
    full_name: Optional[str] = None,
    password: Optional[str] = None,
    avatar_b64: Optional[str] = None,
    bodyweight_kg: Optional[float] = None,
    freq: Optional[str] = None,
    goal: Optional[str] = None,
    db_url: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Met à jour les informations d'un utilisateur en base SQL."""
    with get_db_session(db_url) as s:
        u = s.query(User).filter(User.id == int(user_id)).first()
        if not u:
            return False, "Utilisateur introuvable.", None
        if full_name is not None and full_name.strip():
            u.full_name = full_name.strip()
        if password is not None and password.strip():
            if len(password.strip()) < 4:
                return False, "Le mot de passe doit contenir au moins 4 caractères.", None
            u.password_hash = hash_password(password.strip())
        if avatar_b64 is not None:
            u.avatar_b64 = avatar_b64
        if bodyweight_kg is not None:
            u.bodyweight_kg = max(25.0, min(250.0, float(bodyweight_kg)))
        if freq is not None:
            u.freq = freq
        if goal is not None:
            u.goal = goal
        s.flush()
        return True, "Profil mis à jour.", _user_to_dict(u)


def update_athlete_for_coach(
    coach_id: int,
    athlete_id: int,
    bodyweight_kg: float,
    freq: str,
    goal: str,
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Met à jour la fiche d'un élève après vérification stricte d'appartenance au coach."""
    with get_db_session(db_url) as s:
        ath = s.query(User).filter(User.id == int(athlete_id), User.coach_id == int(coach_id)).first()
        if not ath:
            return False, "Action refusée : cet athlète n'est pas rattaché à votre compte coach."
        ath.bodyweight_kg = max(25.0, min(250.0, float(bodyweight_kg or 70.0)))
        ath.freq = freq
        ath.goal = goal
        s.flush()
        return True, f"Fiche de {ath.full_name} mise à jour."


def delete_athlete_for_coach(
    coach_id: int,
    athlete_id: int,
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Supprime un élève rattaché au coach (cascade training_logs)."""
    with get_db_session(db_url) as s:
        ath = s.query(User).filter(User.id == int(athlete_id), User.coach_id == int(coach_id)).first()
        if not ath:
            return False, "Action refusée : cet athlète n'est pas dans votre espace."
        name = ath.full_name
        s.delete(ath)
        s.flush()
        return True, f"Athlète '{name}' supprimé."


# ==============================================================================
# JOURNAL D'ENTRAÎNEMENT (TRAINING_LOGS) & ISOLATION STRICTE
# ==============================================================================

def create_training_log(
    athlete_id: int,
    coach_id: Optional[int],
    exercise: str,
    exercise_type: str,
    reps: int,
    tut_effective_sec: float,
    added_load_kg: float,
    bodyweight_kg: float,
    difficulty_coef: float,
    external_load_au: float,
    rpe: float,
    srpe_load: float,
    fatigue_drift_deg: Optional[float] = None,
    velocity_loss_pct: Optional[float] = None,
    notes: str = "",
    date_dt: Optional[datetime] = None,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Enregistre une série validée dans la table SQL training_logs."""
    with get_db_session(db_url) as s:
        log = TrainingLog(
            athlete_id=int(athlete_id),
            coach_id=int(coach_id) if coach_id is not None else None,
            date=date_dt or _utcnow(),
            exercise=str(exercise).strip(),
            exercise_type="dynamic" if "dyn" in str(exercise_type).lower() else "isometric",
            reps=int(reps or 0),
            tut_effective_sec=round(float(tut_effective_sec or 0.0), 2),
            added_load_kg=round(float(added_load_kg or 0.0), 2),
            bodyweight_kg=round(float(bodyweight_kg or 70.0), 2),
            difficulty_coef=round(float(difficulty_coef or 1.0), 3),
            external_load_au=round(float(external_load_au or 0.0), 2),
            rpe=round(float(rpe or 7.0), 1),
            srpe_load=round(float(srpe_load or 0.0), 2),
            fatigue_drift_deg=round(float(fatigue_drift_deg), 2) if fatigue_drift_deg is not None else None,
            velocity_loss_pct=round(float(velocity_loss_pct), 2) if velocity_loss_pct is not None else None,
            notes=(notes or "").strip(),
        )
        s.add(log)
        s.flush()
        return _log_to_dict(log)


def get_training_logs_for_athlete(
    viewer_user: Dict[str, Any],
    target_athlete_id: Optional[int] = None,
    db_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Récupère les training_logs avec isolation stricte multi-utilisateurs :
    - Si rôle == 'athlete' : voit UNIQUEMENT ses propres séances (athlete_id == viewer.id).
    - Si rôle == 'coach' :
        * Si target_athlete_id == viewer.id (ou None -> défaut soi-même) : voit ses séances perso.
        * Si target_athlete_id est un élève rattaché (coach_id == viewer.id) : voit ses séances.
        * Refuse tout autre ID (retourne []).
    """
    if not viewer_user:
        return []
    viewer_id = int(viewer_user["id"])
    viewer_role = normalize_role(viewer_user.get("role", "athlete"))

    with get_db_session(db_url) as s:
        if viewer_role == "athlete":
            allowed_id = viewer_id
        else:
            req_id = int(target_athlete_id) if target_athlete_id is not None else viewer_id
            if req_id == viewer_id:
                allowed_id = viewer_id
            else:
                ath = s.query(User.id).filter(User.id == req_id, User.coach_id == viewer_id).first()
                if not ath:
                    return []
                allowed_id = req_id

        rows = (
            s.query(TrainingLog)
            .filter(TrainingLog.athlete_id == allowed_id)
            .order_by(TrainingLog.date.asc(), TrainingLog.id.asc())
            .all()
        )
        return [_log_to_dict(r) for r in rows]


def delete_training_log(
    log_id: int,
    viewer_user: Dict[str, Any],
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Supprime une séance SQL après vérification d'appartenance (athlète ou son coach)."""
    if not viewer_user:
        return False, "Non authentifié."
    viewer_id = int(viewer_user["id"])
    viewer_role = normalize_role(viewer_user.get("role", "athlete"))

    with get_db_session(db_url) as s:
        log = s.query(TrainingLog).filter(TrainingLog.id == int(log_id)).first()
        if not log:
            return False, "Séance introuvable."
        allowed = (log.athlete_id == viewer_id) or (viewer_role == "coach" and log.coach_id == viewer_id)
        if not allowed and viewer_role == "coach":
            ath = s.query(User.id).filter(User.id == log.athlete_id, User.coach_id == viewer_id).first()
            allowed = bool(ath)
        if not allowed:
            return False, "Action refusée : séance hors de votre périmètre."
        s.delete(log)
        s.flush()
        return True, "Séance supprimée."


def get_scoped_athlete_counts(viewer_user: Dict[str, Any], db_url: Optional[str] = None) -> Dict[str, int]:
    """Compteurs synthétiques scopés (pour la page d'accueil et la modale profil)."""
    if not viewer_user:
        return {"figures": 0, "sessions": 0, "athletes": 0}
    uid = int(viewer_user["id"])
    role = normalize_role(viewer_user.get("role", "athlete"))
    with get_db_session(db_url) as s:
        if role == "coach":
            n_ath = s.query(func.count(User.id)).filter(User.coach_id == uid, User.role == "athlete").scalar() or 0
            n_sess = s.query(func.count(TrainingLog.id)).filter(TrainingLog.athlete_id == uid).scalar() or 0
            n_fig = s.query(func.count(func.distinct(Baseline3D.exercise))).filter(Baseline3D.owner_id == uid).scalar() or 0
        else:
            n_ath = 0
            n_sess = s.query(func.count(TrainingLog.id)).filter(TrainingLog.athlete_id == uid).scalar() or 0
            coach_id = viewer_user.get("coach_id")
            if coach_id:
                n_fig = s.query(func.count(func.distinct(Baseline3D.exercise))).filter(
                    Baseline3D.owner_id == int(coach_id), Baseline3D.is_shared.is_(True)
                ).scalar() or 0
            else:
                n_fig = 0
        return {"figures": int(n_fig), "sessions": int(n_sess), "athletes": int(n_ath)}


# ==============================================================================
# GESTION DE SESSION STREAMLIT & PERSISTANCE F5 (QUERY PARAMS)
# ==============================================================================

def init_session_state() -> None:
    """Initialise st.session_state, SQLite/PostgreSQL et restaure le jeton F5 si présent."""
    ensure_database_initialized()
    if not HAS_STREAMLIT:
        return

    defaults = {
        "is_authenticated": False,
        "current_user": None,
        "app_entered": False,
        "active_athlete_id": None,
        "active_video_idx": 0,
        "processed_videos": set(),
        "stopwatches": {},
        "biomech_results": {},
        "active_uploaded_files": [],
        "batch_results": [],
        "last_calib_preview": None,
        "pending_calib_analysis": None,
        "pending_qc_reports": {},
        "session_settings": {"auto_advance": True},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Restauration transparente après rafraîchissement navigateur (F5)
    if st.session_state.current_user is None:
        try:
            tok = st.query_params.get("session", "")
            if isinstance(tok, list):
                tok = tok[0] if tok else ""
            if tok:
                uid = verify_session_token(str(tok))
                if uid is not None:
                    user_dict = get_user_by_id(uid)
                    if user_dict:
                        st.session_state.current_user = user_dict
                        st.session_state.is_authenticated = True
                        st.session_state.app_entered = True
                        if st.session_state.active_athlete_id is None:
                            st.session_state.active_athlete_id = user_dict["id"]
                    else:
                        st.query_params.pop("session", None)
        except Exception:
            pass

    if st.session_state.current_user is not None and st.session_state.active_athlete_id is None:
        st.session_state.active_athlete_id = st.session_state.current_user["id"]


def login_user_in_session(user_dict: Dict[str, Any]) -> None:
    """Connecte l'utilisateur dans st.session_state et signe son jeton ?session= pour F5."""
    if not HAS_STREAMLIT or not user_dict:
        return
    st.session_state.current_user = dict(user_dict)
    st.session_state.is_authenticated = True
    st.session_state.app_entered = True
    st.session_state.active_athlete_id = int(user_dict["id"])
    try:
        st.query_params["session"] = create_session_token(int(user_dict["id"]))
    except Exception:
        pass


def logout_user_from_session(stay_on_auth_portal: bool = True) -> None:
    """Déconnecte proprement l'utilisateur et invalide le paramètre ?session=."""
    if not HAS_STREAMLIT:
        return
    st.session_state.current_user = None
    st.session_state.is_authenticated = False
    st.session_state.active_athlete_id = None
    st.session_state.app_entered = bool(stay_on_auth_portal)
    st.session_state.biomech_results = {}
    st.session_state.batch_results = []
    st.session_state.pending_calib_analysis = None
    try:
        st.query_params.pop("session", None)
    except Exception:
        pass


# ==============================================================================
# UTILITAIRES MÉTIER PARTAGÉS
# ==============================================================================

def detect_student_and_exercise(filename: str, student_list: List[str]) -> Tuple[Optional[str], str]:
    """Extrait intelligemment le prénom de l'athlète et l'exercice depuis le nom du fichier."""
    clean_name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
    detected_student = None
    detected_exercise = clean_name

    for student in student_list:
        for p in student.lower().split():
            if len(p) >= 3 and p in clean_name.lower():
                detected_student = student
                pattern = re.compile(re.escape(student), re.IGNORECASE)
                detected_exercise = pattern.sub("", clean_name).strip(" -_")
                break
        if detected_student:
            break

    return detected_student, detected_exercise if detected_exercise else clean_name


def get_gemini_api_key() -> str:
    """Récupère la clé API Gemini optionnelle (Secrets Streamlit, env, session)."""
    if HAS_STREAMLIT:
        try:
            if hasattr(st, "secrets"):
                for k in ("GEMINI_API_KEY", "gemini_api_key"):
                    if k in st.secrets:
                        return str(st.secrets[k]).strip()
                if "general" in st.secrets and "gemini_api_key" in st.secrets["general"]:
                    return str(st.secrets["general"]["gemini_api_key"]).strip()
        except Exception:
            pass

    env_k = os.getenv("GEMINI_API_KEY", "").strip()
    if env_k:
        return env_k

    if HAS_STREAMLIT:
        try:
            return str(st.session_state.get("active_gemini_key", "")).strip()
        except Exception:
            pass
    return ""
