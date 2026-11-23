"""
core/biomechanics.py - Extraction cinématique et filtrage des angles articulaires
Utilise MediaPipe Pose pour extraire les repères anatomiques frame-par-frame,
calcule les angles articulaires biomécaniques et applique un filtre passe-bas
Butterworth zéro-phase (scipy.signal.filtfilt) pour éliminer le bruit.
"""

import os
import json
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


DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "exercise_thresholds.json")
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "pose_landmarker_lite.task")


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
    """Télécharge automatiquement le modèle PoseLandmarker s'il n'est pas encore présent."""
    if os.path.exists(model_path) and os.path.getsize(model_path) > 1000000:
        return model_path

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    print(f"Téléchargement du modèle MediaPipe Pose vers {model_path}...")
    urllib.request.urlretrieve(MODEL_URL, model_path)
    return model_path


# ==============================================================================
# CALCULS GÉOMÉTRIQUES & ANGLES ARTICULAIRES (BIOMÉCANIQUE)
# ==============================================================================

def compute_angle_2d(p_a: Tuple[float, float], p_vertex: Tuple[float, float], p_c: Tuple[float, float]) -> float:
    """
    Calcule l'angle au sommet p_vertex entre les vecteurs vertex->p_a et vertex->p_c.
    Retourne l'angle en degrés dans l'intervalle [0.0, 180.0].
    """
    v_a = np.array([p_a[0] - p_vertex[0], p_a[1] - p_vertex[1]], dtype=np.float64)
    v_c = np.array([p_c[0] - p_vertex[0], p_c[1] - p_vertex[1]], dtype=np.float64)

    norm_a = np.linalg.norm(v_a)
    norm_c = np.linalg.norm(v_c)

    if norm_a < 1e-6 or norm_c < 1e-6:
        return 180.0

    cos_theta = np.dot(v_a, v_c) / (norm_a * norm_c)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    angle_rad = np.arccos(cos_theta)
    return float(np.degrees(angle_rad))


def compute_body_horizontal_tilt(shoulder: Tuple[float, float], ankle: Tuple[float, float]) -> float:
    """
    Calcule l'inclinaison du corps par rapport à l'horizontale en degrés.
    0° = parfaitement parallèle à l'axe X (horizontal).
    > 0 = chevilles plus basses que les épaules (inclinaison montante).
    < 0 = chevilles plus hautes que les épaules.
    """
    dx = ankle[0] - shoulder[0]
    dy = ankle[1] - shoulder[1]  # Y pointe vers le bas dans les coordonnées image

    if abs(dx) < 1e-6:
        return 90.0 if dy > 0 else -90.0

    # L'angle par rapport à l'horizontale : arctan(dy / |dx|)
    tilt_rad = np.arctan2(dy, abs(dx))
    return float(np.degrees(tilt_rad))


# ==============================================================================
# FILTRAGE DU SIGNAL (BUTTERWORTH ZÉRO-PHASE & MOYENNE MOBILE)
# ==============================================================================

def apply_butterworth_filter(
    signal: np.ndarray,
    fps: float,
    cutoff_hz: float = 3.5,
    order: int = 4
) -> np.ndarray:
    """
    Applique un filtre passe-bas Butterworth zéro-phase (scipy.signal.filtfilt).
    Si le signal est trop court ou SciPy indisponible, utilise une moyenne mobile centrée.
    """
    if len(signal) < 3:
        return signal.copy()

    # Si SciPy est disponible et que le signal a suffisamment de points
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

    # Repli robuste : moyenne mobile centrée
    window = min(5, len(signal))
    if window % 2 == 0:
        window -= 1
    if window < 3:
        return signal.copy()

    kernel = np.ones(window) / window
    # Mode 'same' avec duplication des bords pour éviter les artefacts
    padded = np.pad(signal, (window // 2, window // 2), mode='edge')
    filtered = np.convolve(padded, kernel, mode='valid')
    return np.array(filtered[:len(signal)], dtype=np.float64)


# ==============================================================================
# EXTRACTION CINÉMATIQUE SUR VIDÉO (MEDIAPIPE TASKS + OPENCV)
# ==============================================================================

def extract_kinematics_from_video(
    video_path: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    max_frames: Optional[int] = None,
    sample_stride: int = 1
) -> Dict[str, Any]:
    """
    Lit la vidéo frame par frame, applique MediaPipe PoseLandmarker,
    calcule les séries temporelles d'angles biomécaniques et applique le filtre Butterworth.
    """
    if not HAS_CV2:
        raise ImportError(f"OpenCV (cv2) n'a pas pu être chargé ({CV2_IMPORT_ERROR}). Vérifiez packages.txt sur Streamlit Cloud.")
    if not HAS_MEDIAPIPE:
        raise ImportError(f"MediaPipe n'a pas pu être chargé ({MEDIAPIPE_IMPORT_ERROR}).")

    model_file = ensure_model_asset()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Impossible d'ouvrir le fichier vidéo : {video_path}")

    try:
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        real_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)

        dt = 1.0 / real_fps if real_fps > 0 else 1.0 / 30.0

        if total_video_frames <= 0:
            total_video_frames = 100

        limit_frames = total_video_frames if max_frames is None else min(total_video_frames, max_frames)

        base_options = mp_tasks.BaseOptions(model_asset_path=model_file)
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE
        )

        timestamps: List[float] = []
        raw_elbow_angles: List[float] = []
        raw_body_alignments: List[float] = []
        raw_horizontal_tilts: List[float] = []
        raw_shoulder_trunk_angles: List[float] = []
        raw_hip_y: List[float] = []
        raw_arm_abductions: List[float] = []
        valid_detection_mask: List[bool] = []

        annotated_keyframes: List[Dict[str, Any]] = []
        keyframe_step = max(1, limit_frames // 4)

        with mp_vision.PoseLandmarker.create_from_options(options) as landmarker:
            frame_idx = 0
            while frame_idx < limit_frames:
                success, frame_bgr = cap.read()
                if not success or frame_bgr is None:
                    break

                if frame_idx % sample_stride != 0:
                    frame_idx += 1
                    continue

                curr_time = frame_idx * dt
                timestamps.append(curr_time)

                if progress_callback and frame_idx % max(1, limit_frames // 20) == 0:
                    prog = min(0.95, frame_idx / limit_frames)
                    progress_callback(prog, f"Analyse cinématique : frame {frame_idx}/{limit_frames}")

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                detect_res = landmarker.detect(mp_img)

                if detect_res.pose_landmarks and len(detect_res.pose_landmarks) > 0:
                    landmarks = detect_res.pose_landmarks[0]

                    def lm(idx):
                        return (landmarks[idx].x, landmarks[idx].y)

                    def vis(idx):
                        return getattr(landmarks[idx], 'visibility', 0.9)

                    # Épaule, coude, poignet, hanche, cheville (Gauche et Droite)
                    vis_left = vis(PoseLandmark.LEFT_SHOULDER) + vis(PoseLandmark.LEFT_ELBOW) + vis(PoseLandmark.LEFT_HIP)
                    vis_right = vis(PoseLandmark.RIGHT_SHOULDER) + vis(PoseLandmark.RIGHT_ELBOW) + vis(PoseLandmark.RIGHT_HIP)

                    use_left = vis_left >= vis_right

                    sh_idx = PoseLandmark.LEFT_SHOULDER if use_left else PoseLandmark.RIGHT_SHOULDER
                    el_idx = PoseLandmark.LEFT_ELBOW if use_left else PoseLandmark.RIGHT_ELBOW
                    wr_idx = PoseLandmark.LEFT_WRIST if use_left else PoseLandmark.RIGHT_WRIST
                    hp_idx = PoseLandmark.LEFT_HIP if use_left else PoseLandmark.RIGHT_HIP
                    ak_idx = PoseLandmark.LEFT_ANKLE if use_left else PoseLandmark.RIGHT_ANKLE

                    shoulder = lm(sh_idx)
                    elbow = lm(el_idx)
                    wrist = lm(wr_idx)
                    hip = lm(hp_idx)
                    ankle = lm(ak_idx)

                    # 1. Angle du coude (flexion / extension)
                    elbow_ang = compute_angle_2d(shoulder, elbow, wrist)

                    # 2. Alignement épaule - hanche - cheville (corps gainé)
                    body_align = compute_angle_2d(shoulder, hip, ankle)

                    # 3. Inclinaison par rapport à l'horizontale
                    tilt_ang = compute_body_horizontal_tilt(shoulder, ankle)

                    # 4. Angle ouverture épaule - tronc
                    sh_trunk = compute_angle_2d(elbow, shoulder, hip)

                    # 5. Position verticale moyenne des hanches
                    hip_y_val = (landmarks[PoseLandmark.LEFT_HIP].y + landmarks[PoseLandmark.RIGHT_HIP].y) / 2.0

                    # 6. Abduction des bras (Maltese)
                    opp_sh_idx = PoseLandmark.RIGHT_SHOULDER if use_left else PoseLandmark.LEFT_SHOULDER
                    arm_abd = compute_angle_2d(elbow, shoulder, lm(opp_sh_idx))

                    raw_elbow_angles.append(elbow_ang)
                    raw_body_alignments.append(body_align)
                    raw_horizontal_tilts.append(tilt_ang)
                    raw_shoulder_trunk_angles.append(sh_trunk)
                    raw_hip_y.append(hip_y_val)
                    raw_arm_abductions.append(arm_abd)
                    valid_detection_mask.append(True)

                    # Enregistrement de frames clés annotées pour l'UI
                    if frame_idx % keyframe_step == 0 and len(annotated_keyframes) < 4:
                        annotated = frame_rgb.copy()
                        # Tracer les segments squelette principaux
                        for pt1, pt2 in [(shoulder, elbow), (elbow, wrist), (shoulder, hip), (hip, ankle)]:
                            cv2.line(
                                annotated,
                                (int(pt1[0] * width), int(pt1[1] * height)),
                                (int(pt2[0] * width), int(pt2[1] * height)),
                                (0, 240, 255), 3
                            )
                        # Points articulaires
                        for pt in [shoulder, elbow, wrist, hip, ankle]:
                            cv2.circle(
                                annotated,
                                (int(pt[0] * width), int(pt[1] * height)),
                                6, (16, 185, 129), -1
                            )

                        annotated_keyframes.append({
                            "timestamp": round(curr_time, 2),
                            "frame_idx": frame_idx,
                            "image_rgb": annotated,
                            "elbow_angle": round(elbow_ang, 1),
                            "body_alignment": round(body_align, 1),
                            "tilt_angle": round(tilt_ang, 1)
                        })

                else:
                    # Pas de détection sur cette frame
                    prev_elbow = raw_elbow_angles[-1] if raw_elbow_angles else 180.0
                    prev_align = raw_body_alignments[-1] if raw_body_alignments else 180.0
                    prev_tilt = raw_horizontal_tilts[-1] if raw_horizontal_tilts else 0.0
                    prev_sh = raw_shoulder_trunk_angles[-1] if raw_shoulder_trunk_angles else 45.0
                    prev_hip = raw_hip_y[-1] if raw_hip_y else 0.5
                    prev_abd = raw_arm_abductions[-1] if raw_arm_abductions else 50.0

                    raw_elbow_angles.append(prev_elbow)
                    raw_body_alignments.append(prev_align)
                    raw_horizontal_tilts.append(prev_tilt)
                    raw_shoulder_trunk_angles.append(prev_sh)
                    raw_hip_y.append(prev_hip)
                    raw_arm_abductions.append(prev_abd)
                    valid_detection_mask.append(False)

                frame_idx += 1

        # Application du filtre passe-bas Butterworth zéro-phase
        thresh_cfg = load_exercise_thresholds()
        filter_cfg = thresh_cfg.get("signal_filtering", {})
        cutoff = float(filter_cfg.get("cutoff_frequency_hz", 3.5))
        order = int(filter_cfg.get("butterworth_order", 4))

        arr_elbow = np.array(raw_elbow_angles, dtype=np.float64)
        arr_align = np.array(raw_body_alignments, dtype=np.float64)
        arr_tilt = np.array(raw_horizontal_tilts, dtype=np.float64)
        arr_sh = np.array(raw_shoulder_trunk_angles, dtype=np.float64)
        arr_hip_y = np.array(raw_hip_y, dtype=np.float64)
        arr_abd = np.array(raw_arm_abductions, dtype=np.float64)

        filt_elbow = apply_butterworth_filter(arr_elbow, real_fps, cutoff_hz=cutoff, order=order)
        filt_align = apply_butterworth_filter(arr_align, real_fps, cutoff_hz=cutoff, order=order)
        filt_tilt = apply_butterworth_filter(arr_tilt, real_fps, cutoff_hz=cutoff, order=order)
        filt_sh = apply_butterworth_filter(arr_sh, real_fps, cutoff_hz=cutoff, order=order)
        filt_hip_y = apply_butterworth_filter(arr_hip_y, real_fps, cutoff_hz=cutoff, order=order)
        filt_abd = apply_butterworth_filter(arr_abd, real_fps, cutoff_hz=cutoff, order=order)

        # Calcul de la vitesse verticale des hanches (dy / dt)
        if len(filt_hip_y) > 1:
            hip_vel = np.gradient(filt_hip_y, dt)
        else:
            hip_vel = np.zeros_like(filt_hip_y)

        # Lissage de la vitesse verticale
        filt_hip_vel = apply_butterworth_filter(hip_vel, real_fps, cutoff_hz=cutoff, order=order)

        if progress_callback:
            progress_callback(1.0, "Analyse cinématique terminée.")

        return {
            "fps": real_fps,
            "dt": dt,
            "total_frames": len(timestamps),
            "duration": round(timestamps[-1], 2) if timestamps else 0.0,
            "timestamps": np.array(timestamps, dtype=np.float64),
            "angles_raw": {
                "elbow": arr_elbow,
                "body_alignment": arr_align,
                "body_horizontal_tilt": arr_tilt,
                "shoulder_trunk": arr_sh,
                "hip_y": arr_hip_y,
                "arm_abduction": arr_abd
            },
            "angles_filtered": {
                "elbow": filt_elbow,
                "body_alignment": filt_align,
                "body_horizontal_tilt": filt_tilt,
                "shoulder_trunk": filt_sh,
                "hip_y": filt_hip_y,
                "arm_abduction": filt_abd,
                "hip_vertical_velocity": filt_hip_vel
            },
            "valid_mask": np.array(valid_detection_mask, dtype=bool),
            "keyframes": annotated_keyframes
        }

    finally:
        cap.release()
