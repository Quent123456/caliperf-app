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
    inspect as sa_inspect,
    text as sa_text,
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
    is_demo = Column(Boolean, nullable=False, default=False, index=True)
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


if HAS_STREAMLIT:
    @st.cache_resource(show_spinner=False)
    def _create_cloud_engine_cached(resolved_url: str):
        """Réutilise le pool de connexions PostgreSQL sans renégocier le SSL à chaque interaction."""
        return create_engine(
            resolved_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=5,
            future=True,
        )
else:
    def _create_cloud_engine_cached(resolved_url: str):
        return create_engine(
            resolved_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=5,
            future=True,
        )


def get_engine(db_url: Optional[str] = None):
    """Crée ou récupère le moteur SQLAlchemy configuré (cache_resource Cloud + SQLite local)."""
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
        engine = _create_cloud_engine_cached(resolved)

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
        "is_demo": bool(getattr(u, "is_demo", False)),
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
    try:
        Base.metadata.create_all(engine, checkfirst=True)
    except Exception as e:
        if "already exists" not in str(e).lower() and "uniqueviolation" not in str(e).lower():
            raise

    # Migration douce : ajouter is_demo sur users s'il manque dans une base existante
    is_demo_migrated = False
    try:
        insp = sa_inspect(engine)
        cols = {c["name"] for c in insp.get_columns("users")}
        if "is_demo" not in cols:
            with engine.begin() as conn:
                default_val = "FALSE" if not resolved.startswith("sqlite:") else "0"
                conn.execute(sa_text(f"ALTER TABLE users ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT {default_val}"))
            is_demo_migrated = True
    except Exception:
        pass

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
                is_demo=False,
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
                    is_demo=False,
                )
                session.add(new_u)
                session.flush()
                user_map[clean_u] = new_u

            # 3. Alimenter Élève Démo + 5 élèves tests (is_demo=True) et leurs historiques
            from core.demo_seed import seed_demo_athletes_and_logs
            seed_demo_athletes_and_logs(session, admin_user)

            # 4. Migrer les baselines déjà calibrées uniquement (pas de faux "officiel partagé")
            seen_slots = set()
            for item in (legacy.get("baselines_3d", []) or []):
                if item.get("status") != "calibrated" or not item.get("mean_features"):
                    continue
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
                    is_shared=False,
                    exercise=ex_name,
                    camera_view=c_view,
                    type="dynamic" if "dyn" in str(item.get("type", "")).lower() else "isometric",
                    status="calibrated" if mf_json else "empty",
                    mean_features_json=mf_json,
                    std_features_json=sf_json,
                    rom_bounds_json=rb_json,
                    quality_score=item.get("quality_score"),
                ))

            session.commit()
        else:
            # Marquer les comptes démo existants et compléter Élève Démo s'il n'a aucune séance
            import importlib
            import core.demo_seed as _demo_seed
            if not hasattr(_demo_seed, "DEMO_USERNAMES"):
                importlib.reload(_demo_seed)
            from core.demo_seed import DEMO_USERNAMES, seed_demo_athletes_and_logs
            demo_rows = session.query(User).filter(
                func.lower(User.username).in_(list(DEMO_USERNAMES)) | (func.lower(User.full_name) == "élève démo")
            ).all()
            changed = False
            for du in demo_rows:
                if not getattr(du, "is_demo", False):
                    du.is_demo = True
                    changed = True

            # Si Élève Démo existe encore sans séance (ancien bug) ou lors de migration is_demo
            eleve_demo_u = (
                session.query(User)
                .filter(func.lower(User.username).in_(["eleve_demo", "lve_dmo"]) | (func.lower(User.full_name) == "élève démo"))
                .first()
            )
            needs_eleve_logs = False
            if eleve_demo_u is not None:
                c_ed = session.query(func.count(TrainingLog.id)).filter(TrainingLog.athlete_id == int(eleve_demo_u.id)).scalar() or 0
                needs_eleve_logs = (c_ed == 0)

            if is_demo_migrated or needs_eleve_logs:
                coach_u = (
                    session.query(User)
                    .filter(User.role == "coach")
                    .order_by(User.id.asc())
                    .first()
                )
                if coach_u is not None and seed_demo_athletes_and_logs(session, coach_u) > 0:
                    changed = True

            if changed:
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

def _cache_data_ttl(func_obj):
    if HAS_STREAMLIT:
        return st.cache_data(ttl=120, show_spinner=False)(func_obj)
    return func_obj


def _clear_fn_cache(fn) -> None:
    if hasattr(fn, "clear"):
        try:
            fn.clear()
        except Exception:
            pass


def clear_all_sql_read_caches() -> None:
    """Invalide proprement les caches de lecture SQL après toute écriture."""
    for fn in (
        _get_user_by_id_cached,
        _get_user_by_username_cached,
        _get_coach_athletes_cached,
        _get_training_logs_cached,
        _get_scoped_counts_cached,
    ):
        _clear_fn_cache(fn)


@_cache_data_ttl
def _get_user_by_id_cached(user_id: int, resolved_url: str) -> Optional[Dict[str, Any]]:
    with get_db_session(resolved_url) as s:
        u = s.query(User).filter(User.id == int(user_id)).first()
        return _user_to_dict(u) if u else None


def get_user_by_id(user_id: int, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _get_user_by_id_cached(int(user_id), resolve_database_url(db_url))


@_cache_data_ttl
def _get_user_by_username_cached(clean_u: str, resolved_url: str) -> Optional[Dict[str, Any]]:
    with get_db_session(resolved_url) as s:
        u = s.query(User).filter(func.lower(User.username) == clean_u).first()
        return _user_to_dict(u) if u else None


def get_user_by_username(username: str, db_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    clean_u = sanitize_username(username)
    if not clean_u:
        return None
    return _get_user_by_username_cached(clean_u, resolve_database_url(db_url))


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
        out_u = _user_to_dict(new_user)
    _clear_fn_cache(_get_user_by_id_cached)
    _clear_fn_cache(_get_user_by_username_cached)
    _clear_fn_cache(_get_coach_athletes_cached)
    _clear_fn_cache(_get_scoped_counts_cached)
    return True, f"Compte '{clean_u}' créé avec succès !", out_u


@_cache_data_ttl
def _get_coach_athletes_cached(coach_id: int, resolved_url: str) -> List[Dict[str, Any]]:
    """
    Requête SQL unique groupée (LEFT OUTER JOIN + GROUP BY) retournant les élèves
    du coach ainsi que session_count, avg_tut et avg_rpe sans boucle N+1.
    """
    with get_db_session(resolved_url) as s:
        rows = (
            s.query(
                User,
                func.count(TrainingLog.id).label("session_count"),
                func.coalesce(func.avg(TrainingLog.tut_effective_sec), 0.0).label("avg_tut"),
                func.coalesce(func.avg(TrainingLog.rpe), 0.0).label("avg_rpe"),
            )
            .outerjoin(TrainingLog, TrainingLog.athlete_id == User.id)
            .filter(User.coach_id == int(coach_id), User.role == "athlete")
            .group_by(User.id)
            .order_by(User.full_name.asc())
            .all()
        )
        out: List[Dict[str, Any]] = []
        for u, s_cnt, a_tut, a_rpe in rows:
            d = _user_to_dict(u)
            d["session_count"] = int(s_cnt or 0)
            d["avg_tut"] = round(float(a_tut or 0.0), 1)
            d["avg_rpe"] = round(float(a_rpe or 0.0), 1)
            out.append(d)
        return out


def get_coach_athletes(coach_id: int, db_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retourne exclusivement les élèves rattachés au coach_id avec stats agrégées."""
    return _get_coach_athletes_cached(int(coach_id), resolve_database_url(db_url))


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
        res_u = _user_to_dict(new_ath)
    _clear_fn_cache(_get_coach_athletes_cached)
    _clear_fn_cache(_get_user_by_id_cached)
    _clear_fn_cache(_get_scoped_counts_cached)
    return True, f"Athlète '{clean_name}' (@{cand_u}) créé et rattaché à votre compte !", res_u


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
        coach_name = coach.full_name
        upd_ath = _user_to_dict(ath)
    _clear_fn_cache(_get_user_by_id_cached)
    _clear_fn_cache(_get_user_by_username_cached)
    _clear_fn_cache(_get_coach_athletes_cached)
    _clear_fn_cache(_get_scoped_counts_cached)
    return True, f"Rattaché avec succès au coach {coach_name} !", upd_ath


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
        upd_u = _user_to_dict(u)
    _clear_fn_cache(_get_user_by_id_cached)
    _clear_fn_cache(_get_user_by_username_cached)
    _clear_fn_cache(_get_coach_athletes_cached)
    return True, "Profil mis à jour.", upd_u


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
        full_nm = ath.full_name
    _clear_fn_cache(_get_user_by_id_cached)
    _clear_fn_cache(_get_coach_athletes_cached)
    return True, f"Fiche de {full_nm} mise à jour."


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
    clear_all_sql_read_caches()
    return True, f"Athlète '{name}' supprimé."


def purge_demo_athletes_for_coach(
    coach_id: int,
    db_url: Optional[str] = None,
) -> Tuple[bool, str, int]:
    """Supprime uniquement les élèves marqués is_demo=True rattachés à ce coach."""
    with get_db_session(db_url) as s:
        demos = (
            s.query(User)
            .filter(User.coach_id == int(coach_id), User.role == "athlete", User.is_demo.is_(True))
            .all()
        )
        n_del = len(demos)
        for d_u in demos:
            s.delete(d_u)
        s.flush()
    clear_all_sql_read_caches()
    if n_del == 0:
        return True, "Aucun élève de démonstration à supprimer.", 0
    return True, f"{n_del} élève(s) de démo et leurs séances supprimés.", n_del


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
        res_log = _log_to_dict(log)
    _clear_fn_cache(_get_training_logs_cached)
    _clear_fn_cache(_get_coach_athletes_cached)
    _clear_fn_cache(_get_scoped_counts_cached)
    return res_log


@_cache_data_ttl
def _get_training_logs_cached(
    viewer_id: int,
    viewer_role: str,
    target_id: int,
    resolved_url: str,
) -> List[Dict[str, Any]]:
    with get_db_session(resolved_url) as s:
        if viewer_role == "athlete":
            allowed_id = viewer_id
        else:
            if target_id == viewer_id:
                allowed_id = viewer_id
            else:
                ath = s.query(User.id).filter(User.id == target_id, User.coach_id == viewer_id).first()
                if not ath:
                    return []
                allowed_id = target_id

        rows = (
            s.query(TrainingLog)
            .filter(TrainingLog.athlete_id == allowed_id)
            .order_by(TrainingLog.date.asc(), TrainingLog.id.asc())
            .all()
        )
        return [_log_to_dict(r) for r in rows]


def get_training_logs_for_athlete(
    viewer_user: Dict[str, Any],
    target_athlete_id: Optional[int] = None,
    db_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Récupère les training_logs avec isolation stricte multi-utilisateurs et cache TTL=120s.
    """
    if not viewer_user:
        return []
    viewer_id = int(viewer_user["id"])
    viewer_role = normalize_role(viewer_user.get("role", "athlete"))
    req_id = int(target_athlete_id) if target_athlete_id is not None else viewer_id
    return _get_training_logs_cached(viewer_id, viewer_role, req_id, resolve_database_url(db_url))


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
    _clear_fn_cache(_get_training_logs_cached)
    _clear_fn_cache(_get_coach_athletes_cached)
    _clear_fn_cache(_get_scoped_counts_cached)
    return True, "Séance supprimée."


@_cache_data_ttl
def _get_scoped_counts_cached(uid: int, role: str, coach_id: Optional[int], resolved_url: str) -> Dict[str, int]:
    with get_db_session(resolved_url) as s:
        if role == "coach":
            n_ath = s.query(func.count(User.id)).filter(User.coach_id == uid, User.role == "athlete").scalar() or 0
            n_sess = s.query(func.count(TrainingLog.id)).filter(TrainingLog.athlete_id == uid).scalar() or 0
            n_fig = s.query(func.count(func.distinct(Baseline3D.exercise))).filter(Baseline3D.owner_id == uid).scalar() or 0
        else:
            n_ath = 0
            n_sess = s.query(func.count(TrainingLog.id)).filter(TrainingLog.athlete_id == uid).scalar() or 0
            if coach_id:
                n_fig = s.query(func.count(func.distinct(Baseline3D.exercise))).filter(
                    Baseline3D.owner_id == int(coach_id)
                ).scalar() or 0
            else:
                n_fig = 0
        return {"figures": int(n_fig), "sessions": int(n_sess), "athletes": int(n_ath)}


def get_scoped_athlete_counts(viewer_user: Dict[str, Any], db_url: Optional[str] = None) -> Dict[str, int]:
    """Compteurs synthétiques scopés (pour la page d'accueil et la modale profil)."""
    if not viewer_user:
        return {"figures": 0, "sessions": 0, "athletes": 0}
    uid = int(viewer_user["id"])
    role = normalize_role(viewer_user.get("role", "athlete"))
    cid = int(viewer_user["coach_id"]) if viewer_user.get("coach_id") is not None else None
    return _get_scoped_counts_cached(uid, role, cid, resolve_database_url(db_url))


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
        "active_tab": "🎥 Studio",
        "active_athlete_id": None,
        "selected_athlete_id": None,
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
    prev_user = st.session_state.get("current_user")
    uid = int(user_dict["id"])
    st.session_state.current_user = dict(user_dict)
    st.session_state.is_authenticated = True
    st.session_state.app_entered = True
    if not prev_user or int(prev_user.get("id", -1)) != uid or st.session_state.get("active_athlete_id") is None:
        set_active_athlete_in_session(uid, sync_widgets=False)
    try:
        st.query_params["session"] = create_session_token(uid)
    except Exception:
        pass


def set_active_athlete_in_session(athlete_id: int, sync_widgets: bool = False) -> None:
    """Synchronise l'athlète suivi sans violer l'ordre d'instanciation Streamlit."""
    if not HAS_STREAMLIT:
        return
    aid = int(athlete_id)
    st.session_state.active_athlete_id = aid
    st.session_state.selected_athlete_id = aid
    st.session_state["_sync_athlete_widgets"] = True
    if sync_widgets:
        st.session_state["sidebar_active_athlete_select"] = aid
        st.session_state["stats_athlete_select"] = aid
        st.session_state["studio_athlete_select"] = aid


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
