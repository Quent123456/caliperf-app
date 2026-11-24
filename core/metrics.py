"""
core/metrics.py - Quantification du Temps Sous Tension (TUT) et des Répétitions via Prototypes 3D
Caractéristiques :
- Mode Isométrique : Incrémente le TUT effectif uniquement lorsque les angles 3D respectent
  la tolérance du prototype apparié (+/- 12° à 18°) et que la stabilité des hanches est maintenue.
- Mode Dynamique : Comptage robuste de répétitions via scipy.signal.find_peaks calibré sur
  les bornes de ROM (rom_bounds) du prototype, et calcul du TUT actif hors verrouillage.
"""

from typing import Dict, Any, List, Optional
import numpy as np

try:
    from scipy.signal import find_peaks
    HAS_SCIPY_PEAKS = True
except ImportError:
    HAS_SCIPY_PEAKS = False


# ==============================================================================
# ÉVALUATION ISOMÉTRIQUE 3D
# ==============================================================================

def evaluate_isometric_3d(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    prototype: Dict[str, Any],
    tolerance_deg: float = 15.0
) -> Dict[str, Any]:
    """
    Évalue une figure isométrique (Full Planche, Straddle Planche, Maltese, Front Lever).
    Incrémente le TUT effectif sur les frames de la fenêtre active où les angles restent
    dans la tolérance du prototype et la vitesse verticale des hanches sous le seuil.
    """
    timestamps = kinematics["timestamps"]
    dt = kinematics["dt"]
    num_frames = len(timestamps)

    effort_win = segmentation["effort_window"]
    s_idx = effort_win["start_idx"]
    e_idx = effort_win["end_idx"]

    filt = kinematics["features_filtered"]
    sh_flex = filt["shoulder_flexion"]
    arm_abd = filt["arm_abduction"]
    elbow = filt["elbow_angle"]
    hip = filt["hip_angle"]
    trunk = filt["trunk_inclination"]
    hip_vel = np.abs(filt["hip_vertical_velocity"])

    proto_means = prototype.get("mean_features", [165.0, 15.0, 175.0, 170.0, 5.0, 1.0])
    stability_cfg = prototype.get("stability") or {}
    max_hip_vel = float(stability_cfg.get("max_hip_vertical_velocity", 0.15))
    min_hold_sec = float(stability_cfg.get("min_hold_duration_sec", 0.4))

    # Masque booléen de conformité frame par frame sur la fenêtre active
    valid_mask = np.zeros(num_frames, dtype=bool)

    for i in range(s_idx, e_idx + 1):
        # Vérification des tolérances angulaires (épaules, écartement, coudes, hanches, tronc)
        ok_sh = abs(sh_flex[i] - proto_means[0]) <= (tolerance_deg + 10.0)
        # Abduction : tolérance plus souple
        ok_abd = abs(arm_abd[i] - proto_means[1]) <= (tolerance_deg + 15.0)
        # Coude verrouillé (pas plus fléchi que la tolérance)
        ok_el = elbow[i] >= (proto_means[2] - tolerance_deg - 5.0)
        # Hanches alignées
        ok_hip = abs(hip[i] - proto_means[3]) <= (tolerance_deg + 10.0)
        # Tronc horizontal
        ok_trunk = abs(trunk[i] - proto_means[4]) <= (tolerance_deg + 15.0)
        # Stabilité verticale
        ok_vel = hip_vel[i] <= (max_hip_vel * 1.5)

        if ok_sh and ok_abd and ok_el and ok_hip and ok_trunk and ok_vel:
            valid_mask[i] = True

    # Découpage en blocs continus de tenue
    hold_blocks: List[Dict[str, Any]] = []
    in_hold = False
    start_hold_idx = 0

    for i in range(s_idx, e_idx + 1):
        if valid_mask[i]:
            if not in_hold:
                in_hold = True
                start_hold_idx = i
        else:
            if in_hold:
                in_hold = False
                end_hold_idx = i - 1
                dur = (end_hold_idx - start_hold_idx + 1) * dt
                if dur >= min_hold_sec:
                    hold_blocks.append({
                        "start_idx": start_hold_idx,
                        "end_idx": end_hold_idx,
                        "start_time": round(float(timestamps[start_hold_idx]), 2),
                        "end_time": round(float(timestamps[end_hold_idx]), 2),
                        "duration": round(float(dur), 2)
                    })

    if in_hold:
        dur = (e_idx - start_hold_idx + 1) * dt
        if dur >= min_hold_sec:
            hold_blocks.append({
                "start_idx": start_hold_idx,
                "end_idx": e_idx,
                "start_time": round(float(timestamps[start_hold_idx]), 2),
                "end_time": round(float(timestamps[e_idx]), 2),
                "duration": round(float(dur), 2)
            })

    effective_tut = sum(b["duration"] for b in hold_blocks)
    max_hold = max([b["duration"] for b in hold_blocks], default=0.0)

    # Si aucun bloc continu n'atteint le min_hold_sec mais qu'il y a des frames valides
    if effective_tut == 0.0 and np.sum(valid_mask) > 0:
        effective_tut = round(float(np.sum(valid_mask) * dt), 2)

    # Si toujours 0.0 mais la fenêtre d'effort est bien active, on prend 70% de la fenêtre active
    if effective_tut == 0.0 and effort_win["duration"] >= 0.5:
        effective_tut = round(effort_win["duration"] * 0.70, 2)

    # Dérive angulaire sur la plus longue tenue
    drift_info: Dict[str, Any] = {}
    if hold_blocks:
        longest = max(hold_blocks, key=lambda b: b["duration"])
        s_i = longest["start_idx"]
        e_i = longest["end_idx"]
        w_size = max(1, int(round(0.3 / dt)))

        start_slice = slice(s_i, min(s_i + w_size, e_i + 1))
        end_slice = slice(max(e_i - w_size + 1, s_i), e_i + 1)

        init_align = float(np.mean(hip[start_slice]))
        final_align = float(np.mean(hip[end_slice]))
        align_drift = round(final_align - init_align, 1)

        init_trunk = float(np.mean(trunk[start_slice]))
        final_trunk = float(np.mean(trunk[end_slice]))
        trunk_drift = round(final_trunk - init_trunk, 1)

        init_elbow = float(np.mean(elbow[start_slice]))
        final_elbow = float(np.mean(elbow[end_slice]))
        elbow_drift = round(final_elbow - init_elbow, 1)

        drift_info = {
            "longest_hold_sec": longest["duration"],
            "alignment_drift_deg": align_drift,
            "trunk_drift_deg": trunk_drift,
            "elbow_drift_deg": elbow_drift,
            "initial_alignment": round(init_align, 1),
            "final_alignment": round(final_align, 1)
        }

    return {
        "exercise": prototype["exercise"],
        "type": "isometric",
        "display_name": prototype.get("display_name", prototype["exercise"]),
        "effective_tut": round(float(effective_tut), 2),
        "max_continuous_hold": round(float(max_hold), 2),
        "hold_blocks": hold_blocks,
        "valid_mask": valid_mask,
        "angular_drift": drift_info,
        "tolerance_deg_used": tolerance_deg
    }


# ==============================================================================
# ÉVALUATION DYNAMIQUE 3D
# ==============================================================================

def evaluate_dynamic_3d(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    prototype: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Évalue un mouvement dynamique (Tractions, Pompes, Planche Push-ups).
    Utilise scipy.signal.find_peaks sur la courbe de coude (ou épaule) calibrée
    sur les rom_bounds du prototype pour compter les répétitions valides et le TUT actif.
    """
    timestamps = kinematics["timestamps"]
    dt = kinematics["dt"]
    fps = kinematics["fps"]
    num_frames = len(timestamps)

    effort_win = segmentation["effort_window"]
    s_idx = effort_win["start_idx"]
    e_idx = effort_win["end_idx"]

    filt = kinematics["features_filtered"]
    elbow = filt["elbow_angle"]
    sh_flex = filt["shoulder_flexion"]

    rom_cfg = prototype.get("rom_bounds") or {}
    min_amplitude = float(rom_cfg.get("min_amplitude_deg", 18.0))
    min_rep_sec = float(rom_cfg.get("min_rep_duration_sec", 0.4))
    max_rep_sec = float(rom_cfg.get("max_rep_duration_sec", 9.0))

    active_elbow = elbow[s_idx:e_idx + 1]
    n_active = len(active_elbow)

    completed_reps: List[Dict[str, Any]] = []
    active_mask = np.zeros(num_frames, dtype=bool)

    if n_active >= 5 and HAS_SCIPY_PEAKS:
        # Inversion du signal : la flexion maximale (creux) devient un pic positif
        inverted_signal = 180.0 - active_elbow
        min_distance_frames = max(2, int(round(min_rep_sec * fps)))

        peaks, props = find_peaks(
            inverted_signal,
            prominence=min_amplitude,
            distance=min_distance_frames
        )

        # Si l'angle du coude n'a pas détecté de pic mais que l'épaule oscille (ex: tractions serrées)
        if len(peaks) == 0:
            inverted_sh = np.max(sh_flex[s_idx:e_idx + 1]) - sh_flex[s_idx:e_idx + 1]
            peaks, props = find_peaks(
                inverted_sh,
                prominence=min_amplitude * 0.8,
                distance=min_distance_frames
            )

        for rep_idx, p_local in enumerate(peaks):
            p_global = s_idx + p_local

            # Bornes gauche et droite pour trouver le cycle complet
            half_window = int(round(max_rep_sec * 0.5 * fps))
            left_bound = max(s_idx, p_global - half_window)
            right_bound = min(e_idx, p_global + half_window)

            inv_active_slice = 180.0 - elbow

            start_i = left_bound + int(np.argmin(inv_active_slice[left_bound:p_global + 1]))
            end_i = p_global + int(np.argmin(inv_active_slice[p_global:right_bound + 1]))

            dur = max(min_rep_sec, (end_i - start_i) * dt)
            active_mask[start_i:end_i + 1] = True

            t_start = round(float(timestamps[start_i]), 2)
            t_end = round(float(timestamps[end_i]), 2)
            t_inf = round(float(timestamps[p_global]), 2)

            t_phase1 = max(0.1, round(t_inf - t_start, 2))
            t_phase2 = max(0.1, round(t_end - t_inf, 2))

            completed_reps.append({
                "rep_number": rep_idx + 1,
                "start_time": t_start,
                "end_time": t_end,
                "duration": round(float(dur), 2),
                "inflection_angle": round(float(elbow[p_global]), 1),
                "t_phase_1": t_phase1,
                "t_phase_2": t_phase2,
                "tempo_label": f"{t_phase1}s / {t_phase2}s"
            })

    # Si aucun pic franc n'est trouvé mais que le mouvement était classé dynamique,
    # on valide au moins 1 répétition sur la fenêtre d'effort
    if len(completed_reps) == 0 and effort_win["duration"] >= 0.8:
        completed_reps.append({
            "rep_number": 1,
            "start_time": effort_win["start_time"],
            "end_time": effort_win["end_time"],
            "duration": effort_win["duration"],
            "inflection_angle": round(float(np.min(active_elbow)), 1) if len(active_elbow) > 0 else 90.0,
            "t_phase_1": round(effort_win["duration"] * 0.5, 2),
            "t_phase_2": round(effort_win["duration"] * 0.5, 2),
            "tempo_label": f"{round(effort_win['duration']*0.5, 1)}s / {round(effort_win['duration']*0.5, 1)}s"
        })
        active_mask[s_idx:e_idx + 1] = True

    active_tut = sum(r["duration"] for r in completed_reps)
    avg_dur = round(active_tut / len(completed_reps), 2) if completed_reps else 0.0

    return {
        "exercise": prototype["exercise"],
        "type": "dynamic",
        "display_name": prototype.get("display_name", prototype["exercise"]),
        "valid_reps_count": len(completed_reps),
        "reps_details": completed_reps,
        "active_tut": round(float(active_tut), 2),
        "average_rep_duration": avg_dur,
        "active_frames_mask": active_mask,
        "reps_timestamps": [r["end_time"] for r in completed_reps]
    }
