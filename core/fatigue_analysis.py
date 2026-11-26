"""
core/fatigue_analysis.py - Analyse de la dérive technique intra-série (Chantier 4).
- Isométrique : dérive angulaire (Δθ en degrés) entre la 1re et la dernière seconde de tenue
  sur épaule-tronc, alignement de hanche et inclinaison horizontale + série seconde par seconde.
- Dynamique : perte de vitesse angulaire moyenne (%) entre la 1re et la dernière répétition
  pour estimer la proximité de l'échec musculaire.
"""

from typing import Any, Dict, List, Optional
import numpy as np

from core.load_quantification import load_quantification_config


def _classify_velocity_loss(loss_pct: float, cfg_f: Dict[str, Any]) -> str:
    low = float(cfg_f.get("velocity_loss_low_pct", 10.0))
    mod = float(cfg_f.get("velocity_loss_moderate_pct", 25.0))
    high = float(cfg_f.get("velocity_loss_high_pct", 40.0))
    if loss_pct < low:
        return "Fatigue faible (réserve importante • RIR 4+)"
    if loss_pct < mod:
        return "Fatigue modérée (zone technique productive • RIR 2-3)"
    if loss_pct < high:
        return "Proche de l'échec musculaire (RIR 1-2)"
    return "Échec musculaire / forte perte de vélocité (RIR 0)"


def analyze_intra_set_fatigue(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    evaluation: Optional[Dict[str, Any]] = None,
    exo_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calcule les indicateurs de fatigue mécanique intra-série à partir des séries 3D filtrées
    déjà extraites (zéro ré-inférence MediaPipe).
    """
    if not kinematics or not segmentation:
        return {"type": exo_type or "isometric", "available": False}

    cfg_f = load_quantification_config().get("fatigue", {})
    slice_sec = max(0.4, float(cfg_f.get("isometric_slice_sec", 1.0)))
    drift_warn_deg = float(cfg_f.get("isometric_drift_warning_deg", 8.0))

    resolved_type = exo_type or segmentation.get("type", "isometric")
    is_dyn = "dyn" in str(resolved_type).lower()

    ts = np.asarray(kinematics.get("timestamps", []), dtype=np.float64)
    filt = kinematics.get("features_filtered", {})
    dt = float(kinematics.get("dt", 0.04) or 0.04)

    effort_win = segmentation.get("effort_window", {})
    n_samples = len(ts)
    if n_samples < 3:
        return {"type": "dynamic" if is_dyn else "isometric", "available": False}

    s_idx = int(max(0, min(n_samples - 1, effort_win.get("start_idx", 0))))
    e_idx = int(max(s_idx, min(n_samples - 1, effort_win.get("end_idx", n_samples - 1))))

    if not is_dyn:
        t_act = ts[s_idx:e_idx + 1] - ts[s_idx]
        sh = np.asarray(filt.get("shoulder_flexion", np.zeros(n_samples)), dtype=np.float64)[s_idx:e_idx + 1]
        hip = np.asarray(filt.get("hip_angle", np.zeros(n_samples)), dtype=np.float64)[s_idx:e_idx + 1]
        trunk = np.asarray(filt.get("trunk_inclination", np.zeros(n_samples)), dtype=np.float64)[s_idx:e_idx + 1]

        total_dur = float(t_act[-1]) if len(t_act) > 0 else 0.0
        n_act = len(t_act)

        if total_dur >= slice_sec * 1.8 and n_act >= 6:
            first_mask = t_act <= slice_sec
            last_mask = t_act >= max(0.0, total_dur - slice_sec)
        else:
            half = max(1, n_act // 2)
            first_mask = np.zeros(n_act, dtype=bool)
            first_mask[:half] = True
            last_mask = np.zeros(n_act, dtype=bool)
            last_mask[-half:] = True

        sh_delta = round(float(np.mean(sh[last_mask]) - np.mean(sh[first_mask])), 2)
        hip_delta = round(float(np.mean(hip[last_mask]) - np.mean(hip[first_mask])), 2)
        trunk_delta = round(float(np.mean(trunk[last_mask]) - np.mean(trunk[first_mask])), 2)

        # Dérive maximale absolue entre les articulations clés
        max_abs_drift = round(max(abs(sh_delta), abs(hip_delta), abs(trunk_delta)), 2)

        # Agrégation seconde par seconde pour la courbe Plotly
        n_buckets = max(1, int(np.ceil(max(total_dur, slice_sec) / slice_sec)))
        per_sec_rows: List[Dict[str, Any]] = []
        for b in range(n_buckets):
            b_start = b * slice_sec
            b_end = (b + 1) * slice_sec
            if b == n_buckets - 1:
                b_mask = (t_act >= b_start) & (t_act <= b_end + 1e-6)
            else:
                b_mask = (t_act >= b_start) & (t_act < b_end)
            if not np.any(b_mask):
                continue
            per_sec_rows.append({
                "second": int(b + 1),
                "label": f"{int(b)}–{int(b + 1)}s",
                "shoulder_flexion": round(float(np.mean(sh[b_mask])), 1),
                "hip_angle": round(float(np.mean(hip[b_mask])), 1),
                "trunk_inclination": round(float(np.mean(trunk[b_mask])), 1),
            })

        return {
            "type": "isometric",
            "available": True,
            "fatigue_drift_deg": max_abs_drift,
            "velocity_loss_pct": None,
            "shoulder_drift_deg": sh_delta,
            "hip_drift_deg": hip_delta,
            "trunk_drift_deg": trunk_delta,
            "warning": max_abs_drift > drift_warn_deg,
            "per_second_series": per_sec_rows,
            "summary": (
                f"Dérive Δθ : Épaule {sh_delta:+.1f}° • Hanche {hip_delta:+.1f}° • Tronc {trunk_delta:+.1f}°"
            ),
        }

    # Mode dynamique : perte de vitesse angulaire (%) entre 1re et dernière répétition
    elbow = np.asarray(filt.get("elbow_angle", np.zeros(n_samples)), dtype=np.float64)
    sh = np.asarray(filt.get("shoulder_flexion", np.zeros(n_samples)), dtype=np.float64)
    primary_sig = elbow if np.ptp(elbow[s_idx:e_idx + 1]) >= 15.0 else sh
    ang_vel = np.abs(np.gradient(primary_sig, dt)) if len(primary_sig) > 1 else np.zeros_like(primary_sig)

    reps_detail = (evaluation or {}).get("reps_details", [])
    rep_velocities: List[Dict[str, Any]] = []

    if reps_detail and len(reps_detail) >= 2:
        for rep in reps_detail:
            rt0 = float(rep.get("start_time", 0.0))
            rt1 = float(rep.get("end_time", 0.0))
            mask = (ts >= rt0) & (ts <= rt1)
            if not np.any(mask):
                continue
            mean_v = float(np.mean(ang_vel[mask]))
            peak_v = float(np.max(ang_vel[mask]))
            rep_velocities.append({
                "rep_number": int(rep.get("rep_number", len(rep_velocities) + 1)),
                "mean_angular_vel_dps": round(mean_v, 1),
                "peak_angular_vel_dps": round(peak_v, 1),
                "duration_sec": round(float(rep.get("duration", rt1 - rt0)), 2),
            })
    elif (e_idx - s_idx + 1) >= 8:
        # Découpage de secours par moitiés / tranches si l'évaluation est non calibrée
        act_vel = ang_vel[s_idx:e_idx + 1]
        n_chunks = min(4, max(2, len(act_vel) // 10))
        chunks = np.array_split(act_vel, n_chunks)
        for idx_c, ch in enumerate(chunks):
            rep_velocities.append({
                "rep_number": idx_c + 1,
                "mean_angular_vel_dps": round(float(np.mean(ch)), 1),
                "peak_angular_vel_dps": round(float(np.max(ch)), 1),
                "duration_sec": round(float(len(ch) * dt), 2),
            })

    if len(rep_velocities) >= 2:
        v_first = float(rep_velocities[0]["mean_angular_vel_dps"])
        v_last = float(rep_velocities[-1]["mean_angular_vel_dps"])
        if v_first > 1e-6:
            loss_pct = round(max(0.0, ((v_first - v_last) / v_first) * 100.0), 1)
        else:
            loss_pct = 0.0
    elif len(rep_velocities) == 1:
        loss_pct = 0.0
    else:
        loss_pct = 0.0

    label_status = _classify_velocity_loss(loss_pct, cfg_f)
    return {
        "type": "dynamic",
        "available": len(rep_velocities) > 0,
        "fatigue_drift_deg": None,
        "velocity_loss_pct": loss_pct,
        "rep_velocities": rep_velocities,
        "failure_proximity_label": label_status,
        "summary": f"Perte de vitesse intra-série : {loss_pct:.1f}% • {label_status}",
    }
