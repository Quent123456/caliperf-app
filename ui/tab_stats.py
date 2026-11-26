"""
ui/tab_stats.py - Compartiment 3 : Tableau de bord ACWR EWMA, Stress Tendineux,
Journal SQL des séances & Exports multi-formats (CSV UTF-8-SIG / Excel XLSX).
"""

from datetime import datetime
import time
import pandas as pd
import streamlit as st

from core.calibration import load_baselines_table
from core.database import delete_training_log, get_training_logs_for_athlete
from services.export_service import (
    build_logs_export_dataframe,
    export_dataframe_to_csv_bytes,
    export_workbook_xlsx_bytes,
)
from ui.dashboard_load import render_longitudinal_dashboard
from ui.theme import render_html


def render_tab_stats() -> None:
    """Rend le tableau de bord longitudinal ACWR EWMA, les graphiques et exports."""
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        return

    active_profile = st.session_state.get("active_athlete_profile") or curr_u
    target_id = int(active_profile["id"])

    render_html("""
        <div style="margin-bottom: 0.65rem;">
            <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                📊 Statistiques, ACWR EWMA & Exports
            </h3>
            <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8;">
                Charge aiguë/chronique (EWMA), Monotonie de Foster, stress tendineux et export multi-formats.
            </p>
        </div>
    """)

    logs = get_training_logs_for_athlete(curr_u, target_athlete_id=target_id)
    dash_metrics = render_longitudinal_dashboard(active_profile, logs)

    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 0.9rem 0;'>")

    if not logs:
        render_html("""
            <div class="cali-card" style="text-align:center; padding: 1.7rem 1rem;">
                <div style="font-size:1.9rem; margin-bottom:0.4rem;">📉</div>
                <b style="color:#F8FAFC;">Aucune séance enregistrée pour cet athlète</b>
                <p style="color:#94A3B8; font-size:0.85rem; margin:6px 0 0 0;">
                    Validez vos analyses dans l'onglet <b>Studio</b> pour alimenter le journal SQL et l'ACWR.
                </p>
            </div>
        """)
    else:
        df_logs = pd.DataFrame(logs)
        all_exos = ["Tous les exercices"] + sorted(list(df_logs["exercise"].dropna().astype(str).unique()))
        selected_exo = st.selectbox("🏋️ Filtrer le journal par exercice :", all_exos, key="stats_filter_exo")
        df_filtered = df_logs if selected_exo == "Tous les exercices" else df_logs[df_logs["exercise"] == selected_exo]

        if not df_filtered.empty:
            total_sessions = len(df_filtered)
            total_load = float(df_filtered["external_load_au"].sum())
            avg_tut = float(df_filtered["tut_effective_sec"].mean())
            avg_rpe = float(df_filtered["rpe"].mean())

            k1, k2 = st.columns(2)
            with k1:
                render_html(f"""
                    <div class="cali-kpi-tile" style="margin-bottom:0.6rem;">
                        <div class="cali-kpi-lbl">Séances Filtrées</div>
                        <div class="cali-kpi-val">{total_sessions}</div>
                    </div>
                    <div class="cali-kpi-tile">
                        <div class="cali-kpi-lbl">TUT Moyen</div>
                        <div class="cali-kpi-val" style="color:#00E5FF;">{avg_tut:.1f}<span style="font-size:0.9rem;color:#94A3B8;margin-left:3px;">s</span></div>
                    </div>
                """)
            with k2:
                render_html(f"""
                    <div class="cali-kpi-tile" style="margin-bottom:0.6rem;">
                        <div class="cali-kpi-lbl">Charge Externe Cumulée</div>
                        <div class="cali-kpi-val" style="color:#34D399;">{total_load:.0f}<span style="font-size:0.9rem;color:#94A3B8;margin-left:3px;">UA</span></div>
                    </div>
                    <div class="cali-kpi-tile">
                        <div class="cali-kpi-lbl">RPE Moyen</div>
                        <div class="cali-kpi-val" style="color:#FBBF24;">{avg_rpe:.1f}<span style="font-size:0.9rem;color:#94A3B8;margin-left:3px;">/ 10</span></div>
                    </div>
                """)

            st.markdown("##### 📜 Journal des séances SQL")
            df_disp = build_logs_export_dataframe(df_filtered.to_dict(orient="records"))
            st.dataframe(df_disp, use_container_width=True, hide_index=True)

            if st.button("↩️ Supprimer la dernière séance affichée", key="btn_undo_last_eval", use_container_width=True):
                last_id = int(df_filtered.iloc[-1]["id"])
                ok_d, msg_d = delete_training_log(last_id, curr_u)
                if ok_d:
                    st.toast(f"🗑️ {msg_d}")
                    time.sleep(0.25)
                    st.rerun()
                else:
                    st.error(msg_d)

    # Exports multi-formats CSV (utf-8-sig) et Excel multi-onglets (.xlsx via openpyxl)
    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 0.9rem 0;'>")
    st.markdown("##### 📤 Exports autonomes (CSV Google Sheets & Excel `.xlsx`)")

    df_logs_exp = build_logs_export_dataframe(logs)
    df_base_exp = load_baselines_table(user=curr_u)
    daily_acwr_df = dash_metrics.get("daily_df")

    c_ex1, c_ex2 = st.columns(2)
    with c_ex1:
        csv_bytes = export_dataframe_to_csv_bytes(df_logs_exp)
        st.download_button(
            "📥 Exporter Journal (.csv UTF-8)",
            data=csv_bytes,
            file_name=f"caliperf_journal_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_export_logs_csv",
        )
    with c_ex2:
        xlsx_bytes = export_workbook_xlsx_bytes(logs, daily_acwr_df, df_base_exp)
        st.download_button(
            "📊 Exporter Classeur Complet (.xlsx)",
            data=xlsx_bytes,
            file_name=f"caliperf_rapport_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_export_workbook_xlsx",
        )
