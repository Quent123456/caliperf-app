"""
core/load_quantification.py - Calcul déterministe de la charge externe (UA), sRPE
et configuration externalisée (config/load_config.json) pour CaliPerf.
"""

import json
import os
import re
from typing import Any, Dict, List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOAD_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config", "load_config.json")


def load_quantification_config(config_path: str = LOAD_CONFIG_PATH) -> Dict[str, Any]:
    """Charge la configuration des coefficients, zones ACWR, fatigue et stress tendineux."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def get_exercise_difficulty_coef(
    exercise: str,
    exo_type: str = "isometric",
    config: Dict[str, Any] = None,
) -> float:
    """Retourne le coefficient biomécanique de difficulté configuré pour une figure."""
    cfg = config or load_quantification_config()
    coef_cfg = cfg.get("load_coefficients", {})
    by_exo = coef_cfg.get("by_exercise", {})
    key = _slug(exercise)

    if key in by_exo:
        return float(by_exo[key])

    for k, val in by_exo.items():
        if k in key or key in k:
            return float(val)

    is_dyn = "dyn" in str(exo_type).lower()
    return float(coef_cfg.get("default_dynamic" if is_dyn else "default_isometric", 1.2))


def is_high_tendon_stress_exercise(exercise: str, config: Dict[str, Any] = None) -> bool:
    """Détermine si la figure sollicite un fort levier articulaire / stress tendineux."""
    cfg = config or load_quantification_config()
    tendon_list: List[str] = cfg.get("tendon_stress_exercises", [])
    s_exo = _slug(exercise)
    if not s_exo:
        return False
    for ref in tendon_list:
        s_ref = _slug(ref)
        if s_ref == s_exo or s_ref in s_exo or s_exo in s_ref:
            return True
    return False


def compute_external_load_au(
    exo_type: str,
    tut_effective_sec: float,
    reps: int,
    difficulty_coef: float,
    added_load_kg: float = 0.0,
    bodyweight_kg: float = 70.0,
) -> float:
    """
    Calcule la charge externe pondérée en Unités Arbitraires (UA) :
    - Isométrique : TUT_effectif * Coef_figure * (1 + Lest / PDC)
    - Dynamique   : Reps * TUT_actif * Coef_figure
    """
    tut = max(0.0, float(tut_effective_sec or 0.0))
    coef = max(0.1, float(difficulty_coef or 1.0))
    is_dyn = "dyn" in str(exo_type).lower()

    if is_dyn:
        n_reps = max(0, int(reps or 0))
        return round(float(n_reps) * tut * coef, 2)

    bw = max(25.0, float(bodyweight_kg or 70.0))
    added = max(0.0, float(added_load_kg or 0.0))
    return round(tut * coef * (1.0 + added / bw), 2)


def compute_srpe_load(
    rpe: float,
    exo_type: str,
    tut_effective_sec: float,
    reps: int,
) -> float:
    """
    Calcule la charge interne sRPE = RPE * Volume/Durée :
    - Isométrique : RPE * TUT_effectif (s)
    - Dynamique   : RPE * TUT_actif (ou RPE * Reps si durée active nulle)
    """
    clean_rpe = max(1.0, min(10.0, float(rpe or 1.0)))
    tut = max(0.0, float(tut_effective_sec or 0.0))
    is_dyn = "dyn" in str(exo_type).lower()
    if is_dyn:
        vol = tut if tut > 0.0 else float(max(0, int(reps or 0)))
        return round(clean_rpe * vol, 2)
    return round(clean_rpe * tut, 2)


def compute_set_load_bundle(
    exercise: str,
    exo_type: str,
    tut_effective_sec: float,
    reps: int,
    added_load_kg: float,
    bodyweight_kg: float,
    rpe: float,
    difficulty_coef: float = None,
) -> Dict[str, Any]:
    """Calcule en un appel l'ensemble des métriques de charge d'une série."""
    cfg = load_quantification_config()
    coef = (
        float(difficulty_coef)
        if difficulty_coef is not None and float(difficulty_coef) > 0
        else get_exercise_difficulty_coef(exercise, exo_type=exo_type, config=cfg)
    )
    ext_au = compute_external_load_au(
        exo_type=exo_type,
        tut_effective_sec=tut_effective_sec,
        reps=reps,
        difficulty_coef=coef,
        added_load_kg=added_load_kg,
        bodyweight_kg=bodyweight_kg,
    )
    srpe = compute_srpe_load(
        rpe=rpe,
        exo_type=exo_type,
        tut_effective_sec=tut_effective_sec,
        reps=reps,
    )
    return {
        "difficulty_coef": round(coef, 3),
        "external_load_au": ext_au,
        "srpe_load": srpe,
        "is_tendon_stress": is_high_tendon_stress_exercise(exercise, config=cfg),
    }
