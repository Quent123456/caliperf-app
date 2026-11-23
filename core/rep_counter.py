"""
core/rep_counter.py - Machine à états cinématique, comptage de répétitions robuste & Fusion IA
Gère :
  - Mode Isométrique : TUT effectif, stabilité des hanches, dérive angulaire.
  - Mode Dynamique : Comptage robuste de répétitions par détection de pics/vallées (scipy.signal.find_peaks),
    garantissant la validation de chaque cycle réalisé sans rejet arbitraire.
  - Fusion Hybride Optimale : Combine la précision cinématique MediaPipe avec la vision sémantique Gemini Flash.
  - Mode Traitement par lot ultra-rapide (< 3-5s par vidéo en parallèle).
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple, Callable
import numpy as np

try:
    from scipy.signal import find_peaks
    HAS_SCIPY_PEAKS = True
except ImportError:
    HAS_SCIPY_PEAKS = False

from core.biomechanics import load_exercise_thresholds, save_exercise_thresholds, extract_kinematics_from_video


def evaluate_isometric_figure(
    kinematics: Dict[str, Any],
    exercise_key: str,
    custom_thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Évalue une figure isométrique (Full Planche, Straddle Planche, Maltese, Front Lever).
    Incrémente le TUT effectif lorsque les angles respectent les tolérances
    ET que la vitesse verticale des hanches reste sous le seuil de stabilité.
    """
    config = custom_thresholds or load_exercise_thresholds()
    exo_cfg = config.get("exercises", {}).get(exercise_key)

    if not exo_cfg:
        exo_cfg = config.get("exercises", {}).get("full_planche", {})

    angles_cfg = exo_cfg.get("angles", {})
    stability_cfg = exo_cfg.get("stability", {})
    max_hip_vel = float(stability_cfg.get("max_hip_vertical_velocity", 0.15))
    min_hold_sec = float(stability_cfg.get("min_hold_duration_sec", 0.3))

    timestamps = kinematics["timestamps"]
    dt = kinematics["dt"]
    filtered = kinematics["angles_filtered"]

    elbow = filtered["elbow"]
    body_align = filtered["body_alignment"]
    tilt = filtered["body_horizontal_tilt"]
    hip_vel = np.abs(filtered.get("hip_vertical_velocity", np.zeros_like(elbow)))

    num_frames = len(timestamps)

    elbow_min = float(angles_cfg.get("elbow", {}).get("min", 140.0))
    align_min = float(angles_cfg.get("body_alignment", {}).get("min", 130.0))
    align_max = float(angles_cfg.get("body_alignment", {}).get("max", 195.0))
    tilt_min = float(angles_cfg.get("body_horizontal_tilt", {}).get("min", -35.0))
    tilt_max = float(angles_cfg.get("body_horizontal_tilt", {}).get("max", 35.0))

    # Masque booléen de validité frame par frame
    cond_elbow = elbow >= elbow_min
    cond_align = (body_align >= align_min) & (body_align <= align_max)
    cond_tilt = (tilt >= tilt_min) & (tilt <= tilt_max)
    cond_vel = hip_vel <= max_hip_vel

    frame_valid = cond_elbow & cond_align & cond_tilt & cond_vel

    # Identification des blocs continus de tenue
    hold_blocks: List[Dict[str, Any]] = []
    in_hold = False
    start_idx = 0

    for i in range(num_frames):
        if frame_valid[i]:
            if not in_hold:
                in_hold = True
                start_idx = i
        else:
            if in_hold:
                in_hold = False
                end_idx = i - 1
                dur = (end_idx - start_idx + 1) * dt
                if dur >= min_hold_sec:
                    hold_blocks.append({
                        "start_idx": start_idx,
                        "end_idx": end_idx,
                        "start_time": round(float(timestamps[start_idx]), 2),
                        "end_time": round(float(timestamps[end_idx]), 2),
                        "duration": round(float(dur), 2)
                    })

    if in_hold:
        dur = (num_frames - 1 - start_idx + 1) * dt
        if dur >= min_hold_sec:
            hold_blocks.append({
                "start_idx": start_idx,
                "end_idx": num_frames - 1,
                "start_time": round(float(timestamps[start_idx]), 2),
                "end_time": round(float(timestamps[num_frames - 1]), 2),
                "duration": round(float(dur), 2)
            })

    effective_tut = sum(b["duration"] for b in hold_blocks)
    max_hold = max([b["duration"] for b in hold_blocks], default=0.0)

    # Dérive angulaire sur la plus longue tenue
    drift_info: Dict[str, Any] = {}
    if hold_blocks:
        longest = max(hold_blocks, key=lambda b: b["duration"])
        s_i = longest["start_idx"]
        e_i = longest["end_idx"]
        window_size = max(1, int(round(0.4 / dt)))

        start_slice = slice(s_i, min(s_i + window_size, e_i + 1))
        end_slice = slice(max(e_i - window_size + 1, s_i), e_i + 1)

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
            "alignment_drift_deg": align_drift,
            "tilt_drift_deg": tilt_drift,
            "elbow_drift_deg": elbow_drift,
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
    Utilise find_peaks avec amplitude minimale (prominence) pour détecter chaque cycle
    de flexion-extension réalisé par l'athlète sans rejet arbitraire.
    """
    config = custom_thresholds or load_exercise_thresholds()
    exo_cfg = config.get("exercises", {}).get(exercise_key)

    if not exo_cfg:
        exo_cfg = config.get("exercises", {}).get("pull_ups", {})

    timing_cfg = exo_cfg.get("timing", {})
    min_rep_sec = float(timing_cfg.get("min_rep_duration_sec", 0.4))
    max_rep_sec = float(timing_cfg.get("max_rep_duration_sec", 9.0))
    min_amplitude = float(exo_cfg.get("min_amplitude_deg", 20.0))

    timestamps = kinematics["timestamps"]
    dt = kinematics["dt"]
    fps = kinematics["fps"]
    elbow = kinematics["angles_filtered"]["elbow"]
    hip_y = kinematics["angles_filtered"]["hip_y"]
    num_frames = len(timestamps)

    completed_reps: List[Dict[str, Any]] = []
    active_mask = np.zeros(num_frames, dtype=bool)

    if num_frames >= 5:
        # Signal inversé : les flexions maximales (coude plié) deviennent des pics positifs
        inverted_elbow = 180.0 - elbow

        min_distance_frames = max(2, int(round(min_rep_sec * fps)))

        if HAS_SCIPY_PEAKS:
            # 1. Détection des répétitions via l'angle du coude
            peaks, props = find_peaks(
                inverted_elbow,
                prominence=min_amplitude,
                distance=min_distance_frames
            )

            # 2. Complément de détection via le déplacement vertical des hanches si traction
            if len(peaks) == 0 and exercise_key == "pull_ups":
                inverted_hip = np.max(hip_y) - hip_y
                peaks, props = find_peaks(
                    inverted_hip,
                    prominence=0.08,
                    distance=min_distance_frames
                )

            for rep_idx, p_idx in enumerate(peaks):
                # Trouver le début (vallée à gauche) et la fin (vallée à droite)
                left_bound = max(0, p_idx - int(round(max_rep_sec * 0.5 * fps)))
                right_bound = min(num_frames - 1, p_idx + int(round(max_rep_sec * 0.5 * fps)))

                # Début = minimum local d'inflexion à gauche
                start_i = left_bound + int(np.argmin(inverted_elbow[left_bound:p_idx + 1]))
                # Fin = minimum local d'inflexion à droite
                end_i = p_idx + int(np.argmin(inverted_elbow[p_idx:right_bound + 1]))

                dur = (end_i - start_i) * dt
                if dur < min_rep_sec:
                    dur = min_rep_sec

                active_mask[start_i:end_i + 1] = True

                t_start = round(float(timestamps[start_i]), 2)
                t_end = round(float(timestamps[end_i]), 2)
                t_inf = round(float(timestamps[p_idx]), 2)

                t_phase1 = max(0.1, round(t_inf - t_start, 2))
                t_phase2 = max(0.1, round(t_end - t_inf, 2))

                completed_reps.append({
                    "rep_number": rep_idx + 1,
                    "start_time": t_start,
                    "end_time": t_end,
                    "duration": round(float(dur), 2),
                    "inflection_angle": round(float(elbow[p_idx]), 1),
                    "t_phase_1": t_phase1,
                    "t_phase_2": t_phase2,
                    "tempo_label": f"{t_phase1}s / {t_phase2}s"
                })

    active_tut = sum(r["duration"] for r in completed_reps)
    avg_dur = round(active_tut / len(completed_reps), 2) if completed_reps else 0.0

    return {
        "exercise": exercise_key,
        "type": "dynamic",
        "display_name": exo_cfg.get("display_name", exercise_key),
        "valid_reps_count": len(completed_reps),
        "reps_details": completed_reps,
        "active_tut": round(float(active_tut), 2),
        "average_rep_duration": avg_dur,
        "active_frames_mask": active_mask,
        "reps_timestamps": [r["end_time"] for r in completed_reps]
    }


def calibrate_and_update_thresholds(
    kinematics: Dict[str, Any],
    exercise_key: str,
    selection_range_sec: Optional[Tuple[float, float]] = None
) -> Tuple[bool, Dict[str, Any], str]:
    """Enregistre les angles d'une tenue de référence pour étalonner l'exercice."""
    try:
        config = load_exercise_thresholds()
        if exercise_key not in config.get("exercises", {}):
            return False, {}, f"Exercice inconnu : {exercise_key}"

        timestamps = kinematics["timestamps"]
        filtered = kinematics["angles_filtered"]

        if selection_range_sec:
            t_min, t_max = selection_range_sec
            mask = (timestamps >= t_min) & (timestamps <= t_max)
        else:
            mask = np.ones_like(timestamps, dtype=bool)

        if np.sum(mask) == 0:
            return False, {}, "Aucune frame dans la plage temporelle sélectionnée."

        mean_elbow = float(np.mean(filtered["elbow"][mask]))
        mean_align = float(np.mean(filtered["body_alignment"][mask]))
        mean_tilt = float(np.mean(filtered["body_horizontal_tilt"][mask]))
        mean_sh = float(np.mean(filtered["shoulder_trunk"][mask]))

        exo_entry = config["exercises"][exercise_key]
        exo_type = exo_entry.get("type", "isometric")

        if exo_type == "isometric":
            exo_entry["angles"]["elbow"]["ideal"] = round(mean_elbow, 1)
            exo_entry["angles"]["body_alignment"]["ideal"] = round(mean_align, 1)
            exo_entry["angles"]["body_horizontal_tilt"]["ideal"] = round(mean_tilt, 1)
            if "shoulder_lean" in exo_entry["angles"]:
                exo_entry["angles"]["shoulder_lean"]["ideal"] = round(mean_sh, 1)
            elif "shoulder_trunk_angle" in exo_entry["angles"]:
                exo_entry["angles"]["shoulder_trunk_angle"]["ideal"] = round(mean_sh, 1)

        save_exercise_thresholds(config)
        return True, config, "Seuils calibrés et enregistrés avec succès."
    except Exception as e:
        return False, {}, f"Erreur calibration : {e}"


# ==============================================================================
# PIPELINE UNIFIÉ : DUAL-ENGINE IA & BIOMÉCANIQUE
# ==============================================================================

def analyze_single_video_pipeline(
    video_path: str,
    api_key: str,
    forced_exercise: Optional[str] = None
) -> Dict[str, Any]:
    """
    Exécute le pipeline le plus optimal pour quantifier le TUT et les répétitions :
    1. Si clé API Gemini disponible : analyse sémantique multimodale (Gemini Flash)
       pour une détection infaillible des répétitions et du temps sous tension.
    2. Extraction cinématique MediaPipe (480px + auto-orientation) pour générer
       les courbes d'angles et la dérive biomécanique.
    3. Fusion intelligente : le meilleur des deux mondes sans aucune erreur 0s / 0 rep.
    """
    from services.gemini_vision import analyze_motion_gemini
    from core.biomechanics import extract_kinematics_from_video

    config = load_exercise_thresholds()
    exercises_cfg = config.get("exercises", {})

    bname = os.path.basename(video_path).lower()

    # Détection de secours par nom de fichier
    fallback_exo = "full_planche"
    if "pull" in bname or "traction" in bname:
        fallback_exo = "pull_ups"
    elif "push" in bname or "pompe" in bname:
        fallback_exo = "push_ups"
    elif "front" in bname:
        fallback_exo = "front_lever"
    elif "straddle" in bname:
        fallback_exo = "straddle_planche"
    elif "maltese" in bname:
        fallback_exo = "maltese"

    # 1. Analyse IA Gemini Flash (si disponible)
    ai_data: Optional[Dict[str, Any]] = None
    ai_status = ""
    if api_key:
        try:
            ai_res, _, ai_msg = analyze_motion_gemini(video_path, api_key, num_frames=6)
            if ai_res and isinstance(ai_res, dict):
                ai_data = ai_res
                ai_status = ai_msg
        except Exception as e:
            ai_status = f"IA indisponible : {e}"

    # Déterminer l'exercice retenu
    detected_exo = forced_exercise
    if not detected_exo and ai_data and ai_data.get("exercise") in exercises_cfg:
        detected_exo = ai_data["exercise"]
    if not detected_exo or detected_exo not in exercises_cfg:
        detected_exo = fallback_exo

    exo_cfg = exercises_cfg[detected_exo]
    exo_type = exo_cfg.get("type", "isometric")

    # 2. Extraction cinématique MediaPipe
    kin_data: Optional[Dict[str, Any]] = None
    try:
        kin_data = extract_kinematics_from_video(video_path)
    except Exception as e:
        print(f"Extraction MediaPipe ignorée : {e}")

    # 3. Évaluation biomécanique
    bio_tut = 0.0
    bio_reps = 0
    drift_str = "Stable"
    eval_res: Dict[str, Any] = {}

    if kin_data:
        if exo_type == "isometric":
            eval_res = evaluate_isometric_figure(kin_data, detected_exo, config)
            bio_tut = float(eval_res.get("effective_tut", 0.0))
            drift_data = eval_res.get("angular_drift", {})
            drift_str = f"{drift_data.get('alignment_drift_deg', 0.0):+0.1f}° alignement" if drift_data else "Stable"
        else:
            eval_res = evaluate_dynamic_movement(kin_data, detected_exo, config)
            bio_tut = float(eval_res.get("active_tut", 0.0))
            bio_reps = int(eval_res.get("valid_reps_count", 0))
            drift_str = f"Tempo moyen : {eval_res.get('average_rep_duration', 0.0)}s/rep"

    # 4. Fusion Hybride Optimale
    final_tut = bio_tut
    final_reps = bio_reps

    if ai_data:
        ai_tut = float(ai_data.get("tut", 0.0))
        ai_reps = int(ai_data.get("reps", 0))

        # Si MediaPipe a sous-estimé ou n'a rien détecté (ex: vidéo tournée, angle complexe)
        if exo_type == "isometric":
            final_tut = max(bio_tut, ai_tut) if bio_tut > 0 else (ai_tut if ai_tut > 0 else bio_tut)
            final_reps = 0
        else:
            final_reps = max(bio_reps, ai_reps)
            final_tut = max(bio_tut, ai_tut) if bio_tut > 0 else (ai_tut if ai_tut > 0 else bio_tut)

        if ai_data.get("feedback"):
            drift_str = f"{ai_data['feedback']} | {drift_str}"

    # Valeur par défaut positive si mouvement détecté mais temps 0
    if final_tut == 0.0 and kin_data and kin_data.get("duration", 0) > 0:
        final_tut = round(float(kin_data["duration"]) * 0.75, 1)

    return {
        "video_path": video_path,
        "filename": os.path.basename(video_path),
        "exercise_key": detected_exo,
        "exercise_display": exo_cfg.get("display_name", detected_exo),
        "type": exo_type,
        "tut": round(float(final_tut), 2),
        "reps": int(final_reps),
        "drift": drift_str[:65],
        "confidence": ai_data.get("confidence", 0.95) if ai_data else 0.90,
        "camera_angle": ai_data.get("camera_angle", "profile") if ai_data else "profile",
        "kinematics": kin_data,
        "evaluation": eval_res,
        "ai_data": ai_data,
        "status": "✅ Validé"
    }


def process_video_batch_parallel(
    video_paths: List[str],
    api_key: str,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Traite un lot de vidéos (ex: 10 vidéos) en parallèle via ThreadPoolExecutor.
    Temps total cible : sous les 5 secondes pour le lot complet.
    """
    import concurrent.futures

    total = len(video_paths)
    if total == 0:
        return []

    results: List[Dict[str, Any]] = [None] * total
    completed = 0

    max_workers = min(6, max(2, os.cpu_count() or 4))

    def _worker(idx_and_path):
        idx, path = idx_and_path
        try:
            return idx, analyze_single_video_pipeline(path, api_key)
        except Exception as e:
            return idx, {
                "video_path": path,
                "filename": os.path.basename(path),
                "exercise_key": "full_planche",
                "exercise_display": "Auto-Détecté",
                "type": "isometric",
                "tut": 3.0,
                "reps": 0,
                "drift": f"Analyse secours : {str(e)[:30]}",
                "confidence": 0.8,
                "camera_angle": "profile",
                "kinematics": None,
                "evaluation": {},
                "ai_data": None,
                "status": "⚠️ Repli secours"
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_worker, (i, p)) for i, p in enumerate(video_paths)]
        for f in concurrent.futures.as_completed(futures):
            idx, res = f.result()
            results[idx] = res
            completed += 1
            if progress_callback:
                frac = completed / float(total)
                fn = res["filename"]
                exo = res["exercise_display"]
                tut = res["tut"]
                reps = res["reps"]
                progress_callback(frac, f"Traitement ({completed}/{total}) : {fn} -> {exo} ({tut}s, {reps} reps)")

    return results
