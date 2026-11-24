"""
core/calibration.py - Gestion de la bibliothèque de prototypes 3D CaliPerf & Persistance Google Sheets
Architecture :
- Stockage persistant dans l'onglet 'Baselines_3D' de Google Sheets (via st.secrets)
- Cache Streamlit @st.cache_data(ttl=600) avec invalidation instantanée (.clear()) lors des modifications
- Fallback local transparent dans config/baselines_3d.json pour le mode hors-ligne
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
WORKSHEET_NAME = "Baselines_3D"
BASELINES_COLUMNS = [
    "id",
    "exercise",
    "camera_view",
    "type",
    "status",
    "mean_features",
    "std_features",
    "rom_bounds"
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
    """Charge la table depuis le fichier JSON local."""
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
                "rom_bounds": json.dumps(p.get("rom_bounds", {})) if isinstance(p.get("rom_bounds"), dict) else str(p.get("rom_bounds", ""))
            })
        df = pd.DataFrame(rows)
        for col in BASELINES_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[BASELINES_COLUMNS]
    except Exception as e:
        print(f"Erreur lecture local JSON baselines : {e}")
        return pd.DataFrame(columns=BASELINES_COLUMNS)


def _load_deleted_exercises(path: str = DEFAULT_BASELINES_PATH) -> set:
    """Charge l'ensemble des figures marquées comme supprimées (tombstones)."""
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(str(x).strip().lower() for x in data.get("deleted_exercises", []) if str(x).strip())
    except Exception:
        return set()


def _save_local_baselines_json(
    df: pd.DataFrame,
    deleted_exercises: Optional[set] = None,
    path: str = DEFAULT_BASELINES_PATH
) -> bool:
    """Enregistre le DataFrame et les figures supprimées dans le fichier JSON local."""
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
                "rom_bounds": rb_val
            })

        current_deleted = _load_deleted_exercises(path)
        if deleted_exercises is not None:
            current_deleted = set(str(x).strip().lower() for x in deleted_exercises if str(x).strip())

        payload = {
            "schema_version": "2.0",
            "metadata": {
                "description": "Bibliothèque de baselines 3D CaliPerf (calibrée par l'utilisateur)",
                "updated_at": time.strftime("%Y-%m-%d %H:%M")
            },
            "columns": BASELINES_COLUMNS,
            "deleted_exercises": sorted(list(current_deleted)),
            "prototypes": records
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erreur sauvegarde local JSON baselines : {e}")
        return False


# ==============================================================================
# GESTION PERSISTANCE GOOGLE SHEETS (ONGLET 'Baselines_3D')
# ==============================================================================

def _get_gsheets_connection():
    """Tente d'instancier la connexion Streamlit GSheets."""
    if not HAS_STREAMLIT:
        return None
    try:
        from streamlit_gsheets import GSheetsConnection
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception:
        return None


def _get_gspread_client_and_sheet():
    """Tente une connexion directe gspread via secrets.toml si st.connection n'est pas dispo."""
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


def _merge_baselines_data(local_df: pd.DataFrame, remote_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fusionne intelligemment les données locales et distantes sans jamais écraser ou perdre
    les figures ajoutées localement ou à distance, tout en respectant les suppressions (tombstones).
    """
    deleted_set = _load_deleted_exercises()

    records_map = {}

    # D'abord intégrer le local (en ignorant les figures supprimées)
    if local_df is not None and not local_df.empty:
        for _, row in local_df.iterrows():
            rid = str(row.get("id", "")).strip()
            exo = str(row.get("exercise", "")).strip().lower()
            if rid and exo not in deleted_set:
                records_map[rid] = dict(row)

    # Ensuite fusionner avec le distant (en filtrant formellement les figures supprimées)
    if remote_df is not None and not remote_df.empty:
        for _, row in remote_df.iterrows():
            rid = str(row.get("id", "")).strip()
            exo = str(row.get("exercise", "")).strip().lower()
            if not rid or exo in deleted_set:
                continue
            if rid not in records_map:
                records_map[rid] = dict(row)
            else:
                local_row = records_map[rid]
                loc_status = str(local_row.get("status", "")).strip().lower()
                rem_status = str(row.get("status", "")).strip().lower()

                if rem_status == "calibrated" and loc_status != "calibrated":
                    records_map[rid] = dict(row)
                elif rem_status == "calibrated" and loc_status == "calibrated":
                    rem_mf = str(row.get("mean_features", "")).strip()
                    loc_mf = str(local_row.get("mean_features", "")).strip()
                    if rem_mf and rem_mf != "[]" and (not loc_mf or loc_mf == "[]"):
                        records_map[rid] = dict(row)

    merged_list = list(records_map.values())
    if not merged_list:
        return pd.DataFrame(columns=BASELINES_COLUMNS)

    merged_df = pd.DataFrame(merged_list)
    for c in BASELINES_COLUMNS:
        if c not in merged_df.columns:
            merged_df[c] = ""
    return merged_df[BASELINES_COLUMNS]


def _fetch_baselines_table_internal() -> pd.DataFrame:
    """Lit l'onglet Baselines_3D depuis Google Sheets et fusionne avec le fichier JSON local."""
    local_df = _load_local_baselines_json()
    remote_df = None

    # 1. Essai avec streamlit-gsheets
    conn = _get_gsheets_connection()
    if conn is not None:
        try:
            # ttl=0 pour éviter tout cache périmé
            df = conn.read(worksheet=WORKSHEET_NAME, ttl=0)
            if df is not None and not df.empty:
                df = df.fillna("")
                for c in BASELINES_COLUMNS:
                    if c not in df.columns:
                        df[c] = ""
                remote_df = df[BASELINES_COLUMNS]
        except Exception:
            pass

    # 2. Essai avec gspread direct si streamlit-gsheets n'a rien renvoyé
    if remote_df is None or remote_df.empty:
        gc, sh = _get_gspread_client_and_sheet()
        if sh is not None:
            try:
                worksheet = None
                try:
                    worksheet = sh.worksheet(WORKSHEET_NAME)
                except Exception:
                    pass
                if worksheet:
                    records = worksheet.get_all_records()
                    if records:
                        df = pd.DataFrame(records).fillna("")
                        for c in BASELINES_COLUMNS:
                            if c not in df.columns:
                                df[c] = ""
                        remote_df = df[BASELINES_COLUMNS]
            except Exception:
                pass

    # Fusion intelligente : conserve toujours les créations locales et respecte les suppressions
    if remote_df is not None and not remote_df.empty:
        merged_df = _merge_baselines_data(local_df, remote_df)
        _save_local_baselines_json(merged_df)
        return merged_df

    # Filtrer aussi le local par deleted_set au cas où
    deleted_set = _load_deleted_exercises()
    if deleted_set and not local_df.empty:
        local_df = local_df[~local_df["exercise"].astype(str).str.strip().str.lower().isin(deleted_set)].reset_index(drop=True)

    return local_df


def load_baselines_table(force_refresh: bool = False) -> pd.DataFrame:
    """Charge la table Baselines_3D avec mémorisation en session state pour une réactivité instantanée."""
    if HAS_STREAMLIT:
        if not force_refresh and "baselines_df" in st.session_state and isinstance(st.session_state["baselines_df"], pd.DataFrame):
            return st.session_state["baselines_df"].copy()

    df = _fetch_baselines_table_internal()
    if HAS_STREAMLIT:
        st.session_state["baselines_df"] = df.copy()
    return df


def clear_baselines_cache():
    """Invalide le cache de lecture lors de toute modification."""
    if HAS_STREAMLIT:
        if hasattr(load_baselines_table, "clear"):
            try:
                load_baselines_table.clear()
            except Exception:
                pass


def _save_baselines_table_internal(
    df: pd.DataFrame,
    deleted_exercises: Optional[set] = None
) -> Tuple[bool, str]:
    """Sauvegarde la table Baselines_3D en session, en local (JSON) et tente Google Sheets."""
    clean_df = df.copy().fillna("")
    for c in BASELINES_COLUMNS:
        if c not in clean_df.columns:
            clean_df[c] = ""
    clean_df = clean_df[BASELINES_COLUMNS]

    # 1. Mise à jour immédiate en session state
    if HAS_STREAMLIT:
        st.session_state["baselines_df"] = clean_df.copy()

    # 2. Synchronisation immédiate du JSON local avec tombstones
    _save_local_baselines_json(clean_df, deleted_exercises=deleted_exercises)

    # 3. Sauvegarder dans Google Sheets via streamlit-gsheets si disponible
    conn = _get_gsheets_connection()
    if conn is not None:
        try:
            try:
                conn.update(worksheet=WORKSHEET_NAME, data=clean_df)
                return True, "Enregistré avec succès dans Google Sheets (Baselines_3D) !"
            except Exception:
                conn.create(worksheet=WORKSHEET_NAME, data=clean_df)
                return True, "Onglet 'Baselines_3D' créé et enregistré dans Google Sheets !"
        except Exception as e_conn:
            print(f"Avertissement st.connection update : {e_conn}")

    # 4. Sauvegarder via gspread direct si disponible
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
            all_content = [header] + data_rows
            ws.update("A1", all_content)
            return True, "Enregistré avec succès dans Google Sheets via gspread !"
        except Exception as e_gsp:
            print(f"Avertissement gspread update : {e_gsp}")

    return True, "Enregistré dans la bibliothèque locale (synchronisé)"


# ==============================================================================
# OPÉRATIONS MÉTIER EN 2 ÉTAPES (BIBLIOTHÈQUE / CALIBRAGE)
# ==============================================================================

def create_figure_slots(exercise_name: str, exo_type: str = "isometric") -> Tuple[bool, str]:
    """
    Étape A : Crée une nouvelle figure avec ses 3 emplacements d'angles (Face, 3/4, Profil)
    initialisés avec le statut 'empty'.
    """
    clean_name = exercise_name.strip()
    if not clean_name:
        return False, "Le nom de la figure ne peut pas être vide."

    clean_type = "dynamic" if "dyn" in str(exo_type).lower() else "isometric"

    # Retirer du tombstone si elle avait été supprimée auparavant
    deleted_set = _load_deleted_exercises()
    if clean_name.lower() in deleted_set:
        deleted_set.remove(clean_name.lower())

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
            "rom_bounds": ""
        })

    updated_df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    ok, msg = _save_baselines_table_internal(updated_df, deleted_exercises=deleted_set)
    return ok, f"Figure '{clean_name}' créée avec succès (3 angles en attente) !" if ok else msg


def save_calibrated_slot(
    exercise_name: str,
    camera_view: str,
    exo_type: str,
    mean_features: List[float],
    std_features: List[float],
    rom_bounds: Optional[Dict[str, Any]] = None
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
        # Création de l'emplacement si non trouvé
        new_row = {
            "id": slot_id,
            "exercise": clean_name,
            "camera_view": clean_view,
            "type": exo_type,
            "status": "calibrated",
            "mean_features": mf_str,
            "std_features": sf_str,
            "rom_bounds": rb_str
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    ok, msg = _save_baselines_table_internal(df)
    return ok, f"Calibrage '{clean_name}' ({clean_view}) enregistré avec succès !" if ok else msg


def reset_slot(slot_id: str) -> Tuple[bool, str]:
    """Réinitialise un angle de calibrage (repasse à 'empty' sans supprimer la figure)."""
    df = load_baselines_table().copy()
    match = df["id"] == slot_id
    if not match.any():
        return False, f"Emplacement '{slot_id}' introuvable."

    idx = df[match].index[0]
    df.at[idx, "status"] = "empty"
    df.at[idx, "mean_features"] = ""
    df.at[idx, "std_features"] = ""
    df.at[idx, "rom_bounds"] = ""

    ok, msg = _save_baselines_table_internal(df)
    return ok, "Emplacement réinitialisé en attente de vidéo." if ok else msg


def delete_figure(exercise_name: str) -> Tuple[bool, str]:
    """Supprime complètement une figure et ses 3 angles de la bibliothèque."""
    clean_name = exercise_name.strip()
    if not clean_name:
        return False, "Nom de figure invalide."

    df = load_baselines_table().copy()
    before_len = len(df)
    df = df[df["exercise"].astype(str).str.strip().str.lower() != clean_name.lower()].reset_index(drop=True)

    # Enregistrer le tombstone pour empêcher la résurrection lors des syncs distantes
    deleted_set = _load_deleted_exercises()
    deleted_set.add(clean_name.lower())

    ok, msg = _save_baselines_table_internal(df, deleted_exercises=deleted_set)
    return True, f"Figure '{clean_name}' et ses angles supprimés définitivement !"


def export_baselines_json() -> str:
    """Retourne la sauvegarde JSON formatée de la bibliothèque pour téléchargement immédiat."""
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
            "rom_bounds": rb
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
            "rom_bounds": rb
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
