"""
services/export_service.py - Exports multi-formats autonomes (CSV UTF-8-SIG & Excel XLSX)
pour le journal des séances, la synthèse ACWR/EWMA et les calibrations Baselines_3D.
"""

import io
from typing import Any, Dict, List
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


_LOG_EXPORT_COLS = [
    ("id", "ID"),
    ("date", "Date"),
    ("exercise", "Exercice"),
    ("exercise_type", "Type"),
    ("reps", "Répétitions"),
    ("tut_effective_sec", "TUT Effectif (s)"),
    ("added_load_kg", "Lest Additionnel (kg)"),
    ("bodyweight_kg", "PDC (kg)"),
    ("external_load_au", "Charge Externe"),
    ("rpe", "RPE (1-10)"),
    ("srpe_load", "Charge Interne sRPE"),
    ("fatigue_drift_deg", "Dérive Fatigue (°)"),
    ("velocity_loss_pct", "Perte Vitesse (%)"),
    ("notes", "Notes"),
]


def build_logs_export_dataframe(logs: List[Dict[str, Any]]) -> pd.DataFrame:
    """Construit un DataFrame propre ordonné avec intitulés français lisibles."""
    if not logs:
        return pd.DataFrame(columns=[lbl for _, lbl in _LOG_EXPORT_COLS])
    rows = []
    for log in sorted(logs, key=lambda x: str(x.get("date", "")), reverse=True):
        rows.append({lbl: log.get(key) for key, lbl in _LOG_EXPORT_COLS})
    return pd.DataFrame(rows)


def build_baselines_export_dataframe(baselines_df: pd.DataFrame) -> pd.DataFrame:
    """Formate la table baselines_3d pour l'export CSV/Excel."""
    if baselines_df is None or baselines_df.empty:
        return pd.DataFrame(columns=[
            "ID", "Figure", "Angle Caméra", "Type", "Statut", "Score Qualité",
            "Partagée Élèves", "Moyennes 3D", "Écarts-types 3D", "ROM Bounds"
        ])
    out_rows = []
    for _, r in baselines_df.iterrows():
        out_rows.append({
            "ID": r.get("id", ""),
            "Figure": r.get("exercise", ""),
            "Angle Caméra": r.get("camera_view", ""),
            "Type": r.get("type", ""),
            "Statut": r.get("status", ""),
            "Score Qualité": r.get("quality_score", ""),
            "Partagée Élèves": "Oui" if r.get("is_shared") else "Non",
            "Moyennes 3D": r.get("mean_features", ""),
            "Écarts-types 3D": r.get("std_features", ""),
            "ROM Bounds": r.get("rom_bounds", ""),
        })
    return pd.DataFrame(out_rows)


def export_dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Encode en UTF-8 avec BOM (utf-8-sig) pour ouverture directe sans problème d'accents."""
    return df.to_csv(index=False).encode("utf-8-sig")


def _write_df_to_sheet(ws, df: pd.DataFrame) -> None:
    header_fill = PatternFill(start_color="0D1B2A", end_color="0D1B2A", fill_type="solid")
    header_font = Font(bold=True, color="00E5FF", size=11)
    center_align = Alignment(vertical="center")

    cols = list(df.columns)
    ws.append(cols)
    for col_idx in range(1, len(cols) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    for row in df.itertuples(index=False, name=None):
        clean_row = ["" if (v is None or (isinstance(v, float) and pd.isna(v))) else v for v in row]
        ws.append(clean_row)

    ws.freeze_panes = "A2"
    for col_idx, col_name in enumerate(cols, start=1):
        max_len = len(str(col_name))
        for r_idx in range(2, ws.max_row + 1):
            val = ws.cell(row=r_idx, column=col_idx).value
            if val is not None:
                max_len = max(max_len, min(48, len(str(val))))
        col_letter = ws.cell(row=1, column=col_idx).column_letter
        ws.column_dimensions[col_letter].width = max(12, max_len + 3)


def export_workbook_xlsx_bytes(
    logs: List[Dict[str, Any]],
    acwr_summary_df: pd.DataFrame,
    baselines_df: pd.DataFrame,
) -> bytes:
    """
    Génère un classeur Excel (.xlsx via openpyxl) structuré en 3 onglets propres :
    - Journal_Charge
    - Synthese_ACWR
    - Baselines_3D
    """
    wb = Workbook()
    ws_logs = wb.active
    ws_logs.title = "Journal_Charge"
    _write_df_to_sheet(ws_logs, build_logs_export_dataframe(logs))

    ws_acwr = wb.create_sheet(title="Synthese_ACWR")
    if acwr_summary_df is None or acwr_summary_df.empty:
        acwr_summary_df = pd.DataFrame(columns=[
            "Date", "Charge Externe", "sRPE", "EWMA Aiguë (7j)",
            "EWMA Chronique (28j)", "ACWR"
        ])
    _write_df_to_sheet(ws_acwr, acwr_summary_df)

    ws_base = wb.create_sheet(title="Baselines_3D")
    _write_df_to_sheet(ws_base, build_baselines_export_dataframe(baselines_df))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
