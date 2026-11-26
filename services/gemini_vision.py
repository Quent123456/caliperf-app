"""
services/gemini_vision.py - Analyse vidéo et suivi de mouvement par IA (Gemini Flash Vision)
Optimisé pour une vitesse extrême (< 1.5 - 2s par vidéo) et une fiabilité totale :
- AUCUN upload vidéo complet vers l'API.
- Extraction ciblée de 4 à 6 frames chronologiques via cap.set() sans lire le reste de la vidéo.
- Compression JPEG en mémoire (max 480px) pour une charge réseau minime (< 150 KB au total).
- Analyse sémantique complète : identification de l'exercice, comptage de répétitions (même partielles),
  quantification du TUT effectif et diagnostic biomécanique.
"""

import os
import json
import re
from typing import Dict, Any, List, Tuple, Optional

CV2_IMPORT_ERROR = None
try:
    import cv2
    HAS_CV2 = True
except Exception as e:
    HAS_CV2 = False
    CV2_IMPORT_ERROR = str(e)

try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


def extract_sampled_frames_fast(
    video_path: str,
    max_frames: int = 6,
    max_width: int = 480,
    quality: int = 70
) -> List[Dict[str, Any]]:
    """
    Extrait rapidement max_frames uniformément réparties dans la vidéo sans lire les autres frames.
    Retourne une liste de dicts contenant:
      - 'timestamp': secondes
      - 'frame_idx': numéro de la frame
      - 'jpeg_bytes': octets JPEG
      - 'image_rgb': image numpy pour affichage Streamlit
    """
    if not HAS_CV2:
        raise ImportError(f"OpenCV (cv2) n'est pas chargé : {CV2_IMPORT_ERROR}")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Fichier vidéo introuvable : {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Impossible d'ouvrir la vidéo : {video_path}")

    frames_out: List[Dict[str, Any]] = []

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)

        if total_frames <= 0:
            total_frames = 120

        # Répartition uniforme de 10% à 90%
        if max_frames <= 3:
            ratios = [0.25, 0.50, 0.75]
        elif max_frames <= 4:
            ratios = [0.15, 0.40, 0.65, 0.90]
        else:
            ratios = [0.10, 0.25, 0.45, 0.65, 0.85, 0.95]

        target_indices = [
            min(total_frames - 1, max(0, int(total_frames * r)))
            for r in ratios
        ]

        for idx in target_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame_bgr = cap.read()
            if not ret or frame_bgr is None:
                continue

            h, w = frame_bgr.shape[:2]
            if w > max_width:
                scale = max_width / float(w)
                new_w = max_width
                new_h = max(1, int(h * scale))
                frame_bgr = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            ret_enc, buf = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ret_enc:
                frames_out.append({
                    "timestamp": round(idx / fps, 2),
                    "frame_idx": idx,
                    "jpeg_bytes": buf.tobytes(),
                    "image_rgb": frame_rgb
                })

        return frames_out
    finally:
        cap.release()


def extract_3_frames_fast(video_path: str, max_width: int = 512, quality: int = 75) -> List[Dict[str, Any]]:
    """Rétro-compatibilité pour l'extraction à 3 frames."""
    return extract_sampled_frames_fast(video_path, max_frames=3, max_width=max_width, quality=quality)


def analyze_motion_gemini(
    video_path: str,
    api_key: str,
    num_frames: int = 6
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], str]:
    """
    Analyse complète par IA de la gestuelle, du TUT et des répétitions via Gemini Flash.
    Envoie une séquence temporelle de frames légères et récupère un diagnostic structuré en JSON.
    Retourne : (result_dict, key_frames, message_statut)
    """
    if not HAS_GEMINI:
        return None, [], "SDK google-genai non installé."

    if not api_key:
        return None, [], "Clé API Gemini manquante."

    try:
        key_frames = extract_sampled_frames_fast(video_path, max_frames=num_frames, max_width=480, quality=70)
    except Exception as e:
        return None, [], f"Erreur extraction des frames vidéo : {e}"

    if not key_frames:
        return None, [], "Échec de lecture des frames vidéo."

    timestamps_str = ", ".join([f"Frame {i+1} ({kf['timestamp']}s)" for i, kf in enumerate(key_frames)])

    prompt = (
        "Tu es un expert mondial en analyse vidéo de Callisthénie, Street Workout et Street Lifting.\n"
        f"Voici {len(key_frames)} images chronologiques d'une série : {timestamps_str}.\n\n"
        "TÂCHE :\n"
        "1. Identifie l'exercice : full_planche, straddle_planche, maltese, front_lever, pull_ups, push_ups, planche_push_ups, dips, muscle_ups, ou other.\n"
        "2. Détermine le type : 'isometric' ou 'dynamic'.\n"
        "3. RÉPÉTITIONS : Si le mouvement est dynamique (tractions, pompes, dips, etc.), compte TOUTES les répétitions réalisées ou entamées, sans restriction de perfection formelle. Si isométrique, mets 0.\n"
        "4. TEMPS SOUS TENSION (TUT) : Estime la durée active totale sous tension (en secondes).\n"
        "5. Début (start_time) et fin (end_time) du set en secondes.\n"
        "6. Diagnostic court et encourageant en français sur la forme (verrouillage, alignement, propreté).\n\n"
        "Réponds en JSON STRICT avec ce schéma exact :\n"
        "{\n"
        '  "exercise": "full_planche",\n'
        '  "exercise_display": "Full Planche",\n'
        '  "type": "isometric",\n'
        '  "reps": 0,\n'
        '  "tut": 5.2,\n'
        '  "start_time": 0.5,\n'
        '  "end_time": 5.7,\n'
        '  "quality_score": 8.5,\n'
        '  "camera_angle": "profile",\n'
        '  "confidence": 0.95,\n'
        '  "feedback": "Bonne propreté générale, maintien solide."\n'
        "}"
    )

    try:
        client = genai.Client(api_key=api_key)

        parts: List[Any] = [
            types.Part.from_bytes(data=kf["jpeg_bytes"], mime_type="image/jpeg")
            for kf in key_frames
        ]
        parts.append(prompt)

        candidate_models = [
            "gemini-3.8-flash",
            "gemini-4-hydrogen",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite"
        ]

        response = None
        last_err = None
        model_used = None

        config = types.GenerateContentConfig(
            response_mime_type="application/json"
        )

        for m in candidate_models:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=parts,
                    config=config
                )
                if response and response.text:
                    model_used = m
                    break
            except Exception as err:
                last_err = f"{m}: {err}"
                continue

        if not response or not response.text:
            return None, key_frames, f"Échec Gemini : {last_err}"

        text = response.text.strip()
        # Nettoyage des balises Markdown ```json ... ``` si présentes
        cleaned = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        cleaned = re.sub(r'```$', '', cleaned, flags=re.MULTILINE).strip()

        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            data["_model"] = model_used

            # Normalisation des champs numériques
            data["reps"] = int(data.get("reps", 0))
            data["tut"] = round(float(data.get("tut", 0.0)), 2)
            data["start_time"] = round(float(data.get("start_time", 0.0)), 2)
            data["end_time"] = round(float(data.get("end_time", data["tut"])), 2)
            return data, key_frames, "Analyse IA réussie"

        return None, key_frames, f"Format JSON inattendu : {text[:80]}"

    except Exception as e:
        return None, key_frames, f"Erreur Gemini : {e}"


def classify_exercise_gemini(
    video_path: str,
    api_key: str
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], str]:
    """Rétro-compatibilité pour le routage d'exercice."""
    return analyze_motion_gemini(video_path, api_key, num_frames=4)


def get_gemini_api_key() -> str:
    """Récupère la clé API Gemini de manière résiliente (Secrets Streamlit, env, base JSON, session)."""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
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
        import streamlit as st
        db_k = st.session_state.get("db", {}).get("settings", {}).get("gemini_api_key", "").strip()
        if db_k:
            return db_k
        return st.session_state.get("active_gemini_key", "").strip()
    except Exception:
        return ""
