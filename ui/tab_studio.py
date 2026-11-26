"""
ui/tab_studio.py - Compartiment 1 : Studio Vidéo, Chrono Live TST & Auto-Track 3D.
"""

import time
from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.database import (
    save_db,
    get_gemini_api_key,
    get_persisted_temp_video_path,
    detect_student_and_exercise,
    dispatch_sync_evaluation
)
from core.calibration import (
    load_baselines_table,
    save_calibrated_slot,
    compute_active_feature_vectors,
    VALID_CAMERA_VIEWS
)
from ui.theme import render_html


def _ensure_stopwatch_entry(filename: str) -> dict:
    """Initialise ou retourne l'état du chronomètre pour une vidéo donnée."""
    if filename not in st.session_state.stopwatches:
        st.session_state.stopwatches[filename] = {
            "tst_val": 0.0,
            "in_marker": 0.0,
            "out_marker": 0.0,
            "running": False,
            "start_time": 0.0,
            "rpe": 7.5,
            "reps": 0
        }
    return st.session_state.stopwatches[filename]


def _render_live_stopwatch_display(sw: dict) -> None:
    """
    Affiche le chronomètre digital.
    Lorsqu'il tourne, utilise performance.now() côté client à partir du temps écoulé calculé côté serveur
    pour un affichage temps réel 60fps sans dérive d'horloge et sans rerun serveur.
    """
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


def _get_dynamic_exercise_choices() -> list:
    """Construit la liste des exercices forçables à partir de Baselines_3D + classiques."""
    choices = [("auto", "Auto (1-NN 3D)")]
    seen = set()
    try:
        df_b = load_baselines_table()
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
        "Front Lever", "Back Lever", "Tractions", "Dips", "Pompes"
    ]
    for fb in fallbacks:
        if fb.lower() not in seen:
            seen.add(fb.lower())
            choices.append((fb, fb))

    return choices


def render_tab_studio() -> None:
    """Rend le Studio Vidéo complet (Batch 3D, Auto-Track, Diagnostic Plotly, Chrono TST & RPE)."""
    with st.expander("📁 Importer des vidéos (Galerie Smartphone ou PC)", expanded=not bool(st.session_state.get("active_uploaded_files"))):
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
        st.session_state.active_uploaded_files = uploaded_files
    else:
        uploaded_files = st.session_state.get("active_uploaded_files", [])

    if not uploaded_files:
        render_html("""
            <div class="cali-card-accent" style="text-align:center; padding: 2.2rem 1.2rem; margin-top: 0.35rem;">
                <div style="font-size: 2.3rem; margin-bottom: 0.4rem;">🎬</div>
                <h3 style="margin: 0 0 0.35rem 0; font-size: 1.18rem; color:#F8FAFC;">Studio Vidéo Prêt</h3>
                <p style="color:#94A3B8; font-size: 0.88rem; max-width: 450px; margin: 0 auto; line-height:1.5;">
                    Chargez une ou plusieurs vidéos ci-dessus pour lancer l'Auto-Track 3D ou chronométrer le TST en temps réel.<br>
                    <small style="color:#00E5FF; font-weight:600;">Astuce : glissez latéralement pour naviguer entre les sections 👉</small>
                </p>
            </div>
        """)
        return

    files_dict = {f.name: f for f in uploaded_files}
    file_names = list(files_dict.keys())
    total_files = len(file_names)
    existing_students = list(st.session_state.db.get("students", {}).keys())

    # ------------------------------------------------------------------
    # BANDEAU BATCH PAR LOT 3D
    # ------------------------------------------------------------------
    render_html(f"""
        <div class="cali-card" style="padding: 12px 15px; margin-bottom: 0.65rem; border-color: rgba(0, 229, 255, 0.25);">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <div>
                    <span style="font-size:0.86rem; font-weight:800; color:#00E5FF; text-transform:uppercase; letter-spacing:0.04em;">
                        ⚡ Auto-Analyse 3D ({total_files} vidéo{'s' if total_files > 1 else ''})
                    </span>
                    <div style="color:#94A3B8; font-size:0.76rem; margin-top:2px;">
                        Traitement parallèle local : exercice 1-NN, TUT effectif et répétitions.
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

            all_temp_paths = [get_persisted_temp_video_path(f) for f in uploaded_files]
            with st.spinner("Analyse cinématique 3D locale en cours (< 2.5s / vidéo)..."):
                try:
                    from core.rep_counter import process_video_batch_parallel
                    batch_res = process_video_batch_parallel(all_temp_paths, api_key="", progress_callback=_b_cb)
                    st.session_state.batch_results = batch_res

                    for r in batch_res:
                        fn = r["filename"]
                        sw_entry = _ensure_stopwatch_entry(fn)
                        sw_entry["tst_val"] = float(r["tut"])
                        sw_entry["reps"] = int(r["reps"])
                        sw_entry["detected_exo"] = r["exercise_display"]
                        st.session_state.biomech_results[fn] = r
                        st.session_state.processed_videos.add(fn)

                    st.toast(f"✅ {total_files} vidéo(s) analysée(s) avec succès (Moteur 3D) !")
                    time.sleep(0.25)
                    st.rerun()
                except Exception as err_batch:
                    st.error(f"Erreur durant l'analyse par lot : {err_batch}")

    with col_b_info:
        if st.button("⚡ Analyser la vidéo active", key="btn_run_cur_single", use_container_width=True):
            with st.spinner("Analyse cinématique 3D locale en cours..."):
                try:
                    from core.rep_counter import analyze_single_video_pipeline
                    active_f = files_dict[file_names[min(st.session_state.active_video_idx, total_files - 1)]]
                    cur_temp_path = get_persisted_temp_video_path(active_f)
                    res = analyze_single_video_pipeline(cur_temp_path)
                    fn = res["filename"]
                    sw_entry = _ensure_stopwatch_entry(fn)
                    sw_entry["tst_val"] = float(res["tut"])
                    sw_entry["reps"] = int(res["reps"])
                    sw_entry["detected_exo"] = res["exercise_display"]
                    st.session_state.biomech_results[fn] = res
                    st.session_state.processed_videos.add(fn)
                    st.toast(f"✅ {res['exercise_display']} : TUT = {res['tut']}s | {res['reps']} reps")
                    time.sleep(0.25)
                    st.rerun()
                except Exception as err_single:
                    st.error(f"Erreur d'analyse : {err_single}")

    # Tableau récapitulatif du lot
    if st.session_state.get("batch_results"):
        with st.expander(f"📋 Tableau récapitulatif du lot ({len(st.session_state.batch_results)} vidéos)", expanded=True):
            batch_rows = [
                {
                    "Fichier": b["filename"],
                    "Exercice Détecté": b["exercise_display"],
                    "Type": "Isométrique" if b["type"] == "isometric" else "Dynamique",
                    "TUT Effectif": f"{b['tut']}s",
                    "Répétitions": b["reps"],
                    "Qualité / Dérive": b["drift"],
                    "Statut": b["status"]
                }
                for b in st.session_state.batch_results
            ]
            st.dataframe(pd.DataFrame(batch_rows), use_container_width=True, hide_index=True)

            if st.button("💾 Enregistrer toutes ces séances dans la base", key="btn_save_batch_db", use_container_width=True):
                for b in st.session_state.batch_results:
                    fn = b["filename"]
                    auto_s, _ = detect_student_and_exercise(fn, existing_students)
                    s_name = auto_s if auto_s else (existing_students[0] if existing_students else "Élève Démo")
                    new_e = {
                        "id": f"eval_batch_{int(time.time()*1000)}_{fn[:8]}",
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "student": s_name,
                        "exercise": b["exercise_display"],
                        "tst": b["tut"],
                        "rpe": 7.5,
                        "reps": b["reps"],
                        "video_name": fn,
                        "notes": f"Batch 3D : {b['drift']}",
                        "synced": True
                    }
                    st.session_state.db["evaluations"].append(new_e)
                    st.session_state.processed_videos.add(fn)
                save_db(st.session_state.db)
                st.success("✅ Toutes les séances du lot ont été enregistrées !")
                time.sleep(0.6)
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

    if total_files > 2:
        sel_vid_jump = st.selectbox(
            "Accès direct à une vidéo :",
            options=list(range(total_files)),
            index=cur_idx,
            format_func=lambda idx: f"{idx + 1}. {file_names[idx]} {'✅' if file_names[idx] in st.session_state.processed_videos else '⏳'}",
            key="sel_jump_video_idx"
        )
        if sel_vid_jump != cur_idx:
            st.session_state.active_video_idx = sel_vid_jump
            st.rerun()

    auto_student, auto_exo = detect_student_and_exercise(current_fname, existing_students)
    sw = _ensure_stopwatch_entry(current_fname)

    # ------------------------------------------------------------------
    # WORKSPACE VIDÉO (GAUCHE) + OUTILS CHRONO & VALIDATION (DROITE)
    # ------------------------------------------------------------------
    col_video, col_tools = st.columns([1.45, 1.2], gap="medium")

    with col_video:
        st.video(current_file)

        render_html("""
            <div class="cali-card" style="padding: 8px 12px; margin-top: 6px; margin-bottom: 6px;">
                <div style="font-weight:700; font-size:0.74rem; color:#94A3B8; text-transform:uppercase; letter-spacing:0.05em;">
                    🎯 Repères Début / Fin du Set (Précision Cadre)
                </div>
            </div>
        """)

        c_in, c_out = st.columns(2)
        with c_in:
            in_val = st.number_input("📍 Début set (s)", min_value=0.0, max_value=3600.0, value=float(sw["in_marker"]), step=0.5, key=f"in_{current_fname}")
            sw["in_marker"] = in_val
        with c_out:
            out_val = st.number_input("🏁 Fin set (s)", min_value=0.0, max_value=3600.0, value=float(sw["out_marker"]), step=0.5, key=f"out_{current_fname}")
            sw["out_marker"] = out_val

        diff_marker = max(0.0, round(out_val - in_val, 2)) if out_val > in_val else 0.0
        if st.button(f"⚡ Appliquer : TST = {diff_marker}s", use_container_width=True, key=f"apply_{current_fname}", disabled=(diff_marker <= 0)):
            sw["tst_val"] = diff_marker
            st.toast(f"✅ TST fixé à {diff_marker}s")
            st.rerun()

        # Module Auto-Track 3D local + Secours optionnel Gemini
        with st.expander("🤖 Auto-Track 3D Local : Détection Mouvement & Reps", expanded=False):
            render_html("""
                <div style="background:rgba(0, 229, 255, 0.07); border-left:3px solid #00E5FF; padding:8px 12px; border-radius:8px; margin:6px 0 10px 0; font-size:0.8rem; color:#E0F2FE;">
                    🟢 <b>Moteur 100% Local Déterministe :</b> MediaPipe 3D (World Landmarks métriques), découpage automatique et identification multi-angles (1-NN).
                </div>
            """)

            exo_choices = _get_dynamic_exercise_choices()
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

            if st.button("✨ Lancer l'Auto-Track 3D Rapide (< 2.5s)", key=f"ai_track_{current_fname}", use_container_width=True, type="primary"):
                with st.spinner("Analyse cinématique 3D locale en cours..."):
                    try:
                        from core.rep_counter import analyze_single_video_pipeline
                        cur_temp = get_persisted_temp_video_path(current_file)
                        forced_key = None if forced_opt[0] == "auto" else forced_opt[0]
                        res = analyze_single_video_pipeline(cur_temp, forced_exercise=forced_key, custom_tolerance=custom_tol)
                        sw["tst_val"] = float(res["tut"])
                        sw["reps"] = int(res["reps"])
                        sw["detected_exo"] = res["exercise_display"]
                        st.session_state.biomech_results[current_fname] = res
                        st.session_state.processed_videos.add(current_fname)
                        st.success(f"✅ Détection : **{res['exercise_display']}** ({res.get('camera_view', 'Profil')}) | TUT = **{sw['tst_val']}s** | Reps = **{sw['reps']}**")
                        time.sleep(0.25)
                        st.rerun()
                    except Exception as err_track:
                        st.error(f"Erreur d'analyse Auto-Track 3D : {err_track}")

            gem_key = get_gemini_api_key()
            if gem_key:
                if st.button("🧠 Analyse IA Gemini Vision (Secours)", key=f"gemini_fb_{current_fname}", use_container_width=True):
                    with st.spinner("Analyse Gemini Flash Vision (6 frames)..."):
                        from services.gemini_vision import analyze_motion_gemini
                        cur_temp = get_persisted_temp_video_path(current_file)
                        g_data, _, g_msg = analyze_motion_gemini(cur_temp, gem_key)
                        if g_data:
                            sw["tst_val"] = float(g_data.get("tut", 0.0))
                            sw["reps"] = int(g_data.get("reps", 0))
                            sw["detected_exo"] = g_data.get("exercise_display", auto_exo)
                            st.toast(f"🧠 Gemini : {sw['detected_exo']} | TUT={sw['tst_val']}s | {sw['reps']} reps")
                            if g_data.get("feedback"):
                                st.info(f"💬 IA : {g_data['feedback']}")
                            time.sleep(0.4)
                            st.rerun()
                        else:
                            st.warning(g_msg)

        # Courbes Plotly & Enrichissement Base 3D
        if current_fname in st.session_state.biomech_results:
            bio_r = st.session_state.biomech_results[current_fname]
            kin = bio_r.get("kinematics")
            ev = bio_r.get("evaluation") or {}
            seg = bio_r.get("segmentation") or {}
            effort_w = seg.get("effort_window") or {}

            with st.expander(f"📈 Diagnostic 3D & Courbes ({bio_r.get('exercise_display', 'Exercice')})", expanded=False):
                try:
                    import plotly.graph_objects as go
                    has_plotly = True
                except ImportError:
                    has_plotly = False
                if kin and has_plotly:
                    t_ser = kin["timestamps"]
                    filt_features = kin.get("features_filtered") or kin.get("angles_filtered", {})
                    is_iso = bio_r.get("type") == "isometric"

                    render_html(f"""
                        <div style="background:rgba(13,18,30,0.85); border:1px solid rgba(0,229,255,0.25); padding:9px 12px; border-radius:10px; margin-bottom:10px; font-size:0.82rem;">
                            🎯 <b>Exercice 3D :</b> <span style="color:#00E5FF; font-weight:700;">{bio_r.get('exercise_display')}</span> •
                            📐 <b>Vue :</b> {str(bio_r.get('camera_view', 'Profil')).capitalize()} •
                            💎 <b>Confiance :</b> {int(bio_r.get('confidence', 0.95)*100)}% •
                            ⏱️ <b>Actif :</b> {effort_w.get('start_time', 0.0)}s – {effort_w.get('end_time', 0.0)}s
                        </div>
                    """)

                    fig_3d = go.Figure()
                    if "elbow_angle" in filt_features:
                        fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["elbow_angle"], mode="lines", name="Coude 3D (°)", line=dict(color="#00E5FF", width=2.5)))
                    elif "elbow" in filt_features:
                        fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["elbow"], mode="lines", name="Coude (°)", line=dict(color="#00E5FF", width=2.5)))

                    if "shoulder_flexion" in filt_features:
                        fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["shoulder_flexion"], mode="lines", name="Épaule 3D (°)", line=dict(color="#F59E0B", width=2.0)))

                    if "trunk_inclination" in filt_features:
                        fig_3d.add_trace(go.Scatter(x=t_ser, y=filt_features["trunk_inclination"], mode="lines", name="Inclinaison Tronc (°)", line=dict(color="#10B981", width=1.8, dash="dot")))

                    if is_iso:
                        for hb in ev.get("hold_blocks", []):
                            fig_3d.add_vrect(
                                x0=hb["start_time"], x1=hb["end_time"],
                                fillcolor="rgba(16, 185, 129, 0.2)", layer="below", line_width=0,
                                annotation_text=f"Tenue {hb['duration']}s", annotation_position="top left"
                            )
                    else:
                        reps_list = ev.get("reps_details", ev.get("reps_detail", []))
                        for rep in reps_list:
                            fig_3d.add_vrect(
                                x0=rep["start_time"], x1=rep["end_time"],
                                fillcolor="rgba(0, 229, 255, 0.15)", layer="below", line_width=0,
                                annotation_text=f"R#{rep['rep_number']}", annotation_position="top left"
                            )

                    fig_3d.update_layout(
                        title="Cinématique Articulaire 3D (°)",
                        xaxis_title="Temps (s)",
                        yaxis_title="Degrés (°)",
                        paper_bgcolor="rgba(13, 18, 30, 0.6)",
                        plot_bgcolor="rgba(13, 18, 30, 0.6)",
                        font=dict(color="#F8FAFC"),
                        margin=dict(l=30, r=20, t=35, b=35),
                        height=270,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_3d, use_container_width=True)

                    render_html("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.08); margin:8px 0;'>")
                    render_html("<b>➕ Enregistrer ce calibrage dans la bibliothèque 3D :</b>")
                    c_b_cam, c_b_save = st.columns([1, 1.5])
                    with c_b_cam:
                        user_cam_view = st.selectbox("Angle de vue :", VALID_CAMERA_VIEWS, key=f"sel_cam_add_{current_fname}")
                    with c_b_save:
                        if st.button("💾 Enregistrer dans Baselines_3D", key=f"btn_add_to_base_{current_fname}", use_container_width=True):
                            if seg and "effort_window" in seg:
                                means_v, stds_v = compute_active_feature_vectors(kin, seg["effort_window"])
                                exo_lbl = bio_r.get("exercise_display", "Figure")
                                exo_tp = bio_r.get("type", "isometric")
                                ok_b, msg_b = save_calibrated_slot(
                                    exercise_name=exo_lbl,
                                    camera_view=user_cam_view,
                                    exo_type=exo_tp,
                                    mean_features=means_v.tolist(),
                                    std_features=stds_v.tolist()
                                )
                                if ok_b:
                                    st.success(f"✅ {exo_lbl} ({user_cam_view}) calibré dans Baselines_3D !")
                                    time.sleep(0.4)
                                    st.rerun()
                                else:
                                    st.error(msg_b)
                            else:
                                st.warning("Données cinématiques insuffisantes pour enregistrer un calibrage.")

        c_rep1, c_rep2 = st.columns(2)
        with c_rep1:
            reps_input = st.number_input("Nombre de répétitions :", min_value=0, max_value=150, value=int(sw.get("reps", 0)), step=1, key=f"reps_inp_{current_fname}")
            sw["reps"] = reps_input
        with c_rep2:
            if reps_input > 0 and sw["tst_val"] > 0:
                tempo_rep = round(sw["tst_val"] / reps_input, 1)
                render_html(f"""
                    <div style="padding-top:12px;">
                        <span style="font-size:0.72rem; color:#94A3B8; font-weight:700;">TEMPO MOYEN / REP</span><br>
                        <b style="font-family:'JetBrains Mono',monospace; font-size:1.15rem; color:#00E5FF;">{tempo_rep} s / rep</b>
                    </div>
                """)

    with col_tools:
        with st.container(border=True):
            _render_live_stopwatch_display(sw)

            c_run, c_raz = st.columns([1.55, 1])
            with c_run:
                is_run = sw["running"]
                btn_label = "⏸️ PAUSE" if is_run else "▶️ DÉMARRER"
                btn_type = "secondary" if is_run else "primary"
                if st.button(btn_label, key=f"btn_run_{current_fname}", type=btn_type, use_container_width=True):
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

            with st.form(key=f"eval_form_{current_fname}"):
                student_options = existing_students if existing_students else ["Aucun élève"]
                def_student_idx = student_options.index(auto_student) if auto_student and auto_student in student_options else 0

                sel_student = st.selectbox("👤 Athlète :", student_options, index=def_student_idx)
                def_exo = sw.get("detected_exo", auto_exo)
                val_exo = st.text_input("🏋️ Exercice :", value=def_exo)

                rpe_score = st.slider("🔥 Effort perçu (RPE 1-10) :", min_value=1.0, max_value=10.0, value=float(sw.get("rpe", 7.5)), step=0.5)
                sw["rpe"] = rpe_score

                if rpe_score <= 5.5:
                    rpe_class, rpe_text = "rpe-low", "🟢 Récupération / Technique (RIR 4+)"
                elif rpe_score <= 7.5:
                    rpe_class, rpe_text = "rpe-mod", "🔵 Hypertrophie productive (RIR 2-3)"
                elif rpe_score <= 9.0:
                    rpe_class, rpe_text = "rpe-opt", "🟡 Intensité élevée / Fin de bloc (RIR 1)"
                else:
                    rpe_class, rpe_text = "rpe-max", "🔴 Échec musculaire total / PR (RIR 0)"

                render_html(f'<div class="rpe-indicator {rpe_class}">{rpe_text}</div>')

                coach_notes = st.text_input("💬 Feedback / Consigne :", placeholder="Ex: Coudes bien verrouillés, bon tempo")
                submit_eval = st.form_submit_button("⚡ VALIDER & ENREGISTRER", type="primary", use_container_width=True)

                if submit_eval:
                    if sw["running"]:
                        sw["tst_val"] += time.time() - sw["start_time"]
                        sw["running"] = False

                    final_tst = round(float(sw["tst_val"]), 2)
                    if final_tst <= 0:
                        st.warning("⚠️ Chronomètre à 0s. Veuillez mesurer le TST.")
                    elif sel_student == "Aucun élève":
                        st.error("Ajoutez un athlète dans l'onglet 'Athlètes'.")
                    else:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        new_eval = {
                            "id": f"eval_{int(time.time()*1000)}",
                            "student": sel_student,
                            "exercise": val_exo,
                            "tst": final_tst,
                            "rpe": rpe_score,
                            "reps": int(sw.get("reps", 0)),
                            "video_name": current_fname,
                            "date": now_str,
                            "notes": coach_notes,
                            "synced": False
                        }

                        ok_sync, _ = dispatch_sync_evaluation(
                            st.session_state.db["settings"],
                            sel_student,
                            val_exo,
                            final_tst,
                            rpe_score,
                            int(sw.get("reps", 0)),
                            coach_notes,
                            now_str
                        )
                        new_eval["synced"] = ok_sync

                        st.session_state.db["evaluations"].append(new_eval)
                        save_db(st.session_state.db)

                        st.session_state.processed_videos.add(current_fname)
                        st.toast(f"✅ Séance validée : {sel_student} (TST: {final_tst}s | RPE: {rpe_score})")

                        if st.session_state.db["settings"].get("auto_advance", True) and cur_idx < total_files - 1:
                            st.session_state.active_video_idx += 1

                        time.sleep(0.5)
                        st.rerun()
