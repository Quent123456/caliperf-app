"""
services/gemini_vision.py - Identification sémantique ultra-rapide de l'exercice (Gemini Flash)
Optimisé pour le traitement par lot :
- AUCUN upload vidéo complet vers l'API.
- Extraction ciblée de 3 frames (25%, 50%, 75%) via cap.set() sans lire le reste de la vidéo.
- Redimensionnement à 512px max et compression JPEG 75% en mémoire.
- Appel Gemini Flash avec response_mime_type="application/json" (< 1.5 seconde par vidéo).
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


def extract_3_frames_fast(
    video_path: str,
    max_width: int = 512,
    quality: int = 75
) -> List[Dict[str, Any]]:
    """
    Extrait instantanément 3 frames clés (25%, 50%, 75%) par saut de tête de lecture (seek).
    Ne lit aucune autre frame de la vidéo.
    Retourne une liste de dicts avec:
      - 'timestamp': secondes
      - 'jpeg_bytes': octets JPEG compressés (en mémoire)
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
            total_frames = 100

        # Ratios stricts demandés : 25%, 50%, 75%
        ratios = [0.25, 0.50, 0.75]
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


def classify_exercise_gemini(
    video_path: str,
    api_key: str
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], str]:
    """
    Identification sémantique instantanée via Gemini Flash sur 3 frames légères en mémoire.
    Retourne : (result_dict, key_frames, message)
    """
    if not HAS_GEMINI:
        return None, [], "SDK google-genai non installé."

    if not api_key:
        return None, [], "Clé API Gemini manquante."

    try:
        key_frames = extract_3_frames_fast(video_path, max_width=512, quality=75)
    except Exception as e:
        return None, [], f"Erreur extraction des 3 frames clés : {e}"

    if not key_frames:
        return None, [], "Échec de lecture des frames clés (vidéo corrompue ou vide)."

    prompt = (
        "Expert en Callisthénie / Street Workout. "
        "Voici 3 images chronologiques (début, milieu, fin) d'un mouvement.\n"
        "Identifie l'exercice parmi :\n"
        "- 'full_planche', 'straddle_planche', 'maltese', 'front_lever'\n"
        "- 'pull_ups', 'push_ups', 'planche_push_ups'\n"
        "- 'other'\n\n"
        "Réponds en JSON strict avec ce schéma exact :\n"
        '{"exercise": "full_planche", "type": "isometric", "camera_angle": "profile", "confidence": 0.95, "exercise_display": "Full Planche"}'
    )

    try:
        client = genai.Client(api_key=api_key)

        parts: List[Any] = [
            types.Part.from_bytes(data=kf["jpeg_bytes"], mime_type="image/jpeg")
            for kf in key_frames
        ]
        parts.append(prompt)

        candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
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
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            data["_model"] = model_used
            return data, key_frames, "Identification réussie"

        return None, key_frames, f"JSON non conforme : {text[:100]}"

    except Exception as e:
        return None, key_frames, f"Erreur Gemini : {e}"
