"""
core/biomechanics.py - Extraction cinématique haute performance et détection d'orientation
Optimisations strictes :
- Détection intelligente de l'orientation (correction auto des vidéos smartphone tournées à 90°).
- Redimensionnement systématique de chaque frame à max_width=480px (extrêmement rapide < 2-3s).
- Saut de frames adaptatif (analyse à 20-25 fps effectifs).
- Aucune écriture de fichier vidéo annoté sur disque.
- Mise en cache intelligente (@st.cache_data) indexée sur le hash de la vidéo :
  recalcul instantané (< 0.01s) des métriques en cas de modification des seuils.
"""

import os
import json
import hashlib
import urllib.request
from typing import Dict, Any, List, Optional, Tuple, Callable
import numpy as np

# Imports optionnels sécurisés
CV2_IMPORT_ERROR = None
try:
    import cv2
    HAS_CV2 = True
except Exception as e:
    HAS_CV2 = False
    CV2_IMPORT_ERROR = str(e)

try:
    from scipy import signal as scipy_signal
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

MEDIAPIPE_IMPORT_ERROR = None
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.vision import PoseLandmark
    HAS_MEDIAPIPE = True
except Exception as e:
    HAS_MEDIAPIPE = False
    MEDIAPIPE_IMPORT_ERROR = str(e)

# Streamlit import pour le cache
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "pose_landmarker_lite.task")
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "exercise_thresholds.json")


def load_exercise_thresholds(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Charge les seuils biomécaniques depuis le fichier JSON externe."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Fichier de seuils biomécaniques introuvable : {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_exercise_thresholds(data: Dict[str, Any], config_path: str = DEFAULT_CONFIG_PATH) -> bool:
    """Enregistre les seuils mis à jour dans le fichier JSON externe."""
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erreur de sauvegarde des seuils : {e}")
        return False


def ensure_model_asset(model_path: str = MODEL_PATH) -> str:
    """Télécharge le modèle PoseLandmarker Lite s'il n'est pas encore présent."""
    if os.path.exists(model_path) and os.path.getsize(model_path) > 1000000:
        return model_path

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    urllib.request.urlretrieve(MODEL_URL, model_path)
    return model_path


def compute_video_hash(video_path: str) -> str:
    """Calcule une empreinte rapide (MD5) de la vidéo basée sur sa taille et son en-tête."""
    if not os.path.exists(video_path):
        return "non_existent_file"
    file_size = os.path.getsize(video_path)
    hasher = hashlib.md5()
    hasher.update(str(file_size).encode())
    with open(video_path, "rb") as f:
        chunk = f.read(1024 * 512)  # 512 KB
        hasher.update(chunk)
    return hasher.hexdigest()


# ==============================================================================
# CALCULS GÉOMÉTRIQUES & ANGLES ARTICULAIRES
# ==============================================================================

def compute_angle_2d(p_a: Tuple[float, float], p_vertex: Tuple[float, float], p_c: Tuple[float, float]) -> float:
    """Calcule l'angle au sommet p_vertex en degrés [0, 180]."""
    v_a = np.array([p_a[0] - p_vertex[0], p_a[1] - p_vertex[1]], dtype=np.float64)
    v_c = np.array([p_c[0] - p_vertex[0], p_c[1] - p_vertex[1]], dtype=np.float64)

    norm_a = np.linalg.norm(v_a)
    norm_c = np.linalg.norm(v_c)

    if norm_a < 1e-6 or norm_c < 1e-6:
        return 180.0

    cos_theta = np.dot(v_a, v_c) / (norm_a * norm_c)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_theta)))


def compute_body_horizontal_tilt(shoulder: Tuple[float, float], ankle: Tuple[float, float]) -> float:
    """Calcule l'inclinaison par rapport à l'horizontale (0° = parallèle au sol)."""
    dx = ankle[0] - shoulder[0]
    dy = ankle[1] - shoulder[1]

    if abs(dx) < 1e-6:
        return 90.0 if dy > 0 else -90.0

    tilt_rad = np.arctan2(dy, abs(dx))
    return float(np.degrees(tilt_rad))


# ==============================================================================
# FILTRAGE DU SIGNAL (BUTTERWORTH ZÉRO-PHASE)
# ==============================================================================

def apply_butterworth_filter(
    signal: np.ndarray,
    fps: float,
    cutoff_hz: float = 3.5,
    order: int = 4
) -> np.ndarray:
    """Filtre passe-bas Butterworth zéro-phase (scipy.signal.filtfilt)."""
    if len(signal) < 3:
        return signal.copy()

    min_pad = 3 * max(order, 4)
    if HAS_SCIPY and fps > 0 and len(signal) > min_pad:
        nyquist = 0.5 * fps
        norm_cutoff = min(0.95, max(0.01, cutoff_hz / nyquist))
        try:
            b, a = scipy_signal.butter(order, norm_cutoff, btype='low', analog=False)
            filtered = scipy_signal.filtfilt(b, a, signal)
            return np.array(filtered, dtype=np.float64)
        except Exception:
            pass

    # Moyenne mobile centrée de secours
    window = min(5, len(signal))
    if window % 2 == 0:
        window -= 1
    if window < 3:
        return signal.copy()

    kernel = np.ones(window) / window
    padded = np.pad(signal, (window // 2, window // 2), mode='edge')
    filtered = np.convolve(padded, kernel, mode='valid')
    return np.array(filtered[:len(signal)], dtype=np.float64)


# ==============================================================================
# DÉTECTION AUTO D'ORIENTATION
# ==============================================================================

def detect_optimal_rotation(cap, landmarker, max_width: int = 480) -> Optional[int]:
    """
    Détecte si la vidéo a été enregistrée de côté (ex: 90° sur smartphone).
    Si le corps est détecté vertical alors qu'une rotation 90° le rend horizontal,
    retourne le code de rotation cv2 approprié (ou None).
    """
    if not HAS_CV2 or landmarker is None:
        return None

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return None

        # Tester sur une frame représentative (~30%)
        test_idx = max(0, min(total_frames - 1, int(total_frames * 0.3)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, test_idx)
        ret, frame = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        if not ret or frame is None:
            return None

        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / float(w)
            frame = cv2.resize(frame, (max_width, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)

        def _test_pose(img_bgr):
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            mp_i = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res = landmarker.detect(mp_i)
            if res.pose_landmarks and len(res.pose_landmarks) > 0:
                lm = res.pose_landmarks[0]
                sh = (lm[PoseLandmark.LEFT_SHOULDER].x, lm[PoseLandmark.LEFT_SHOULDER].y)
                ak = (lm[PoseLandmark.LEFT_ANKLE].x, lm[PoseLandmark.LEFT_ANKLE].y)
                return abs(compute_body_horizontal_tilt(sh, ak)), True
            return 999.0, False

        tilt_orig, found_orig = _test_pose(frame)

        # Si le tilt original est déjà horizontal (< 40°), ne pas pivoter
        if found_orig and tilt_orig < 40.0:
            return None

        # Tester 90° CCW
        rot_ccw = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        tilt_ccw, found_ccw = _test_pose(rot_ccw)

        # Tester 90° CW
        rot_cw = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        tilt_cw, found_cw = _test_pose(rot_cw)

        # Si l'une des rotations donne un corps bien plus horizontal et détecté
        best_code = None
        best_tilt = tilt_orig

        if found_ccw and tilt_ccw < 35.0 and tilt_ccw < best_tilt:
            best_code = cv2.ROTATE_90_COUNTERCLOCKWISE
            best_tilt = tilt_ccw

        if found_cw and tilt_cw < 35.0 and tilt_cw < best_tilt:
            best_code = cv2.ROTATE_90_CLOCKWISE
            best_tilt = tilt_cw

        return best_code
    except Exception:
        return None


# ==============================================================================
# EXTRACTION CINÉMATIQUE ACCÉLÉRÉE (DOWNSCALE 480px + CACHE)
# ==============================================================================

def _run_kinematic_extraction(
    video_path: str,
    max_width: int = 480,
    target_analysis_fps: float = 24.0
) -> Dict[str, Any]:
    """Moteur interne d'extraction vidéo optimisé avec détection d'orientation."""
    if not HAS_CV2:
        raise ImportError(f"OpenCV (cv2) n'est pas chargé : {CV2_IMPORT_ERROR}")
    if not HAS_MEDIAPIPE:
        raise ImportError(f"MediaPipe n'est pas chargé : {MEDIAPIPE_IMPORT_ERROR}")

    model_file = ensure_model_asset()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Impossible d'ouvrir la vidéo : {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        real_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)

        # Saut de frames pour traiter à ~20-25 fps effectifs (extrêmement rapide)
        stride = 1
        if real_fps > 30.0:
            stride = max(1, int(round(real_fps / target_analysis_fps)))

        effective_fps = real_fps / float(stride)
        dt = 1.0 / effective_fps

        base_options = mp_tasks.BaseOptions(model_asset_path=model_file)
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE
        )

        timestamps: List[float] = []
        raw_elbow: List[float] = []
        raw_align: List[float] = []
        raw_tilt: List[float] = []
        raw_sh_trunk: List[float] = []
        raw_hip_y: List[float] = []

        frame_idx = 0
        with mp_vision.PoseLandmarker.create_from_options(options) as landmarker:
            rot_code = detect_optimal_rotation(cap, landmarker, max_width=max_width)

            while True:
                ret, frame_bgr = cap.read()
                if not ret or frame_bgr is None:
                    break

                if frame_idx % stride != 0:
                    frame_idx += 1
                    continue

                curr_t = frame_idx / real_fps
                timestamps.append(curr_t)

                if rot_code is not None:
                    frame_bgr = cv2.rotate(frame_bgr, rot_code)

                # DOWNSCALE STRICT à max_width=480 pour vitesse maximale (< 2s)
                h, w = frame_bgr.shape[:2]
                if w > max_width:
                    scale = max_width / float(w)
                    new_w = max_width
                    new_h = max(1, int(h * scale))
                    frame_bgr = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                detect_res = landmarker.detect(mp_img)

                if detect_res.pose_landmarks and len(detect_res.pose_landmarks) > 0:
                    lm = detect_res.pose_landmarks[0]

                    def p(idx):
                        return (lm[idx].x, lm[idx].y)

                    def vis(idx):
                        return getattr(lm[idx], 'visibility', 0.9)

                    # Sélection du côté le plus visible
                    vis_l = vis(PoseLandmark.LEFT_SHOULDER) + vis(PoseLandmark.LEFT_ELBOW) + vis(PoseLandmark.LEFT_HIP)
                    vis_r = vis(PoseLandmark.RIGHT_SHOULDER) + vis(PoseLandmark.RIGHT_ELBOW) + vis(PoseLandmark.RIGHT_HIP)
                    use_l = vis_l >= vis_r

                    sh = p(PoseLandmark.LEFT_SHOULDER if use_l else PoseLandmark.RIGHT_SHOULDER)
                    el = p(PoseLandmark.LEFT_ELBOW if use_l else PoseLandmark.RIGHT_ELBOW)
                    wr = p(PoseLandmark.LEFT_WRIST if use_l else PoseLandmark.RIGHT_WRIST)
                    hp = p(PoseLandmark.LEFT_HIP if use_l else PoseLandmark.RIGHT_HIP)
                    ak = p(PoseLandmark.LEFT_ANKLE if use_l else PoseLandmark.RIGHT_ANKLE)

                    ang_elbow = compute_angle_2d(sh, el, wr)
                    ang_align = compute_angle_2d(sh, hp, ak)
                    ang_tilt = compute_body_horizontal_tilt(sh, ak)
                    ang_sh = compute_angle_2d(el, sh, hp)
                    hip_y_val = (lm[PoseLandmark.LEFT_HIP].y + lm[PoseLandmark.RIGHT_HIP].y) / 2.0

                    raw_elbow.append(ang_elbow)
                    raw_align.append(ang_align)
                    raw_tilt.append(ang_tilt)
                    raw_sh_trunk.append(ang_sh)
                    raw_hip_y.append(hip_y_val)
                else:
                    raw_elbow.append(raw_elbow[-1] if raw_elbow else 180.0)
                    raw_align.append(raw_align[-1] if raw_align else 175.0)
                    raw_tilt.append(raw_tilt[-1] if raw_tilt else 0.0)
                    raw_sh_trunk.append(raw_sh_trunk[-1] if raw_sh_trunk else 45.0)
                    raw_hip_y.append(raw_hip_y[-1] if raw_hip_y else 0.5)

                frame_idx += 1

        if not timestamps:
            timestamps = [0.0]
            raw_elbow = [180.0]
            raw_align = [175.0]
            raw_tilt = [0.0]
            raw_sh_trunk = [45.0]
            raw_hip_y = [0.5]

        # Filtrage Butterworth zéro-phase
        arr_t = np.array(timestamps, dtype=np.float64)
        arr_elbow = np.array(raw_elbow, dtype=np.float64)
        arr_align = np.array(raw_align, dtype=np.float64)
        arr_tilt = np.array(raw_tilt, dtype=np.float64)
        arr_sh = np.array(raw_sh_trunk, dtype=np.float64)
        arr_hip_y = np.array(raw_hip_y, dtype=np.float64)

        cutoff = 3.5
        filt_elbow = apply_butterworth_filter(arr_elbow, effective_fps, cutoff_hz=cutoff)
        filt_align = apply_butterworth_filter(arr_align, effective_fps, cutoff_hz=cutoff)
        filt_tilt = apply_butterworth_filter(arr_tilt, effective_fps, cutoff_hz=cutoff)
        filt_sh = apply_butterworth_filter(arr_sh, effective_fps, cutoff_hz=cutoff)
        filt_hip_y = apply_butterworth_filter(arr_hip_y, effective_fps, cutoff_hz=cutoff)

        hip_vel = np.gradient(filt_hip_y, dt) if len(filt_hip_y) > 1 else np.zeros_like(filt_hip_y)
        filt_hip_vel = apply_butterworth_filter(hip_vel, effective_fps, cutoff_hz=cutoff)

        return {
            "fps": effective_fps,
            "real_fps": real_fps,
            "dt": dt,
            "total_frames": len(timestamps),
            "duration": round(float(arr_t[-1]), 2) if len(arr_t) > 0 else 0.0,
            "timestamps": arr_t,
            "angles_raw": {
                "elbow": arr_elbow,
                "body_alignment": arr_align,
                "body_horizontal_tilt": arr_tilt,
                "shoulder_trunk": arr_sh,
                "hip_y": arr_hip_y
            },
            "angles_filtered": {
                "elbow": filt_elbow,
                "body_alignment": filt_align,
                "body_horizontal_tilt": filt_tilt,
                "shoulder_trunk": filt_sh,
                "hip_y": filt_hip_y,
                "hip_vertical_velocity": filt_hip_vel
            },
            "rotation_applied": rot_code
        }
    finally:
        cap.release()


# Décorateur de cache Streamlit conditionnel
if HAS_STREAMLIT:
    @st.cache_data(show_spinner=False)
    def _cached_kinematic_extraction(video_hash: str, video_path: str) -> Dict[str, Any]:
        return _run_kinematic_extraction(video_path)

    def extract_kinematics_from_video(video_path: str) -> Dict[str, Any]:
        v_hash = compute_video_hash(video_path)
        return _cached_kinematic_extraction(v_hash, video_path)
else:
    def extract_kinematics_from_video(video_path: str) -> Dict[str, Any]:
        return _run_kinematic_extraction(video_path)


# ==============================================================================
# ANNOTATION À LA VOLÉE (FRAME PAR FRAME SUR DEMANDE)
# ==============================================================================

def generate_annotated_frame_on_demand(
    video_path: str,
    target_time_sec: float,
    max_width: int = 640
) -> Optional[np.ndarray]:
    """Génère une image annotée unique à la volée pour l'affichage interactif."""
    if not HAS_CV2 or not HAS_MEDIAPIPE:
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    try:
        real_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        target_frame = max(0, int(round(target_time_sec * real_fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame_bgr = cap.read()
        if not ret or frame_bgr is None:
            return None

        model_file = ensure_model_asset()
        base_options = mp_tasks.BaseOptions(model_asset_path=model_file)
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE
        )

        with mp_vision.PoseLandmarker.create_from_options(options) as landmarker:
            rot_code = detect_optimal_rotation(cap, landmarker, max_width=max_width)
            if rot_code is not None:
                frame_bgr = cv2.rotate(frame_bgr, rot_code)

            h, w = frame_bgr.shape[:2]
            if w > max_width:
                scale = max_width / float(w)
                new_w = max_width
                new_h = max(1, int(h * scale))
                frame_bgr = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                h, w = new_h, new_w

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            res = landmarker.detect(mp_img)

            if res.pose_landmarks and len(res.pose_landmarks) > 0:
                lm = res.pose_landmarks[0]

                def px(idx):
                    return (int(lm[idx].x * w), int(lm[idx].y * h))

                connections = [
                    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_ELBOW),
                    (PoseLandmark.LEFT_ELBOW, PoseLandmark.LEFT_WRIST),
                    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_HIP),
                    (PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_KNEE),
                    (PoseLandmark.LEFT_KNEE, PoseLandmark.LEFT_ANKLE),
                    (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_ELBOW),
                    (PoseLandmark.RIGHT_ELBOW, PoseLandmark.RIGHT_WRIST),
                    (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_HIP),
                    (PoseLandmark.RIGHT_HIP, PoseLandmark.RIGHT_KNEE),
                    (PoseLandmark.RIGHT_KNEE, PoseLandmark.RIGHT_ANKLE),
                ]
                for p1, p2 in connections:
                    cv2.line(frame_bgr, px(p1), px(p2), (0, 245, 255), 2)

                for idx in [
                    PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_ELBOW, PoseLandmark.LEFT_WRIST,
                    PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_ANKLE,
                    PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_ELBOW, PoseLandmark.RIGHT_WRIST,
                    PoseLandmark.RIGHT_HIP, PoseLandmark.RIGHT_ANKLE
                ]:
                    cv2.circle(frame_bgr, px(idx), 4, (0, 255, 128), -1)

            return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()
