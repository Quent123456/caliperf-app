"""
core/calibration.py - Gestion des prototypes multi-angles et identification 1-NN 3D
Caractéristiques :
- Chargement / sauvegarde des prototypes dans config/baselines_3d.json
- Ne moyenne JAMAIS les vecteurs de différents angles : chaque calibrage = 1 prototype distinct
- Identification par Plus Proche Voisin Normalisé (1-NN) avec pénalité sur orientation ventrale/dorsale
- Calcul du score de confiance en %
- Fonctions d'enrichissement pour ajouter ou supprimer des prototypes
"""

import os
import json
import time
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

DEFAULT_BASELINES_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "baselines_3d.json")

FEATURE_KEYS = [
    "shoulder_flexion",
    "arm_abduction",
    "elbow_angle",
    "hip_angle",
    "trunk_inclination",
    "ventral_dorsal"
]


def load_baselines_3d(path: str = DEFAULT_BASELINES_PATH) -> Dict[str, Any]:
    """Charge le fichier de calibrage multi-angles JSON."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier de baselines 3D introuvable : {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_baselines_3d(data: Dict[str, Any], path: str = DEFAULT_BASELINES_PATH) -> bool:
    """Enregistre les prototypes mis à jour dans le fichier JSON."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erreur de sauvegarde baselines 3D : {e}")
        return False


def compute_active_feature_vectors(
    kinematics: Dict[str, Any],
    effort_window: Dict[str, Any]
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calcule le vecteur moyen (6D) et les écarts-types (6D) sur la fenêtre d'effort active.
    """
    s_idx = effort_window["start_idx"]
    e_idx = effort_window["end_idx"]
    filt = kinematics["features_filtered"]

    means: List[float] = []
    stds: List[float] = []

    for k in FEATURE_KEYS:
        series = filt[k][s_idx:e_idx + 1]
        if len(series) == 0:
            means.append(0.0)
            stds.append(1.0)
        else:
            means.append(float(np.mean(series)))
            stds.append(max(float(np.std(series)), 1.0))

    return np.array(means, dtype=np.float64), np.array(stds, dtype=np.float64)


def identify_exercise_1nn(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    baselines_path: str = DEFAULT_BASELINES_PATH,
    forced_exercise: Optional[str] = None
) -> Dict[str, Any]:
    """
    Identifie l'exercice et la perspective caméra par Plus Proche Voisin Normalisé (1-NN).
    Compare la signature 3D active à tous les prototypes de type correspondant (isometric ou dynamic).
    """
    baselines_cfg = load_baselines_3d(baselines_path)
    prototypes = baselines_cfg.get("prototypes", [])
    detected_type = segmentation.get("type", "isometric")
    effort_win = segmentation.get("effort_window", {})

    active_means, active_stds = compute_active_feature_vectors(kinematics, effort_win)

    if not prototypes:
        return {
            "exercise": forced_exercise or "full_planche",
            "display_name": "Full Planche",
            "camera_view": "profile",
            "type": detected_type,
            "confidence": 0.80,
            "distance": 0.0,
            "matched_prototype": None,
            "active_means": active_means.tolist(),
            "active_stds": active_stds.tolist()
        }

    # Filtrage par type (ou forçage)
    candidate_protos = [p for p in prototypes if p.get("type") == detected_type]
    if not candidate_protos:
        candidate_protos = prototypes

    if forced_exercise:
        forced_matches = [p for p in candidate_protos if p.get("exercise") == forced_exercise]
        if forced_matches:
            candidate_protos = forced_matches

    distances: List[Tuple[float, Dict[str, Any]]] = []

    for proto in candidate_protos:
        proto_means = np.array(proto["mean_features"], dtype=np.float64)
        proto_stds = np.array(proto["std_features"], dtype=np.float64)

        # Pénalité stricte sur l'orientation ventrale/dorsale (indice 5)
        # Ne doit JAMAIS confondre Planche (+1) et Front Lever (-1)
        vd_video = active_means[5]
        vd_proto = proto_means[5]
        orient_mismatch = (vd_video * vd_proto) < 0

        # Distance euclidienne normalisée par l'écart-type
        diff = (active_means - proto_means) / np.maximum(proto_stds, 1.5)
        dist = float(np.sqrt(np.sum(diff**2)))

        if orient_mismatch:
            dist += 150.0  # Rejet catégorique

        distances.append((dist, proto))

    distances.sort(key=lambda x: x[0])
    best_dist, best_proto = distances[0]
    second_dist = distances[1][0] if len(distances) > 1 else (best_dist + 5.0)

    # Calcul de confiance relative (%)
    if best_dist < 1.0:
        confidence = 0.98
    elif best_dist < 3.0:
        confidence = 0.94
    else:
        denom = best_dist + second_dist
        ratio = 1.0 - (best_dist / max(denom, 1e-6))
        confidence = max(0.65, min(0.96, ratio))

    return {
        "exercise": best_proto["exercise"],
        "display_name": best_proto.get("display_name", best_proto["exercise"]),
        "camera_view": best_proto.get("camera_view", "profile"),
        "type": best_proto.get("type", detected_type),
        "confidence": round(float(confidence), 2),
        "distance": round(float(best_dist), 2),
        "matched_prototype": best_proto,
        "active_means": [round(float(v), 1) for v in active_means],
        "active_stds": [round(float(v), 1) for v in active_stds]
    }


def extract_prototype_from_video(
    kinematics: Dict[str, Any],
    segmentation: Dict[str, Any],
    exercise_key: str,
    display_name: str,
    camera_view: str = "profile",
    exo_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Génère un nouveau prototype de calibrage complet à partir de la vidéo analysée.
    """
    effort_win = segmentation["effort_window"]
    active_means, active_stds = compute_active_feature_vectors(kinematics, effort_win)
    final_type = exo_type or segmentation["type"]

    proto_id = f"{exercise_key}_{camera_view}_{int(time.time())}"

    # Construction des bornes selon le type
    stability = None
    rom_bounds = None

    if final_type == "isometric":
        stability = {
            "max_hip_vertical_velocity": 0.15,
            "min_hold_duration_sec": 0.4
        }
    else:
        filt = kinematics["features_filtered"]
        s_idx = effort_win["start_idx"]
        e_idx = effort_win["end_idx"]
        el_active = filt["elbow_angle"][s_idx:e_idx + 1]

        rom_bounds = {
            "primary_joint": "elbow_angle",
            "min_amplitude_deg": 22.0,
            "lockout_angle": round(float(np.max(el_active)), 1) if len(el_active) > 0 else 165.0,
            "inflection_angle": round(float(np.min(el_active)), 1) if len(el_active) > 0 else 90.0,
            "min_rep_duration_sec": 0.4,
            "max_rep_duration_sec": 9.0
        }

    return {
        "id": proto_id,
        "exercise": exercise_key,
        "display_name": display_name,
        "camera_view": camera_view,
        "type": final_type,
        "mean_features": [round(float(v), 1) for v in active_means],
        "std_features": [max(round(float(v), 1), 2.0) for v in active_stds],
        "stability": stability,
        "rom_bounds": rom_bounds,
        "source": "user_calibrated",
        "created_at": time.strftime("%Y-%m-%d")
    }


def add_or_update_prototype_in_file(
    prototype_data: Dict[str, Any],
    baselines_path: str = DEFAULT_BASELINES_PATH
) -> Tuple[bool, str]:
    """Ajoute ou remplace un prototype dans le fichier JSON."""
    try:
        config = load_baselines_3d(baselines_path)
        prototypes = config.get("prototypes", [])

        # Remplacement si même id
        idx = next((i for i, p in enumerate(prototypes) if p.get("id") == prototype_data["id"]), -1)
        if idx >= 0:
            prototypes[idx] = prototype_data
        else:
            prototypes.append(prototype_data)

        config["prototypes"] = prototypes
        save_baselines_3d(config, baselines_path)
        return True, f"Prototype '{prototype_data.get('display_name')}' ({prototype_data.get('camera_view')}) enregistré !"
    except Exception as e:
        return False, f"Erreur lors de l'enregistrement du prototype : {e}"


def delete_prototype_from_file(
    prototype_id: str,
    baselines_path: str = DEFAULT_BASELINES_PATH
) -> Tuple[bool, str]:
    """Supprime un prototype par son identifiant."""
    try:
        config = load_baselines_3d(baselines_path)
        prototypes = config.get("prototypes", [])
        new_protos = [p for p in prototypes if p.get("id") != prototype_id]
        if len(new_protos) == len(prototypes):
            return False, f"Prototype '{prototype_id}' introuvable."
        config["prototypes"] = new_protos
        save_baselines_3d(config, baselines_path)
        return True, f"Prototype '{prototype_id}' supprimé."
    except Exception as e:
        return False, f"Erreur suppression : {e}"
