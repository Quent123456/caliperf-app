"""
ui/tab_athletes.py - Compartiment 4 : Dossiers Athlètes, Objectifs & Historique rapide.
"""

import html
import re
import time
from datetime import datetime
import streamlit as st

from core.database import save_db
from ui.theme import render_html


def render_tab_athletes() -> None:
    """Rend l'espace de gestion des dossiers athlètes."""
    render_html("""
        <div style="margin-bottom: 0.65rem;">
            <h3 style="margin:0; font-size:1.18rem; font-weight:800; color:#F8FAFC;">
                👥 Dossiers Athlètes
            </h3>
            <p style="margin:2px 0 0 0; font-size:0.8rem; color:#94A3B8;">
                Créez vos fiches athlètes, suivez leur volume d'entraînement et mettez à jour leurs objectifs.
            </p>
        </div>
    """)

    with st.expander("➕ Inscrire un nouvel athlète", expanded=False):
        with st.form("add_student_tab_form", clear_on_submit=True):
            c_n1, c_n2 = st.columns(2)
            with c_n1:
                new_prenom = st.text_input("Prénom :")
            with c_n2:
                new_nom = st.text_input("Nom :")
            new_freq = st.selectbox(
                "Fréquence hebdomadaire :",
                ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Quotidien"]
            )
            new_goal = st.text_area(
                "Objectif principal :",
                placeholder="Ex: Débloquer le Front Lever & séries de Dips à +30kg"
            )

            if st.form_submit_button("✅ Enregistrer l'athlète", type="primary", use_container_width=True):
                if new_nom.strip() and new_prenom.strip():
                    full_name = f"{new_prenom.strip()} {new_nom.strip()}"
                    st.session_state.db["students"][full_name] = {
                        "freq": new_freq,
                        "goal": new_goal.strip() if new_goal.strip() else "Objectif général",
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    save_db(st.session_state.db)
                    st.success(f"{full_name} inscrit avec succès !")
                    time.sleep(0.4)
                    st.rerun()
                else:
                    st.warning("Veuillez renseigner le nom et le prénom.")

    students = st.session_state.db.get("students", {})
    if not students:
        st.info("Aucun athlète dans la base.")
        return

    search_s = ""
    if len(students) > 3:
        search_s = st.text_input("🔍 Rechercher un athlète :", placeholder="Nom ou prénom...", key="search_athletes_input").strip().lower()

    evals = st.session_state.db.get("evaluations", [])

    matched_items = [
        (name, details)
        for name, details in list(students.items())
        if not search_s or search_s in name.lower()
    ]

    if not matched_items:
        st.caption("Aucun athlète ne correspond à cette recherche.")
        return

    for name, details in matched_items:
        student_evals = [e for e in evals if e.get("student") == name]
        avg_tst = (sum(e.get("tst", 0) for e in student_evals) / len(student_evals)) if student_evals else 0.0
        avg_rpe = (sum(e.get("rpe", 0) for e in student_evals) / len(student_evals)) if student_evals else 0.0
        safe_name = html.escape(str(name))
        safe_freq = html.escape(str(details.get("freq", "Non précisée")))
        safe_goal = html.escape(str(details.get("goal", "Aucun objectif spécifié")))
        clean_k = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).lower()).strip("_")

        render_html(f"""
            <div class="cali-card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                    <h4 style="margin:0; font-size:1.05rem; font-weight:800; color:#F8FAFC;">👤 {safe_name}</h4>
                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                        <span class="badge-lime">{len(student_evals)} Séances</span>
                        <span class="badge-cyan">TST moy: {avg_tst:.1f}s</span>
                        <span class="badge-amber">RPE: {avg_rpe:.1f}</span>
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

        c_ed, c_del = st.columns([2, 1])
        with c_ed:
            with st.expander(f"✏️ Modifier fiche ({name})", expanded=False):
                with st.form(f"edit_stud_form_{clean_k}"):
                    freq_opts = ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Quotidien"]
                    cur_f = details.get("freq", "4x / semaine")
                    f_idx = freq_opts.index(cur_f) if cur_f in freq_opts else 2
                    upd_freq = st.selectbox("Fréquence :", freq_opts, index=f_idx)
                    upd_goal = st.text_input("Objectif :", value=details.get("goal", ""))
                    if st.form_submit_button("💾 Enregistrer", use_container_width=True):
                        st.session_state.db["students"][name]["freq"] = upd_freq
                        st.session_state.db["students"][name]["goal"] = upd_goal.strip() or "Objectif général"
                        save_db(st.session_state.db)
                        st.toast(f"✅ Fiche de {name} mise à jour")
                        time.sleep(0.25)
                        st.rerun()
        with c_del:
            if st.button("🗑️ Supprimer", key=f"del_stud_{clean_k}", use_container_width=True):
                del st.session_state.db["students"][name]
                save_db(st.session_state.db)
                st.toast(f"Athlète {name} supprimé.")
                time.sleep(0.3)
                st.rerun()
