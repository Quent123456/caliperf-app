"""
ui/tab_stats.py - Compartiment 3 : Suivi & ACWR, Fragment Journal SQL mobile-first,
confirmation de suppression & Exports autonomes (CSV UTF-8-SIG / Excel XLSX).
"""

from datetime import datetime
from typing import Any, Dict, List
import pandas as pd
import streamlit as st

from core.auth import normalize_role
from core.calibration import load_baselines_table
from core.database import (
    delete_training_log,
    get_coach_athletes,
    get_training_logs_for_athlete,
    set_active_athlete_in_session,
)
from services.export_service import (
    build_logs_export_dataframe,
    export_dataframe_to_csv_bytes,
    export_workbook_xlsx_bytes,
    generate_athlete_pdf_report,
)
from ui.dashboard_load import render_longitudinal_dashboard
from ui.theme import render_empty_state, render_html


def _format_mobile_journal_dataframe(df_filtered: pd.DataFrame) -> pd.DataFrame:
    """Formate les colonnes clés pour une lecture directe sans scroll horizontal sur mobile."""
    rows = []
    sorted_df = df_filtered.sort_values(by="date", ascending=False)
    for _, r in sorted_df.iterrows():
        raw_dt = str(r.get("date", ""))
        short_dt = f"{raw_dt[8:10]}/{raw_dt[5:7]} {raw_dt[11:16]}" if len(raw_dt) >= 16 else raw_dt[:10]
        is_dyn = "dyn" in str(r.get("exercise_type", "")).lower()
        mode_lbl = "Dyn" if is_dyn else "Iso"
        tut_v = float(r.get("tut_effective_sec", 0.0) or 0.0)
        reps_v = int(r.get("reps", 0) or 0)
        if is_dyn and reps_v > 0:
            tut_reps_lbl = f"{reps_v}r / {tut_v:.1f}s"
        elif reps_v > 0:
            tut_reps_lbl = f"{tut_v:.1f}s ({reps_v}r)"
        else:
            tut_reps_lbl = f"{tut_v:.1f}s"
        rows.append({
            "Date": short_dt,
            "Exercice": str(r.get("exercise", "")),
            "Type": mode_lbl,
            "Volume": tut_reps_lbl,
            "Effort": f"{float(r.get('rpe', 0.0) or 0.0):.1f}/10",
        })
    return pd.DataFrame(rows)


def _fragment_decorator(fn):
    if hasattr(st, "fragment"):
        return st.fragment(fn)
    return fn


@_fragment_decorator
def _render_filtered_journal_fragment(logs: List[Dict[str, Any]], curr_u: Dict[str, Any]) -> None:
    """Fragment isolé : filtrer par exercice ou supprimer ne recharge pas les graphiques de charge."""
    df_logs = pd.DataFrame(logs)
    all_exos = ["Tous les exercices"] + sorted(list(df_logs["exercise"].dropna().astype(str).unique()))
    selected_exo = st.selectbox("Filtrer par exercice :", all_exos, key="stats_filter_exo")
    df_filtered = df_logs if selected_exo == "Tous les exercices" else df_logs[df_logs["exercise"] == selected_exo]

    if not df_filtered.empty:
        total_sessions = len(df_filtered)
        total_tut = float(df_filtered["tut_effective_sec"].sum())
        avg_tut = float(df_filtered["tut_effective_sec"].mean())
        avg_rpe = float(df_filtered["rpe"].mean())

        render_html(f"""
            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:0.85rem;">
                <div class="cali-kpi-tile">
                    <div class="cali-kpi-lbl">Séances filtrées</div>
                    <div class="cali-kpi-val">{total_sessions}</div>
                </div>
                <div class="cali-kpi-tile">
                    <div class="cali-kpi-lbl">Temps sous tension total</div>
                    <div class="cali-kpi-val" style="color:#34D399;">{total_tut:.0f}<span style="font-size:0.85rem;color:#94A3B8;margin-left:3px;">s</span></div>
                </div>
                <div class="cali-kpi-tile">
                    <div class="cali-kpi-lbl">Temps moyen / série</div>
                    <div class="cali-kpi-val" style="color:#00E5FF;">{avg_tut:.1f}<span style="font-size:0.85rem;color:#94A3B8;margin-left:3px;">s</span></div>
                </div>
                <div class="cali-kpi-tile">
                    <div class="cali-kpi-lbl">Effort moyen</div>
                    <div class="cali-kpi-val" style="color:#FBBF24;">{avg_rpe:.1f}<span style="font-size:0.85rem;color:#94A3B8;margin-left:3px;">/10</span></div>
                </div>
            </div>
        """)

        st.markdown("##### Historique des séances")
        df_mobile = _format_mobile_journal_dataframe(df_filtered)
        st.dataframe(df_mobile, use_container_width=True, hide_index=True)

        confirm_del = st.checkbox("Confirmer la suppression", key="stats_confirm_delete_last")
        if st.button(
            "Supprimer la dernière séance affichée",
            key="btn_undo_last_eval",
            use_container_width=True,
            disabled=not confirm_del,
        ):
            last_id = int(df_filtered.iloc[-1]["id"])
            ok_d, msg_d = delete_training_log(last_id, curr_u)
            if ok_d:
                st.toast(msg_d)
                try:
                    st.rerun(scope="app")
                except TypeError:
                    st.rerun()
            else:
                st.error(msg_d)


def render_tab_stats() -> None:
    """Rend le tableau de bord de suivi de charge, les graphiques et exports."""
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        return

    render_html("<h3 style='margin:0 0 0.55rem 0; font-size:1.15rem; font-weight:800; color:#F8FAFC;'>Suivi de charge & progression</h3>")

    curr_role = normalize_role(curr_u.get("role", "athlete"))
    if curr_role == "coach":
        profile_by_id = st.session_state.get("selectable_profiles_map")
        option_ids = st.session_state.get("selectable_profile_ids")
        if not profile_by_id or not option_ids:
            coach_athletes = get_coach_athletes(int(curr_u["id"]))
            profiles = [curr_u] + coach_athletes
            profile_by_id = {int(p["id"]): p for p in profiles}
            option_ids = [int(p["id"]) for p in profiles]

        def _on_stats_athlete_change() -> None:
            chosen = st.session_state.get("stats_athlete_select")
            if chosen is not None:
                set_active_athlete_in_session(int(chosen), sync_widgets=True)

        selected_stat_id = st.selectbox(
            "Athlète affiché :",
            options=option_ids,
            format_func=lambda pid: (
                f"Moi-même ({profile_by_id[pid]['full_name']})"
                if pid == int(curr_u["id"]) else
                f"{profile_by_id[pid]['full_name']} ({profile_by_id[pid]['bodyweight_kg']:.0f} kg)"
            ),
            key="stats_athlete_select",
            on_change=_on_stats_athlete_change,
        )
        active_profile = profile_by_id[int(selected_stat_id)]
        st.session_state["active_athlete_profile"] = active_profile
    else:
        active_profile = st.session_state.get("active_athlete_profile") or curr_u

    target_id = int(active_profile["id"])
    logs = get_training_logs_for_athlete(curr_u, target_athlete_id=target_id)
    dash_metrics = render_longitudinal_dashboard(active_profile, logs)

    render_html("<hr style='border:0; border-top:1px solid rgba(148,163,184,0.14); margin: 1.05rem 0;'>")

    if not logs:
        render_empty_state(
            title="Aucune séance pour le moment",
            description="Aucune séance pour le moment. Analyse une vidéo dans le Studio ou ajoute une série manuellement pour démarrer le suivi.",
            action_label="Ouvrir le Studio",
            target_tab="🎥 Studio",
            icon="",
            key="empty_stats_go_studio",
        )
    else:
        _render_filtered_journal_fragment(logs, curr_u)

    render_html("<hr style='border:0; border-top:1px solid rgba(148,163,184,0.14); margin: 1.05rem 0;'>")
    st.markdown("##### Exports & Bilan PDF")

    df_logs_exp = build_logs_export_dataframe(logs)
    df_base_exp = load_baselines_table(user=curr_u)
    daily_acwr_df = dash_metrics.get("daily_df")

    c_ex1, c_ex2, c_ex3 = st.columns(3)
    with c_ex1:
        csv_bytes = export_dataframe_to_csv_bytes(df_logs_exp)
        st.download_button(
            "Exporter en CSV",
            data=csv_bytes,
            file_name=f"caliperf_journal_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_export_logs_csv",
        )
    with c_ex2:
        xlsx_bytes = export_workbook_xlsx_bytes(logs, daily_acwr_df, df_base_exp)
        st.download_button(
            "Exporter en Excel",
            data=xlsx_bytes,
            file_name=f"caliperf_rapport_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_export_workbook_xlsx",
        )
    with c_ex3:
        coach_prof = curr_u if curr_role == "coach" else None
        pdf_bytes = generate_athlete_pdf_report(active_profile, coach_prof, logs, dash_metrics)
        safe_fn = "".join(c if c.isalnum() else "_" for c in str(active_profile.get("username", "athlete"))).strip("_") or "athlete"
        st.download_button(
            "Bilan PDF",
            data=pdf_bytes,
            file_name=f"caliperf_bilan_{safe_fn}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="btn_export_athlete_pdf",
        )
