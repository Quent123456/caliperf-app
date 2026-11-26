"""
core/quality_control.py - Moteur déterministe de contrôle qualité vidéo (Quality Control Gate)
Exécuté systématiquement avant tout enregistrement dans la bibliothèque Baselines_3D.

Évalue 5 critères objectifs sans relancer d'inférence MediaPipe :
1. Cadrage & occupation spatiale (pose_landmarks 2D sur la fenêtre active)
2. Confiance de détection anatomique (visibility sur chaîne cinétique principale)
3. Intégrité temporelle & cadence (FPS réel, stabilité VFR, durée active / répétitions)
4. Pureté d'exécution & stabilité cinématique (pose_world_landmarks 3D filtrés & bruit)
5. Cohérence de l'angle de vue déclaré (Face / 3/4 / Profil vs ratio projeté 2D des épaules)
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

try:
    from scipy.signal import find_peaks
    HAS_SCIPY_PEAKS = True
except ImportError:
    HAS_SCIPY_PEAKS = False


# ==============================================================================
# CONFIGURATION CENTRALISÉE DES SEUILS (AUCUN SEUIL DISPERSÉ EN DUR)
# ==============================================================================

QC_CONFIG: Dict[str, Any] = {
    "landmarks": {
        "names_fr": {
            0: "tête",
            11: "épaule gauche",
            12: "épaule droite",
            13: "coude gauche",
            14: "coude droit",
            15: "poignet gauche",
            16: "poignet droit",
            23: "hanche gauche",
            24: "hanche droite",
            25: "genou gauche",
            26: "genou droit",
            27: "cheville gauche",
            28: "cheville droite",
            31: "pointe de pied gauche",
            32: "pointe de pied droit",
        },
        # Indices MediaPipe PoseLandmark (33 points)
        "NOSE": 0,
        "LEFT_SHOULDER": 11,
        "RIGHT_SHOULDER": 12,
        "LEFT_ELBOW": 13,
        "RIGHT_ELBOW": 14,
        "LEFT_WRIST": 15,
        "RIGHT_WRIST": 16,
        "LEFT_HIP": 23,
        "RIGHT_HIP": 24,
        "LEFT_KNEE": 25,
        "RIGHT_KNEE": 26,
        "LEFT_ANKLE": 27,
        "RIGHT_ANKLE": 28,
        "LEFT_FOOT_INDEX": 31,
        "RIGHT_FOOT_INDEX": 32,
    },
    "framing": {
        # Repères extrêmes : épaules, coudes, poignets, hanches, genoux, chevilles, pointes de pieds
        "extreme_indices": [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 31, 32],
        # Repères utilisés pour la boîte englobante du corps
        "bbox_indices": [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 31, 32],
        "margin_min": 0.03,
        "margin_max": 0.97,
        "min_in_frame_ratio": 0.95,
        "bbox_span_min": 0.45,
        "bbox_span_max": 0.85,
        "landmark_eval_vis_min": 0.25,
    },
    "visibility": {
        # Chaîne cinétique principale : épaules, coudes, poignets, hanches, genoux, chevilles
        "kinetic_chain_indices": [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28],
        "min_mean_visibility": 0.80,
        "critical_joint_min_vis": 0.60,
        "max_low_vis_frame_fraction": 0.15,
    },
    "temporal": {
        "min_fps_reject": 24.0,
        "min_fps_warning": 28.0,
        "vfr_min_samples": 10,
        "vfr_cv_warning": 0.20,
        "vfr_max_jump_ratio": 2.2,
        "min_isometric_duration_sec": 1.5,
        "min_dynamic_reps": 2,
        "dynamic_prominence_deg": 18.0,
        "dynamic_min_rep_sec": 0.4,
    },
    "kinematic_purity": {
        "isometric_angle_keys": ["shoulder_flexion", "elbow_angle", "hip_angle"],
        "isometric_std_warning_deg": 6.0,
        "isometric_std_reject_deg": 10.0,
        "isometric_pelvis_slice_sec": 0.4,
        "isometric_pelvis_drop_warning_m": 0.06,
        "dynamic_rom_cv_warning": 0.25,
        "dynamic_rom_spread_warning_deg": 25.0,
        "dynamic_noise_angle_keys": ["elbow_angle", "shoulder_flexion", "hip_angle"],
        "dynamic_noise_rms_warning_deg": 6.0,
    },
    "camera_view": {
        "profil_max_shoulder_ratio": 0.42,
        "face_min_shoulder_ratio": 0.38,
        "three_quarter_min_shoulder_ratio": 0.18,
        "arm_scale_weight": 0.85,
        "min_ref_scale": 0.05,
        "min_pair_vis": 0.35,
    },
    "scoring": {
        "penalty_warning": 12,
        "penalty_reject": 35,
        "max_score_on_reject": 49,
    },
}


# ==============================================================================
# MODÈLES DE DONNÉES STRUCTURÉS
# ==============================================================================

@dataclass
class QualityCheckItem:
    """Résultat détaillé d'un des 5 critères de contrôle qualité."""
    id: str
    title: str
    status: str  # "PASS" | "WARNING" | "REJECT"
    score: int
    message: str
    recommendation: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualityReport:
    """Rapport consolidé produit par le Quality Control Gate."""
    status: str  # "PASS" | "WARNING" | "REJECT"
    global_score: int
    checks: List[QualityCheckItem]
    summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "global_score": int(self.global_score),
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
            "metadata": dict(self.metadata),
        }


# ==============================================================================
# HELPERS GÉOMÉTRIQUES & TEMPORELS INTERNES
# ==============================================================================

def _get_active_bounds(kinematics: Dict[str, Any], segmentation: Dict[str, Any]) -> Tuple[int, int]:
    """Extrait les bornes [start_idx, end_idx] sécurisées sur la fenêtre active."""
    n_samples = len(kinematics.get("timestamps", []))
    if n_samples <= 0:
        return 0, -1
    effort_win = segmentation.get("effort_window", {}) if segmentation else {}
    s_idx = int(max(0, min(n_samples - 1, effort_win.get("start_idx", 0))))
    e_idx = int(max(s_idx, min(n_samples - 1, effort_win.get("end_idx", n_samples - 1))))
    return s_idx, e_idx


def _extract_landmarks_2d_slice(
    kinematics: Dict[str, Any],
    s_idx: int,
    e_idx: int
) -> Optional[np.ndarray]:
    """Récupère la tranche (N_act, 33, 3) des pose_landmarks 2D normalisés."""
    lm_arr = kinematics.get("landmarks_2d_xyv")
    if lm_arr is None or not isinstance(lm_arr, np.ndarray) or lm_arr.ndim != 3:
        return None
    if e_idx < s_idx or s_idx >= lm_arr.shape[0]:
        return None
    return lm_arr[s_idx:min(e_idx + 1, lm_arr.shape[0])]


def _detect_dynamic_reps_amplitudes(
    kinematics: Dict[str, Any],
    s_idx: int,
    e_idx: int,
    cfg_t: Dict[str, Any]
) -> Tuple[int, List[float]]:
    """
    Détecte les répétitions complètes sur la fenêtre active sans repli artificiel,
    et retourne (nombre_de_reps, amplitudes_ROM_par_rep).
    """
    filt = kinematics.get("features_filtered", {})
    elbow = filt.get("elbow_angle", np.array([]))
    sh_flex = filt.get("shoulder_flexion", np.array([]))
    fps = float(kinematics.get("fps", 25.0) or 25.0)

    if len(elbow) <= e_idx or (e_idx - s_idx + 1) < 5:
        return 0, []

    active_elbow = np.asarray(elbow[s_idx:e_idx + 1], dtype=np.float64)
    active_sh = np.asarray(sh_flex[s_idx:e_idx + 1], dtype=np.float64) if len(sh_flex) > e_idx else active_elbow

    prominence = float(cfg_t["dynamic_prominence_deg"])
    min_dist = max(2, int(round(float(cfg_t["dynamic_min_rep_sec"]) * fps)))

    # Choisir l'articulation ayant la plus grande oscillation active
    use_elbow = np.ptp(active_elbow) >= prominence * 0.9
    if use_elbow:
        signal_inv = np.max(active_elbow) - active_elbow
        signal_raw = active_elbow
    else:
        signal_inv = np.max(active_sh) - active_sh
        signal_raw = active_sh
        prominence *= 0.85

    peaks: np.ndarray
    if HAS_SCIPY_PEAKS:
        peaks, props = find_peaks(signal_inv, prominence=prominence, distance=min_dist)
        amplitudes = list(props.get("prominences", []))
        return int(len(peaks)), [float(a) for a in amplitudes]

    # Repli déterministe sans scipy
    local_peaks: List[int] = []
    for i in range(1, len(signal_inv) - 1):
        if signal_inv[i] > signal_inv[i - 1] and signal_inv[i] >= signal_inv[i + 1]:
            if not local_peaks or (i - local_peaks[-1]) >= min_dist:
                local_peaks.append(i)
    amps: List[float] = []
    half_win = max(3, min_dist)
    for p in local_peaks:
        l_val = float(np.max(signal_raw[max(0, p - half_win):p + 1]))
        r_val = float(np.max(signal_raw[p:min(len(signal_raw), p + half_win + 1)]))
        rom_p = min(l_val, r_val) - float(signal_raw[p])
        if rom_p >= prominence:
            amps.append(float(rom_p))
    return len(amps), amps


def _localize_cut_edge(xs: np.ndarray, ys: np.ndarray, indices: List[int], cfg_f: Dict[str, Any], names_fr: Dict[int, str]) -> str:
    """Identifie le bord de l'image où une extrémité est coupée pour formuler un conseil précis."""
    m_min = float(cfg_f["margin_min"])
    m_max = float(cfg_f["margin_max"])
    counts = {"bottom": 0, "top": 0, "left": 0, "right": 0}
    culprit_parts: List[str] = []

    for j, idx in enumerate(indices):
        xj = xs[:, j]
        yj = ys[:, j]
        valid_j = np.isfinite(xj) & np.isfinite(yj)
        if not np.any(valid_j):
            continue
        b_cnt = int(np.sum(yj[valid_j] > m_max))
        t_cnt = int(np.sum(yj[valid_j] < m_min))
        l_cnt = int(np.sum(xj[valid_j] < m_min))
        r_cnt = int(np.sum(xj[valid_j] > m_max))
        counts["bottom"] += b_cnt
        counts["top"] += t_cnt
        counts["left"] += l_cnt
        counts["right"] += r_cnt
        if (b_cnt + t_cnt + l_cnt + r_cnt) > 0:
            part_name = names_fr.get(idx, f"repère #{idx}")
            if part_name not in culprit_parts and len(culprit_parts) < 2:
                culprit_parts.append(part_name)

    dominant_edge = max(counts, key=lambda k: counts[k])
    parts_txt = " / ".join(culprit_parts) if culprit_parts else "extrémités"

    if counts[dominant_edge] == 0:
        return "Reculez d'environ 1 mètre afin de garder l'ensemble du corps dans le cadre."
    if dominant_edge == "bottom":
        return f"Reculez de 0,5 à 1 mètre ou relevez légèrement l'angle : {parts_txt} coupé(s) en bas du cadre."
    if dominant_edge == "top":
        return f"Reculez de 0,5 à 1 mètre ou recadrez plus haut : {parts_txt} coupé(s) en haut du cadre."
    if dominant_edge == "left":
        return f"Reculez d'environ 1 mètre ou recentrez vers la gauche : {parts_txt} coupé(s) sur le bord gauche."
    return f"Reculez d'environ 1 mètre ou recentrez vers la droite : {parts_txt} coupé(s) sur le bord droit."


# ==============================================================================
# LES 5 CONTRÔLES OBJECTIFS INDIVIDUELS
# ==============================================================================

def _check_framing(
    lm_active: Optional[np.ndarray],
    cfg: Dict[str, Any]
) -> QualityCheckItem:
    """Critère 1 : Cadrage (marge de sécurité 0.03-0.97 >= 95%) et occupation spatiale (45%-85%)."""
    cfg_f = cfg["framing"]
    names_fr = cfg["landmarks"]["names_fr"]

    if lm_active is None or len(lm_active) == 0:
        return QualityCheckItem(
            id="framing",
            title="Cadrage & occupation spatiale",
            status="REJECT",
            score=0,
            message="Aucun squelette 2D exploitable détecté sur la fenêtre d'effort.",
            recommendation="Filmez l'athlète de la tête aux pieds sur un fond contrasté avec zoom 1.0x.",
            metrics={"in_frame_ratio": 0.0, "bbox_span_median": 0.0},
        )

    ext_idx = cfg_f["extreme_indices"]
    bbox_idx = cfg_f["bbox_indices"]
    m_min = float(cfg_f["margin_min"])
    m_max = float(cfg_f["margin_max"])
    ratio_min = float(cfg_f["min_in_frame_ratio"])

    xs = lm_active[:, ext_idx, 0]
    ys = lm_active[:, ext_idx, 1]
    vis_ext = lm_active[:, ext_idx, 2]

    # Une frame valide de pose possède des coordonnées finies sur les repères extrêmes
    finite_mask = np.all(np.isfinite(xs), axis=1) & np.all(np.isfinite(ys), axis=1)
    in_bounds_per_lm = (xs >= m_min) & (xs <= m_max) & (ys >= m_min) & (ys <= m_max)
    # Sur les frames détectées, toutes les extrémités doivent rester dans la marge
    frame_ok = finite_mask & np.all(in_bounds_per_lm, axis=1)
    in_frame_ratio = float(np.mean(frame_ok))

    # Calcul de la boîte englobante du corps sur la fenêtre active
    bx = lm_active[:, bbox_idx, 0]
    by = lm_active[:, bbox_idx, 1]
    bvis = lm_active[:, bbox_idx, 2]
    vis_min = float(cfg_f["landmark_eval_vis_min"])

    spans: List[float] = []
    for i in range(len(lm_active)):
        valid_pts = np.isfinite(bx[i]) & np.isfinite(by[i]) & (bvis[i] >= vis_min)
        if np.sum(valid_pts) < 4:
            valid_pts = np.isfinite(bx[i]) & np.isfinite(by[i])
        if np.sum(valid_pts) >= 2:
            w_span = float(np.max(bx[i, valid_pts]) - np.min(bx[i, valid_pts]))
            h_span = float(np.max(by[i, valid_pts]) - np.min(by[i, valid_pts]))
            spans.append(max(w_span, h_span))

    bbox_span_med = float(np.median(spans)) if spans else 0.0
    span_low = float(cfg_f["bbox_span_min"])
    span_high = float(cfg_f["bbox_span_max"])

    if in_frame_ratio < ratio_min:
        rec = _localize_cut_edge(xs, ys, ext_idx, cfg_f, names_fr)
        return QualityCheckItem(
            id="framing",
            title="Cadrage & occupation spatiale",
            status="REJECT",
            score=25,
            message=(
                f"Extrémités hors marge de sécurité ({in_frame_ratio * 100:.0f} % des frames cadrées "
                f"< {ratio_min * 100:.0f} % requis)."
            ),
            recommendation=rec,
            metrics={
                "in_frame_ratio": round(in_frame_ratio, 3),
                "bbox_span_median": round(bbox_span_med, 3),
            },
        )

    if bbox_span_med < span_low:
        return QualityCheckItem(
            id="framing",
            title="Cadrage & occupation spatiale",
            status="WARNING",
            score=76,
            message=(
                f"Sujet trop éloigné ({bbox_span_med * 100:.0f} % du cadre < {span_low * 100:.0f} % recommandé)."
            ),
            recommendation="Rapprochez la caméra de 0,5 à 1 mètre (3 à 4 grands pas au total) pour améliorer la netteté articulaire.",
            metrics={
                "in_frame_ratio": round(in_frame_ratio, 3),
                "bbox_span_median": round(bbox_span_med, 3),
            },
        )

    if bbox_span_med > span_high:
        return QualityCheckItem(
            id="framing",
            title="Cadrage & occupation spatiale",
            status="WARNING",
            score=78,
            message=(
                f"Sujet très proche des bords ({bbox_span_med * 100:.0f} % du cadre > {span_high * 100:.0f} %)."
            ),
            recommendation="Reculez d'environ 0,5 à 1 mètre pour éviter la distorsion perspective et le risque de coupure.",
            metrics={
                "in_frame_ratio": round(in_frame_ratio, 3),
                "bbox_span_median": round(bbox_span_med, 3),
            },
        )

    return QualityCheckItem(
        id="framing",
        title="Cadrage & occupation spatiale",
        status="PASS",
        score=100,
        message=(
            f"Cadrage conforme : {in_frame_ratio * 100:.0f} % dans les marges, "
            f"occupation du corps à {bbox_span_med * 100:.0f} %."
        ),
        recommendation="",
        metrics={
            "in_frame_ratio": round(in_frame_ratio, 3),
            "bbox_span_median": round(bbox_span_med, 3),
        },
    )


def _check_visibility(
    lm_active: Optional[np.ndarray],
    cfg: Dict[str, Any]
) -> QualityCheckItem:
    """Critère 2 : Confiance anatomique moyenne (>= 0.80) et drops par articulation (< 0.60 sur > 15%)."""
    cfg_v = cfg["visibility"]
    names_fr = cfg["landmarks"]["names_fr"]
    chain_idx = cfg_v["kinetic_chain_indices"]

    if lm_active is None or len(lm_active) == 0:
        return QualityCheckItem(
            id="visibility",
            title="Confiance de détection anatomique",
            status="REJECT",
            score=0,
            message="Visibilité anatomique indisponible sur la fenêtre active.",
            recommendation="Vérifiez l'éclairage frontal/latéral et évitez tout contre-jour ou reflet de miroir.",
            metrics={"mean_visibility": 0.0, "worst_joint_low_fraction": 1.0},
        )

    vis_mat = np.nan_to_num(lm_active[:, chain_idx, 2], nan=0.0)
    mean_vis = float(np.mean(vis_mat))
    min_mean = float(cfg_v["min_mean_visibility"])
    crit_thresh = float(cfg_v["critical_joint_min_vis"])
    max_low_frac = float(cfg_v["max_low_vis_frame_fraction"])

    low_fractions = np.mean(vis_mat < crit_thresh, axis=0)
    worst_pos = int(np.argmax(low_fractions))
    worst_idx = chain_idx[worst_pos]
    worst_frac = float(low_fractions[worst_pos])
    worst_name = names_fr.get(worst_idx, f"articulation #{worst_idx}")

    low_joint_details = [
        f"{names_fr.get(chain_idx[j], chain_idx[j])} ({low_fractions[j] * 100:.0f} %)"
        for j in range(len(chain_idx))
        if low_fractions[j] > max_low_frac
    ]

    if mean_vis < min_mean or low_joint_details:
        reasons = []
        if mean_vis < min_mean:
            reasons.append(f"visibilité moyenne {mean_vis * 100:.0f} % < {min_mean * 100:.0f} %")
        if low_joint_details:
            reasons.append(
                f"perte de confiance (< {crit_thresh:.2f}) sur {', '.join(low_joint_details[:3])}"
            )
        return QualityCheckItem(
            id="visibility",
            title="Confiance de détection anatomique",
            status="REJECT",
            score=30,
            message="Détection anatomique insuffisante : " + " ; ".join(reasons) + ".",
            recommendation=(
                "Évitez les contre-jours, reflets dans un miroir et occlusions ; "
                "portez des vêtements ajustés contrastant avec le fond."
            ),
            metrics={
                "mean_visibility": round(mean_vis, 3),
                "worst_joint": worst_name,
                "worst_joint_low_fraction": round(worst_frac, 3),
            },
        )

    return QualityCheckItem(
        id="visibility",
        title="Confiance de détection anatomique",
        status="PASS",
        score=100,
        message=(
            f"Chaîne cinétique nette : visibilité moyenne à {mean_vis * 100:.0f} % "
            f"(pire perte locale : {worst_frac * 100:.0f} %)."
        ),
        recommendation="",
        metrics={
            "mean_visibility": round(mean_vis, 3),
            "worst_joint": worst_name,
            "worst_joint_low_fraction": round(worst_frac, 3),
        },
    )


def _check_temporal_integrity(
    kinematics: Dict[str, Any],
    s_idx: int,
    e_idx: int,
    exo_type: str,
    cfg: Dict[str, Any]
) -> QualityCheckItem:
    """Critère 3 : Cadence FPS (>= 24, avertissement < 28 ou VFR) et durée >= 1.5s ou >= 2 reps."""
    cfg_t = cfg["temporal"]

    raw_fps = float(kinematics.get("raw_fps") or kinematics.get("fps", 30.0) or 0.0)
    fps_valid_meta = bool(kinematics.get("fps_metadata_valid", raw_fps > 0.0))
    ts = np.asarray(kinematics.get("timestamps", []), dtype=np.float64)
    active_dur = float(ts[e_idx] - ts[s_idx]) if (len(ts) > e_idx >= s_idx and s_idx >= 0) else 0.0

    # Stabilité VFR à partir des timestamps OpenCV bruts s'ils sont renseignés
    fps_unstable = False
    vfr_cv = 0.0
    raw_ms = kinematics.get("raw_frame_timestamps_ms")
    if raw_ms is not None and len(raw_ms) >= int(cfg_t["vfr_min_samples"]):
        arr_ms = np.asarray(raw_ms, dtype=np.float64)
        deltas = np.diff(arr_ms)
        pos_deltas = deltas[deltas > 0.0]
        if len(pos_deltas) >= int(cfg_t["vfr_min_samples"]) - 2:
            med_dt = float(np.median(pos_deltas))
            mean_dt = float(np.mean(pos_deltas))
            if med_dt > 0.0 and mean_dt > 0.0:
                vfr_cv = float(np.std(pos_deltas) / mean_dt)
                max_ratio = float(np.max(pos_deltas) / med_dt)
                if vfr_cv > float(cfg_t["vfr_cv_warning"]) or max_ratio > float(cfg_t["vfr_max_jump_ratio"]):
                    fps_unstable = True

    is_dyn = (exo_type == "dynamic")
    reps_count = 0
    rep_amps: List[float] = []
    if is_dyn:
        reps_count, rep_amps = _detect_dynamic_reps_amplitudes(kinematics, s_idx, e_idx, cfg_t)

    # Validation bloquante 1 : FPS < 24
    if not fps_valid_meta or raw_fps < float(cfg_t["min_fps_reject"]):
        return QualityCheckItem(
            id="temporal",
            title="Intégrité temporelle & cadence",
            status="REJECT",
            score=35,
            message=f"Fréquence d'images trop faible ({raw_fps:.1f} FPS < {cfg_t['min_fps_reject']:.0f} FPS minimum).",
            recommendation="Passez votre caméra en 30 FPS ou 60 FPS constants avant de refilmer.",
            metrics={
                "raw_fps": round(raw_fps, 1),
                "fps_unstable": fps_unstable,
                "active_duration_sec": round(active_dur, 2),
                "reps_detected": reps_count,
                "rep_amplitudes": rep_amps,
            },
        )

    # Validation bloquante 2 : Durée iso < 1.5s ou < 2 reps dynamiques
    min_iso_dur = float(cfg_t["min_isometric_duration_sec"])
    min_reps = int(cfg_t["min_dynamic_reps"])
    if not is_dyn and active_dur < min_iso_dur:
        return QualityCheckItem(
            id="temporal",
            title="Intégrité temporelle & cadence",
            status="REJECT",
            score=30,
            message=(
                f"Fenêtre d'effort isométrique trop courte ({active_dur:.2f}s < {min_iso_dur:.1f}s requis)."
            ),
            recommendation="Maintenez la figure au moins 3 à 5 secondes strictes pour obtenir une référence fiable.",
            metrics={
                "raw_fps": round(raw_fps, 1),
                "fps_unstable": fps_unstable,
                "active_duration_sec": round(active_dur, 2),
                "reps_detected": reps_count,
                "rep_amplitudes": rep_amps,
            },
        )

    if is_dyn and reps_count < min_reps:
        return QualityCheckItem(
            id="temporal",
            title="Intégrité temporelle & cadence",
            status="REJECT",
            score=30,
            message=(
                f"Répétitions complètes insuffisantes ({reps_count} détectée(s) < {min_reps} requises)."
            ),
            recommendation="Réalisez 2 à 3 répétitions propres à amplitude complète sur la vidéo de calibrage.",
            metrics={
                "raw_fps": round(raw_fps, 1),
                "fps_unstable": fps_unstable,
                "active_duration_sec": round(active_dur, 2),
                "reps_detected": reps_count,
                "rep_amplitudes": rep_amps,
            },
        )

    # Avertissement cadence (< 28 FPS ou FPS Auto instable)
    if raw_fps < float(cfg_t["min_fps_warning"]) or fps_unstable:
        warn_parts = []
        if raw_fps < float(cfg_t["min_fps_warning"]):
            warn_parts.append(f"cadence à {raw_fps:.1f} FPS (< {cfg_t['min_fps_warning']:.0f} FPS)")
        if fps_unstable:
            warn_parts.append(f"cadence variable détectée (CV={vfr_cv * 100:.0f} %)")
        return QualityCheckItem(
            id="temporal",
            title="Intégrité temporelle & cadence",
            status="WARNING",
            score=80,
            message="Cadence sous-optimale : " + " et ".join(warn_parts) + ".",
            recommendation="Désactivez le mode « FPS Auto » dans les réglages caméra et verrouillez à 30 ou 60 FPS.",
            metrics={
                "raw_fps": round(raw_fps, 1),
                "fps_unstable": fps_unstable,
                "vfr_cv": round(vfr_cv, 3),
                "active_duration_sec": round(active_dur, 2),
                "reps_detected": reps_count,
                "rep_amplitudes": rep_amps,
            },
        )

    summary_val = (
        f"{reps_count} répétition(s) détectée(s) en {active_dur:.1f}s"
        if is_dyn else f"tenue active de {active_dur:.1f}s"
    )
    return QualityCheckItem(
        id="temporal",
        title="Intégrité temporelle & cadence",
        status="PASS",
        score=100,
        message=f"{raw_fps:.0f} FPS constants • {summary_val}.",
        recommendation="",
        metrics={
            "raw_fps": round(raw_fps, 1),
            "fps_unstable": fps_unstable,
            "vfr_cv": round(vfr_cv, 3),
            "active_duration_sec": round(active_dur, 2),
            "reps_detected": reps_count,
            "rep_amplitudes": rep_amps,
        },
    )


def _check_kinematic_purity(
    kinematics: Dict[str, Any],
    s_idx: int,
    e_idx: int,
    exo_type: str,
    reps_amps: List[float],
    cfg: Dict[str, Any]
) -> QualityCheckItem:
    """Critère 4 : Stabilité isométrique (écart-type + dérive bassin) ou régularité/bruit dynamique."""
    cfg_k = cfg["kinematic_purity"]
    raw = kinematics.get("features_raw", {})
    filt = kinematics.get("features_filtered", {})
    fps = float(kinematics.get("fps", 25.0) or 25.0)

    if e_idx < s_idx:
        return QualityCheckItem(
            id="kinematic_purity",
            title="Pureté d'exécution & stabilité 3D",
            status="REJECT",
            score=0,
            message="Fenêtre cinématique 3D vide.",
            recommendation="Refilmez la figure sur une séquence continue d'au moins 3 secondes.",
            metrics={},
        )

    if exo_type != "dynamic":
        stds: Dict[str, float] = {}
        for key in cfg_k["isometric_angle_keys"]:
            series = np.asarray(filt.get(key, []), dtype=np.float64)
            if len(series) > e_idx:
                stds[key] = float(np.std(series[s_idx:e_idx + 1]))

        max_std = max(stds.values(), default=0.0)
        worst_angle = max(stds, key=lambda k: stds[k]) if stds else "elbow_angle"

        # Dérive verticale du bassin (pose_world_landmarks +Y = gravité vers le bas)
        pelvis_drop_m = 0.0
        hip_y_raw = np.asarray(raw.get("hip_y", []), dtype=np.float64)
        if len(hip_y_raw) > e_idx and (e_idx - s_idx + 1) >= 4:
            hip_seg = hip_y_raw[s_idx:e_idx + 1]
            slice_n = max(1, min(len(hip_seg) // 3, int(round(float(cfg_k["isometric_pelvis_slice_sec"]) * fps))))
            start_y = float(np.mean(hip_seg[:slice_n]))
            end_y = float(np.mean(hip_seg[-slice_n:]))
            # Chute = progression vers +Y (vers le sol)
            pelvis_drop_m = float(end_y - start_y)

        std_rej = float(cfg_k["isometric_std_reject_deg"])
        std_warn = float(cfg_k["isometric_std_warning_deg"])
        drop_warn = float(cfg_k["isometric_pelvis_drop_warning_m"])

        if max_std > std_rej:
            return QualityCheckItem(
                id="kinematic_purity",
                title="Pureté d'exécution & stabilité 3D",
                status="REJECT",
                score=25,
                message=(
                    f"Instabilité angulaire excessive : σ max = {max_std:.1f}° ({worst_angle}) > {std_rej:.0f}°."
                ),
                recommendation=(
                    "Coupez les phases de montée/descente et filmez uniquement une tenue verrouillée et stable."
                ),
                metrics={
                    "max_angle_std_deg": round(max_std, 2),
                    "stds_deg": {k: round(v, 2) for k, v in stds.items()},
                    "pelvis_drop_m": round(pelvis_drop_m, 3),
                },
            )

        warn_reasons = []
        if max_std > std_warn:
            warn_reasons.append(f"dérive angulaire modérée (σ = {max_std:.1f}° > {std_warn:.0f}°)")
        if pelvis_drop_m > drop_warn:
            warn_reasons.append(f"affaissement progressif du bassin (+{pelvis_drop_m * 100:.1f} cm)")

        if warn_reasons:
            return QualityCheckItem(
                id="kinematic_purity",
                title="Pureté d'exécution & stabilité 3D",
                status="WARNING",
                score=78,
                message="Tenue partiellement instable : " + " et ".join(warn_reasons) + ".",
                recommendation=(
                    "Vérifiez que la vidéo commence une fois la position verrouillée et se termine avant le relâchement."
                ),
                metrics={
                    "max_angle_std_deg": round(max_std, 2),
                    "stds_deg": {k: round(v, 2) for k, v in stds.items()},
                    "pelvis_drop_m": round(pelvis_drop_m, 3),
                },
            )

        return QualityCheckItem(
            id="kinematic_purity",
            title="Pureté d'exécution & stabilité 3D",
            status="PASS",
            score=100,
            message=(
                f"Tenue verrouillée propre : σ max = {max_std:.1f}° • dérive bassin = {pelvis_drop_m * 100:+.1f} cm."
            ),
            recommendation="",
            metrics={
                "max_angle_std_deg": round(max_std, 2),
                "stds_deg": {k: round(v, 2) for k, v in stds.items()},
                "pelvis_drop_m": round(pelvis_drop_m, 3),
            },
        )

    # Cas dynamique : régularité ROM + bruit résiduel (raw vs filtered)
    residuals: Dict[str, float] = {}
    for key in cfg_k["dynamic_noise_angle_keys"]:
        r_ser = np.asarray(raw.get(key, []), dtype=np.float64)
        f_ser = np.asarray(filt.get(key, []), dtype=np.float64)
        if len(r_ser) > e_idx and len(f_ser) > e_idx:
            diff = r_ser[s_idx:e_idx + 1] - f_ser[s_idx:e_idx + 1]
            residuals[key] = float(np.sqrt(np.mean(diff ** 2)))

    max_noise_rms = max(residuals.values(), default=0.0)
    noise_thresh = float(cfg_k["dynamic_noise_rms_warning_deg"])

    rom_cv = 0.0
    rom_spread = 0.0
    if len(reps_amps) >= 2:
        arr_amp = np.asarray(reps_amps, dtype=np.float64)
        mean_amp = float(np.mean(arr_amp))
        rom_spread = float(np.ptp(arr_amp))
        if mean_amp > 1e-6:
            rom_cv = float(np.std(arr_amp) / mean_amp)

    irregular_rom = (
        len(reps_amps) >= 2
        and (
            rom_cv > float(cfg_k["dynamic_rom_cv_warning"])
            or rom_spread > float(cfg_k["dynamic_rom_spread_warning_deg"])
        )
    )
    high_noise = max_noise_rms > noise_thresh

    if irregular_rom or high_noise:
        reasons = []
        if irregular_rom:
            reasons.append(f"amplitude irrégulière entre répétitions (écart {rom_spread:.0f}°, CV={rom_cv * 100:.0f} %)")
        if high_noise:
            reasons.append(f"bruit cinématique élevé (résidu {max_noise_rms:.1f}° > {noise_thresh:.0f}°)")
        return QualityCheckItem(
            id="kinematic_purity",
            title="Pureté d'exécution & stabilité 3D",
            status="WARNING",
            score=80,
            message="Exécution dynamique perfectible : " + " et ".join(reasons) + ".",
            recommendation=(
                "Exécutez des répétitions homogènes à amplitude complète sous un éclairage stable pour réduire le bruit."
            ),
            metrics={
                "noise_rms_deg": round(max_noise_rms, 2),
                "rom_cv": round(rom_cv, 3),
                "rom_spread_deg": round(rom_spread, 1),
            },
        )

    return QualityCheckItem(
        id="kinematic_purity",
        title="Pureté d'exécution & stabilité 3D",
        status="PASS",
        score=100,
        message=(
            f"Mouvement dynamique régulier : bruit résiduel {max_noise_rms:.1f}°"
            + (f" • écart ROM {rom_spread:.0f}°" if len(reps_amps) >= 2 else "")
            + "."
        ),
        recommendation="",
        metrics={
            "noise_rms_deg": round(max_noise_rms, 2),
            "rom_cv": round(rom_cv, 3),
            "rom_spread_deg": round(rom_spread, 1),
        },
    )


def _check_camera_view_coherence(
    lm_active: Optional[np.ndarray],
    camera_view: str,
    cfg: Dict[str, Any]
) -> QualityCheckItem:
    """Critère 5 : Compare la séparation projetée 2D des épaules à l'angle déclaré."""
    cfg_c = cfg["camera_view"]
    idx = cfg["landmarks"]
    clean_view = (camera_view or "Profil").strip()

    if lm_active is None or len(lm_active) == 0:
        return QualityCheckItem(
            id="camera_view",
            title="Cohérence de l'angle de vue",
            status="WARNING",
            score=75,
            message=f"Impossible de vérifier géométriquement l'angle déclaré ({clean_view}).",
            recommendation="Vérifiez que la caméra correspond bien à l'emplacement sélectionné.",
            metrics={"declared_view": clean_view, "shoulder_width_ratio": None},
        )

    sh_l_i, sh_r_i = idx["LEFT_SHOULDER"], idx["RIGHT_SHOULDER"]
    el_l_i, el_r_i = idx["LEFT_ELBOW"], idx["RIGHT_ELBOW"]
    wr_l_i, wr_r_i = idx["LEFT_WRIST"], idx["RIGHT_WRIST"]
    hp_l_i, hp_r_i = idx["LEFT_HIP"], idx["RIGHT_HIP"]

    min_vis = float(cfg_c["min_pair_vis"])
    arm_w = float(cfg_c["arm_scale_weight"])
    min_scale = float(cfg_c["min_ref_scale"])

    ratios: List[float] = []
    for frame in lm_active:
        coords = frame[:, :2]
        vis = frame[:, 2]
        needed = [sh_l_i, sh_r_i, hp_l_i, hp_r_i]
        if not np.all(np.isfinite(coords[needed])):
            continue
        if min(vis[sh_l_i], vis[sh_r_i]) < min_vis * 0.5:
            continue

        sh_dist = float(np.linalg.norm(coords[sh_l_i] - coords[sh_r_i]))
        sh_mid = 0.5 * (coords[sh_l_i] + coords[sh_r_i])
        hp_mid = 0.5 * (coords[hp_l_i] + coords[hp_r_i])
        torso_len = float(np.linalg.norm(sh_mid - hp_mid))

        arm_lens: List[float] = []
        if np.all(np.isfinite(coords[[sh_l_i, el_l_i, wr_l_i]])):
            arm_lens.append(float(np.linalg.norm(coords[sh_l_i] - coords[wr_l_i])))
        if np.all(np.isfinite(coords[[sh_r_i, el_r_i, wr_r_i]])):
            arm_lens.append(float(np.linalg.norm(coords[sh_r_i] - coords[wr_r_i])))
        mean_arm = float(np.mean(arm_lens)) if arm_lens else 0.0

        ref_scale = max(torso_len, arm_w * mean_arm, min_scale)
        ratios.append(sh_dist / ref_scale)

    if not ratios:
        return QualityCheckItem(
            id="camera_view",
            title="Cohérence de l'angle de vue",
            status="WARNING",
            score=78,
            message=f"Repères d'épaules/hanches insuffisants pour confirmer l'angle « {clean_view} ».",
            recommendation="Assurez-vous que le haut du corps reste bien visible tout au long de l'effort.",
            metrics={"declared_view": clean_view, "shoulder_width_ratio": None},
        )

    ratio_med = float(np.median(ratios))

    if clean_view == "Profil" and ratio_med > float(cfg_c["profil_max_shoulder_ratio"]):
        return QualityCheckItem(
            id="camera_view",
            title="Cohérence de l'angle de vue",
            status="WARNING",
            score=75,
            message=(
                f"Incohérence potentielle : les deux épaules sont nettement écartées à l'écran "
                f"(ratio {ratio_med:.2f} > {cfg_c['profil_max_shoulder_ratio']:.2f}) pour un angle déclaré « Profil »."
            ),
            recommendation="Vérifiez si cette vidéo correspond plutôt à « Face » ou « 3/4 », sinon placez la caméra à 90° strict.",
            metrics={"declared_view": clean_view, "shoulder_width_ratio": round(ratio_med, 3)},
        )

    if clean_view == "Face" and ratio_med < float(cfg_c["face_min_shoulder_ratio"]):
        return QualityCheckItem(
            id="camera_view",
            title="Cohérence de l'angle de vue",
            status="WARNING",
            score=75,
            message=(
                f"Incohérence potentielle : les épaules paraissent rapprochées/de côté "
                f"(ratio {ratio_med:.2f} < {cfg_c['face_min_shoulder_ratio']:.2f}) pour un angle déclaré « Face »."
            ),
            recommendation="Sélectionnez « Profil » ou « 3/4 » si c'est l'angle filmé, ou filmez strictement face à l'athlète (0°).",
            metrics={"declared_view": clean_view, "shoulder_width_ratio": round(ratio_med, 3)},
        )

    if clean_view == "3/4" and ratio_med < float(cfg_c["three_quarter_min_shoulder_ratio"]):
        return QualityCheckItem(
            id="camera_view",
            title="Cohérence de l'angle de vue",
            status="WARNING",
            score=78,
            message=(
                f"Les épaules sont presque superposées (ratio {ratio_med:.2f} < {cfg_c['three_quarter_min_shoulder_ratio']:.2f}), "
                "prise de vue proche d'un Profil strict plutôt que « 3/4 »."
            ),
            recommendation="Vérifiez si l'angle réel est « Profil » (90°) ou décalez la caméra à 45° pour l'angle « 3/4 ».",
            metrics={"declared_view": clean_view, "shoulder_width_ratio": round(ratio_med, 3)},
        )

    return QualityCheckItem(
        id="camera_view",
        title="Cohérence de l'angle de vue",
        status="PASS",
        score=100,
        message=f"Angle « {clean_view} » cohérent avec la projection des épaules (ratio {ratio_med:.2f}).",
        recommendation="",
        metrics={"declared_view": clean_view, "shoulder_width_ratio": round(ratio_med, 3)},
    )


# ==============================================================================
# POINT D'ENTRÉE PRINCIPAL DU QUALITY CONTROL GATE
# ==============================================================================

def evaluate_calibration_quality(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    camera_view: str,
    exo_type: Optional[str] = None,
    exercise_name: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> QualityReport:
    """
    Évalue systématiquement la qualité technique et biomécanique d'une vidéo de calibrage 3D
    avant son enregistrement dans Baselines_3D. Ne duplique pas l'inférence MediaPipe.
    """
    cfg = config or QC_CONFIG
    s_idx, e_idx = _get_active_bounds(kinematics, segmentation)
    resolved_type = exo_type or (segmentation.get("type") if segmentation else None) or "isometric"
    clean_type = "dynamic" if "dyn" in str(resolved_type).lower() else "isometric"
    clean_view = (camera_view or "Profil").strip()

    lm_active = _extract_landmarks_2d_slice(kinematics, s_idx, e_idx)

    c_framing = _check_framing(lm_active, cfg)
    c_visibility = _check_visibility(lm_active, cfg)
    c_temporal = _check_temporal_integrity(kinematics, s_idx, e_idx, clean_type, cfg)
    reps_amps = c_temporal.metrics.get("rep_amplitudes", [])
    c_purity = _check_kinematic_purity(kinematics, s_idx, e_idx, clean_type, reps_amps, cfg)
    c_angle = _check_camera_view_coherence(lm_active, clean_view, cfg)

    checks = [c_framing, c_visibility, c_temporal, c_purity, c_angle]

    n_reject = sum(1 for c in checks if c.status == "REJECT")
    n_warn = sum(1 for c in checks if c.status == "WARNING")

    scoring = cfg["scoring"]
    raw_score = 100 - n_reject * int(scoring["penalty_reject"]) - n_warn * int(scoring["penalty_warning"])
    if n_reject > 0:
        global_status = "REJECT"
        global_score = max(0, min(int(scoring["max_score_on_reject"]), raw_score))
        summary = (
            f"Calibrage refusé ({n_reject} erreur(s) bloquante(s), score {global_score}/100). "
            "Refilmez selon le protocole avant d'enregistrer dans Baselines_3D."
        )
    elif n_warn > 0:
        global_status = "WARNING"
        global_score = max(0, min(95, raw_score))
        summary = (
            f"Calibrage acceptable avec {n_warn} avertissement(s) (score {global_score}/100). "
            "Vérifiez les recommandations ou confirmez explicitement."
        )
    else:
        global_status = "PASS"
        global_score = max(0, min(100, raw_score))
        summary = f"Qualité vidéo optimale (score {global_score}/100) : prête pour Baselines_3D."

    return QualityReport(
        status=global_status,
        global_score=int(global_score),
        checks=checks,
        summary=summary,
        metadata={
            "exercise": exercise_name,
            "camera_view": clean_view,
            "exo_type": clean_type,
            "active_start_idx": s_idx,
            "active_end_idx": e_idx,
            "n_active_frames": max(0, e_idx - s_idx + 1),
            "active_duration_sec": c_temporal.metrics.get("active_duration_sec", 0.0),
            "raw_fps": c_temporal.metrics.get("raw_fps", 0.0),
            "reps_detected": c_temporal.metrics.get("reps_detected", 0),
        },
    )
