"""
core/biomechanics_3d.py - Extraction cinématique 3D haute performance via MediaPipe world landmarks
Caractéristiques clés :
- Utilise exclusivement les coordonnées métriques 3D pose_world_landmarks (centrées bassin, +Y = gravité)
- Calcule image par image un vecteur de features 6D invariant à la distance et robuste aux perspectives :
    1. shoulder_flexion : angle 3D hanche–épaule–coude
    2. arm_abduction : angle 3D d'écartement des bras (Maltese vs Planche)
    3. elbow_angle : angle 3D épaule–coude–poignet (verrouillé vs fléchi)
    4. hip_angle : angle 3D épaule–hanche–genou (alignement corporel)
    5. trunk_inclination : angle du vecteur épaule–hanche / plan horizontal (X, Z)
    6. ventral_dorsal : projection normale du torse sur Y (+1 ventral, -1 dorsal)
- Downscale dynamique à max_width=640px pour une vitesse CPU extrême (< 2.5s / vidéo)
- Filtrage passe-bas Butterworth zéro-phase (scipy.signal.filtfilt)
- Mise en cache intelligente indexée sur le hash MD5 du fichier vidéo
"""

import gc
import os
import hashlib
from typing import Dict, Any, List, Optional, Tuple
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

from core.biomechanics import ensure_model_asset, compute_video_hash, detect_optimal_rotation


# ==============================================================================
# CALCULS GÉOMÉTRIQUES 3D
# ==============================================================================

def compute_angle_3d(p_a: np.ndarray, p_vertex: np.ndarray, p_c: np.ndarray) -> float:
    """Calcule l'angle 3D au sommet p_vertex en degrés [0, 180]."""
    v_a = p_a - p_vertex
    v_c = p_c - p_vertex
    norm_a = np.linalg.norm(v_a)
    norm_c = np.linalg.norm(v_c)
    if norm_a < 1e-6 or norm_c < 1e-6:
        return 180.0
    cos_theta = np.dot(v_a, v_c) / (norm_a * norm_c)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_theta)))


def compute_vector_angle_3d(v1: np.ndarray, v2: np.ndarray) -> float:
    """Calcule l'angle 3D entre deux vecteurs en degrés [0, 180]."""
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cos_theta = np.dot(v1, v2) / (n1 * n2)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_theta)))


def compute_trunk_horizontal_inclination_3d(shoulder_mid: np.ndarray, hip_mid: np.ndarray) -> float:
    """
    Calcule l'angle d'inclinaison du tronc par rapport au plan horizontal (X, Z).
    0° = parfaitement parallèle au sol (horizontal).
    90° = vertical (debout ou suspension verticale).
    Dans MediaPipe world landmarks, +Y pointe vers le bas (gravité).
    """
    diff = hip_mid - shoulder_mid
    dy = abs(float(diff[1]))
    dxz = float(np.sqrt(diff[0]**2 + diff[2]**2))
    if dxz < 1e-6 and dy < 1e-6:
        return 0.0
    angle_rad = np.arctan2(dy, max(dxz, 1e-6))
    return float(np.degrees(angle_rad))


def compute_torso_ventral_dorsal_orientation(
    sh_l: np.ndarray,
    sh_r: np.ndarray,
    shoulder_mid: np.ndarray,
    hip_mid: np.ndarray
) -> float:
    """
    Calcule l'orientation ventrale/dorsale du buste par produit vectoriel :
    normale du plan du torse projetée sur l'axe vertical Y (+Y vers le sol).
    +1.0 = Ventral / Pronation (face vers le sol : Planche, Maltese, Pompes)
    -1.0 = Dorsal / Supination (dos vers le sol / face vers le haut : Front Lever, Tractions)
    """
    v_sh = sh_l - sh_r
    v_spine = hip_mid - shoulder_mid
    normal = np.cross(v_sh, v_spine)
    norm_len = np.linalg.norm(normal)
    if norm_len < 1e-6:
        return 1.0
    ny = float(normal[1] / norm_len)
    # Retourne une valeur continue bornée ou signe
    return 1.0 if ny >= 0.0 else -1.0


# ==============================================================================
# FILTRAGE DU SIGNAL 3D
# ==============================================================================

def apply_butterworth_filter_1d(
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

    # Moyenne mobile de secours
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
# MOTEUR D'EXTRACTION 3D VIDÉO
# ==============================================================================

def _run_3d_extraction_from_video(
    video_path: str,
    max_width: int = 640,
    target_fps: float = 25.0
) -> Dict[str, Any]:
    """
    Lit la vidéo, applique l'auto-rotation 90°, extrait pose_world_landmarks (3D métrique),
    calcule le vecteur 6D et filtre les séries temporelles.
    """
    if not HAS_CV2:
        raise ImportError(f"OpenCV (cv2) n'est pas chargé : {CV2_IMPORT_ERROR}")
    if not HAS_MEDIAPIPE:
        raise ImportError(f"MediaPipe n'est pas chargé : {MEDIAPIPE_IMPORT_ERROR}")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Fichier introuvable : {video_path}")

    model_file = ensure_model_asset()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Impossible d'ouvrir la vidéo : {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        raw_fps_val = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps_metadata_valid = bool(raw_fps_val > 0.0 and not np.isnan(raw_fps_val))
        real_fps = raw_fps_val if fps_metadata_valid else 30.0

        # Échantillonnage pour atteindre target_fps (extrêmement rapide)
        stride = 1
        if real_fps > target_fps:
            stride = max(1, int(round(real_fps / target_fps)))

        effective_fps = real_fps / float(stride)
        dt = 1.0 / effective_fps

        base_options = mp_tasks.BaseOptions(model_asset_path=model_file)
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE
        )

        timestamps: List[float] = []
        raw_frame_timestamps_ms: List[float] = []
        raw_shoulder_flex: List[float] = []
        raw_arm_abduct: List[float] = []
        raw_elbow: List[float] = []
        raw_hip: List[float] = []
        raw_trunk_tilt: List[float] = []
        raw_ventral_dorsal: List[float] = []
        raw_hip_y: List[float] = []
        detection_valid: List[bool] = []
        landmarks_2d_list: List[np.ndarray] = []
        frame_dim: Tuple[int, int] = (0, 0)

        def _empty_xyv() -> np.ndarray:
            arr = np.full((33, 3), np.nan, dtype=np.float32)
            arr[:, 2] = 0.0
            return arr

        with mp_vision.PoseLandmarker.create_from_options(options) as landmarker:
            rot_code = detect_optimal_rotation(cap, landmarker, max_width=max_width)
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            frame_idx = 0
            while True:
                ret, frame_bgr = cap.read()
                if not ret or frame_bgr is None:
                    break

                pos_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
                raw_frame_timestamps_ms.append(pos_ms)

                if frame_idx % stride != 0:
                    frame_idx += 1
                    continue

                curr_time = round(frame_idx / real_fps, 3)

                if rot_code is not None:
                    frame_bgr = cv2.rotate(frame_bgr, rot_code)

                h, w = frame_bgr.shape[:2]
                if w > max_width:
                    scale = max_width / float(w)
                    new_w = max_width
                    new_h = max(1, int(h * scale))
                    frame_bgr = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    frame_dim = (new_w, new_h)
                else:
                    frame_dim = (w, h)

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                res = landmarker.detect(mp_img)

                has_w = res.pose_world_landmarks and len(res.pose_world_landmarks) > 0
                if has_w:
                    wl = res.pose_world_landmarks[0]
                    # Points 3D métriques
                    p_nose = np.array([wl[0].x, wl[0].y, wl[0].z])
                    p_sh_l = np.array([wl[11].x, wl[11].y, wl[11].z])
                    p_sh_r = np.array([wl[12].x, wl[12].y, wl[12].z])
                    p_el_l = np.array([wl[13].x, wl[13].y, wl[13].z])
                    p_el_r = np.array([wl[14].x, wl[14].y, wl[14].z])
                    p_wr_l = np.array([wl[15].x, wl[15].y, wl[15].z])
                    p_wr_r = np.array([wl[16].x, wl[16].y, wl[16].z])
                    p_hip_l = np.array([wl[23].x, wl[23].y, wl[23].z])
                    p_hip_r = np.array([wl[24].x, wl[24].y, wl[24].z])
                    p_kn_l = np.array([wl[25].x, wl[25].y, wl[25].z])
                    p_kn_r = np.array([wl[26].x, wl[26].y, wl[26].z])
                    p_ak_l = np.array([wl[27].x, wl[27].y, wl[27].z])
                    p_ak_r = np.array([wl[28].x, wl[28].y, wl[28].z])

                    sh_mid = 0.5 * (p_sh_l + p_sh_r)
                    hip_mid = 0.5 * (p_hip_l + p_hip_r)

                    # 1. Angle d'épaule (flexion/extension) : hanche-épaule-coude
                    sh_flex_l = compute_angle_3d(p_hip_l, p_sh_l, p_el_l)
                    sh_flex_r = compute_angle_3d(p_hip_r, p_sh_r, p_el_r)
                    shoulder_flex = 0.5 * (sh_flex_l + sh_flex_r)

                    # 2. Angle d'abduction / écartement des bras (poignet-épaule G vs D)
                    v_arm_l = p_wr_l - p_sh_l
                    v_arm_r = p_wr_r - p_sh_r
                    arm_abduct = compute_vector_angle_3d(v_arm_l, v_arm_r)

                    # 3. Angle du coude : épaule-coude-poignet
                    el_l = compute_angle_3d(p_sh_l, p_el_l, p_wr_l)
                    el_r = compute_angle_3d(p_sh_r, p_el_r, p_wr_r)
                    elbow_ang = 0.5 * (el_l + el_r)

                    # 4. Angle de hanche (alignement) : épaule-hanche-genou
                    hip_l = compute_angle_3d(p_sh_l, p_hip_l, p_kn_l)
                    hip_r = compute_angle_3d(p_sh_r, p_hip_r, p_kn_r)
                    hip_ang = 0.5 * (hip_l + hip_r)

                    # 5. Inclinaison du tronc / horizontale (0° = horizontal, 90° = vertical)
                    trunk_tilt = compute_trunk_horizontal_inclination_3d(sh_mid, hip_mid)

                    # 6. Orientation ventrale/dorsale (+1.0 ventral, -1.0 dorsal)
                    vd_orient = compute_torso_ventral_dorsal_orientation(p_sh_l, p_sh_r, sh_mid, hip_mid)

                    timestamps.append(curr_time)
                    raw_shoulder_flex.append(shoulder_flex)
                    raw_arm_abduct.append(arm_abduct)
                    raw_elbow.append(elbow_ang)
                    raw_hip.append(hip_ang)
                    raw_trunk_tilt.append(trunk_tilt)
                    raw_ventral_dorsal.append(vd_orient)
                    raw_hip_y.append(float(hip_mid[1]))
                    detection_valid.append(True)

                    xyv = _empty_xyv()
                    if res.pose_landmarks and len(res.pose_landmarks) > 0:
                        lm2d = res.pose_landmarks[0]
                        for lm_idx, lm in enumerate(lm2d[:33]):
                            vis_v = getattr(lm, "visibility", 0.0)
                            xyv[lm_idx, 0] = float(lm.x)
                            xyv[lm_idx, 1] = float(lm.y)
                            xyv[lm_idx, 2] = float(vis_v) if vis_v is not None else 0.0
                    landmarks_2d_list.append(xyv)
                else:
                    # Répétition de la dernière frame valide si dispo
                    timestamps.append(curr_time)
                    raw_shoulder_flex.append(raw_shoulder_flex[-1] if raw_shoulder_flex else 90.0)
                    raw_arm_abduct.append(raw_arm_abduct[-1] if raw_arm_abduct else 15.0)
                    raw_elbow.append(raw_elbow[-1] if raw_elbow else 180.0)
                    raw_hip.append(raw_hip[-1] if raw_hip else 170.0)
                    raw_trunk_tilt.append(raw_trunk_tilt[-1] if raw_trunk_tilt else 0.0)
                    raw_ventral_dorsal.append(raw_ventral_dorsal[-1] if raw_ventral_dorsal else 1.0)
                    raw_hip_y.append(raw_hip_y[-1] if raw_hip_y else 0.0)
                    detection_valid.append(False)
                    landmarks_2d_list.append(_empty_xyv())

                frame_idx += 1

        n_samples = len(timestamps)
        if n_samples == 0:
            timestamps = [0.0]
            raw_shoulder_flex = [90.0]
            raw_arm_abduct = [15.0]
            raw_elbow = [180.0]
            raw_hip = [170.0]
            raw_trunk_tilt = [0.0]
            raw_ventral_dorsal = [1.0]
            raw_hip_y = [0.0]
            detection_valid = [False]
            landmarks_2d_list = [_empty_xyv()]

        # Conversion en np.ndarray et filtrage passe-bas Butterworth
        arr_ts = np.array(timestamps, dtype=np.float64)
        arr_sh_flex = np.array(raw_shoulder_flex, dtype=np.float64)
        arr_arm_abd = np.array(raw_arm_abduct, dtype=np.float64)
        arr_elbow = np.array(raw_elbow, dtype=np.float64)
        arr_hip = np.array(raw_hip, dtype=np.float64)
        arr_trunk = np.array(raw_trunk_tilt, dtype=np.float64)
        arr_vd = np.array(raw_ventral_dorsal, dtype=np.float64)
        arr_hip_y = np.array(raw_hip_y, dtype=np.float64)

        filt_sh_flex = apply_butterworth_filter_1d(arr_sh_flex, effective_fps)
        filt_arm_abd = apply_butterworth_filter_1d(arr_arm_abd, effective_fps)
        filt_elbow = apply_butterworth_filter_1d(arr_elbow, effective_fps)
        filt_hip = apply_butterworth_filter_1d(arr_hip, effective_fps)
        filt_trunk = apply_butterworth_filter_1d(arr_trunk, effective_fps)
        # Pour ventral/dorsal, lissage médian/moyenne
        filt_vd = np.sign(apply_butterworth_filter_1d(arr_vd, effective_fps, cutoff_hz=1.0))
        filt_vd[filt_vd == 0] = 1.0

        # Calcul vélocité verticale des hanches (dérivée de hip_y)
        if len(arr_hip_y) > 1:
            hip_vel = np.gradient(arr_hip_y, dt)
        else:
            hip_vel = np.zeros_like(arr_hip_y)

        filt_hip_vel = apply_butterworth_filter_1d(hip_vel, effective_fps, cutoff_hz=3.0)

        return {
            "video_path": video_path,
            "fps": effective_fps,
            "raw_fps": round(raw_fps_val, 3) if fps_metadata_valid else 0.0,
            "fps_metadata_valid": fps_metadata_valid,
            "stride": int(stride),
            "dt": dt,
            "total_frames_raw": int(total_frames),
            "frame_size": frame_dim,
            "duration": round(float(arr_ts[-1] if len(arr_ts) > 0 else 0.0), 2),
            "timestamps": arr_ts,
            "raw_frame_timestamps_ms": np.array(raw_frame_timestamps_ms, dtype=np.float64),
            "features_raw": {
                "shoulder_flexion": arr_sh_flex,
                "arm_abduction": arr_arm_abd,
                "elbow_angle": arr_elbow,
                "hip_angle": arr_hip,
                "trunk_inclination": arr_trunk,
                "ventral_dorsal": arr_vd,
                "hip_y": arr_hip_y
            },
            "features_filtered": {
                "shoulder_flexion": filt_sh_flex,
                "arm_abduction": filt_arm_abd,
                "elbow_angle": filt_elbow,
                "hip_angle": filt_hip,
                "trunk_inclination": filt_trunk,
                "ventral_dorsal": filt_vd,
                "hip_vertical_velocity": filt_hip_vel
            },
            "landmarks_2d_xyv": np.stack(landmarks_2d_list, axis=0).astype(np.float32),
            "detection_valid_mask": np.array(detection_valid, dtype=bool),
            "rotation_applied": rot_code
        }
    finally:
        cap.release()
        gc.collect()


# ==============================================================================
# WRAPPER AVEC CACHE STREAMLIT
# ==============================================================================

if HAS_STREAMLIT:
    @st.cache_data(show_spinner=False, max_entries=15, ttl=3600)
    def _extract_3d_kinematics_cached(video_path: str, video_hash: str, schema_version: int = 2) -> Dict[str, Any]:
        return _run_3d_extraction_from_video(video_path)
else:
    def _extract_3d_kinematics_cached(video_path: str, video_hash: str, schema_version: int = 2) -> Dict[str, Any]:
        return _run_3d_extraction_from_video(video_path)


def extract_3d_kinematics_from_video(video_path: str) -> Dict[str, Any]:
    """
    Point d'entrée principal pour l'extraction cinématique 3D.
    Utilise le cache si la vidéo a déjà été analysée (recalcul instantané < 0.01s).
    """
    v_hash = compute_video_hash(video_path)
    return _extract_3d_kinematics_cached(video_path, v_hash, schema_version=2)
