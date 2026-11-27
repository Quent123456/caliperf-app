"""
core/calibration.py - Gestion SQL de la bibliothèque de prototypes 3D CaliPerf & Classifieur 1-NN.
Architecture autonome (zéro Google Sheets) avec isolation stricte multi-utilisateurs :
- Coach : possède et gère ses propres baselines, contrôle `is_shared` pour ses élèves, et
  peut consulter/utiliser les figures officielles partagées du coach administrateur principal ('admin')
  sans pouvoir les modifier ni voir les baselines privées/partagées d'autres coachs tiers.
- Élève : accède en lecture/reconnaissance 1-NN uniquement aux baselines `is_shared=True`
  de son coach attitré (plus le catalogue officiel partagé s'il est sans coach).
- Tout enregistrement de calibrage transite par le Quality Control Gate et persiste `quality_score`.
"""

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlalchemy import and_, or_, func

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

from core.auth import is_master_coach, normalize_role
from core.database import (
    Baseline3D,
    User,
    _clear_fn_cache,
    get_db_session,
    resolve_database_url,
)

BASELINES_COLUMNS = [
    "id",
    "slot_key",
    "owner_id",
    "owner",
    "is_shared",
    "is_master",
    "exercise",
    "camera_view",
    "type",
    "status",
    "mean_features",
    "std_features",
    "rom_bounds",
    "quality_score",
]
VALID_CAMERA_VIEWS = ["Face", "3/4", "Profil"]

FEATURE_KEYS = [
    "shoulder_flexion",
    "arm_abduction",
    "elbow_angle",
    "hip_angle",
    "trunk_inclination",
    "ventral_dorsal",
]


def make_slot_id(exercise: str, camera_view: str) -> str:
    """Génère un identifiant lisible pour un couple (exercice, angle)."""
    clean_exo = re.sub(r"[^a-zA-Z0-9]+", "_", exercise.strip().lower()).strip("_")
    clean_view = "3_4" if camera_view == "3/4" else camera_view.lower()
    return f"{clean_exo}_{clean_view}"


def _resolve_active_user(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if user is not None:
        return user
    if HAS_STREAMLIT:
        return st.session_state.get("current_user")
    return None


def _rows_to_dataframe(rows: List[Tuple[Baseline3D, User]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=BASELINES_COLUMNS)
    records = []
    for b, owner_u in rows:
        owner_uname = str(owner_u.username) if owner_u else "admin"
        records.append({
            "id": int(b.id),
            "slot_key": make_slot_id(b.exercise, b.camera_view),
            "owner_id": int(b.owner_id),
            "owner": owner_uname,
            "is_shared": bool(b.is_shared),
            "is_master": (owner_uname.lower() == "admin"),
            "exercise": str(b.exercise),
            "camera_view": str(b.camera_view),
            "type": str(b.type),
            "status": str(b.status),
            "mean_features": str(b.mean_features_json or ""),
            "std_features": str(b.std_features_json or ""),
            "rom_bounds": str(b.rom_bounds_json or ""),
            "quality_score": int(b.quality_score) if b.quality_score is not None else None,
        })
    return pd.DataFrame(records)[BASELINES_COLUMNS]


# ==============================================================================
# LECTURE SCOPÉE MULTI-UTILISATEURS (SQL)
# ==============================================================================

def _cache_cal_ttl(fn):
    if HAS_STREAMLIT:
        return st.cache_data(ttl=120, show_spinner=False)(fn)
    return fn


@_cache_cal_ttl
def _load_baselines_cached(uid: Optional[int], role: str, coach_id: Optional[int], resolved_url: str) -> pd.DataFrame:
    with get_db_session(resolved_url) as s:
        q = s.query(Baseline3D, User).join(User, Baseline3D.owner_id == User.id)
        if uid is None:
            return pd.DataFrame(columns=BASELINES_COLUMNS)
        if role == "coach":
            # Isolation stricte par coach : uniquement SES figures (owner_id == uid)
            q = q.filter(Baseline3D.owner_id == int(uid))
        else:
            # Élève : uniquement les figures de son coach attitré (via coach_id)
            if coach_id is None:
                return pd.DataFrame(columns=BASELINES_COLUMNS)
            q = q.filter(Baseline3D.owner_id == int(coach_id))
        rows = q.order_by(Baseline3D.exercise.asc(), Baseline3D.id.asc()).all()
        return _rows_to_dataframe(rows)


def load_baselines_table(
    user: Optional[Dict[str, Any]] = None,
    force_refresh: bool = False,
    db_url: Optional[str] = None,
) -> pd.DataFrame:
    """
    Charge la table baselines_3d depuis SQL avec isolation stricte et cache TTL=120s :
    - Coach : uniquement ses propres figures (owner_id == user.id).
    - Élève : uniquement les figures de son coach attitré (owner_id == user.coach_id).
    """
    if force_refresh:
        _clear_fn_cache(_load_baselines_cached)
    active_u = _resolve_active_user(user)
    if not active_u:
        return pd.DataFrame(columns=BASELINES_COLUMNS)
    uid = int(active_u["id"])
    role = normalize_role(active_u.get("role", "athlete"))
    cid = int(active_u["coach_id"]) if active_u.get("coach_id") is not None else None
    return _load_baselines_cached(uid, role, cid, resolve_database_url(db_url))


# ==============================================================================
# OPÉRATIONS MÉTIER EN 2 ÉTAPES (BIBLIOTHÈQUE / CALIBRAGE)
# ==============================================================================

def create_figure_slots(
    exercise_name: str,
    exo_type: str = "isometric",
    user: Optional[Dict[str, Any]] = None,
    owner: Optional[str] = None,
    is_master: bool = False,
    is_shared: bool = False,
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Étape A : Crée 3 emplacements (Face, 3/4, Profil) dans SQL baselines_3d pour le coach courant.
    Par défaut is_shared=False et owner_id=current_coach.id (isolé au coach et à ses élèves rattachés).
    """
    clean_name = (exercise_name or "").strip()
    if not clean_name:
        return False, "Le nom de la figure ne peut pas être vide."

    active_u = _resolve_active_user(user)
    if active_u and normalize_role(active_u.get("role", "")) != "coach":
        return False, "Seuls les coachs peuvent créer de nouvelles figures 3D."

    clean_type = "dynamic" if "dyn" in str(exo_type).lower() else "isometric"

    with get_db_session(db_url) as s:
        if active_u:
            owner_id = int(active_u["id"])
        elif owner:
            u_obj = s.query(User).filter(func.lower(User.username) == owner.strip().lower()).first()
            if not u_obj:
                return False, f"Propriétaire '{owner}' introuvable."
            owner_id = int(u_obj.id)
        else:
            u_obj = s.query(User).filter(func.lower(User.username) == "admin").first()
            if not u_obj:
                return False, "Aucun compte coach initialisé."
            owner_id = int(u_obj.id)

        exists = (
            s.query(Baseline3D.id)
            .filter(
                Baseline3D.owner_id == owner_id,
                func.lower(Baseline3D.exercise) == clean_name.lower(),
            )
            .first()
        )
        if exists:
            return False, f"La figure '{clean_name}' existe déjà dans votre bibliothèque."

        for view in VALID_CAMERA_VIEWS:
            s.add(Baseline3D(
                owner_id=owner_id,
                is_shared=bool(is_shared),
                exercise=clean_name,
                camera_view=view,
                type=clean_type,
                status="empty",
            ))
        s.flush()
    _clear_fn_cache(_load_baselines_cached)
    return True, f"Figure '{clean_name}' créée avec succès (3 angles en attente) !"


def save_calibrated_slot(
    exercise_name: str,
    camera_view: str,
    exo_type: str,
    mean_features: List[float],
    std_features: List[float],
    rom_bounds: Optional[Dict[str, Any]] = None,
    user: Optional[Dict[str, Any]] = None,
    owner: Optional[str] = None,
    is_shared: bool = False,
    quality_report: Optional[Any] = None,
    qc_confirmed_warning: bool = False,
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Étape B : Enregistre les statistiques 3D calibrées et le quality_score en SQL
    après validation systématique par le Quality Control Gate.
    """
    q_score: Optional[int] = None
    if quality_report is not None:
        if isinstance(quality_report, dict):
            qc_status = quality_report.get("status", "")
            q_score = quality_report.get("global_score")
        else:
            qc_status = getattr(quality_report, "status", "")
            q_score = getattr(quality_report, "global_score", None)

        if qc_status == "REJECT":
            return False, "Enregistrement bloqué par le Quality Control Gate : vidéo rejetée (statut REJECT)."
        if qc_status == "WARNING" and not qc_confirmed_warning:
            return False, "Enregistrement bloqué : veuillez cocher la confirmation malgré l'avertissement qualité."

    clean_name = (exercise_name or "").strip()
    clean_view = (camera_view or "").strip()
    if clean_view not in VALID_CAMERA_VIEWS:
        return False, f"Angle de vue invalide : {clean_view}."

    active_u = _resolve_active_user(user)
    if active_u and normalize_role(active_u.get("role", "")) != "coach":
        return False, "Action refusée : seul un coach peut calibrer la bibliothèque 3D."

    clean_type = "dynamic" if "dyn" in str(exo_type).lower() else "isometric"
    mf_str = json.dumps([round(float(x), 1) for x in mean_features])
    sf_str = json.dumps([max(round(float(x), 1), 2.0) for x in std_features])
    rb_str = json.dumps(rom_bounds) if rom_bounds else ""

    with get_db_session(db_url) as s:
        if active_u:
            owner_id = int(active_u["id"])
        elif owner:
            u_obj = s.query(User).filter(func.lower(User.username) == owner.strip().lower()).first()
            if not u_obj:
                return False, f"Propriétaire '{owner}' introuvable."
            owner_id = int(u_obj.id)
        else:
            u_obj = s.query(User).filter(func.lower(User.username) == "admin").first()
            if not u_obj:
                return False, "Compte coach principal introuvable."
            owner_id = int(u_obj.id)

        existing_slot = (
            s.query(Baseline3D)
            .filter(
                Baseline3D.owner_id == owner_id,
                func.lower(Baseline3D.exercise) == clean_name.lower(),
                Baseline3D.camera_view == clean_view,
            )
            .first()
        )
        if existing_slot:
            existing_slot.status = "calibrated"
            existing_slot.type = clean_type
            existing_slot.mean_features_json = mf_str
            existing_slot.std_features_json = sf_str
            existing_slot.rom_bounds_json = rb_str
            if q_score is not None:
                existing_slot.quality_score = int(q_score)
        else:
            # Crée les 3 slots pour ce coach si inexistant (ex: surcharge d'une figure officielle par un coach)
            for v in VALID_CAMERA_VIEWS:
                is_target = (v == clean_view)
                s.add(Baseline3D(
                    owner_id=owner_id,
                    is_shared=bool(is_shared),
                    exercise=clean_name,
                    camera_view=v,
                    type=clean_type,
                    status="calibrated" if is_target else "empty",
                    mean_features_json=mf_str if is_target else None,
                    std_features_json=sf_str if is_target else None,
                    rom_bounds_json=rb_str if is_target else None,
                    quality_score=int(q_score) if (is_target and q_score is not None) else None,
                ))
        s.flush()
    _clear_fn_cache(_load_baselines_cached)
    return True, f"Calibrage '{clean_name}' ({clean_view}) enregistré dans la base SQL !"


def toggle_figure_sharing(
    exercise_name: str,
    is_shared: bool,
    user: Optional[Dict[str, Any]] = None,
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Permet à un coach d'activer ou couper le partage d'une figure avec ses élèves."""
    active_u = _resolve_active_user(user)
    if not active_u or normalize_role(active_u.get("role", "")) != "coach":
        return False, "Action réservée aux coachs."

    uid = int(active_u["id"])
    with get_db_session(db_url) as s:
        rows = (
            s.query(Baseline3D)
            .filter(
                Baseline3D.owner_id == uid,
                func.lower(Baseline3D.exercise) == exercise_name.strip().lower(),
            )
            .all()
        )
        if not rows:
            return False, "Vous ne pouvez modifier le partage que de vos propres figures."
        for r in rows:
            r.is_shared = bool(is_shared)
        s.flush()
    _clear_fn_cache(_load_baselines_cached)
    state_lbl = "partagée avec vos élèves" if is_shared else "privée (coach uniquement)"
    return True, f"Figure '{exercise_name}' désormais {state_lbl}."


def reset_slot(
    slot_id: int,
    user: Optional[Dict[str, Any]] = None,
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Réinitialise un emplacement à 'empty' si l'utilisateur en est propriétaire."""
    active_u = _resolve_active_user(user)
    if not active_u or normalize_role(active_u.get("role", "")) != "coach":
        return False, "Action refusée."

    uid = int(active_u["id"])
    with get_db_session(db_url) as s:
        slot = s.query(Baseline3D).filter(Baseline3D.id == int(slot_id)).first()
        if not slot:
            return False, "Emplacement introuvable."
        if int(slot.owner_id) != uid:
            return False, "Action refusée : vous ne pouvez réinitialiser que vos propres figures."
        slot.status = "empty"
        slot.mean_features_json = None
        slot.std_features_json = None
        slot.rom_bounds_json = None
        slot.quality_score = None
        s.flush()
    _clear_fn_cache(_load_baselines_cached)
    return True, "Emplacement réinitialisé en attente de vidéo."


def delete_figure(
    exercise_name: str,
    user: Optional[Dict[str, Any]] = None,
    db_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """Supprime les 3 slots d'une figure uniquement si le coach connecté en est propriétaire."""
    clean_name = (exercise_name or "").strip()
    if not clean_name:
        return False, "Nom de figure invalide."

    active_u = _resolve_active_user(user)
    if not active_u or normalize_role(active_u.get("role", "")) != "coach":
        return False, "Action refusée : seul le coach créateur peut supprimer une figure."

    uid = int(active_u["id"])
    with get_db_session(db_url) as s:
        rows = (
            s.query(Baseline3D)
            .filter(
                Baseline3D.owner_id == uid,
                func.lower(Baseline3D.exercise) == clean_name.lower(),
            )
            .all()
        )
        if not rows:
            return False, "Action refusée : figure officielle ou appartenant à un autre compte."
        for r in rows:
            s.delete(r)
        s.flush()
    _clear_fn_cache(_load_baselines_cached)
    return True, f"Figure '{clean_name}' supprimée de votre bibliothèque."


def export_baselines_json(user: Optional[Dict[str, Any]] = None, db_url: Optional[str] = None) -> str:
    """Exporte la bibliothèque visible par l'utilisateur au format JSON."""
    df = load_baselines_table(user=user, db_url=db_url)
    records = []
    for _, row in df.iterrows():
        try:
            mf = json.loads(row["mean_features"]) if str(row["mean_features"]).strip() else []
        except Exception:
            mf = []
        try:
            sf = json.loads(row["std_features"]) if str(row["std_features"]).strip() else []
        except Exception:
            sf = []
        try:
            rb = json.loads(row["rom_bounds"]) if str(row["rom_bounds"]).strip() else None
        except Exception:
            rb = None

        records.append({
            "id": int(row["id"]),
            "exercise": str(row["exercise"]),
            "camera_view": str(row["camera_view"]),
            "type": str(row["type"]),
            "status": str(row["status"]),
            "owner": str(row["owner"]),
            "is_shared": bool(row["is_shared"]),
            "quality_score": row["quality_score"],
            "mean_features": mf,
            "std_features": sf,
            "rom_bounds": rb,
        })

    payload = {
        "export_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_records": len(records),
        "prototypes": records,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ==============================================================================
# CALCULS CINÉMATIQUES & CLASSIFIEUR 1-NN SCOPÉ
# ==============================================================================

def compute_active_feature_vectors(
    kinematics: Dict[str, Any],
    effort_window: Dict[str, Any]
) -> Tuple[np.ndarray, np.ndarray]:
    """Calcule le vecteur moyen (6D) et les écarts-types (6D) sur la fenêtre active."""
    s_idx = effort_window.get("start_idx", 0)
    e_idx = effort_window.get("end_idx", max(0, len(kinematics["timestamps"]) - 1))
    filt = kinematics["features_filtered"]

    means: List[float] = []
    stds: List[float] = []

    for k in FEATURE_KEYS:
        series = filt[k][s_idx:e_idx + 1]
        if len(series) == 0:
            means.append(0.0)
            stds.append(1.0)
        else:
            means.append(float(np.mean(series)))
            stds.append(max(float(np.std(series)), 1.0))

    return np.array(means, dtype=np.float64), np.array(stds, dtype=np.float64)


def get_calibrated_prototypes(
    user: Optional[Dict[str, Any]] = None,
    db_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Récupère uniquement les prototypes calibrés accessibles à l'utilisateur actif."""
    df = load_baselines_table(user=user, db_url=db_url)
    if df.empty or "status" not in df.columns:
        return []

    calib_rows = df[df["status"] == "calibrated"]
    prototypes: List[Dict[str, Any]] = []

    for _, row in calib_rows.iterrows():
        try:
            mf = json.loads(row["mean_features"]) if str(row["mean_features"]).strip() else []
            sf = json.loads(row["std_features"]) if str(row["std_features"]).strip() else []
        except Exception:
            continue
        if len(mf) < 6:
            continue

        try:
            rb = json.loads(row["rom_bounds"]) if str(row["rom_bounds"]).strip() else None
        except Exception:
            rb = None

        exo_type = str(row["type"])
        stability = {
            "max_hip_vertical_velocity": 0.15,
            "min_hold_duration_sec": 0.4,
        } if exo_type == "isometric" else None

        prototypes.append({
            "id": int(row["id"]),
            "exercise": str(row["exercise"]),
            "display_name": str(row["exercise"]),
            "camera_view": str(row["camera_view"]),
            "type": exo_type,
            "status": "calibrated",
            "mean_features": mf,
            "std_features": sf,
            "stability": stability,
            "rom_bounds": rb,
            "owner": str(row.get("owner", "admin")),
            "owner_id": int(row.get("owner_id", 1)),
            "is_shared": bool(row.get("is_shared", True)),
            "quality_score": row.get("quality_score"),
        })

    return prototypes


def identify_exercise_1nn(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    baselines_path: Optional[str] = None,
    forced_exercise: Optional[str] = None,
    user: Optional[Dict[str, Any]] = None,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Classifieur 1-NN comparant la vidéo aux prototypes calibrés accessibles en SQL."""
    prototypes = get_calibrated_prototypes(user=user, db_url=db_url)
    detected_type = segmentation.get("type", "isometric")
    effort_win = segmentation.get("effort_window", {})

    active_means, active_stds = compute_active_feature_vectors(kinematics, effort_win)

    if not prototypes:
        return {
            "exercise": forced_exercise or "non_calibre",
            "display_name": forced_exercise or "Non Calibré",
            "camera_view": "Profil",
            "type": detected_type,
            "confidence": 0.0,
            "distance": 999.0,
            "matched_prototype": None,
            "status": "uncalibrated",
            "message": "⚠️ Aucun mouvement calibré accessible. Calibrez vos figures dans l'onglet Calibrage 3D.",
            "active_means": [round(float(v), 1) for v in active_means],
            "active_stds": [round(float(v), 1) for v in active_stds],
        }

    candidate_protos = [p for p in prototypes if p.get("type") == detected_type]
    if not candidate_protos:
        candidate_protos = prototypes

    if forced_exercise:
        forced_matches = [p for p in candidate_protos if p.get("exercise", "").lower() == forced_exercise.lower()]
        if forced_matches:
            candidate_protos = forced_matches

    distances: List[Tuple[float, Dict[str, Any]]] = []
    for proto in candidate_protos:
        proto_means = np.array(proto["mean_features"], dtype=np.float64)
        proto_stds = np.array(proto["std_features"], dtype=np.float64)
        orient_mismatch = (active_means[5] * proto_means[5]) < 0
        diff = (active_means - proto_means) / np.maximum(proto_stds, 1.5)
        dist = float(np.sqrt(np.sum(diff ** 2)))
        if orient_mismatch:
            dist += 150.0
        distances.append((dist, proto))

    distances.sort(key=lambda x: x[0])
    best_dist, best_proto = distances[0]
    second_dist = distances[1][0] if len(distances) > 1 else (best_dist + 5.0)

    if best_dist < 1.2:
        confidence = 0.98
    elif best_dist < 3.0:
        confidence = 0.92
    else:
        denom = best_dist + second_dist
        ratio = 1.0 - (best_dist / max(denom, 1e-6))
        confidence = max(0.60, min(0.95, ratio))

    return {
        "exercise": best_proto["exercise"],
        "display_name": best_proto.get("display_name", best_proto["exercise"]),
        "camera_view": best_proto.get("camera_view", "Profil"),
        "type": best_proto.get("type", detected_type),
        "confidence": round(float(confidence), 2),
        "distance": round(float(best_dist), 2),
        "matched_prototype": best_proto,
        "status": "calibrated",
        "active_means": [round(float(v), 1) for v in active_means],
        "active_stds": [round(float(v), 1) for v in active_stds],
    }
