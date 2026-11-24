"""
core/calibration.py - Gestion de la bibliothèque de prototypes 3D CaliPerf & Persistance
Architecture :
- Source de vérité unique & réactive : st.session_state.db["baselines_3d"] synchronisé dans caliperf_db.json
- Sauvegarde locale transparente dans config/baselines_3d.json pour versioning et repli
- Synchronisation Google Sheets optionnelle (onglet 'Baselines_3D') si un compte de service est configuré
- Système de permissions & rôles :
    - Administrateur Principal (is_master=True, owner='admin') : bibliothèque officielle permanente, non modifiable par autrui
    - Coachs (is_master=False, owner='username') : ajout de figures personnalisées, non supprimables par d'autres coachs
    - Promotion : l'Administrateur peut intégrer une figure de coach dans la base officielle permanente
- Création en 2 étapes :
    Étape A : Création de la figure (3 angles générés : Face, 3/4, Profil avec status="empty")
    Étape B : Association d'une vidéo de calibrage -> extraction 3D et passage en status="calibrated"
- Règle 1-NN : Comparaison UNIQUEMENT avec les prototypes dont le status est "calibrated"
"""

import os
import json
import re
import time
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

DEFAULT_BASELINES_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "baselines_3d.json")
DB_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "caliperf_db.json")
WORKSHEET_NAME = "Baselines_3D"
BASELINES_COLUMNS = [
    "id",
    "exercise",
    "camera_view",
    "type",
    "status",
    "mean_features",
    "std_features",
    "rom_bounds",
    "owner",
    "is_master"
]
VALID_CAMERA_VIEWS = ["Face", "3/4", "Profil"]

FEATURE_KEYS = [
    "shoulder_flexion",
    "arm_abduction",
    "elbow_angle",
    "hip_angle",
    "trunk_inclination",
    "ventral_dorsal"
]


def make_slot_id(exercise: str, camera_view: str) -> str:
    """Génère un identifiant propre et unique pour chaque emplacement de calibrage."""
    clean_exo = re.sub(r'[^a-zA-Z0-9]+', '_', exercise.strip().lower()).strip('_')
    clean_view = "3_4" if camera_view == "3/4" else camera_view.lower()
    return f"{clean_exo}_{clean_view}"


# ==============================================================================
# GESTION DU STOCKAGE LOCAL (JSON FALLBACK & CACHE)
# ==============================================================================

def _load_local_baselines_json(path: str = DEFAULT_BASELINES_PATH) -> pd.DataFrame:
    """Charge la table depuis le fichier JSON local ou depuis caliperf_db.json."""
    # 1. Vérifie d'abord caliperf_db.json
    if os.path.exists(DB_FILE_PATH):
        try:
            with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
                db_data = json.load(f)
            b_list = db_data.get("baselines_3d", [])
            if b_list and isinstance(b_list, list):
                df = pd.DataFrame(b_list)
                for col in BASELINES_COLUMNS:
                    if col not in df.columns:
                        if col == "owner":
                            df[col] = "admin"
                        elif col == "is_master":
                            df[col] = True
                        else:
                            df[col] = ""
                return df[BASELINES_COLUMNS]
        except Exception:
            pass

    # 2. Vérifie config/baselines_3d.json
    if not os.path.exists(path):
        return pd.DataFrame(columns=BASELINES_COLUMNS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        protos = data.get("prototypes", [])
        if not protos:
            return pd.DataFrame(columns=BASELINES_COLUMNS)

        rows = []
        for p in protos:
            rows.append({
                "id": str(p.get("id", "")),
                "exercise": str(p.get("exercise", "")),
                "camera_view": str(p.get("camera_view", "Profil")),
                "type": str(p.get("type", "isometric")),
                "status": str(p.get("status", "calibrated")),
                "mean_features": json.dumps(p.get("mean_features", [])) if isinstance(p.get("mean_features"), list) else str(p.get("mean_features", "")),
                "std_features": json.dumps(p.get("std_features", [])) if isinstance(p.get("std_features"), list) else str(p.get("std_features", "")),
                "rom_bounds": json.dumps(p.get("rom_bounds", {})) if isinstance(p.get("rom_bounds"), dict) else str(p.get("rom_bounds", "")),
                "owner": str(p.get("owner", "admin")),
                "is_master": bool(p.get("is_master", True))
            })
        df = pd.DataFrame(rows)
        for col in BASELINES_COLUMNS:
            if col not in df.columns:
                if col == "owner":
                    df[col] = "admin"
                elif col == "is_master":
                    df[col] = True
                else:
                    df[col] = ""
        return df[BASELINES_COLUMNS]
    except Exception as e:
        print(f"Erreur lecture local JSON baselines : {e}")
        return pd.DataFrame(columns=BASELINES_COLUMNS)


def _save_local_baselines_json(df: pd.DataFrame, path: str = DEFAULT_BASELINES_PATH) -> bool:
    """Enregistre le DataFrame dans le fichier JSON local."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        records = []
        for _, row in df.iterrows():
            mf = row["mean_features"]
            sf = row["std_features"]
            rb = row["rom_bounds"]

            try:
                mf_val = json.loads(mf) if isinstance(mf, str) and mf.strip() else (mf if isinstance(mf, list) else [])
            except Exception:
                mf_val = []

            try:
                sf_val = json.loads(sf) if isinstance(sf, str) and sf.strip() else (sf if isinstance(sf, list) else [])
            except Exception:
                sf_val = []

            try:
                rb_val = json.loads(rb) if isinstance(rb, str) and rb.strip() else (rb if isinstance(rb, dict) else None)
            except Exception:
                rb_val = None

            records.append({
                "id": str(row["id"]),
                "exercise": str(row["exercise"]),
                "camera_view": str(row["camera_view"]),
                "type": str(row["type"]),
                "status": str(row["status"]),
                "mean_features": mf_val,
                "std_features": sf_val,
                "rom_bounds": rb_val,
                "owner": str(row.get("owner", "admin")),
                "is_master": bool(row.get("is_master", True))
            })

        payload = {
            "schema_version": "2.0",
            "metadata": {
                "description": "Bibliothèque de baselines 3D CaliPerf (calibrée par l'utilisateur)",
                "updated_at": time.strftime("%Y-%m-%d %H:%M")
            },
            "columns": BASELINES_COLUMNS,
            "deleted_exercises": [],
            "prototypes": records
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erreur sauvegarde local JSON baselines : {e}")
        return False


# ==============================================================================
# GESTION OPTIONNELLE GOOGLE SHEETS
# ==============================================================================

def _get_gspread_client_and_sheet():
    """Tente une connexion directe gspread via secrets.toml si un compte de service est configuré."""
    if not HAS_STREAMLIT or not hasattr(st, "secrets"):
        return None, None
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_dict = None
        spreadsheet_target = None

        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            sec = st.secrets["connections"]["gsheets"]
            creds_dict = sec.get("credentials") or sec.get("service_account")
            spreadsheet_target = sec.get("spreadsheet")

        if not creds_dict and "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])

        if not spreadsheet_target:
            spreadsheet_target = st.secrets.get("spreadsheet_url") or st.secrets.get("spreadsheet") or st.secrets.get("spreadsheet_name")

        if not creds_dict or not spreadsheet_target:
            return None, None

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(credentials)

        if str(spreadsheet_target).startswith("http"):
            sh = gc.open_by_url(str(spreadsheet_target))
        else:
            sh = gc.open(str(spreadsheet_target))

        return gc, sh
    except Exception:
        return None, None


def _fetch_sheets_baselines_if_available() -> Optional[pd.DataFrame]:
    """Tente de lire l'onglet Baselines_3D depuis Google Sheets si configuré."""
    gc, sh = _get_gspread_client_and_sheet()
    if sh is None:
        return None
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
        records = ws.get_all_records()
        if records and isinstance(records, list):
            df = pd.DataFrame(records)
            for c in BASELINES_COLUMNS:
                if c not in df.columns:
                    if c == "owner":
                        df[c] = "admin"
                    elif c == "is_master":
                        df[c] = True
                    else:
                        df[c] = ""
            return df[BASELINES_COLUMNS]
    except Exception:
        pass
    return None


# ==============================================================================
# CHARGEMENT ET SAUVEGARDE UNIFIÉS
# ==============================================================================

def load_baselines_table(force_refresh: bool = False) -> pd.DataFrame:
    """
    Charge la table Baselines_3D.
    1. Si force_refresh ou premier chargement : tente de charger/synchroniser depuis Google Sheets.
    2. Source de vérité en mémoire : st.session_state.db["baselines_3d"].
    3. Repli local transparent : caliperf_db.json puis config/baselines_3d.json.
    """
    # 1. Vérification Google Sheets (une seule fois par session pour ménager le quota API, ou si force_refresh)
    if HAS_STREAMLIT and hasattr(st, "session_state"):
        if force_refresh or not st.session_state.get("_gsheets_baselines_synced", False):
            st.session_state["_gsheets_baselines_synced"] = True
            sheets_df = _fetch_sheets_baselines_if_available()
            if sheets_df is not None and not sheets_df.empty:
                if "db" in st.session_state and isinstance(st.session_state.db, dict):
                    st.session_state.db["baselines_3d"] = sheets_df.to_dict(orient="records")
                _save_local_baselines_json(sheets_df)
                return sheets_df

    # 2. Source de vérité session_state
    if HAS_STREAMLIT and hasattr(st, "session_state") and "db" in st.session_state:
        db = st.session_state.db
        if isinstance(db, dict) and "baselines_3d" in db and isinstance(db["baselines_3d"], list):
            if db["baselines_3d"]:
                df = pd.DataFrame(db["baselines_3d"])
                for c in BASELINES_COLUMNS:
                    if c not in df.columns:
                        if c == "owner":
                            df[c] = "admin"
                        elif c == "is_master":
                            df[c] = True
                        else:
                            df[c] = ""
                return df[BASELINES_COLUMNS]

    # 3. Sinon charger depuis le disque (caliperf_db.json ou config/baselines_3d.json)
    local_df = _load_local_baselines_json()
    if not local_df.empty:
        if HAS_STREAMLIT and hasattr(st, "session_state") and "db" in st.session_state:
            st.session_state.db["baselines_3d"] = local_df.to_dict(orient="records")
        return local_df

    return pd.DataFrame(columns=BASELINES_COLUMNS)


def clear_baselines_cache():
    """Invalide le cache de synchronisation pour forcer la relecture Google Sheets au besoin."""
    if HAS_STREAMLIT and hasattr(st, "session_state"):
        st.session_state["_gsheets_baselines_synced"] = False


def _save_baselines_table_internal(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Sauvegarde atomique et immédiate de la bibliothèque dans :
    1. st.session_state.db["baselines_3d"]
    2. caliperf_db.json
    3. config/baselines_3d.json
    4. Google Sheets (optionnel si gspread + service account configuré)
    """
    clean_df = df.copy().fillna("")
    for c in BASELINES_COLUMNS:
        if c not in clean_df.columns:
            if c == "owner":
                clean_df[c] = "admin"
            elif c == "is_master":
                clean_df[c] = True
            else:
                clean_df[c] = ""
    clean_df = clean_df[BASELINES_COLUMNS]
    records = clean_df.to_dict(orient="records")

    # 1. Mise à jour en session state
    if HAS_STREAMLIT and hasattr(st, "session_state") and "db" in st.session_state:
        st.session_state.db["baselines_3d"] = records

    # 2. Sauvegarde atomique dans caliperf_db.json
    try:
        from caliperf import save_db
        if HAS_STREAMLIT and hasattr(st, "session_state") and "db" in st.session_state:
            save_db(st.session_state.db)
    except Exception:
        pass

    # Écriture directe de sécurité dans caliperf_db.json
    try:
        if os.path.exists(DB_FILE_PATH):
            with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
                f_db = json.load(f)
            f_db["baselines_3d"] = records
            with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(f_db, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    # 3. Synchronisation immédiate du JSON local config/baselines_3d.json
    _save_local_baselines_json(clean_df)

    # 4. Synchronisation optionnelle Google Sheets si service account disponible
    gc, sh = _get_gspread_client_and_sheet()
    if sh is not None:
        try:
            try:
                ws = sh.worksheet(WORKSHEET_NAME)
            except Exception:
                ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=max(50, len(clean_df) + 10), cols=len(BASELINES_COLUMNS))

            ws.clear()
            header = BASELINES_COLUMNS
            data_rows = clean_df.values.tolist()
            ws.update("A1", [header] + data_rows)
        except Exception as e_gsp:
            print(f"Avertissement synchronisation Google Sheets : {e_gsp}")

    clear_baselines_cache()
    return True, "Enregistré avec succès !"


# ==============================================================================
# OPÉRATIONS MÉTIER EN 2 ÉTAPES (BIBLIOTHÈQUE / CALIBRAGE)
# ==============================================================================

def create_figure_slots(
    exercise_name: str,
    exo_type: str = "isometric",
    owner: str = "admin",
    is_master: bool = True
) -> Tuple[bool, str]:
    """
    Étape A : Crée une nouvelle figure avec ses 3 emplacements d'angles (Face, 3/4, Profil)
    initialisés avec le statut 'empty'.
    - Si l'administrateur crée la figure, is_master=True (officielle et permanente).
    - Si un coach crée la figure, is_master=False (personnalisée, owner=username).
    """
    clean_name = exercise_name.strip()
    if not clean_name:
        return False, "Le nom de la figure ne peut pas être vide."

    clean_type = "dynamic" if "dyn" in str(exo_type).lower() else "isometric"
    df = load_baselines_table().copy()

    # Vérifier si la figure existe déjà
    existing_figures = [str(x).strip().lower() for x in df["exercise"].unique() if str(x).strip()]
    if clean_name.lower() in existing_figures:
        return False, f"La figure '{clean_name}' existe déjà dans la bibliothèque."

    new_rows = []
    for view in VALID_CAMERA_VIEWS:
        slot_id = make_slot_id(clean_name, view)
        new_rows.append({
            "id": slot_id,
            "exercise": clean_name,
            "camera_view": view,
            "type": clean_type,
            "status": "empty",
            "mean_features": "",
            "std_features": "",
            "rom_bounds": "",
            "owner": owner,
            "is_master": is_master
        })

    updated_df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    ok, msg = _save_baselines_table_internal(updated_df)
    return ok, f"Figure '{clean_name}' créée avec succès (3 angles en attente) !" if ok else msg


def save_calibrated_slot(
    exercise_name: str,
    camera_view: str,
    exo_type: str,
    mean_features: List[float],
    std_features: List[float],
    rom_bounds: Optional[Dict[str, Any]] = None,
    owner: str = "admin"
) -> Tuple[bool, str]:
    """
    Étape B : Associe les données 3D analysées à un emplacement précis et passe son statut à 'calibrated'.
    """
    clean_name = exercise_name.strip()
    clean_view = camera_view.strip()
    slot_id = make_slot_id(clean_name, clean_view)

    df = load_baselines_table().copy()

    mf_str = json.dumps([round(float(x), 1) for x in mean_features])
    sf_str = json.dumps([max(round(float(x), 1), 2.0) for x in std_features])
    rb_str = json.dumps(rom_bounds) if rom_bounds else ""

    # Recherche de l'emplacement existant
    match_mask = (df["exercise"].astype(str).str.strip().str.lower() == clean_name.lower()) & (df["camera_view"] == clean_view)

    if match_mask.any():
        idx = df[match_mask].index[0]
        df.at[idx, "status"] = "calibrated"
        df.at[idx, "type"] = exo_type
        df.at[idx, "mean_features"] = mf_str
        df.at[idx, "std_features"] = sf_str
        df.at[idx, "rom_bounds"] = rb_str
    else:
        new_row = {
            "id": slot_id,
            "exercise": clean_name,
            "camera_view": clean_view,
            "type": exo_type,
            "status": "calibrated",
            "mean_features": mf_str,
            "std_features": sf_str,
            "rom_bounds": rb_str,
            "owner": owner,
            "is_master": False
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    ok, msg = _save_baselines_table_internal(df)
    return ok, f"Calibrage '{clean_name}' ({clean_view}) enregistré avec succès !" if ok else msg


def reset_slot(slot_id: str, user_role: str = "admin", username: str = "admin") -> Tuple[bool, str]:
    """
    Réinitialise un angle de calibrage (repasse à 'empty' sans supprimer la figure).
    Un coach ne peut pas réinitialiser un angle de la bibliothèque officielle de l'admin.
    """
    df = load_baselines_table().copy()
    match = df["id"] == slot_id
    if not match.any():
        return False, f"Emplacement '{slot_id}' introuvable."

    idx = df[match].index[0]
    is_master = bool(df.at[idx, "is_master"]) if "is_master" in df.columns else True
    owner = str(df.at[idx, "owner"]) if "owner" in df.columns else "admin"

    if is_master and user_role.lower() != "admin":
        return False, "Action refusée : Seul l'administrateur peut réinitialiser une figure officielle."

    if not is_master and user_role.lower() != "admin" and owner.lower() != username.lower():
        return False, "Action refusée : Vous ne pouvez réinitialiser que vos propres figures."

    df.at[idx, "status"] = "empty"
    df.at[idx, "mean_features"] = ""
    df.at[idx, "std_features"] = ""
    df.at[idx, "rom_bounds"] = ""

    ok, msg = _save_baselines_table_internal(df)
    return ok, "Emplacement réinitialisé en attente de vidéo." if ok else msg


def delete_figure(
    exercise_name: str,
    user_role: str = "admin",
    username: str = "admin"
) -> Tuple[bool, str]:
    """
    Supprime une figure de la bibliothèque selon les règles de permission :
    - Figure officielle (is_master=True) : supprimable UNIQUEMENT par l'administrateur principal.
    - Figure personnalisée (is_master=False) : supprimable par son créateur ou par l'administrateur.
    """
    clean_name = exercise_name.strip()
    if not clean_name:
        return False, "Nom de figure invalide."

    df = load_baselines_table().copy()
    if df.empty or "exercise" not in df.columns:
        return False, "La bibliothèque est déjà vide."

    matches = df[df["exercise"].astype(str).str.strip().str.lower() == clean_name.lower()]
    if matches.empty:
        return False, f"Figure '{clean_name}' introuvable."

    is_official = bool(matches.iloc[0].get("is_master", True))
    fig_owner = str(matches.iloc[0].get("owner", "admin")).strip().lower()

    if is_official and user_role.lower() != "admin":
        return False, f"Action refusée : '{clean_name}' est une figure officielle permanente de l'administrateur."

    if not is_official and user_role.lower() != "admin" and fig_owner != username.strip().lower():
        return False, f"Action refusée : Vous ne pouvez supprimer que vos propres figures personnalisées."

    df = df[df["exercise"].astype(str).str.strip().str.lower() != clean_name.lower()].reset_index(drop=True)
    ok, msg = _save_baselines_table_internal(df)
    return True, f"Figure '{clean_name}' supprimée avec succès."


def promote_to_master(exercise_name: str) -> Tuple[bool, str]:
    """
    Permet à l'administrateur d'intégrer une figure créée par un coach dans la bibliothèque
    officielle permanente (is_master=True, owner='admin').
    """
    df = load_baselines_table().copy()
    matches = df[df["exercise"].astype(str).str.strip().str.lower() == exercise_name.strip().lower()]
    if matches.empty:
        return False, f"Figure '{exercise_name}' introuvable."

    for idx in matches.index:
        df.at[idx, "is_master"] = True
        df.at[idx, "owner"] = "admin"

    ok, msg = _save_baselines_table_internal(df)
    return ok, f"Figure '{exercise_name}' intégrée avec succès à la bibliothèque officielle !" if ok else msg


def export_baselines_json() -> str:
    """Retourne la sauvegarde JSON formatée de la bibliothèque pour téléchargement si nécessaire."""
    df = load_baselines_table()
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
            "id": str(row["id"]),
            "exercise": str(row["exercise"]),
            "camera_view": str(row["camera_view"]),
            "type": str(row["type"]),
            "status": str(row["status"]),
            "mean_features": mf,
            "std_features": sf,
            "rom_bounds": rb,
            "owner": str(row.get("owner", "admin")),
            "is_master": bool(row.get("is_master", True))
        })

    payload = {
        "export_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_records": len(records),
        "columns": BASELINES_COLUMNS,
        "prototypes": records
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ==============================================================================
# CALCULS CINÉMATIQUES & 1-NN AVEC FILTRE STATUS='calibrated'
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


def get_calibrated_prototypes() -> List[Dict[str, Any]]:
    """
    Règle stricte : Récupère UNIQUEMENT les prototypes de la base ayant status == 'calibrated'.
    Ignore catégoriquement les emplacements vides (status == 'empty').
    """
    df = load_baselines_table()
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
            "min_hold_duration_sec": 0.4
        } if exo_type == "isometric" else None

        prototypes.append({
            "id": str(row["id"]),
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
            "is_master": bool(row.get("is_master", True))
        })

    return prototypes


def identify_exercise_1nn(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    baselines_path: Optional[str] = None,
    forced_exercise: Optional[str] = None
) -> Dict[str, Any]:
    """
    Classifieur 1-NN comparant la vidéo UNIQUEMENT aux lignes 'calibrated' de Baselines_3D.
    Si aucun prototype n'est encore calibré, renvoie un statut explicite sans planter.
    """
    prototypes = get_calibrated_prototypes()
    detected_type = segmentation.get("type", "isometric")
    effort_win = segmentation.get("effort_window", {})

    active_means, active_stds = compute_active_feature_vectors(kinematics, effort_win)

    # Si aucun prototype n'a encore été calibré par l'utilisateur
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
            "message": "⚠️ Aucun mouvement calibré dans la bibliothèque. Créez et calibrez vos figures dans l'onglet Calibrage 3D.",
            "active_means": [round(float(v), 1) for v in active_means],
            "active_stds": [round(float(v), 1) for v in active_stds]
        }

    # Filtrer par type (isométrique / dynamique)
    candidate_protos = [p for p in prototypes if p.get("type") == detected_type]
    if not candidate_protos:
        candidate_protos = prototypes

    if forced_exercise:
        forced_matches = [p for p in candidate_protos if p.get("exercise").lower() == forced_exercise.lower()]
        if forced_matches:
            candidate_protos = forced_matches

    distances: List[Tuple[float, Dict[str, Any]]] = []

    for proto in candidate_protos:
        proto_means = np.array(proto["mean_features"], dtype=np.float64)
        proto_stds = np.array(proto["std_features"], dtype=np.float64)

        # Pénalité stricte sur l'orientation ventrale (+1) vs dorsale (-1)
        vd_video = active_means[5]
        vd_proto = proto_means[5]
        orient_mismatch = (vd_video * vd_proto) < 0

        # Distance euclidienne normalisée par l'écart-type
        diff = (active_means - proto_means) / np.maximum(proto_stds, 1.5)
        dist = float(np.sqrt(np.sum(diff**2)))

        if orient_mismatch:
            dist += 150.0  # Élimine la confusion entre figures opposées

        distances.append((dist, proto))

    distances.sort(key=lambda x: x[0])
    best_dist, best_proto = distances[0]
    second_dist = distances[1][0] if len(distances) > 1 else (best_dist + 5.0)

    # Score de confiance relatif
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
        "active_stds": [round(float(v), 1) for v in active_stds]
    }
