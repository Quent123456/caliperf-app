"""
ui/tab_studio.py - Compartiment 1 : Studio Vidéo en flux RAM sécurisé, Chrono TST,
Analyse de Dérive Intra-Série & Pont direct vers training_logs SQL.
"""

import time
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.auth import normalize_role
from core.calibration import (
    VALID_CAMERA_VIEWS,
    compute_active_feature_vectors,
    load_baselines_table,
    save_calibrated_slot,
)
from core.database import (
    create_training_log,
    detect_student_and_exercise,
    get_coach_athletes,
    get_gemini_api_key,
    set_active_athlete_in_session,
)
from core.load_quantification import compute_set_load_bundle
from core.quality_control import evaluate_calibration_quality
from core.video_io import temporary_video_file
from ui.calibration_qc import render_qc_save_gate, render_quality_diagnostic_card
from ui.theme import render_html


def _ensure_stopwatch_entry(filename: str) -> dict:
    """Initialise ou retourne l'état du chronomètre et de pré-remplissage pour une vidéo."""
    if filename not in st.session_state.stopwatches:
        st.session_state.stopwatches[filename] = {
            "tst_val": 0.0,
            "in_marker": 0.0,
            "out_marker": 0.0,
            "running": False,
            "start_time": 0.0,
            "rpe": 7.5,
            "reps": 0,
            "added_load_kg": 0.0,
            "exo_type": "isometric",
        }
    return st.session_state.stopwatches[filename]


def _render_live_stopwatch_display(sw: dict) -> None:
    """Affiche le chronomètre digital 60fps sans dérive lors du défilement."""
    if sw["running"]:
        elapsed_now = max(0.0, float(sw["tst_val"]) + (time.time() - float(sw["start_time"])))
        components.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@700&family=JetBrains+Mono:wght@800&display=swap" rel="stylesheet">
        <style>
            html, body {{
                margin: 0; padding: 0; background: transparent;
                font-family: 'Plus Jakarta Sans', sans-serif;
                overflow: hidden;
            }}
            .wrap {{ text-align: center; padding: 2px 0; }}
            .sub {{
                font-size: 11px; color: #34D399; font-weight: 700;
                letter-spacing: 0.08em; text-transform: uppercase;
                display: inline-flex; align-items: center; gap: 6px;
            }}
            .dot {{
                width: 8px; height: 8px; border-radius: 50%; background: #10B981;
                box-shadow: 0 0 8px #10B981; animation: pulse 1s infinite ease-in-out;
            }}
            @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
            .timer {{
                font-family: 'JetBrains Mono', monospace;
                font-variant-numeric: tabular-nums;
                font-size: 42px; font-weight: 800; color: #10B981;
                text-shadow: 0 0 20px rgba(16, 185, 129, 0.45);
                line-height: 1.1; margin-top: 2px;
            }}
            .unit {{ font-size: 19px; color: #94A3B8; margin-left: 2px; }}
        </style>
        </head>
        <body>
            <div class="wrap">
                <div class="sub"><span class="dot"></span> CHRONO EN COURS</div>
                <div class="timer"><span id="val">{elapsed_now:.2f}</span><span class="unit">s</span></div>
            </div>
            <script>
                var baseVal = {elapsed_now:.4f};
                var t0 = performance.now();
                var el = document.getElementById('val');
                function tick() {{
                    var cur = baseVal + (performance.now() - t0) / 1000.0;
                    el.textContent = cur.toFixed(2);
                    requestAnimationFrame(tick);
                }}
                requestAnimationFrame(tick);
            </script>
        </body>
        </html>
        """, height=76)
    else:
        disp_tst = float(sw["tst_val"])
        render_html(f"""
            <div style="text-align: center; padding: 0.1rem 0 0.35rem 0;">
                <span class="digital-sub">TEMPS SOUS TENSION (TST)</span>
                <div class="digital-timer">{disp_tst:.2f}<span style="font-size:1.25rem; color:#94A3B8; margin-left:3px;">s</span></div>
            </div>
        """)


def _get_dynamic_exercise_choices(user) -> list:
    """Construit la liste des exercices forçables depuis baselines_3d SQL scopée."""
    choices = [("auto", "Auto (1-NN 3D)")]
    seen = set()
    try:
        df_b = load_baselines_table(user=user)
        if not df_b.empty and "exercise" in df_b.columns:
            calib_df = df_b[df_b["status"] == "calibrated"] if "status" in df_b.columns else df_b
            target_df = calib_df if not calib_df.empty else df_b
            for ex in target_df["exercise"].unique():
                clean_ex = str(ex).strip()
                if clean_ex and clean_ex.lower() not in seen:
                    seen.add(clean_ex.lower())
                    choices.append((clean_ex, clean_ex))
    except Exception:
        pass

    fallbacks = [
        "Full Planche", "Straddle Planche", "Maltese",
        "Front Lever", "Back Lever", "Tractions", "Dips", "Pompes", "Hefesto"
    ]
    for fb in fallbacks:
        if fb.lower() not in seen:
            seen.add(fb.lower())
            choices.append((fb, fb))

    return choices


def _render_intra_set_fatigue_panel(bio_r: dict, current_fname: str) -> None:
    """Affiche l'analyse de dérive technique intra-série (Δθ ou perte de vélocité %)."""
    fatigue = bio_r.get("fatigue") or {}
    if not fatigue.get("available"):
        return

    with st.expander("🔋 Dérive Technique Intra-Série & Fatigue", expanded=True):
        if fatigue.get("type") == "isometric":
            sh_d = fatigue.get("shoulder_drift_deg", 0.0)
            hip_d = fatigue.get("hip_drift_deg", 0.0)
            trunk_d = fatigue.get("trunk_drift_deg", 0.0)
            c1, c2, c3 = st.columns(3)
            c1.metric("Δθ Épaule", f"{sh_d:+.1f}°")
            c2.metric("Δθ Hanche", f"{hip_d:+.1f}°")
            c3.metric("Δθ Tronc", f"{trunk_d:+.1f}°")

            series = fatigue.get("per_second_series", [])
            if series:
                try:
                    import plotly.graph_objects as go
                    df_sec = pd.DataFrame(series)
                    fig_f = go.Figure()
                    fig_f.add_trace(go.Scatter(x=df_sec["label"], y=df_sec["shoulder_flexion"], mode="lines+markers", name="Épaule (°)", line=dict(color="#00E5FF", width=2.4)))
                    fig_f.add_trace(go.Scatter(x=df_sec["label"], y=df_sec["hip_angle"], mode="lines+markers", name="Hanche (°)", line=dict(color="#10B981", width=2.2)))
                    fig_f.add_trace(go.Scatter(x=df_sec["label"], y=df_sec["trunk_inclination"], mode="lines+markers", name="Tronc (°)", line=dict(color="#F59E0B", width=2.0)))
                    fig_f.update_layout(
                        title="Évolution angulaire seconde par seconde",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(13,18,30,0.65)",
                        font=dict(color="#F8FAFC"),
                        height=230,
                        margin=dict(l=14, r=14, t=34, b=24),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig_f, use_container_width=True, key=f"fatigue_iso_chart_{current_fname}")
                except ImportError:
                    pass
        else:
            loss_pct = float(fatigue.get("velocity_loss_pct", 0.0) or 0.0)
            st.metric("Perte de vélocité (Rep 1 → Dernière Rep)", f"{loss_pct:.1f}%", fatigue.get("failure_proximity_label", ""))
            rep_vels = fatigue.get("rep_velocities", [])
            if rep_vels:
                try:
                    import plotly.express as px
                    df_rv = pd.DataFrame(rep_vels)
                    fig_v = px.bar(
                        df_rv,
                        x="rep_number",
                        y="mean_angular_vel_dps",
                        text="mean_angular_vel_dps",
                        color_discrete_sequence=["#00E5FF"],
                        labels={"rep_number": "Répétition #", "mean_angular_vel_dps": "Vitesse moyenne (°/s)"},
                        template="plotly_dark",
                    )
                    fig_v.update_layout(
                        title="Vitesse angulaire moyenne par répétition",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(13,18,30,0.65)",
                        height=220,
                        margin=dict(l=14, r=14, t=34, b=24),
                    )
                    st.plotly_chart(fig_v, use_container_width=True, key=f"fatigue_dyn_chart_{current_fname}")
                except ImportError:
                    pass


def render_tab_studio() -> None:
    """Rend le Studio Vidéo complet (streaming RAM, Auto-Track 3D, Fatigue, Charge & SQL)."""
    curr_u = st.session_state.get("current_user")
    if not curr_u:
        return

    u_id = int(curr_u["id"])
    u_role = normalize_role(curr_u.get("role", "athlete"))
    active_profile = st.session_state.get("active_athlete_profile") or curr_u

    if u_role == "coach":
        profile_map = st.session_state.get("selectable_profiles_map")
        opt_ids_top = st.session_state.get("selectable_profile_ids")
        if not profile_map or not opt_ids_top:
            coach_athletes = get_coach_athletes(u_id)
            selectable = [curr_u] + coach_athletes
            profile_map = {int(p["id"]): p for p in selectable}
            opt_ids_top = [int(p["id"]) for p in selectable]
        else:
            selectable = [profile_map[pid] for pid in opt_ids_top]

        def _on_studio_ath_change() -> None:
            chosen = st.session_state.get("studio_athlete_select")
            if chosen is not None:
                set_active_athlete_in_session(int(chosen), sync_widgets=True)

        sel_top_id = st.selectbox(
            "🎯 Athlète suivi (enregistrement SQL) :",
            options=opt_ids_top,
            format_func=lambda pid: (
                f"🏋️ Moi-même ({profile_map[pid]['full_name']})"
                if pid == u_id else
                f"🤸 {profile_map[pid]['full_name']} ({profile_map[pid]['bodyweight_kg']:.0f} kg)"
            ),
            key="studio_athlete_select",
            on_change=_on_studio_ath_change,
        )
        active_profile = profile_map[int(sel_top_id)]
        st.session_state["active_athlete_profile"] = active_profile
    else:
        selectable = [curr_u]
        profile_map = {u_id: curr_u}

    with st.expander("📁 Importer des vidéos (Flux sécurisé jusqu'à 10 fichiers)", expanded=not bool(st.session_state.get("active_uploaded_files"))):
        uploaded_files = st.file_uploader(
            "Importer les vidéos (.mp4, .mov, .avi)",
            type=["mp4", "mov", "avi"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )
        if st.session_state.get("active_uploaded_files"):
            if st.button("🧹 Vider la file de vidéos", key="btn_clear_studio_queue", use_container_width=True):
                st.session_state.active_uploaded_files = []
                st.session_state.batch_results = []
                st.session_state.active_video_idx = 0
                st.rerun()

    if uploaded_files:
        if len(uploaded_files) > 10:
            st.warning("⚠️ Lot limité à 10 vidéos simultanées pour préserver la RAM Cloud : les 10 premières ont été retenues.")
            uploaded_files = uploaded_files[:10]
        st.session_state.active_uploaded_files = uploaded_files
    else:
        uploaded_files = st.session_state.get("active_uploaded_files", [])

    if not uploaded_files:
        render_html("""
            <div class="cali-card-accent" style="text-align:center; padding: 2.2rem 1.2rem; margin-top: 0.35rem;">
                <div style="font-size: 2.3rem; margin-bottom: 0.4rem;">🎬</div>
                <h3 style="margin: 0 0 0.35rem 0; font-size: 1.18rem; color:#F8FAFC;">Studio Vidéo Prêt</h3>
                <p style="color:#94A3B8; font-size: 0.88rem; max-width: 450px; margin: 0 auto; line-height:1.5;">
                    Chargez une ou plusieurs vidéos (traitement flux RAM sécurisé) pour lancer l'Auto-Track 3D, mesurer la fatigue intra-série et logger la charge en SQL.<br>
                    <small style="color:#00E5FF; font-weight:600;">Astuce : glissez latéralement pour naviguer entre les onglets 👉</small>
                </p>
            </div>
        """)
        return

    files_dict = {f.name: f for f in uploaded_files}
    file_names = list(files_dict.keys())
    total_files = len(file_names)
    athlete_names = [str(p["full_name"]) for p in selectable]

    # ------------------------------------------------------------------
    # BANDEAU BATCH EN FLUX STREAMING (CHAMPS RAM STRICTS)
    # ------------------------------------------------------------------
    render_html(f"""
        <div class="cali-card" style="padding: 12px 15px; margin-bottom: 0.65rem; border-color: rgba(0, 229, 255, 0.25);">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <div>
                    <span style="font-size:0.86rem; font-weight:800; color:#00E5FF; text-transform:uppercase; letter-spacing:0.04em;">
                        ⚡ Auto-Analyse 3D ({total_files} vidéo{'s' if total_files > 1 else ''})
                    </span>
                    <div style="color:#94A3B8; font-size:0.76rem; margin-top:2px;">
                        Traitement flux frame-par-frame + suppression immédiate des temporaires (RAM &lt; 1 Go).
                    </div>
                </div>
                <span class="badge-cyan">{len([n for n in file_names if n in st.session_state.processed_videos])}/{total_files} traitée(s)</span>
            </div>
        </div>
    """)

    col_b_run, col_b_info = st.columns([1.45, 1])
    with col_b_run:
        lbl_btn = f"🚀 Lancer l'Auto-Analyse 3D du Lot ({total_files} vidéos)" if total_files > 1 else "🚀 Lancer l'Auto-Analyse 3D"
        if st.button(lbl_btn, key="btn_run_batch_all", type="primary", use_container_width=True):
            p_bar = st.progress(0.0)
            p_txt = st.empty()

            def _b_cb(frac, msg):
                p_bar.progress(frac)
                p_txt.caption(msg)

            with st.spinner("Analyse cinématique 3D en flux sécurisé..."):
                try:
                    from core.rep_counter import process_uploaded_batch_streaming
                    batch_res = process_uploaded_batch_streaming(uploaded_files, user=curr_u, progress_callback=_b_cb)
                    st.session_state.batch_results = batch_res

                    for r in batch_res:
                        fn = r["filename"]
                        sw_entry = _ensure_stopwatch_entry(fn)
                        sw_entry["tst_val"] = float(r["tut"])
                        sw_entry["reps"] = int(r["reps"])
                        sw_entry["detected_exo"] = r["exercise_display"]
                        sw_entry["exo_type"] = r.get("type", "isometric")
                        st.session_state.biomech_results[fn] = r
                        st.session_state.processed_videos.add(fn)

                    st.toast(f"✅ {total_files} vidéo(s) analysée(s) et fichiers temporaires nettoyés !")
                    time.sleep(0.2)
                    st.rerun()
                except Exception as err_batch:
                    st.error(f"Erreur durant l'analyse par lot : {err_batch}")

    with col_b_info:
        if st.button("⚡ Analyser la vidéo active", key="btn_run_cur_single", use_container_width=True):
            with st.spinner("Analyse cinématique 3D en flux sécurisé..."):
                try:
                    from core.rep_counter import analyze_single_video_pipeline
                    active_f = files_dict[file_names[min(st.session_state.active_video_idx, total_files - 1)]]
                    with temporary_video_file(active_f) as cur_temp_path:
                        res = analyze_single_video_pipeline(cur_temp_path, user=curr_u)
                    res["filename"] = active_f.name
                    fn = res["filename"]
                    sw_entry = _ensure_stopwatch_entry(fn)
                    sw_entry["tst_val"] = float(res["tut"])
                    sw_entry["reps"] = int(res["reps"])
                    sw_entry["detected_exo"] = res["exercise_display"]
                    sw_entry["exo_type"] = res.get("type", "isometric")
                    st.session_state.biomech_results[fn] = res
                    st.session_state.processed_videos.add(fn)
                    st.toast(f"✅ {res['exercise_display']} : TUT = {res['tut']}s | {res['reps']} reps")
                    time.sleep(0.2)
                    st.rerun()
                except Exception as err_single:
                    st.error(f"Erreur d'analyse : {err_single}")

    # Pont Batch -> Validation & Enregistrement SQL training_logs
    if st.session_state.get("batch_results"):
        with st.expander(f"📋 Récapitulatif du lot & Enregistrement SQL ({len(st.session_state.batch_results)} vidéos)", expanded=True):
            batch_rows = []
            for b in st.session_state.batch_results:
                fat = b.get("fatigue") or {}
                fat_str = (
                    f"Δ {fat.get('fatigue_drift_deg', 0.0):.1f}°"
                    if b.get("type") == "isometric" and fat.get("available") else
                    (f"-{fat.get('velocity_loss_pct', 0.0):.1f}% v" if fat.get("available") else "—")
                )
                batch_rows.append({
                    "Fichier": b["filename"],
                    "Exercice": b["exercise_display"],
                    "Type": "Isométrique" if b["type"] == "isometric" else "Dynamique",
                    "TUT (s)": b["tut"],
                    "Reps": b["reps"],
                    "Fatigue": fat_str,
                    "Statut": b["status"],
                })
            st.dataframe(pd.DataFrame(batch_rows), use_container_width=True, hide_index=True)

            with st.form("form_save_batch_training_logs"):
                cb1, cb2, cb3 = st.columns([1.4, 1.0, 1.0])
                with cb1:
                    b_ath_id = st.selectbox(
                        "Athlète cible :",
                        options=[int(p["id"]) for p in selectable],
                        index=[int(p["id"]) for p in selectable].index(int(active_profile["id"])) if int(active_profile["id"]) in profile_map else 0,
                        format_func=lambda pid: profile_map[pid]["full_name"],
                    )
                with cb2:
                    b_lest = st.number_input("Lest additionnel (kg) :", min_value=0.0, max_value=200.0, value=0.0, step=1.25)
                with cb3:
                    b_rpe = st.slider("RPE moyen du lot :", min_value=1.0, max_value=10.0, value=7.5, step=0.5)

                if st.form_submit_button("💾 Enregistrer tout le lot dans training_logs (SQL)", type="primary", use_container_width=True):
                    target_ath = profile_map[int(b_ath_id)]
                    bw_val = float(target_ath.get("bodyweight_kg", 70.0) or 70.0)
                    coach_ref = u_id if u_role == "coach" else target_ath.get("coach_id")
                    for b in st.session_state.batch_results:
                        exo_nm = b["exercise_display"]
                        exo_tp = b.get("type", "isometric")
                        bundle = compute_set_load_bundle(
                            exercise=exo_nm,
                            exo_type=exo_tp,
                            tut_effective_sec=float(b["tut"]),
                            reps=int(b["reps"]),
                            added_load_kg=b_lest,
                            bodyweight_kg=bw_val,
                            rpe=b_rpe,
                        )
                        fat = b.get("fatigue") or {}
                        create_training_log(
                            athlete_id=int(b_ath_id),
                            coach_id=coach_ref,
                            exercise=exo_nm,
                            exercise_type=exo_tp,
                            reps=int(b["reps"]),
                            tut_effective_sec=float(b["tut"]),
                            added_load_kg=b_lest,
                            bodyweight_kg=bw_val,
                            difficulty_coef=bundle["difficulty_coef"],
                            external_load_au=bundle["external_load_au"],
                            rpe=b_rpe,
                            srpe_load=bundle["srpe_load"],
                            fatigue_drift_deg=fat.get("fatigue_drift_deg"),
                            velocity_loss_pct=fat.get("velocity_loss_pct"),
                            notes=f"Batch 3D ({b['filename']})",
                        )
                        st.session_state.processed_videos.add(b["filename"])
                    st.success(f"✅ {len(st.session_state.batch_results)} série(s) enregistrée(s) dans SQL training_logs pour {target_ath['full_name']} !")
                    time.sleep(0.35)
                    st.rerun()

    # ------------------------------------------------------------------
    # NAVIGATION DANS LA FILE VIDÉO
    # ------------------------------------------------------------------
    cur_idx = min(st.session_state.active_video_idx, total_files - 1)
    st.session_state.active_video_idx = cur_idx
    current_fname = file_names[cur_idx]
    current_file = files_dict[current_fname]

    col_prev, col_status, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("◀️ Préc.", key="btn_prev_vid", use_container_width=True, disabled=(cur_idx == 0)):
            st.session_state.active_video_idx = max(0, cur_idx - 1)
            st.rerun()
    with col_status:
        is_analyzed = current_fname in st.session_state.processed_videos
        badge_type = "badge-lime" if is_analyzed else "badge-amber"
        status_text = "✅ Validée" if is_analyzed else "⏳ En attente"
        render_html(f"""
            <div style="text-align:center; padding-top: 2px;">
                <span style="font-size: 0.84rem; font-weight:700; color:#F8FAFC;">Vidéo {cur_idx + 1} / {total_files}</span>
                <div style="margin-top:3px;"><span class="{badge_type}">{status_text}</span></div>
            </div>
        """)
    with col_next:
        if st.button("Suiv. ▶️", key="btn_next_vid", use_container_width=True, disabled=(cur_idx >= total_files - 1)):
            st.session_state.active_video_idx = min(total_files - 1, cur_idx + 1)
            st.rerun()

    auto_student_name, auto_exo = detect_student_and_exercise(current_fname, athlete_names)
    sw = _ensure_stopwatch_entry(current_fname)

    col_video, col_tools = st.columns([1.45, 1.2], gap="medium")

    with col_video:
        st.video(current_file)

        with st.expander("🤖 Auto-Track 3D Local : Détection Mouvement, Reps & Fatigue", expanded=True):
            exo_choices = _get_dynamic_exercise_choices(curr_u)
            col_tol1, col_tol2 = st.columns([1.4, 1.1])
            with col_tol1:
                custom_tol = st.slider("Tolérance angulaire (±°)", min_value=8.0, max_value=25.0, value=15.0, step=1.0, key=f"tol_slider_{current_fname}")
            with col_tol2:
                forced_opt = st.selectbox(
                    "Forcer l'exercice :",
                    exo_choices,
                    format_func=lambda x: x[1],
                    key=f"forced_exo_{current_fname}"
                )

            if st.button("✨ Lancer l'Auto-Track 3D Rapide", key=f"ai_track_{current_fname}", use_container_width=True, type="primary"):
                with st.spinner("Analyse cinématique 3D en flux sécurisé..."):
                    try:
                        from core.rep_counter import analyze_single_video_pipeline
                        forced_key = None if forced_opt[0] == "auto" else forced_opt[0]
                        with temporary_video_file(current_file) as cur_temp:
                            res = analyze_single_video_pipeline(
                                cur_temp,
                                forced_exercise=forced_key,
                                custom_tolerance=custom_tol,
                                user=curr_u,
                            )
                        res["filename"] = current_fname
                        sw["tst_val"] = float(res["tut"])
                        sw["reps"] = int(res["reps"])
                        sw["detected_exo"] = res["exercise_display"]
                        sw["exo_type"] = res.get("type", "isometric")
                        st.session_state.biomech_results[current_fname] = res
                        st.session_state.processed_videos.add(current_fname)
                        st.success(f"✅ {res['exercise_display']} ({res.get('camera_view', 'Profil')}) | TUT = {sw['tst_val']}s | Reps = {sw['reps']}")
                        time.sleep(0.2)
                        st.rerun()
                    except Exception as err_track:
                        st.error(f"Erreur Auto-Track 3D : {err_track}")

            gem_key = get_gemini_api_key()
            if gem_key:
                if st.button("🧠 Analyse IA Gemini Vision (Secours)", key=f"gemini_fb_{current_fname}", use_container_width=True):
                    with st.spinner("Analyse Gemini Flash Vision..."):
                        from services.gemini_vision import analyze_motion_gemini
                        with temporary_video_file(current_file) as cur_temp:
                            g_data, _, g_msg = analyze_motion_gemini(cur_temp, gem_key)
                        if g_data:
                            sw["tst_val"] = float(g_data.get("tut", 0.0))
                            sw["reps"] = int(g_data.get("reps", 0))
                            sw["detected_exo"] = g_data.get("exercise_display", auto_exo)
                            sw["exo_type"] = g_data.get("type", "isometric")
                            st.toast(f"🧠 Gemini : {sw['detected_exo']} | TUT={sw['tst_val']}s | {sw['reps']} reps")
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.warning(g_msg)

        # Courbes Plotly, Dérive Fatigue Intra-Série & Enrichissement Baselines_3D (avec QC Gate)
        if current_fname in st.session_state.biomech_results:
            bio_r = st.session_state.biomech_results[current_fname]
            _render_intra_set_fatigue_panel(bio_r, current_fname)

            kin = bio_r.get("kinematics")
            ev = bio_r.get("evaluation") or {}
            seg = bio_r.get("segmentation") or {}
            effort_w = seg.get("effort_window") or {}

            with st.expander(f"📈 Diagnostic 3D & Sauvegarde Baseline ({bio_r.get('exercise_display', 'Exercice')})", expanded=False):
                try:
                    import plotly.graph_objects as go
                    has_plotly = True
                except ImportError:
                    has_plotly = False
                if kin and has_plotly:
                    t_ser = kin["timestamps"]
                    filt_features = kin.get("features_filtered") or {}
                    is_iso = bio_r.get("type") == "isometric"

                    fig_3d = go.Figure()
                    if "elbow_angle" in filt_features:
                        fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["elbow_angle"], mode="lines", name="Coude 3D (°)", line=dict(color="#00E5FF", width=2.5)))
                    if "shoulder_flexion" in filt_features:
                        fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["shoulder_flexion"], mode="lines", name="Épaule 3D (°)", line=dict(color="#F59E0B", width=2.0)))
                    if "trunk_inclination" in filt_features:
                        fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["trunk_inclination"], mode="lines", name="Inclinaison Tronc (°)", line=dict(color="#10B981", width=1.8, dash="dot")))

                    if is_iso:
                        for hb in ev.get("hold_blocks", []):
                            fig_3d.add_vrect(x0=hb["start_time"], x1=hb["end_time"], fillcolor="rgba(16,185,129,0.2)", layer="below", line_width=0)
                    else:
                        for rep in ev.get("reps_details", []):
                            fig_3d.add_vrect(x0=rep["start_time"], x1=rep["end_time"], fillcolor="rgba(0,229,255,0.15)", layer="below", line_width=0)

                    fig_3d.update_layout(
                        title="Cinématique Articulaire 3D (°)",
                        xaxis_title="Temps (s)",
                        yaxis_title="Degrés (°)",
                        paper_bgcolor="rgba(13,18,30,0.6)",
                        plot_bgcolor="rgba(13,18,30,0.6)",
                        font=dict(color="#F8FAFC"),
                        margin=dict(l=24, r=16, t=35, b=30),
                        height=250,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig_3d, use_container_width=True)

                    if u_role == "coach" and kin and seg and "effort_window" in seg:
                        render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin:8px 0;'>")
                        render_html("<b>➕ Enregistrer ce calibrage dans Baselines_3D (SQL) :</b>")
                        user_cam_view = st.selectbox("Angle de vue :", VALID_CAMERA_VIEWS, key=f"sel_cam_add_{current_fname}")
                        exo_lbl = bio_r.get("exercise_display", "Figure")
                        exo_tp = bio_r.get("type", "isometric")
                        qc_studio = evaluate_calibration_quality(
                            kinematics=kin,
                            segmentation=seg,
                            camera_view=user_cam_view,
                            exo_type=exo_tp,
                            exercise_name=exo_lbl,
                        )
                        render_quality_diagnostic_card(qc_studio, compact=True)
                        clicked_b, qc_ack_b = render_qc_save_gate(
                            report=qc_studio,
                            save_button_key=f"btn_add_to_base_{current_fname}",
                            confirm_checkbox_key=f"chk_studio_qc_{current_fname}_{user_cam_view}",
                            button_label="💾 Enregistrer dans Baselines_3D",
                        )
                        if clicked_b:
                            means_v, stds_v = compute_active_feature_vectors(kin, effort_w)
                            ok_b, msg_b = save_calibrated_slot(
                                exercise_name=exo_lbl,
                                camera_view=user_cam_view,
                                exo_type=exo_tp,
                                mean_features=means_v.tolist(),
                                std_features=stds_v.tolist(),
                                user=curr_u,
                                is_shared=False,
                                quality_report=qc_studio,
                                qc_confirmed_warning=qc_ack_b,
                            )
                            if ok_b:
                                st.success(f"✅ {exo_lbl} ({user_cam_view}) calibré en SQL !")
                                time.sleep(0.3)
                                st.rerun()
                            else:
                                st.error(msg_b)

    with col_tools:
        with st.container(border=True):
            _render_live_stopwatch_display(sw)

            c_run, c_raz = st.columns([1.55, 1])
            with c_run:
                is_run = sw["running"]
                if st.button("⏸️ PAUSE" if is_run else "▶️ DÉMARRER", key=f"btn_run_{current_fname}", type="secondary" if is_run else "primary", use_container_width=True):
                    if sw["running"]:
                        sw["tst_val"] += time.time() - sw["start_time"]
                        sw["running"] = False
                    else:
                        sw["start_time"] = time.time()
                        sw["running"] = True
                    st.rerun()
            with c_raz:
                if st.button("🔄 RAZ", key=f"btn_raz_{current_fname}", use_container_width=True):
                    sw["tst_val"] = 0.0
                    sw["running"] = False
                    st.rerun()

            c_a1, c_a2, c_a3, c_a4 = st.columns(4)
            with c_a1:
                if st.button("-1s", key=f"m1_{current_fname}", use_container_width=True):
                    sw["tst_val"] = max(0.0, sw["tst_val"] - 1.0)
                    st.rerun()
            with c_a2:
                if st.button("+0.5s", key=f"p05_{current_fname}", use_container_width=True):
                    sw["tst_val"] += 0.5
                    st.rerun()
            with c_a3:
                if st.button("+1s", key=f"p1_{current_fname}", use_container_width=True):
                    sw["tst_val"] += 1.0
                    st.rerun()
            with c_a4:
                if st.button("+5s", key=f"p5_{current_fname}", use_container_width=True):
                    sw["tst_val"] += 5.0
                    st.rerun()

            render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin: 0.55rem 0;'>")
            render_html("<b style='font-size:0.86rem;color:#00E5FF;'>⚡ Pont Vidéo → Quantification de Charge SQL</b>")

            bio_cur = st.session_state.biomech_results.get(current_fname, {})
            fat_cur = bio_cur.get("fatigue") or {}

            # Sélecteur athlète pré-rempli (sidebar ou détecté dans nom de fichier)
            default_aid = int(active_profile["id"])
            if auto_student_name:
                for p in selectable:
                    if p["full_name"] == auto_student_name:
                        default_aid = int(p["id"])
                        break
            opt_ids = [int(p["id"]) for p in selectable]

            with st.form(key=f"eval_form_{current_fname}"):
                sel_aid = st.selectbox(
                    "👤 Athlète :",
                    options=opt_ids,
                    index=opt_ids.index(default_aid) if default_aid in opt_ids else 0,
                    format_func=lambda pid: profile_map[pid]["full_name"],
                )
                target_ath_obj = profile_map[int(sel_aid)]

                c_ex1, c_ex2 = st.columns([1.4, 1.0])
                with c_ex1:
                    val_exo = st.text_input("🏋️ Exercice :", value=str(sw.get("detected_exo", auto_exo)))
                with c_ex2:
                    cur_tp = str(bio_cur.get("type", sw.get("exo_type", "isometric")))
                    val_type = st.selectbox("Type :", ["isometric", "dynamic"], index=1 if cur_tp == "dynamic" else 0, format_func=lambda x: "Isométrique" if x == "isometric" else "Dynamique")

                c_num1, c_num2, c_num3 = st.columns(3)
                with c_num1:
                    val_tut = st.number_input("TUT actif (s) :", min_value=0.0, max_value=3600.0, value=round(float(sw.get("tst_val", 0.0)), 2), step=0.5)
                with c_num2:
                    val_reps = st.number_input("Répétitions :", min_value=0, max_value=200, value=int(sw.get("reps", 0)), step=1)
                with c_num3:
                    val_lest = st.number_input("Lest (kg) :", min_value=0.0, max_value=200.0, value=float(sw.get("added_load_kg", 0.0)), step=1.25)

                bw_ref = float(target_ath_obj.get("bodyweight_kg", 70.0) or 70.0)
                rpe_score = st.slider(f"🔥 RPE de série (1–10) • PDC {bw_ref:.0f} kg :", min_value=1.0, max_value=10.0, value=float(sw.get("rpe", 7.5)), step=0.5)

                preview_bundle = compute_set_load_bundle(
                    exercise=val_exo,
                    exo_type=val_type,
                    tut_effective_sec=val_tut,
                    reps=val_reps,
                    added_load_kg=val_lest,
                    bodyweight_kg=bw_ref,
                    rpe=rpe_score,
                )

                render_html(f"""
                    <div style="background:rgba(0,229,255,0.08);border:1px solid rgba(0,229,255,0.25);border-radius:10px;padding:8px 10px;margin:4px 0 8px 0;font-size:0.78rem;display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;">
                        <span>⚡ Charge externe : <b style="color:#00E5FF;font-family:'JetBrains Mono',monospace;">{preview_bundle['external_load_au']:.1f} UA</b></span>
                        <span>🔥 sRPE : <b style="color:#FBBF24;font-family:'JetBrains Mono',monospace;">{preview_bundle['srpe_load']:.1f}</b></span>
                    </div>
                """)

                coach_notes = st.text_input("💬 Notes / Consignes :", placeholder="Ex: Verrouillage strict, bon tempo")
                submit_eval = st.form_submit_button("💾 VALIDER & LOGGER EN SQL", type="primary", use_container_width=True)

                if submit_eval:
                    if sw["running"]:
                        val_tut = round(val_tut + (time.time() - float(sw["start_time"])), 2)
                        sw["running"] = False

                    if val_tut <= 0 and val_reps <= 0:
                        st.warning("⚠️ Indiquez un TUT > 0 s ou au moins 1 répétition.")
                    else:
                        sw["tst_val"] = float(val_tut)
                        sw["reps"] = int(val_reps)
                        sw["added_load_kg"] = float(val_lest)
                        sw["rpe"] = float(rpe_score)

                        final_bundle = compute_set_load_bundle(
                            exercise=val_exo,
                            exo_type=val_type,
                            tut_effective_sec=val_tut,
                            reps=val_reps,
                            added_load_kg=val_lest,
                            bodyweight_kg=bw_ref,
                            rpe=rpe_score,
                        )
                        coach_ref = u_id if u_role == "coach" else target_ath_obj.get("coach_id")

                        create_training_log(
                            athlete_id=int(sel_aid),
                            coach_id=coach_ref,
                            exercise=val_exo,
                            exercise_type=val_type,
                            reps=int(val_reps),
                            tut_effective_sec=float(val_tut),
                            added_load_kg=float(val_lest),
                            bodyweight_kg=bw_ref,
                            difficulty_coef=final_bundle["difficulty_coef"],
                            external_load_au=final_bundle["external_load_au"],
                            rpe=float(rpe_score),
                            srpe_load=final_bundle["srpe_load"],
                            fatigue_drift_deg=fat_cur.get("fatigue_drift_deg"),
                            velocity_loss_pct=fat_cur.get("velocity_loss_pct"),
                            notes=coach_notes or f"Vidéo: {current_fname}",
                        )
                        st.session_state.processed_videos.add(current_fname)
                        st.toast(f"✅ Log SQL enregistré : {target_ath_obj['full_name']} • {final_bundle['external_load_au']} UA")

                        if st.session_state.get("session_settings", {}).get("auto_advance", True) and cur_idx < total_files - 1:
                            st.session_state.active_video_idx += 1

                        time.sleep(0.35)
                        st.rerun()
