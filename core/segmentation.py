"""
core/segmentation.py - Auto-trimming de l'effort et classification Statique vs Dynamique
Fonctionnalités :
1. Auto-Trimming : Isole la fenêtre d'effort active en rognant les temps morts
   (marche, mise en place, magnésie) au début et à la fin de la vidéo.
2. Séparation Isométrique vs Dynamique : Analyse l'écart-type (sigma) et l'amplitude
   pic-à-pic des angles articulaires sur la fenêtre active.
"""

from typing import Dict, Any, Tuple
import numpy as np


def detect_active_effort_window(
    kinematics: Dict[str, Any],
    min_active_duration_sec: float = 0.5
) -> Dict[str, Any]:
    """
    Détecte automatiquement la fenêtre temporelle de travail actif.
    Règles de détection de l'effort :
    - Position horizontale (trunk_inclination < 50°) : Planches, Maltese, Front Lever, Pompes.
    - OU Suspension / charge de barre (ventral_dorsal < 0 et shoulder_flexion > 60° ou coude fléchi) : Tractions.
    - Élimine la marche/debout inactif (corps vertical + bras au repos).
    """
    timestamps = kinematics["timestamps"]
    dt = kinematics["dt"]
    num_frames = len(timestamps)

    if num_frames < 3:
        return {
            "start_idx": 0,
            "end_idx": max(0, num_frames - 1),
            "start_time": float(timestamps[0]) if num_frames > 0 else 0.0,
            "end_time": float(timestamps[-1]) if num_frames > 0 else 0.0,
            "duration": float(timestamps[-1] - timestamps[0]) if num_frames > 0 else 0.0,
            "active_mask": np.ones(num_frames, dtype=bool)
        }

    filt = kinematics["features_filtered"]
    trunk = filt["trunk_inclination"]
    elbow = filt["elbow_angle"]
    sh_flex = filt["shoulder_flexion"]
    vd = filt["ventral_dorsal"]
    valid_detect = kinematics.get("detection_valid_mask", np.ones(num_frames, dtype=bool))

    # Critère 1 : corps horizontal (Planche, Front Lever, Pompes, Maltese)
    cond_horizontal = trunk <= 48.0

    # Critère 2 : suspension active / tractions (bras engagés, coude fléchi ou flexion épaule haute)
    cond_hanging_traction = (vd < 0) & ((sh_flex >= 55.0) | (elbow <= 150.0))

    # Masque brut d'activité
    raw_active = (cond_horizontal | cond_hanging_traction) & valid_detect

    # Si presque aucune frame n'est détectée par les critères stricts,
    # on vérifie si la vidéo est déjà une courte découpe de set
    if np.sum(raw_active) < int(min_active_duration_sec / dt):
        # Repli : on considère que l'effort est l'ensemble de la vidéo
        raw_active = np.ones(num_frames, dtype=bool)

    # Fermeture temporelle pour boucher les coupures courtes (< 0.4s)
    gap_frames = max(1, int(round(0.4 / dt)))
    closed_active = raw_active.copy()
    last_true = -1
    for i in range(num_frames):
        if closed_active[i]:
            if last_true != -1 and (i - last_true) <= gap_frames:
                closed_active[last_true:i] = True
            last_true = i

    active_indices = np.where(closed_active)[0]
    if len(active_indices) == 0:
        start_idx = 0
        end_idx = num_frames - 1
    else:
        start_idx = int(active_indices[0])
        end_idx = int(active_indices[-1])

    # Assurer une durée minimale
    min_frames = max(2, int(round(min_active_duration_sec / dt)))
    if (end_idx - start_idx + 1) < min_frames:
        start_idx = 0
        end_idx = num_frames - 1

    final_mask = np.zeros(num_frames, dtype=bool)
    final_mask[start_idx:end_idx + 1] = True

    start_t = round(float(timestamps[start_idx]), 2)
    end_t = round(float(timestamps[end_idx]), 2)
    active_dur = round(max(0.0, end_t - start_t), 2)

    return {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "start_time": start_t,
        "end_time": end_t,
        "duration": active_dur,
        "active_mask": final_mask
    }


def classify_static_vs_dynamic(
    kinematics: Dict[str, Any],
    effort_window: Dict[str, Any],
    sigma_threshold_deg: float = 7.0,
    peak_to_peak_threshold_deg: float = 22.0
) -> Dict[str, Any]:
    """
    Détermine si l'effort est 'isometric' (maintien statique) ou 'dynamic' (répétitions).
    Analyse l'écart-type et l'amplitude pic-à-pic de l'angle du coude et de la flexion d'épaule
    sur la fenêtre active filtrée.
    """
    s_idx = effort_window["start_idx"]
    e_idx = effort_window["end_idx"]

    filt = kinematics["features_filtered"]
    elbow_active = filt["elbow_angle"][s_idx:e_idx + 1]
    sh_flex_active = filt["shoulder_flexion"][s_idx:e_idx + 1]

    if len(elbow_active) < 3:
        return {
            "type": "isometric",
            "elbow_std": 0.0,
            "elbow_p2p": 0.0,
            "shoulder_std": 0.0,
            "shoulder_p2p": 0.0,
            "reason": "Séquence trop courte pour dynamique"
        }

    elbow_std = float(np.std(elbow_active))
    elbow_p2p = float(np.ptp(elbow_active))

    sh_std = float(np.std(sh_flex_active))
    sh_p2p = float(np.ptp(sh_flex_active))

    # Un mouvement est dynamique si le coude ou l'épaule présente une oscillation significative
    is_dynamic = (
        (elbow_std >= sigma_threshold_deg and elbow_p2p >= peak_to_peak_threshold_deg) or
        (sh_std >= sigma_threshold_deg and sh_p2p >= peak_to_peak_threshold_deg)
    )

    detected_type = "dynamic" if is_dynamic else "isometric"

    return {
        "type": detected_type,
        "elbow_std": round(elbow_std, 1),
        "elbow_p2p": round(elbow_p2p, 1),
        "shoulder_std": round(sh_std, 1),
        "shoulder_p2p": round(sh_p2p, 1),
        "reason": f"Elbow σ={elbow_std:.1f}°, P2P={elbow_p2p:.1f}° | Shoulder σ={sh_std:.1f}°, P2P={sh_p2p:.1f}°"
    }


def segment_and_classify_video(kinematics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exécute le pipeline complet de segmentation :
    1. Découpage de la fenêtre active (Auto-trimming)
    2. Classification Statique vs Dynamique
    """
    effort_win = detect_active_effort_window(kinematics)
    classification = classify_static_vs_dynamic(kinematics, effort_win)

    return {
        "effort_window": effort_win,
        "classification": classification,
        "type": classification["type"]
    }
