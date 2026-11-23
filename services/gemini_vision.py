"""
services/gemini_vision.py - Identification sémantique de l'exercice via Gemini Vision (Flash)
Extrait 3 à 4 frames clés de la vidéo (OpenCV) et interroge l'API Gemini pour router
automatiquement l'exercice vers le bon profil biomécanique.
"""

import os
import json
import re
import time
from typing import Dict, Any, List, Tuple, Optional

# Imports optionnels sécurisés avec capture d'erreur détaillée
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


def extract_key_frames(video_path: str, num_frames: int = 4) -> List[Dict[str, Any]]:
    """
    Extrait un échantillon uniforme de frames clés réparties sur la vidéo.
    Retourne une liste de dicts contenant:
      - 'timestamp': position en secondes
      - 'frame_idx': index de la frame
      - 'jpeg_bytes': image compressée JPEG
      - 'image_rgb': tableau numpy RGB (pour affichage Streamlit)
    """
    if not HAS_CV2:
        raise ImportError(f"OpenCV (cv2) n'est pas chargé : {CV2_IMPORT_ERROR}")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Fichier vidéo introuvable : {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Impossible d'ouvrir la vidéo avec OpenCV : {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        if total_frames <= 0:
            total_frames = 100

        # Répartition sur l'intervalle utile (15% à 85% de la vidéo pour ignorer la mise en place)
        if total_frames > 10:
            fractions = [0.15 + (0.70 * i / max(1, num_frames - 1)) for i in range(num_frames)]
        else:
            fractions = [i / max(1, num_frames) for i in range(num_frames)]

        key_frames = []
        for frac in fractions:
            target_frame = min(total_frames - 1, max(0, int(total_frames * frac)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            success, frame_bgr = cap.read()
            if not success or frame_bgr is None:
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            timestamp = target_frame / fps

            # Encodage JPEG avec compression contrôlée
            ret, buf = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                key_frames.append({
                    "timestamp": round(timestamp, 2),
                    "frame_idx": target_frame,
                    "jpeg_bytes": buf.tobytes(),
                    "image_rgb": frame_rgb
                })

        return key_frames
    finally:
        cap.release()


def classify_exercise_gemini(
    video_path: str,
    api_key: str,
    num_frames: int = 4
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], str]:
    """
    Routeur IA d'exercice par analyse de frames clés avec Gemini Vision.
    Si OpenCV est disponible, extrait 3-4 images clés.
    Si OpenCV est indisponible ou échoue, se replie de manière transparente
    sur l'upload direct de la vidéo vers l'API Gemini.
    Retourne : (result_dict, key_frames, message)
    """
    if not HAS_GEMINI:
        return None, [], "SDK google-genai non installé."

    if not api_key:
        return None, [], "Clé API Gemini manquante."

    if not os.path.exists(video_path):
        return None, [], f"Fichier vidéo introuvable : {video_path}"

    key_frames: List[Dict[str, Any]] = []
    used_direct_video = False

    # 1. Tentative d'extraction rapide des frames clés avec OpenCV
    if HAS_CV2:
        try:
            key_frames = extract_key_frames(video_path, num_frames=num_frames)
        except Exception as e:
            print(f"[Gemini Vision] Extraction OpenCV échouée ({e}), repli direct vidéo...")
            key_frames = []

    prompt = (
        "Tu es un expert biomécanique en Callisthénie et Street Workout. "
        "Analyse ce contenu d'entraînement (images clés ou vidéo).\n\n"
        "IDENTIFIE L'EXERCICE OU LA FIGURE PRINCIPALE parmi ces profils cibles :\n"
        "- 'full_planche' : Full Planche (maintien horizontal au sol ou parallettes, jambes jointes)\n"
        "- 'straddle_planche' : Straddle Planche (maintien horizontal, jambes écartées)\n"
        "- 'maltese' : Maltese / Hirondelle (bras très écartés, corps ras du sol/anneaux)\n"
        "- 'front_lever' : Front Lever (corps horizontal sous la barre ou anneaux)\n"
        "- 'pull_ups' : Tractions dynamiques (montée/descente sur barre de traction)\n"
        "- 'push_ups' : Pompes au sol / parallettes classiques\n"
        "- 'planche_push_ups' : Pompes en position de planche (fléchir/tendre en planche)\n"
        "- 'other' : Autre mouvement\n\n"
        "Détermine également :\n"
        "1. type : 'isometric' (tenue statique) ou 'dynamic' (répétitions)\n"
        "2. camera_angle : 'profile' (profil net), 'front' (face), 'three_quarter' (3/4)\n"
        "3. confidence : niveau de certitude entre 0.0 et 1.0\n\n"
        "FORMAT DE RÉPONSE OBLIGATOIRE :\n"
        "Réponds STRICTEMENT par un objet JSON sans aucun formatage Markdown autour :\n"
        '{"exercise": "full_planche", "type": "isometric", "camera_angle": "profile", "confidence": 0.95, "exercise_display": "Full Planche", "notes": "Vue de profil, corps horizontal bras tendus"}'
    )

    client = None
    uploaded_remote_file = None

    try:
        client = genai.Client(api_key=api_key)
        contents: List[Any] = []

        if key_frames:
            # Mode rapide : envoi de 3-4 images clés
            for kf in key_frames:
                part = types.Part.from_bytes(data=kf["jpeg_bytes"], mime_type="image/jpeg")
                contents.append(part)
            contents.append(prompt)
        else:
            # Mode repli ultra-résilient : upload direct de la vidéo via Gemini Files API
            used_direct_video = True
            uploaded_remote_file = client.files.upload(file=video_path)

            max_wait = 45
            waited = 0
            while hasattr(uploaded_remote_file, "state") and str(getattr(uploaded_remote_file, "state", "")).upper() == "PROCESSING" and waited < max_wait:
                time.sleep(2)
                waited += 2
                try:
                    uploaded_remote_file = client.files.get(name=uploaded_remote_file.name)
                except Exception:
                    break

            contents = [uploaded_remote_file, prompt]

        candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
        response = None
        last_err = None
        model_used = None

        for m in candidate_models:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=contents
                )
                if response and response.text:
                    model_used = m
                    break
            except Exception as err:
                last_err = f"{m}: {err}"
                continue

        # Nettoyage du fichier vidéo distant si utilisé
        if uploaded_remote_file:
            try:
                client.files.delete(name=uploaded_remote_file.name)
            except Exception:
                pass

        if not response or not response.text:
            return None, key_frames, f"Échec de l'appel Gemini ({last_err})"

        text = response.text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            data["_model"] = model_used
            data["_method"] = "direct_video" if used_direct_video else "keyframes_cv2"
            return data, key_frames, "Identification réussie"

        return None, key_frames, f"Réponse non conforme reçue : {text[:120]}"

    except Exception as e:
        if uploaded_remote_file and client:
            try:
                client.files.delete(name=uploaded_remote_file.name)
            except Exception:
                pass
        return None, key_frames, f"Erreur Gemini Vision : {e}"
