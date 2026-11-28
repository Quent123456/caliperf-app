"""
services/export_service.py - Exports multi-formats autonomes (CSV UTF-8-SIG & Excel XLSX)
pour le journal des séances, la synthèse ACWR/EWMA et les calibrations Baselines_3D.
"""

import io
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
from fpdf import FPDF
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


def _pdf_safe(val: Any, max_len: int = 44) -> str:
    """Normalise une chaîne pour encodage Latin-1 sûr dans les polices PDF standard."""
    txt = str(val if val is not None else "")
    replacements = {
        "—": "-",
        "–": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "•": "|",
        "…": "...",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        txt = txt.replace(src, dst)
    cleaned = txt.encode("latin-1", "ignore").decode("latin-1").strip()
    if max_len > 0 and len(cleaned) > max_len:
        return cleaned[: max_len - 2].rstrip() + ".."
    return cleaned


def generate_athlete_pdf_report(
    athlete_profile: Dict[str, Any],
    coach_profile: Optional[Dict[str, Any]],
    logs: List[Dict[str, Any]],
    acwr_metrics: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Génère un bilan PDF synthétique d'une page (fpdf2) :
    - En-tête CaliPerf Pro, noms du coach et de l'athlète
    - KPIs globaux : TUT total, répétitions totales, ratio ACWR actuel
    - Tableau des 10 dernières séances enregistrées
    """
    ath_name = _pdf_safe((athlete_profile or {}).get("full_name") or (athlete_profile or {}).get("username") or "Athlète", 40)
    ath_bw = float((athlete_profile or {}).get("bodyweight_kg", 70.0) or 70.0)
    ath_goal = _pdf_safe((athlete_profile or {}).get("goal") or "Non renseigné", 72)

    coach_name = _pdf_safe(
        (coach_profile or {}).get("full_name") or (coach_profile or {}).get("username") or "CaliPerf Coach",
        40,
    )

    sorted_logs = sorted(logs or [], key=lambda x: str(x.get("date", "")), reverse=True)
    total_tut = sum(float(l.get("tut_effective_sec", 0.0) or 0.0) for l in sorted_logs)
    total_reps = sum(int(l.get("reps", 0) or 0) for l in sorted_logs)
    total_sessions = len(sorted_logs)

    acwr_val = float((acwr_metrics or {}).get("acwr", 0.0) or 0.0)
    acwr_lbl = _pdf_safe((acwr_metrics or {}).get("acwr_label") or "Aucune charge active", 36)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    # Bandeau supérieur CaliPerf Obsidian
    pdf.set_fill_color(11, 16, 28)
    pdf.rect(0, 0, 210, 30, style="F")
    pdf.set_fill_color(0, 229, 255)
    pdf.rect(0, 29, 210, 1.4, style="F")

    pdf.set_xy(14, 7)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(0, 229, 255)
    pdf.cell(95, 8, "CALIPERF PRO", ln=0)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(87, 8, f"Genere le {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="R", ln=1)

    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(248, 250, 252)
    pdf.cell(182, 7, "BILAN LONGITUDINAL ATHLETE", ln=1)

    # Cartouche Athlète & Coach
    pdf.set_fill_color(244, 247, 252)
    pdf.set_draw_color(203, 213, 225)
    pdf.rect(14, 36, 182, 24, style="DF")

    pdf.set_xy(18, 39)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(92, 6, f"Athlete : {ath_name} ({ath_bw:.1f} kg)", ln=0)
    pdf.cell(84, 6, f"Coach : {coach_name}", align="R", ln=1)

    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(174, 6, f"Objectif : {ath_goal}", ln=1)
    pdf.set_x(18)
    pdf.cell(174, 5, f"Total seances historisees : {total_sessions}", ln=1)

    # 3 Tuiles KPI
    kpi_y = 66
    card_w = 58
    gap = 4
    kpis = [
        ("TUT TOTAL", f"{total_tut:.1f} s", f"{total_sessions} seance(s)"),
        ("REPETITIONS TOTALES", f"{total_reps}", "Cumul historique"),
        ("RATIO ACWR ACTUEL", f"{acwr_val:.2f}", acwr_lbl),
    ]
    for idx_k, (lbl_k, val_k, sub_k) in enumerate(kpis):
        cx = 14 + idx_k * (card_w + gap)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(203, 213, 225)
        pdf.rect(cx, kpi_y, card_w, 24, style="DF")

        pdf.set_xy(cx + 3, kpi_y + 3)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(card_w - 6, 4, lbl_k, ln=1)

        pdf.set_x(cx + 3)
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(14, 116, 144)
        pdf.cell(card_w - 6, 8, val_k, ln=1)

        pdf.set_x(cx + 3)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(card_w - 6, 4, sub_k, ln=1)

    # Tableau des 10 dernières séances
    pdf.set_xy(14, 98)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(182, 7, "10 DERNIERES SEANCES ENREGISTREES", ln=1)

    recent_10 = sorted_logs[:10]
    if not recent_10:
        pdf.set_xy(14, 108)
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(182, 10, "Aucune seance enregistree pour cet athlete a ce jour.", ln=1)
    else:
        col_widths = [28, 48, 16, 14, 20, 18, 16, 22]
        headers = ["Date", "Exercice", "Type", "Reps", "TUT (s)", "Lest (kg)", "RPE", "sRPE"]
        pdf.set_xy(14, 107)
        pdf.set_fill_color(15, 23, 42)
        pdf.set_text_color(0, 229, 255)
        pdf.set_font("Helvetica", "B", 8)
        for cw, htxt in zip(col_widths, headers):
            pdf.cell(cw, 8, htxt, border=1, align="C", fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for r_idx, row in enumerate(recent_10):
            raw_dt = str(row.get("date", ""))
            short_dt = f"{raw_dt[8:10]}/{raw_dt[5:7]}/{raw_dt[2:4]} {raw_dt[11:16]}" if len(raw_dt) >= 16 else raw_dt[:10]
            exo_nm = _pdf_safe(row.get("exercise", ""), 24)
            is_dyn = "dyn" in str(row.get("exercise_type", "")).lower()
            tp_lbl = "Dyn" if is_dyn else "Iso"
            reps_v = int(row.get("reps", 0) or 0)
            tut_v = float(row.get("tut_effective_sec", 0.0) or 0.0)
            lest_v = float(row.get("added_load_kg", 0.0) or 0.0)
            rpe_v = float(row.get("rpe", 0.0) or 0.0)
            srpe_v = float(row.get("srpe_load", 0.0) or 0.0)

            vals = [
                _pdf_safe(short_dt, 16),
                exo_nm,
                tp_lbl,
                str(reps_v),
                f"{tut_v:.1f}",
                f"{lest_v:.1f}",
                f"{rpe_v:.1f}",
                f"{srpe_v:.1f}",
            ]
            aligns = ["L", "L", "C", "R", "R", "R", "R", "R"]
            fill_row = (r_idx % 2 == 1)
            if fill_row:
                pdf.set_fill_color(241, 245, 249)
            pdf.set_text_color(30, 41, 59)
            pdf.set_x(14)
            for cw, v_str, al in zip(col_widths, vals, aligns):
                pdf.cell(cw, 7.5, v_str, border=1, align=al, fill=fill_row)
            pdf.ln()

    # Pied de page
    pdf.set_xy(14, 282)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(182, 5, "CaliPerf Pro - Cockpit Biomecanique 3D & Quantification de Charge", align="C")

    return bytes(pdf.output())
