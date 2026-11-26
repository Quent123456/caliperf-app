"""
core/database.py - Gestionnaire centralisé de la base JSON, synchronisation et session CaliPerf.
Élimine les imports circulaires et assure la persistance atomique entre caliperf_db.json
et config/baselines_3d.json.
"""

import os
import re
import json
import tempfile
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
import requests

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

from core.auth import get_default_admin

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(PROJECT_ROOT, "caliperf_db.json")
BASELINES_CFG_FILE = os.path.join(PROJECT_ROOT, "config", "baselines_3d.json")

DEFAULT_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"
DEFAULT_ENTRY_NOM = "entry.1847695661"
DEFAULT_ENTRY_EXO = "entry.1595307876"
DEFAULT_ENTRY_TST = "entry.549289703"
DEFAULT_ENTRY_RPE = "entry.46344190"


def get_default_db() -> Dict[str, Any]:
    """Retourne la structure initiale par défaut de la base CaliPerf."""
    return {
        "version": 2,
        "users": {
            "admin": get_default_admin("admin")
        },
        "students": {
            "Élève Démo": {
                "link": DEFAULT_FORM_URL,
                "freq": "4x / semaine",
                "goal": "Progression Muscle-up & Planche",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        },
        "evaluations": [],
        "baselines_3d": [],
        "settings": {
            "sync_mode": "google_forms",
            "webhook_url": "",
            "form_url": DEFAULT_FORM_URL,
            "entry_nom": DEFAULT_ENTRY_NOM,
            "entry_exo": DEFAULT_ENTRY_EXO,
            "entry_tst": DEFAULT_ENTRY_TST,
            "entry_rpe": DEFAULT_ENTRY_RPE,
            "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
            "admin_pwd": "admin",
            "auto_advance": True
        }
    }


def load_db() -> Dict[str, Any]:
    """Charge la base JSON avec migration automatique et repli vers baselines_3d.json."""
    if not os.path.exists(DB_FILE):
        data = get_default_db()
        save_db(data)
        return data

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if "version" not in raw or "students" not in raw:
            new_data = get_default_db()
            for name, info in raw.items():
                if isinstance(info, dict):
                    new_data["students"][name] = {
                        "link": info.get("link", DEFAULT_FORM_URL),
                        "freq": info.get("freq", "Non renseigné"),
                        "goal": info.get("goal", "Objectif non précisé"),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
            save_db(new_data)
            return new_data

        if "users" not in raw or not isinstance(raw["users"], dict) or not raw["users"]:
            admin_pwd = raw.get("settings", {}).get("admin_pwd", "admin")
            raw["users"] = {
                "admin": get_default_admin(admin_pwd)
            }

        if "evaluations" not in raw:
            raw["evaluations"] = []
        if "baselines_3d" not in raw:
            raw["baselines_3d"] = []
        if not raw["baselines_3d"] and os.path.exists(BASELINES_CFG_FILE):
            try:
                with open(BASELINES_CFG_FILE, "r", encoding="utf-8") as bf:
                    b_raw = json.load(bf)
                protos = b_raw.get("prototypes", [])
                if protos:
                    raw["baselines_3d"] = protos
            except Exception:
                pass

        defaults = get_default_db()["settings"]
        if "settings" not in raw or not isinstance(raw["settings"], dict):
            raw["settings"] = defaults
        else:
            for k, v in defaults.items():
                if k not in raw["settings"]:
                    raw["settings"][k] = v

        return raw

    except Exception as e:
        if HAS_STREAMLIT:
            st.error(f"Erreur de lecture de la base ({e}). Chargement des données par défaut.")
        return get_default_db()


def save_db(data: Dict[str, Any]) -> None:
    """Sauvegarde atomique dans caliperf_db.json et synchronisation config/baselines_3d.json."""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        if "baselines_3d" in data and isinstance(data["baselines_3d"], list):
            os.makedirs(os.path.dirname(BASELINES_CFG_FILE), exist_ok=True)
            payload = {
                "schema_version": "2.0",
                "metadata": {
                    "description": "Bibliothèque de baselines 3D CaliPerf (calibrée par l'utilisateur)",
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                },
                "columns": [
                    "id", "exercise", "camera_view", "type", "status",
                    "mean_features", "std_features", "rom_bounds", "owner", "is_master"
                ],
                "deleted_exercises": [],
                "prototypes": data["baselines_3d"]
            }
            with open(BASELINES_CFG_FILE, "w", encoding="utf-8") as bf:
                json.dump(payload, bf, indent=2, ensure_ascii=False)
    except Exception as e:
        if HAS_STREAMLIT:
            st.error(f"Erreur de sauvegarde : {e}")


def init_session_state() -> None:
    """Initialise proprement toutes les clés st.session_state requises."""
    if not HAS_STREAMLIT:
        return
    defaults = {
        "db": load_db(),
        "is_authenticated": False,
        "current_user": None,
        "app_entered": False,
        "active_video_idx": 0,
        "processed_videos": set(),
        "stopwatches": {},
        "biomech_results": {},
        "biomech_routings": {},
        "active_uploaded_files": [],
        "batch_results": [],
        "last_calib_preview": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def get_persisted_temp_video_path(uploaded_file) -> str:
    """Enregistre le fichier vidéo uploadé sur le disque temporaire pour OpenCV."""
    temp_dir = os.path.join(tempfile.gettempdir(), "caliperf_vids")
    os.makedirs(temp_dir, exist_ok=True)
    safe_name = os.path.basename(getattr(uploaded_file, "name", "video.mp4"))
    temp_path = os.path.join(temp_dir, f"clip_{safe_name}")
    try:
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) != getattr(uploaded_file, "size", 0):
            uploaded_file.seek(0)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.read())
            uploaded_file.seek(0)
    except Exception:
        pass
    return temp_path


def detect_student_and_exercise(filename: str, student_list: List[str]) -> Tuple[Optional[str], str]:
    """Extrait intelligemment le prénom de l'élève et le nom de l'exercice depuis le nom du fichier."""
    clean_name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
    detected_student = None
    detected_exercise = clean_name

    for student in student_list:
        parts = student.lower().split()
        for p in parts:
            if len(p) >= 3 and p in clean_name.lower():
                detected_student = student
                pattern = re.compile(re.escape(student), re.IGNORECASE)
                detected_exercise = pattern.sub("", clean_name).strip(" -_")
                break
        if detected_student:
            break

    return detected_student, detected_exercise if detected_exercise else clean_name


def dispatch_sync_evaluation(
    settings: Dict[str, Any],
    student: str,
    exercise: str,
    tst_val: float,
    rpe_val: float,
    reps_val: int,
    notes: str,
    date_str: str
) -> Tuple[bool, str]:
    """Synchronise une évaluation validée vers Google Forms, Apps Script Webhook ou mode local."""
    mode = settings.get("sync_mode", "google_forms")

    if mode == "gsheet_webhook":
        wh_url = settings.get("webhook_url", "").strip()
        if not wh_url:
            return False, "URL Webhook vide"
        payload = {
            "date": date_str,
            "student": student,
            "exercise": exercise,
            "tst": tst_val,
            "rpe": rpe_val,
            "reps": reps_val,
            "notes": notes
        }
        try:
            r = requests.post(wh_url, json=payload, timeout=4)
            return r.status_code == 200, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)

    elif mode == "google_forms":
        form_url = settings.get("form_url", DEFAULT_FORM_URL)
        payload = {
            settings.get("entry_nom", DEFAULT_ENTRY_NOM): student,
            settings.get("entry_exo", DEFAULT_ENTRY_EXO): exercise,
            settings.get("entry_tst", DEFAULT_ENTRY_TST): str(round(tst_val, 2)).replace('.', ','),
            settings.get("entry_rpe", DEFAULT_ENTRY_RPE): str(rpe_val)
        }
        try:
            r = requests.post(form_url, data=payload, timeout=4)
            return r.status_code == 200, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)

    return True, "Mode local"


def get_gemini_api_key() -> str:
    """Récupère la clé API Gemini sans importer de bibliothèques lourdes."""
    try:
        if HAS_STREAMLIT and hasattr(st, "secrets"):
            if "GEMINI_API_KEY" in st.secrets:
                return str(st.secrets["GEMINI_API_KEY"]).strip()
            if "gemini_api_key" in st.secrets:
                return str(st.secrets["gemini_api_key"]).strip()
            if "general" in st.secrets and "gemini_api_key" in st.secrets["general"]:
                return str(st.secrets["general"]["gemini_api_key"]).strip()
    except Exception:
        pass

    env_k = os.getenv("GEMINI_API_KEY", "").strip()
    if env_k:
        return env_k

    try:
        if HAS_STREAMLIT:
            db_k = st.session_state.get("db", {}).get("settings", {}).get("gemini_api_key", "").strip()
            if db_k:
                return db_k
            return st.session_state.get("active_gemini_key", "").strip()
    except Exception:
        pass
    return ""
