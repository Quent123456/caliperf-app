"""
core/rep_counter.py - Machine à états cinématique & diagnostic de calibration
Évalue les séries temporelles filtrées selon les règles de config/exercise_thresholds.json.
Gère :
  - Mode Isométrique (TUT effectif, stabilité des hanches, dérive angulaire en fin de tenue)
  - Mode Dynamique (comptage de répétitions complètes, TUT actif hors verrouillage)
  - Mode Calibration (extraction des moyennes et enregistrement dans la configuration)
"""

import os
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from core.biomechanics import load_exercise_thresholds, save_exercise_thresholds


def evaluate_isometric_figure(
    kinematics: Dict[str, Any],
    exercise_key: str,
    custom_thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Évalue une figure isométrique (Full Planche, Straddle Planche, Maltese, Front Lever).
    Incrémente le TUT effectif uniquement lorsque les angles respectent les tolérances
    ET que la vitesse verticale des hanches reste sous le seuil de stabilité.
    """
    config = custom_thresholds or load_exercise_thresholds()
    exo_cfg = config.get("exercises", {}).get(exercise_key)

    if not exo_cfg:
        raise ValueError(f"Exercice inconnu dans la configuration : {exercise_key}")

    angles_cfg = exo_cfg.get("angles", {})
    stability_cfg = exo_cfg.get("stability", {})
    max_hip_vel = float(stability_cfg.get("max_hip_vertical_velocity", 0.08))

    timestamps = kinematics["timestamps"]
    dt = kinematics["dt"]
    filtered = kinematics["angles_filtered"]

    elbow = filtered["elbow"]
    body_align = filtered["body_alignment"]
    tilt = filtered["body_horizontal_tilt"]
    hip_vel = np.abs(filtered.get("hip_vertical_velocity", np.zeros_like(elbow)))

    num_frames = len(timestamps)
    frame_valid = np.zeros(num_frames, dtype=bool)

    # Récupération des seuils
    elbow_min = float(angles_cfg.get("elbow", {}).get("min", 165.0))
    align_min = float(angles_cfg.get("body_alignment", {}).get("min", 160.0))
    align_max = float(angles_cfg.get("body_alignment", {}).get("max", 195.0))
    tilt_min = float(angles_cfg.get("body_horizontal_tilt", {}).get("min", -15.0))
    tilt_max = float(angles_cfg.get("body_horizontal_tilt", {}).get("max", 15.0))

    for i in range(num_frames):
        cond_elbow = elbow[i] >= elbow_min
        cond_align = align_min <= body_align[i] <= align_max
        cond_tilt = tilt_min <= tilt[i] <= tilt_max
        cond_stability = hip_vel[i] <= max_hip_vel

        frame_valid[i] = cond_elbow and cond_align and cond_tilt and cond_stability

    # Identification des blocs continus de tenue
    hold_blocks: List[Dict[str, Any]] = []
    in_hold = False
    start_idx = 0

    for i in range(num_frames):
        if frame_valid[i] and not in_hold:
            in_hold = True
            start_idx = i
        elif not frame_valid[i] and in_hold:
            in_hold = False
            duration = (i - start_idx) * dt
            if duration >= float(stability_cfg.get("min_hold_duration_sec", 0.5)):
                hold_blocks.append({
                    "start_time": round(float(timestamps[start_idx]), 2),
                    "end_time": round(float(timestamps[i - 1]), 2),
                    "duration": round(float(duration), 2),
                    "start_idx": start_idx,
                    "end_idx": i - 1
                })

    if in_hold:
        duration = (num_frames - start_idx) * dt
        if duration >= float(stability_cfg.get("min_hold_duration_sec", 0.5)):
            hold_blocks.append({
                "start_time": round(float(timestamps[start_idx]), 2),
                "end_time": round(float(timestamps[-1]), 2),
                "duration": round(float(duration), 2),
                "start_idx": start_idx,
                "end_idx": num_frames - 1
            })

    # TUT effectif total cumulé
    effective_tut = sum(b["duration"] for b in hold_blocks)
    max_hold = max((b["duration"] for b in hold_blocks), default=0.0)

    # Calcul de la dérive angulaire sur la tenue la plus longue
    drift_info: Dict[str, Any] = {}
    if hold_blocks:
        longest = max(hold_blocks, key=lambda b: b["duration"])
        s_idx = longest["start_idx"]
        e_idx = longest["end_idx"]
        block_len = e_idx - s_idx + 1

        # Fenêtre de comparaison : min(2 secondes, 25% du bloc)
        window_frames = max(1, min(int(2.0 / dt), block_len // 4))

        start_slice = slice(s_idx, s_idx + window_frames)
        end_slice = slice(max(s_idx, e_idx - window_frames + 1), e_idx + 1)

        init_align = float(np.mean(body_align[start_slice]))
        final_align = float(np.mean(body_align[end_slice]))
        align_drift = round(final_align - init_align, 1)

        init_tilt = float(np.mean(tilt[start_slice]))
        final_tilt = float(np.mean(tilt[end_slice]))
        tilt_drift = round(final_tilt - init_tilt, 1)

        init_elbow = float(np.mean(elbow[start_slice]))
        final_elbow = float(np.mean(elbow[end_slice]))
        elbow_drift = round(final_elbow - init_elbow, 1)

        drift_info = {
            "longest_hold_sec": longest["duration"],
            "alignment_drift_deg": align_drift,  # négatif = cassure/affaissement
            "tilt_drift_deg": tilt_drift,        # positif = bascule vers le sol
            "elbow_drift_deg": elbow_drift,      # négatif = flexion des bras
            "initial_alignment": round(init_align, 1),
            "final_alignment": round(final_align, 1),
            "initial_elbow": round(init_elbow, 1),
            "final_elbow": round(final_elbow, 1)
        }

    return {
        "exercise": exercise_key,
        "type": "isometric",
        "display_name": exo_cfg.get("display_name", exercise_key),
        "effective_tut": round(effective_tut, 2),
        "max_continuous_hold": round(max_hold, 2),
        "hold_blocks": hold_blocks,
        "frame_valid_mask": frame_valid,
        "angular_drift": drift_info,
        "thresholds_used": {
            "elbow_min": elbow_min,
            "align_min": align_min,
            "align_max": align_max,
            "tilt_min": tilt_min,
            "tilt_max": tilt_max,
            "max_hip_velocity": max_hip_vel
        }
    }


def evaluate_dynamic_movement(
    kinematics: Dict[str, Any],
    exercise_key: str,
    custom_thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Évalue un mouvement dynamique (Tractions, Pompes, Planche Push-ups).
    Machine à états :
      LOCKOUT -> DESCENT/ECCENTRIC -> INFLECTION (seuil validé) -> CONCENTRIC -> LOCKOUT_RETURN
    Calcule le TUT actif en excluant les pauses statiques prolongées au verrouillage.
    """
    config = custom_thresholds or load_exercise_thresholds()
    exo_cfg = config.get("exercises", {}).get(exercise_key)

    if not exo_cfg:
        raise ValueError(f"Exercice inconnu dans la configuration : {exercise_key}")

    phases_cfg = exo_cfg.get("phases", {})
    timing_cfg = exo_cfg.get("timing", {})

    lockout_thresh = float(phases_cfg.get("lockout_bottom" if exercise_key == "pull_ups" else "lockout_top", {}).get("elbow_min", 160.0))
    inflection_thresh = float(phases_cfg.get("inflection_top" if exercise_key == "pull_ups" else "inflection_bottom", {}).get("elbow_max", 85.0))
    min_rep_sec = float(timing_cfg.get("min_rep_duration_sec", 0.6))
    max_rep_sec = float(timing_cfg.get("max_rep_duration_sec", 8.0))
    lockout_pause_limit = float(timing_cfg.get("lockout_pause_threshold_sec", 0.4))

    timestamps = kinematics["timestamps"]
    dt = kinematics["dt"]
    elbow = kinematics["angles_filtered"]["elbow"]
    num_frames = len(timestamps)

    # Machine à états
    # État 0: WAITING_FOR_START
    # État 1: MOVING_TOWARDS_INFLECTION (excentrique ou concentrique selon exo)
    # État 2: INFLECTION_REACHED
    # État 3: MOVING_BACK_TO_LOCKOUT
    state = "WAITING"
    rep_start_idx = 0
    inflection_idx = 0
    inflection_val = 180.0 if exercise_key == "pull_ups" else 0.0

    completed_reps: List[Dict[str, Any]] = []
    active_mask = np.zeros(num_frames, dtype=bool)

    for i in range(num_frames):
        ang = elbow[i]

        if state == "WAITING":
            # Détection du départ (l'angle quitte le verrouillage de plus de 8°)
            if ang < (lockout_thresh - 8.0):
                state = "MOVING_TO_INFLECTION"
                rep_start_idx = max(0, i - 1)
                inflection_val = ang
                inflection_idx = i
                active_mask[i] = True

        elif state == "MOVING_TO_INFLECTION":
            active_mask[i] = True
            if exercise_key == "pull_ups":
                if ang < inflection_val:
                    inflection_val = ang
                    inflection_idx = i
                if ang <= inflection_thresh:
                    state = "INFLECTION_REACHED"
            else:
                if ang < inflection_val:
                    inflection_val = ang
                    inflection_idx = i
                if ang <= inflection_thresh:
                    state = "INFLECTION_REACHED"

        elif state == "INFLECTION_REACHED":
            active_mask[i] = True
            # Commence à remonter vers le verrouillage
            if ang > (inflection_val + 6.0):
                state = "MOVING_TO_LOCKOUT"

        elif state == "MOVING_TO_LOCKOUT":
            active_mask[i] = True
            if ang >= (lockout_thresh - 6.0):
                # Répétition terminée avec retour au verrouillage
                rep_end_idx = i
                duration = (rep_end_idx - rep_start_idx) * dt

                if min_rep_sec <= duration <= max_rep_sec:
                    rep_t_start = round(float(timestamps[rep_start_idx]), 2)
                    rep_t_end = round(float(timestamps[rep_end_idx]), 2)
                    rep_t_inflection = round(float(timestamps[inflection_idx]), 2)

                    t_down = round(rep_t_inflection - rep_t_start, 2)
                    t_up = round(rep_t_end - rep_t_inflection, 2)

                    completed_reps.append({
                        "rep_number": len(completed_reps) + 1,
                        "start_time": rep_t_start,
                        "end_time": rep_t_end,
                        "duration": round(duration, 2),
                        "inflection_angle": round(float(inflection_val), 1),
                        "t_phase_1": t_down,
                        "t_phase_2": t_up,
                        "tempo_label": f"{t_down}s / {t_up}s"
                    })

                state = "WAITING"

    total_active_tut = sum(r["duration"] for r in completed_reps)
    avg_tempo = round(total_active_tut / len(completed_reps), 2) if completed_reps else 0.0

    return {
        "exercise": exercise_key,
        "type": "dynamic",
        "display_name": exo_cfg.get("display_name", exercise_key),
        "valid_reps_count": len(completed_reps),
        "active_tut": round(total_active_tut, 2),
        "average_rep_duration": avg_tempo,
        "reps_detail": completed_reps,
        "active_mask": active_mask,
        "thresholds_used": {
            "lockout_thresh": lockout_thresh,
            "inflection_thresh": inflection_thresh,
            "min_rep_sec": min_rep_sec,
            "max_rep_sec": max_rep_sec
        }
    }


def calibrate_and_update_thresholds(
    kinematics: Dict[str, Any],
    exercise_key: str,
    time_window: Optional[Tuple[float, float]] = None,
    config_path: str = "config/exercise_thresholds.json"
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Mode Calibration : Extrait les moyennes angulaires d'une exécution de référence
    et met à jour config/exercise_thresholds.json pour cet exercice.
    """
    try:
        config = load_exercise_thresholds(config_path)
        if exercise_key not in config.get("exercises", {}):
            return False, {}, f"Exercice '{exercise_key}' non trouvé dans la configuration."

        timestamps = kinematics["timestamps"]
        filtered = kinematics["angles_filtered"]

        if time_window:
            t_min, t_max = time_window
            mask = (timestamps >= t_min) & (timestamps <= t_max)
        else:
            mask = np.ones(len(timestamps), dtype=bool)

        if not np.any(mask):
            return False, {}, "Aucune donnée dans la fenêtre temporelle sélectionnée."

        mean_elbow = float(np.mean(filtered["elbow"][mask]))
        mean_align = float(np.mean(filtered["body_alignment"][mask]))
        mean_tilt = float(np.mean(filtered["body_horizontal_tilt"][mask]))
        mean_sh = float(np.mean(filtered["shoulder_trunk"][mask]))

        exo = config["exercises"][exercise_key]
        angles_sec = exo.setdefault("angles", {})

        # Mise à jour des valeurs idéales et tolérances calibrées
        if "elbow" in angles_sec:
            angles_sec["elbow"]["ideal"] = round(mean_elbow, 1)
            angles_sec["elbow"]["min"] = round(max(150.0, mean_elbow - 10.0), 1)

        if "body_alignment" in angles_sec:
            angles_sec["body_alignment"]["ideal"] = round(mean_align, 1)
            angles_sec["body_alignment"]["min"] = round(mean_align - 12.0, 1)
            angles_sec["body_alignment"]["max"] = round(mean_align + 12.0, 1)

        if "body_horizontal_tilt" in angles_sec:
            angles_sec["body_horizontal_tilt"]["ideal"] = round(mean_tilt, 1)
            angles_sec["body_horizontal_tilt"]["min"] = round(mean_tilt - 12.0, 1)
            angles_sec["body_horizontal_tilt"]["max"] = round(mean_tilt + 12.0, 1)

        calibrated_values = {
            "mean_elbow": round(mean_elbow, 1),
            "mean_alignment": round(mean_align, 1),
            "mean_tilt": round(mean_tilt, 1),
            "mean_shoulder_trunk": round(mean_sh, 1)
        }

        success = save_exercise_thresholds(config, config_path)
        if success:
            return True, calibrated_values, "Calibration enregistrée avec succès."
        return False, calibrated_values, "Erreur lors de la sauvegarde du fichier JSON."

    except Exception as e:
        return False, {}, f"Erreur de calibration : {e}"
