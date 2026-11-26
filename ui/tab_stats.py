"""
ui/tab_stats.py - Compartiment 3 : Statistiques, Graphiques TST/RPE & Registre des séances.
"""

import time
from datetime import datetime
import pandas as pd
import streamlit as st

from core.database import save_db
from ui.theme import render_html


def render_tab_stats() -> None:
    """Rend le tableau de bord statistique TST / RPE / Répétitions."""
    render_html("""
        <div style="margin-bottom: 0.65rem;">
            <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                📊 Statistiques & Progression
            </h3>
            <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8;">
                Analyse pure du Temps Sous Tension (TST), des répétitions et de la charge perçue (RPE).
            </p>
        </div>
    """)

    evals = st.session_state.db.get("evaluations", [])
    if not evals:
        render_html("""
            <div class="cali-card" style="text-align:center; padding: 2rem 1rem;">
                <div style="font-size:2rem; margin-bottom:0.4rem;">📉</div>
                <b style="color:#F8FAFC;">Aucune séance enregistrée</b>
                <p style="color:#94A3B8; font-size:0.86rem; margin:6px 0 0 0;">
                    Évaluez vos premières vidéos dans l'onglet <b>Studio</b> pour voir apparaître vos courbes de progression.
                </p>
            </div>
        """)
        return

    df_evals = pd.DataFrame(evals)
    if "reps" not in df_evals.columns:
        df_evals["reps"] = 0
    if "notes" not in df_evals.columns:
        df_evals["notes"] = ""

    # Filtres Athlète + Exercice
    all_students = ["Tous les athlètes"] + sorted(list(df_evals["student"].dropna().astype(str).unique()))
    all_exos = ["Tous les exercices"] + sorted(list(df_evals["exercise"].dropna().astype(str).unique()))

    c_filt1, c_filt2 = st.columns(2)
    with c_filt1:
        selected_student = st.selectbox("👤 Filtrer par athlète :", all_students, key="stats_filter_student")
    with c_filt2:
        selected_exo = st.selectbox("🏋️ Filtrer par exercice :", all_exos, key="stats_filter_exo")

    df_filtered = df_evals.copy()
    if selected_student != "Tous les athlètes":
        df_filtered = df_filtered[df_filtered["student"] == selected_student]
    if selected_exo != "Tous les exercices":
        df_filtered = df_filtered[df_filtered["exercise"] == selected_exo]

    if df_filtered.empty:
        st.info("Aucune séance ne correspond à cette combinaison de filtres.")
        return

    total_sessions = len(df_filtered)
    total_tst = float(df_filtered["tst"].sum())
    avg_tst = float(df_filtered["tst"].mean())
    avg_rpe = float(df_filtered["rpe"].mean())

    k1, k2 = st.columns(2)
    with k1:
        render_html(f"""
            <div class="cali-kpi-tile" style="margin-bottom:0.6rem;">
                <div class="cali-kpi-lbl">Séances Analysées</div>
                <div class="cali-kpi-val">{total_sessions}</div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">TST Moyen</div>
                <div class="cali-kpi-val" style="color:#00E5FF;">{avg_tst:.1f}<span style="font-size:0.9rem;color:#94A3B8;margin-left:3px;">s</span></div>
            </div>
        """)
    with k2:
        render_html(f"""
            <div class="cali-kpi-tile" style="margin-bottom:0.6rem;">
                <div class="cali-kpi-lbl">TST Cumulé</div>
                <div class="cali-kpi-val" style="color:#34D399;">{total_tst:.1f}<span style="font-size:0.9rem;color:#94A3B8;margin-left:3px;">s</span></div>
            </div>
            <div class="cali-kpi-tile">
                <div class="cali-kpi-lbl">RPE Moyen</div>
                <div class="cali-kpi-val" style="color:#FBBF24;">{avg_rpe:.1f}<span style="font-size:0.9rem;color:#94A3B8;margin-left:3px;">/ 10</span></div>
            </div>
        """)

    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 0.9rem 0;'>")

    # Sélecteur de graphique horizontal (sans nested st.tabs pour zéro conflit swipe)
    try:
        import plotly.express as px
        has_plotly = True
    except ImportError:
        has_plotly = False

    if has_plotly and not df_filtered.empty:
        chart_mode = st.radio(
            "Vue graphique :",
            ["📈 Évolution TST", "🔥 Répartition RPE", "🔁 Volume Répétitions"],
            horizontal=True,
            label_visibility="collapsed",
            key="stats_chart_mode_radio"
        )

        if chart_mode == "📈 Évolution TST":
            fig_tst = px.line(
                df_filtered,
                x="date",
                y="tst",
                color="exercise",
                markers=True,
                labels={"tst": "Temps Sous Tension (s)", "date": "Date", "exercise": "Exercice"},
                template="plotly_dark"
            )
            fig_tst.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(13,18,30,0.65)",
                font_family="Plus Jakarta Sans",
                margin=dict(l=10, r=10, t=25, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_tst, use_container_width=True)

        elif chart_mode == "🔥 Répartition RPE":
            fig_rpe = px.histogram(
                df_filtered,
                x="rpe",
                nbins=10,
                color_discrete_sequence=["#00E5FF"],
                labels={"rpe": "Niveau RPE"},
                template="plotly_dark"
            )
            fig_rpe.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(13,18,30,0.65)",
                font_family="Plus Jakarta Sans",
                margin=dict(l=10, r=10, t=25, b=20)
            )
            st.plotly_chart(fig_rpe, use_container_width=True)

        else:
            fig_reps = px.bar(
                df_filtered,
                x="date",
                y="reps",
                color="exercise",
                labels={"reps": "Répétitions", "date": "Date", "exercise": "Exercice"},
                template="plotly_dark"
            )
            fig_reps.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(13,18,30,0.65)",
                font_family="Plus Jakarta Sans",
                margin=dict(l=10, r=10, t=25, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_reps, use_container_width=True)

    st.markdown("##### 📜 Registre des séances")
    cols_present = ["date", "student", "exercise", "tst", "reps", "rpe", "notes"]
    df_disp = df_filtered[cols_present].copy()
    df_disp.columns = ["Date", "Athlète", "Exercice", "TST (s)", "Reps", "RPE", "Notes"]
    st.dataframe(df_disp, use_container_width=True, hide_index=True)

    col_exp, col_del_last = st.columns([2, 1])
    with col_exp:
        csv_bytes = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exporter les données (CSV)",
            data=csv_bytes,
            file_name=f"caliperf_stats_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_del_last:
        if st.button("↩️ Suppr. dernière", key="btn_undo_last_eval", help="Supprimer la toute dernière séance enregistrée", use_container_width=True):
            if st.session_state.db.get("evaluations"):
                removed = st.session_state.db["evaluations"].pop()
                save_db(st.session_state.db)
                st.toast(f"🗑️ Séance '{removed.get('exercise', '')}' retirée")
                time.sleep(0.3)
                st.rerun()
