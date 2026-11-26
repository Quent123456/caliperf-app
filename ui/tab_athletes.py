"""
ui/tab_athletes.py - Compartiment 4 : Gestion isolée des athlètes SQL & PDC.
"""

import html
import time
import streamlit as st

from core.auth import normalize_role
from core.database import (
    create_athlete_for_coach,
    delete_athlete_for_coach,
    get_coach_athletes,
    get_training_logs_for_athlete,
    get_user_by_id,
    link_athlete_to_coach_by_code,
    login_user_in_session,
    update_athlete_for_coach,
    update_user_profile_sql,
)
from ui.theme import render_html


def render_tab_athletes() -> None:
    """Rend la gestion des élèves pour le coach (isolation coach_id) ou le profil élève."""
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        return

    u_id = int(curr_u["id"])
    u_role = normalize_role(curr_u.get("role", "athlete"))

    if u_role != "coach":
        fresh_u = get_user_by_id(u_id) or curr_u
        render_html("""
            <div style="margin-bottom: 0.65rem;">
                <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                    🤸 Mon Suivi & Rattachement Coach
                </h3>
                <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8;">
                    Mettez à jour votre poids de corps (PDC) pour la quantification exacte et associez votre coach.
                </p>
            </div>
        """)
        with st.form("athlete_self_profile_form"):
            bw = st.number_input("Poids de corps (kg) :", min_value=25.0, max_value=250.0, value=float(fresh_u.get("bodyweight_kg", 70.0)), step=0.5)
            freq = st.selectbox("Fréquence :", ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine"], index=2)
            goal = st.text_input("Objectif principal :", value=str(fresh_u.get("goal", "")))
            if st.form_submit_button("💾 Enregistrer mon profil", type="primary", use_container_width=True):
                ok_u, msg_u, upd_u = update_user_profile_sql(u_id, bodyweight_kg=bw, freq=freq, goal=goal)
                if ok_u and upd_u:
                    login_user_in_session(upd_u)
                    st.success("✅ Profil mis à jour !")
                    time.sleep(0.25)
                    st.rerun()

        if fresh_u.get("coach_id"):
            coach_u = get_user_by_id(int(fresh_u["coach_id"]))
            if coach_u:
                st.info(f"🏋️ Coach rattaché : **{coach_u['full_name']}** (@{coach_u['username']})")
        else:
            with st.form("athlete_join_coach_form"):
                code_inp = st.text_input("Code d'invitation de votre coach :", placeholder="ex: CALI-1A2B3C")
                if st.form_submit_button("🔗 Rejoindre ce coach", use_container_width=True):
                    ok_l, msg_l, upd_u = link_athlete_to_coach_by_code(u_id, code_inp)
                    if ok_l and upd_u:
                        login_user_in_session(upd_u)
                        st.success(msg_l)
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error(msg_l)
        return

    # Vue Coach
    invite_code = curr_u.get("invite_code") or "—"
    render_html(f"""
        <div style="margin-bottom: 0.65rem;">
            <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                👥 Mes Athlètes & Code d'Invitation
            </h3>
            <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8;">
                Code invitation coach : <b style="color:#00E5FF; font-family:'JetBrains Mono',monospace;">{html.escape(invite_code)}</b> • Isolation stricte par coach.
            </p>
        </div>
    """)

    with st.expander("➕ Créer un élève directement dans mon espace", expanded=False):
        with st.form("add_student_tab_form", clear_on_submit=True):
            c_n1, c_n2 = st.columns([1.6, 1.0])
            with c_n1:
                new_full = st.text_input("Nom complet / Prénom :", placeholder="ex: Lucas Martin")
            with c_n2:
                new_bw = st.number_input("Poids de corps (kg) :", min_value=25.0, max_value=250.0, value=70.0, step=0.5)

            c_cr1, c_cr2 = st.columns(2)
            with c_cr1:
                new_uname = st.text_input("Identifiant de connexion (optionnel) :", placeholder="ex: lucas_m")
            with c_cr2:
                new_pwd = st.text_input("Mot de passe initial :", value="caliperf123", type="password")

            new_freq = st.selectbox(
                "Fréquence hebdomadaire :",
                ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Quotidien"],
                index=2
            )
            new_goal = st.text_area(
                "Objectif principal :",
                placeholder="Ex: Débloquer le Front Lever & séries de Dips lestés"
            )

            if st.form_submit_button("✅ Enregistrer l'athlète", type="primary", use_container_width=True):
                ok_a, msg_a, new_ath = create_athlete_for_coach(
                    coach_id=u_id,
                    full_name=new_full,
                    username=new_uname,
                    password=new_pwd,
                    bodyweight_kg=new_bw,
                    freq=new_freq,
                    goal=new_goal,
                )
                if ok_a and new_ath:
                    st.success(f"✅ {msg_a}")
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.error(msg_a)

    athletes = get_coach_athletes(u_id)
    if not athletes:
        st.info("Aucun élève rattaché pour le moment. Créez-en un ci-dessus ou partagez votre code d'invitation.")
        return

    search_s = ""
    if len(athletes) > 3:
        search_s = st.text_input("🔍 Rechercher un athlète :", placeholder="Nom ou identifiant...", key="search_athletes_input").strip().lower()

    matched = [
        a for a in athletes
        if not search_s or search_s in str(a["full_name"]).lower() or search_s in str(a["username"]).lower()
    ]
    if not matched:
        st.caption("Aucun athlète ne correspond à cette recherche.")
        return

    for ath in matched:
        aid = int(ath["id"])
        ath_logs = get_training_logs_for_athlete(curr_u, target_athlete_id=aid)
        avg_tut = (sum(l["tut_effective_sec"] for l in ath_logs) / len(ath_logs)) if ath_logs else 0.0
        avg_rpe = (sum(l["rpe"] for l in ath_logs) / len(ath_logs)) if ath_logs else 0.0
        safe_name = html.escape(str(ath["full_name"]))
        safe_uname = html.escape(str(ath["username"]))
        safe_freq = html.escape(str(ath.get("freq", "4x / semaine")))
        safe_goal = html.escape(str(ath.get("goal", "") or "Objectif général"))
        bw_val = float(ath.get("bodyweight_kg", 70.0))
        is_selected = int(st.session_state.get("active_athlete_id") or u_id) == aid

        border_style = "border:1px solid rgba(0,229,255,0.45);" if is_selected else ""
        render_html(f"""
            <div class="cali-card" style="{border_style}">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                    <div>
                        <h4 style="margin:0; font-size:1.05rem; font-weight:800; color:#F8FAFC;">👤 {safe_name} <small style="color:#64748B;">@{safe_uname}</small></h4>
                    </div>
                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                        <span class="badge-lime">{len(ath_logs)} Séances</span>
                        <span class="badge-cyan">PDC: {bw_val:.0f} kg</span>
                        <span class="badge-amber">TUT: {avg_tut:.1f}s • RPE: {avg_rpe:.1f}</span>
                    </div>
                </div>
                <div style="margin-top:8px; font-size:0.82rem; color:#94A3B8;">
                    📅 Fréquence : <b style="color:#F8FAFC;">{safe_freq}</b>
                </div>
                <div style="margin-top:6px; font-size:0.82rem; color:#CBD5E1; background:rgba(0,0,0,0.28); border:1px solid rgba(255,255,255,0.05); padding:7px 10px; border-radius:9px;">
                    🎯 <b>Objectif :</b> {safe_goal}
                </div>
            </div>
        """)

        c_sel, c_ed, c_del = st.columns([1.3, 1.5, 1.0])
        with c_sel:
            lbl_s = "✅ Athlète actif" if is_selected else "🎯 Suivre cet athlète"
            if st.button(lbl_s, key=f"sel_ath_{aid}", use_container_width=True, disabled=is_selected):
                st.session_state.active_athlete_id = aid
                st.toast(f"🎯 Athlète actif : {ath['full_name']}")
                st.rerun()
        with c_ed:
            with st.expander("✏️ Modifier", expanded=False):
                with st.form(f"edit_stud_form_{aid}"):
                    freq_opts = ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Quotidien"]
                    cur_f = ath.get("freq", "4x / semaine")
                    f_idx = freq_opts.index(cur_f) if cur_f in freq_opts else 2
                    upd_bw = st.number_input("PDC (kg) :", min_value=25.0, max_value=250.0, value=bw_val, step=0.5)
                    upd_freq = st.selectbox("Fréquence :", freq_opts, index=f_idx)
                    upd_goal = st.text_input("Objectif :", value=str(ath.get("goal", "")))
                    if st.form_submit_button("💾 Enregistrer", use_container_width=True):
                        ok_up, msg_up = update_athlete_for_coach(u_id, aid, upd_bw, upd_freq, upd_goal)
                        if ok_up:
                            st.toast(f"✅ {msg_up}")
                            time.sleep(0.2)
                            st.rerun()
                        else:
                            st.error(msg_up)
        with c_del:
            if st.button("🗑️ Supprimer", key=f"del_stud_{aid}", use_container_width=True):
                ok_dl, msg_dl = delete_athlete_for_coach(u_id, aid)
                if ok_dl:
                    if int(st.session_state.get("active_athlete_id") or 0) == aid:
                        st.session_state.active_athlete_id = u_id
                    st.toast(f"🗑️ {msg_dl}")
                    time.sleep(0.25)
                    st.rerun()
                else:
                    st.error(msg_dl)
