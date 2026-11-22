"""
Caliperf V2 - Espace Coaching & Performance
Application professionnelle de vidéo-analyse pour le coaching sportif (Calisthenics & Force).
Mesure précise du Temps Sous Tension (TST), suivi du RPE, gestion des athlètes et synchronisation Google Forms.
"""

import os
import json
import time
import re
from datetime import datetime
import pandas as pd
import requests
import streamlit as st

# Import optionnel de plotly pour les graphiques de progression
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ==============================================================================
# 1. CONFIGURATION DE LA PAGE
# ==============================================================================
st.set_page_config(
    page_title="Caliperf V2 | Coach Pro Studio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "caliperf_db.json"
DEFAULT_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"
DEFAULT_ENTRY_NOM = "entry.1847695661"
DEFAULT_ENTRY_EXO = "entry.1595307876"
DEFAULT_ENTRY_TST = "entry.549289703"
DEFAULT_ENTRY_RPE = "entry.46344190"

# ==============================================================================
# 2. GESTIONNAIRE DE BASE DE DONNÉES (RÉTRO-COMPATIBLE V1 & V2)
# ==============================================================================
def get_default_db():
    return {
        "version": 2,
        "students": {
            "Élève Démo": {
                "link": DEFAULT_FORM_URL,
                "freq": "4x / semaine",
                "goal": "Progression Muscle-up & Planche",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        },
        "evaluations": [],
        "settings": {
            "form_url": DEFAULT_FORM_URL,
            "entry_nom": DEFAULT_ENTRY_NOM,
            "entry_exo": DEFAULT_ENTRY_EXO,
            "entry_tst": DEFAULT_ENTRY_TST,
            "entry_rpe": DEFAULT_ENTRY_RPE,
            "admin_pwd": "admin",
            "auto_advance": True,
            "send_to_google": True
        }
    }

def load_db():
    """Charge la base JSON avec migration automatique si ancien format V1."""
    if not os.path.exists(DB_FILE):
        data = get_default_db()
        save_db(data)
        return data

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Détection ancien format V1 (dictionnaire simple { "Nom": { "link":... } })
        if "version" not in raw or "students" not in raw:
            new_data = get_default_db()
            for name, info in raw.items():
                if isinstance(info, dict):
                    new_data["students"][name] = {
                        "link": info.get("link", DEFAULT_FORM_URL),
                        "freq": info.get("freq", "Non renseigné"),
                        "goal": info.get("goal", "Objectif non précisé"),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
            save_db(new_data)
            return new_data

        # Vérification des sous-clés
        if "evaluations" not in raw:
            raw["evaluations"] = []
        if "settings" not in raw:
            raw["settings"] = get_default_db()["settings"]
        return raw

    except Exception as e:
        st.error(f"Erreur de lecture de la base ({e}). Chargement des données par défaut.")
        return get_default_db()

def save_db(data):
    """Sauvegarde atomique et sécurisée dans caliperf_db.json."""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Erreur de sauvegarde: {e}")

# Initialisation du State global
if "db" not in st.session_state:
    st.session_state.db = load_db()

if "is_authenticated" not in st.session_state:
    st.session_state.is_authenticated = False

if "active_video_idx" not in st.session_state:
    st.session_state.active_video_idx = 0

if "processed_videos" not in st.session_state:
    st.session_state.processed_videos = set()

if "stopwatches" not in st.session_state:
    st.session_state.stopwatches = {}

# ==============================================================================
# 3. DIRECTION ARTISTIQUE & DESIGN SYSTEM (DARK ATHLETIC KINETIC)
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

    /* Global Typography & Colors */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Background Athletic Mesh */
    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at 10% 20%, #0d1527 0%, #080d19 45%, #04060c 100%);
        color: #f1f5f9;
    }

    [data-testid="stSidebar"] {
        background: #090e1a !important;
        border-right: 1px solid rgba(255, 255, 255, 0.07);
    }

    /* Cards & Containers */
    .cali-card {
        background: rgba(15, 23, 42, 0.72);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 1.25rem 1.4rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
        margin-bottom: 1.1rem;
        transition: border 0.2s ease, transform 0.2s ease;
    }
    .cali-card:hover {
        border-color: rgba(0, 240, 255, 0.35);
    }

    /* Metric Badges */
    .badge-cyan {
        background: rgba(0, 240, 255, 0.12);
        color: #00f0ff;
        border: 1px solid rgba(0, 240, 255, 0.3);
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: inline-block;
    }

    .badge-lime {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-block;
    }

    .badge-amber {
        background: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-block;
    }

    /* Digital Readout */
    .digital-timer {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.8rem;
        font-weight: 700;
        color: #00f0ff;
        text-shadow: 0 0 20px rgba(0, 240, 255, 0.45);
        letter-spacing: -0.02em;
        line-height: 1;
        margin: 0.4rem 0 0.8rem 0;
    }

    .digital-sub {
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 500;
    }

    /* RPE Level Visual Banner */
    .rpe-indicator {
        padding: 10px 14px;
        border-radius: 10px;
        margin-top: 8px;
        font-size: 0.85rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .rpe-low {
        background: rgba(16, 185, 129, 0.15);
        border-left: 4px solid #10b981;
        color: #6ee7b7;
    }
    .rpe-mod {
        background: rgba(59, 130, 246, 0.15);
        border-left: 4px solid #3b82f6;
        color: #93c5fd;
    }
    .rpe-opt {
        background: rgba(245, 158, 11, 0.15);
        border-left: 4px solid #f59e0b;
        color: #fde68a;
    }
    .rpe-max {
        background: rgba(239, 68, 68, 0.2);
        border-left: 4px solid #ef4444;
        color: #fca5a5;
    }

    /* Button Enhancements */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(0, 240, 255, 0.2);
    }

    /* Inputs */
    .stTextInput input, .stSelectbox select, .stTextArea textarea {
        border-radius: 8px !important;
        background-color: rgba(15, 23, 42, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: white !important;
    }

    /* Header styling */
    h1, h2, h3, h4 {
        color: #f8fafc;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. FONCTIONS UTILITAIRES & AUTOMATISATION
# ==============================================================================
def detect_student_and_exercise(filename, student_list):
    """
    Détecte automatiquement l'athlète et le nom de l'exercice à partir du fichier vidéo.
    Exemple: 'Lucas_Dips_Lestés_20kg.mp4' -> Athlète: Lucas, Exo: Dips Lestés 20kg
    """
    clean_name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
    detected_student = None
    detected_exercise = clean_name

    # Recherche du nom d'un élève dans le nom du fichier
    for student in student_list:
        parts = student.lower().split()
        for p in parts:
            if len(p) >= 3 and p in clean_name.lower():
                detected_student = student
                # Retirer le nom de l'élève du nom d'exercice
                pattern = re.compile(re.escape(student), re.IGNORECASE)
                detected_exercise = pattern.sub("", clean_name).strip(" -_")
                break
        if detected_student:
            break

    return detected_student, detected_exercise if detected_exercise else clean_name

def send_to_google_forms(form_url, entries, student_name, exercise, tst_seconds, rpe_val):
    """Envoi non-bloquant et sécurisé vers Google Forms."""
    payload = {
        entries["entry_nom"]: student_name,
        entries["entry_exo"]: exercise,
        entries["entry_tst"]: str(round(tst_seconds, 2)).replace('.', ','),
        entries["entry_rpe"]: str(rpe_val)
    }
    try:
        res = requests.post(form_url, data=payload, timeout=4)
        return res.status_code == 200, res.status_code
    except Exception as e:
        return False, str(e)

# ==============================================================================
# 5. SIDEBAR : IDENTIFICATION & NAVIGATION
# ==============================================================================
with st.sidebar:
    st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom: 0.5rem;">
            <div style="background: linear-gradient(135deg, #00f0ff, #3b82f6); padding: 8px; border-radius: 10px; display:inline-block;">
                <span style="font-size: 20px;">⚡</span>
            </div>
            <div>
                <h3 style="margin:0; font-size: 1.3rem; font-weight:800; letter-spacing: -0.03em;">CALIPERF <span style="color:#00f0ff;">PRO</span></h3>
                <p style="margin:0; font-size:0.75rem; color:#64748b; font-weight:600;">VIDEO COACHING OS V2</p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # État d'authentification Coach
    admin_pwd_target = st.session_state.db["settings"].get("admin_pwd", "admin")

    if not st.session_state.is_authenticated:
        with st.expander("🔐 Connexion Coach", expanded=True):
            entered_pwd = st.text_input("Code Coach :", type="password", key="sidebar_login_pwd")
            if st.button("Déverrouiller l'Espace Pro", use_container_width=True, type="primary"):
                if entered_pwd == admin_pwd_target:
                    st.session_state.is_authenticated = True
                    st.rerun()
                else:
                    st.error("Code erroné.")
    else:
        col_auth1, col_auth2 = st.columns([2, 1])
        with col_auth1:
            st.markdown('<span class="badge-lime">🟢 Mode Coach Actif</span>', unsafe_allow_html=True)
        with col_auth2:
            if st.button("Sortir", key="logout_btn"):
                st.session_state.is_authenticated = False
                st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 1rem 0;'>", unsafe_allow_html=True)

    # Menu de Navigation ergonomique
    nav_options = [
        "🎥 Studio Vidéo & TST",
        "📊 Progression & Stats",
        "👥 Athlètes & Fiches",
        "⚙️ Paramètres & Synchro"
    ]
    menu_choice = st.radio("Navigation", nav_options, label_visibility="collapsed")

    st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 1rem 0;'>", unsafe_allow_html=True)

    # Mini Dashboard Stats Sidebar
    total_students = len(st.session_state.db.get("students", {}))
    total_evals = len(st.session_state.db.get("evaluations", []))
    st.markdown(f"""
        <div style="font-size:0.8rem; color:#94a3b8; display:flex; justify-content:space-between; margin-bottom: 4px;">
            <span>Athlètes enregistrés:</span> <b style="color:white;">{total_students}</b>
        </div>
        <div style="font-size:0.8rem; color:#94a3b8; display:flex; justify-content:space-between;">
            <span>Analyses TST stockées:</span> <b style="color:#00f0ff;">{total_evals}</b>
        </div>
    """, unsafe_allow_html=True)


# ==============================================================================
# VUE 1 : STUDIO VIDÉO & CHRONO TST (LE CŒUR DU LOGICIEL)
# ==============================================================================
if menu_choice == "🎥 Studio Vidéo & TST":
    st.markdown("""
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1rem;">
            <div>
                <h2 style="margin:0;">⚡ Studio d'Analyse TST</h2>
                <p style="margin:0; color:#94a3b8; font-size:0.9rem;">
                    Glissez vos vidéos, chronométrez le Temps Sous Tension et validez en un clic.
                </p>
            </div>
            <div>
                <span class="badge-cyan">V2 Haute Vitesse</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Zone de dépôt vidéos compacte et intuitive
    with st.expander("📁 Importer des vidéos de séances (Dépôt par lot)", expanded=True):
        uploaded_files = st.file_uploader(
            "Importer les vidéos des athlètes (.mp4, .mov, .avi)",
            type=['mp4', 'mov', 'avi'],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

    if not uploaded_files:
        st.markdown("""
            <div class="cali-card" style="text-align:center; padding: 2.5rem 1rem;">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📥</div>
                <h3 style="margin-bottom: 0.3rem;">Aucune vidéo en attente</h3>
                <p style="color:#94a3b8; max-width: 500px; margin: 0 auto; font-size: 0.95rem;">
                    Glissez les vidéos des sets de vos élèves ci-dessus pour lancer l'analyse vidéo,
                    mesurer le Temps Sous Tension (TST) et consigner l'effort (RPE).
                </p>
            </div>
        """, unsafe_allow_html=True)
    else:
        # File d'attente intelligente
        files_dict = {f.name: f for f in uploaded_files}
        file_names = list(files_dict.keys())

        # Barre de sélection horizontale rapide avec statut
        st.markdown("##### 🎞️ File d'attente des analyses")
        cols_queue = st.columns(min(len(file_names), 5))
        for idx, fname in enumerate(file_names[:5]):
            is_done = fname in st.session_state.processed_videos
            status_symbol = "✅" if is_done else "⏳"
            with cols_queue[idx]:
                short_label = (fname[:16] + '..') if len(fname) > 18 else fname
                btn_type = "primary" if idx == st.session_state.active_video_idx else "secondary"
                if st.button(f"{status_symbol} {short_label}", key=f"queue_{idx}", use_container_width=True, type=btn_type):
                    st.session_state.active_video_idx = idx
                    st.rerun()

        # Sélecteur complet si plus de 5 fichiers
        if len(file_names) > 5:
            display_options = [
                ("✅ " if n in st.session_state.processed_videos else "⏳ ") + n
                for n in file_names
            ]
            sel = st.selectbox("Sélectionner une autre vidéo :", display_options, index=st.session_state.active_video_idx)
            current_idx = display_options.index(sel)
            if current_idx != st.session_state.active_video_idx:
                st.session_state.active_video_idx = current_idx
                st.rerun()

        # Fichier sélectionné
        current_fname = file_names[min(st.session_state.active_video_idx, len(file_names)-1)]
        current_file = files_dict[current_fname]

        # Détection automatique de l'athlète et de l'exercice
        existing_students = list(st.session_state.db["students"].keys())
        auto_student, auto_exo = detect_student_and_exercise(current_fname, existing_students)

        # Initialisation du chronomètre pour cette vidéo
        if current_fname not in st.session_state.stopwatches:
            st.session_state.stopwatches[current_fname] = {
                "tst_val": 0.0,
                "in_marker": 0.0,
                "out_marker": 0.0,
                "running": False,
                "start_time": 0.0
            }
        sw = st.session_state.stopwatches[current_fname]

        # Disposition en 2 colonnes ergonomiques (Lecteur Vidéo à gauche, Outils & TST à droite)
        col_video, col_tools = st.columns([1.6, 1.2], gap="large")

        with col_video:
            st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                    <span style="font-weight:700; color:#f8fafc; font-size:1.05rem;">🎬 {current_fname}</span>
                    <span class="{'badge-lime' if current_fname in st.session_state.processed_videos else 'badge-amber'}">
                        {'Analysée' if current_fname in st.session_state.processed_videos else 'À évaluer'}
                    </span>
                </div>
            """, unsafe_allow_html=True)

            st.video(current_file)

            # Outils de repères temporels rapides (In/Out markers)
            st.markdown("""
                <div class="cali-card" style="margin-top: 10px; padding: 12px 16px;">
                    <div style="font-weight:700; font-size:0.85rem; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px;">
                        🎯 Repères Début/Fin du Set (Précision Cadre)
                    </div>
                </div>
            """, unsafe_allow_html=True)
            c_in, c_out, c_calc = st.columns([1, 1, 1.2])
            with c_in:
                in_val = st.number_input("📍 Début set (sec)", min_value=0.0, max_value=3600.0, value=float(sw["in_marker"]), step=0.5, key=f"in_{current_fname}")
                sw["in_marker"] = in_val
            with c_out:
                out_val = st.number_input("🏁 Fin set (sec)", min_value=0.0, max_value=3600.0, value=float(sw["out_marker"]), step=0.5, key=f"out_{current_fname}")
                sw["out_marker"] = out_val
            with c_calc:
                diff_marker = max(0.0, round(out_val - in_val, 2)) if out_val > in_val else 0.0
                st.write("")
                st.write("")
                if st.button(f"⚡ Appliquer ({diff_marker}s)", use_container_width=True, key=f"apply_{current_fname}", disabled=(diff_marker <= 0)):
                    sw["tst_val"] = diff_marker
                    st.rerun()

        with col_tools:
            st.markdown('<div class="cali-card">', unsafe_allow_html=True)

            # Onglets de chronométrage
            tab_chrono, tab_direct = st.tabs(["⏱️ Chronomètre Dynamique", "✏️ Saisie Manuelle"])

            with tab_chrono:
                # Affichage Digital Neon
                disp_tst = sw["tst_val"]
                st.markdown(f"""
                    <div style="text-align: center; padding: 0.5rem 0;">
                        <span class="digital-sub">TEMPS SOUS TENSION MESURÉ</span>
                        <div class="digital-timer">{disp_tst:.2f}<span style="font-size:1.5rem; color:#94a3b8;"> s</span></div>
                    </div>
                """, unsafe_allow_html=True)

                # Boutons de contrôle
                c_b1, c_b2, c_b3 = st.columns([1.2, 1, 1])
                with c_b1:
                    if st.button("▶️ Démarrer" if not sw["running"] else "⏸️ Pause", key=f"btn_run_{current_fname}", type="primary", use_container_width=True):
                        if sw["running"]:
                            sw["tst_val"] += time.time() - sw["start_time"]
                            sw["running"] = False
                        else:
                            sw["start_time"] = time.time()
                            sw["running"] = True
                        st.rerun()
                with c_b2:
                    if st.button("🔄 RAZ", key=f"btn_raz_{current_fname}", use_container_width=True):
                        sw["tst_val"] = 0.0
                        sw["running"] = False
                        st.rerun()
                with c_b3:
                    if st.button("+5s", key=f"btn_plus5_{current_fname}", use_container_width=True):
                        sw["tst_val"] += 5.0
                        st.rerun()

                # Ajustements fins
                adj_c1, adj_c2, adj_c3 = st.columns(3)
                with adj_c1:
                    if st.button("-1.0s", key=f"m1_{current_fname}", use_container_width=True):
                        sw["tst_val"] = max(0.0, sw["tst_val"] - 1.0)
                        st.rerun()
                with adj_c2:
                    if st.button("+0.5s", key=f"p05_{current_fname}", use_container_width=True):
                        sw["tst_val"] += 0.5
                        st.rerun()
                with adj_c3:
                    if st.button("+1.0s", key=f"p1_{current_fname}", use_container_width=True):
                        sw["tst_val"] += 1.0
                        st.rerun()

            with tab_direct:
                manual_input = st.number_input(
                    "Saisir directement le TST (secondes) :",
                    min_value=0.0,
                    max_value=600.0,
                    value=float(sw["tst_val"]),
                    step=0.25,
                    key=f"manual_{current_fname}"
                )
                if st.button("Fixer cette valeur", key=f"set_manual_{current_fname}", use_container_width=True):
                    sw["tst_val"] = manual_input
                    st.rerun()

            st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.8rem 0;'>", unsafe_allow_html=True)

            # FORMULAIRE D'ÉVALUATION RAPIDE
            with st.form(key=f"eval_form_{current_fname}"):
                # 1. Sélection Athlète
                student_options = existing_students if existing_students else ["Aucun élève"]
                default_student_idx = 0
                if auto_student and auto_student in student_options:
                    default_student_idx = student_options.index(auto_student)

                sel_student = st.selectbox(
                    "👤 Athlète :",
                    student_options,
                    index=default_student_idx
                )

                # 2. Nom de l'exercice
                val_exo = st.text_input("🏋️ Exercice :", value=auto_exo)

                # 3. RPE avec slider dynamique
                rpe_score = st.slider("🔥 Effort perçu (RPE 1-10) :", min_value=1.0, max_value=10.0, value=7.5, step=0.5)

                # Indicateur visuel RPE
                if rpe_score <= 5.5:
                    rpe_class, rpe_text = "rpe-low", "🟢 Récupération / Technique facile (RIR 4+)"
                elif rpe_score <= 7.5:
                    rpe_class, rpe_text = "rpe-mod", "🔵 Hypertrophie productive (RIR 2-3)"
                elif rpe_score <= 9.0:
                    rpe_class, rpe_text = "rpe-opt", "🟡 Intensité élevée / Fin de bloc (RIR 1)"
                else:
                    rpe_class, rpe_text = "rpe-max", "🔴 Échec musculaire total / PR Maximal (RIR 0)"

                st.markdown(f'<div class="rpe-indicator {rpe_class}">{rpe_text}</div>', unsafe_allow_html=True)

                # 4. Note / Feedback optionnel
                coach_notes = st.text_input("💬 Note technique / Consigne (optionnel) :", placeholder="Ex: Coudes bien verrouillés, ralentir la phase excentrique")

                # 5. Options d'envoi
                col_sub1, col_sub2 = st.columns([1.5, 1])
                with col_sub1:
                    sync_google = st.checkbox("Synchroniser Google Form", value=st.session_state.db["settings"].get("send_to_google", True))

                # Bouton de validation principal
                submit_eval = st.form_submit_button("⚡ VALIDER & ENREGISTRER", type="primary", use_container_width=True)

                if submit_eval:
                    final_tst = round(sw["tst_val"], 2)
                    if final_tst <= 0:
                        st.warning("⚠️ Le chronomètre TST est à 0s. Veuillez mesurer le temps avant de valider.")
                    elif sel_student == "Aucun élève":
                        st.error("Créez d'abord un athlète dans l'onglet 'Athlètes & Fiches'.")
                    else:
                        # 1. Sauvegarde locale dans evaluations
                        new_eval = {
                            "id": f"eval_{int(time.time()*1000)}",
                            "student": sel_student,
                            "exercise": val_exo,
                            "tst": final_tst,
                            "rpe": rpe_score,
                            "video_name": current_fname,
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "notes": coach_notes,
                            "google_synced": False
                        }

                        # 2. Synchronisation Google Forms
                        if sync_google:
                            form_url = st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL)
                            entries = {
                                "entry_nom": st.session_state.db["settings"].get("entry_nom", DEFAULT_ENTRY_NOM),
                                "entry_exo": st.session_state.db["settings"].get("entry_exo", DEFAULT_ENTRY_EXO),
                                "entry_tst": st.session_state.db["settings"].get("entry_tst", DEFAULT_ENTRY_TST),
                                "entry_rpe": st.session_state.db["settings"].get("entry_rpe", DEFAULT_ENTRY_RPE),
                            }
                            ok, resp = send_to_google_forms(form_url, entries, sel_student, val_exo, final_tst, rpe_score)
                            new_eval["google_synced"] = ok
                            if not ok:
                                st.warning(f"Données enregistrées localement, mais échec Google Form ({resp}).")
                            else:
                                st.toast("✅ Synchronisé avec Google Forms !")

                        st.session_state.db["evaluations"].append(new_eval)
                        save_db(st.session_state.db)

                        # Marquer la vidéo comme traitée
                        st.session_state.processed_videos.add(current_fname)
                        st.success(f"Séance enregistrée pour {sel_student} (TST: {final_tst}s | RPE: {rpe_score}) !")

                        # Passer automatiquement à la vidéo suivante si souhaité
                        if st.session_state.db["settings"].get("auto_advance", True) and st.session_state.active_video_idx < len(file_names) - 1:
                            st.session_state.active_video_idx += 1

                        time.sleep(1)
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# VUE 2 : PROGRESSION, ANALYTICS & HISTORIQUE
# ==============================================================================
elif menu_choice == "📊 Progression & Stats":
    st.markdown("""
        <div style="margin-bottom: 1rem;">
            <h2 style="margin:0;">📊 Progression & Historique d'Entraînement</h2>
            <p style="margin:0; color:#94a3b8; font-size:0.9rem;">
                Visualisez le Temps Sous Tension et l'évolution du RPE par athlète et par exercice.
            </p>
        </div>
    """, unsafe_allow_html=True)

    evals = st.session_state.db.get("evaluations", [])

    if not evals:
        st.info("Aucune analyse enregistrée pour l'instant. Rendez-vous dans le Studio pour évaluer vos premières vidéos !")
    else:
        df_evals = pd.DataFrame(evals)

        # KPI Counters
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Total Séances Analysées", len(df_evals))
        with k2:
            st.metric("Athlètes Actifs", df_evals["student"].nunique())
        with k3:
            st.metric("TST Moyen", f"{df_evals['tst'].mean():.1f} s")
        with k4:
            st.metric("RPE Moyen", f"{df_evals['rpe'].mean():.1f} / 10")

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 1.2rem 0;'>", unsafe_allow_html=True)

        # Filtres interactifs
        c_filter1, c_filter2 = st.columns([1, 1])
        all_students = ["Tous les athlètes"] + sorted(list(df_evals["student"].unique()))
        with c_filter1:
            selected_student_filter = st.selectbox("Filtrer par athlète :", all_students)

        df_filtered = df_evals if selected_student_filter == "Tous les athlètes" else df_evals[df_evals["student"] == selected_student_filter]

        # Graphiques interactifs si Plotly est disponible
        if HAS_PLOTLY and not df_filtered.empty:
            g1, g2 = st.columns([1.5, 1])
            with g1:
                st.markdown("##### 📈 Évolution du Temps Sous Tension (TST)")
                fig_tst = px.line(
                    df_filtered,
                    x="date",
                    y="tst",
                    color="exercise",
                    markers=True,
                    labels={"tst": "Temps Sous Tension (s)", "date": "Date Séance", "exercise": "Exercice"},
                    template="plotly_dark"
                )
                fig_tst.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(15,23,42,0.6)",
                    font_family="Plus Jakarta Sans",
                    margin=dict(l=20, r=20, t=30, b=20)
                )
                st.plotly_chart(fig_tst, use_container_width=True)

            with g2:
                st.markdown("##### 🎯 Répartition RPE")
                fig_rpe = px.histogram(
                    df_filtered,
                    x="rpe",
                    nbins=10,
                    color_discrete_sequence=["#00f0ff"],
                    labels={"rpe": "Niveau RPE"},
                    template="plotly_dark"
                )
                fig_rpe.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(15,23,42,0.6)",
                    font_family="Plus Jakarta Sans",
                    margin=dict(l=20, r=20, t=30, b=20)
                )
                st.plotly_chart(fig_rpe, use_container_width=True)

        # Tableau d'historique détaillé
        st.markdown("##### 📜 Registre des évaluations")
        df_display = df_filtered[["date", "student", "exercise", "tst", "rpe", "google_synced", "notes"]].copy()
        df_display.columns = ["Date", "Athlète", "Exercice", "TST (sec)", "RPE", "Google Form", "Notes Coach"]
        st.dataframe(df_display, use_container_width=True)

        # Export CSV
        csv_data = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Exporter les données en CSV",
            data=csv_data,
            file_name=f"caliperf_evaluations_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )


# ==============================================================================
# VUE 3 : ATHLÈTES & FICHES
# ==============================================================================
elif menu_choice == "👥 Athlètes & Fiches":
    st.markdown("""
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1rem;">
            <div>
                <h2 style="margin:0;">👥 Dossiers Athlètes</h2>
                <p style="margin:0; color:#94a3b8; font-size:0.9rem;">
                    Gérez vos élèves, leurs objectifs et consultez leurs bilans de performances.
                </p>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Formulaire d'ajout rapide
    with st.expander("➕ Inscrire un nouvel athlète", expanded=False):
        with st.form("add_student_form"):
            col_nom, col_prenom = st.columns(2)
            with col_nom:
                new_nom = st.text_input("Nom de famille :")
            with col_prenom:
                new_prenom = st.text_input("Prénom :")

            col_f, col_link = st.columns(2)
            with col_f:
                new_freq = st.selectbox(
                    "Fréquence d'entraînement :",
                    ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Quotidien"]
                )
            with col_link:
                new_link = st.text_input("Lien Google Form personnalisé (optionnel) :", value=st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL))

            new_goal = st.text_area("Objectif athlétique principal :", placeholder="Ex: Débloquer le Front Lever et améliorer l'endurance sur les dips")

            if st.form_submit_button("✅ Enregistrer l'athlète", type="primary"):
                if new_nom.strip() and new_prenom.strip():
                    full_name = f"{new_prenom.strip()} {new_nom.strip()}"
                    st.session_state.db["students"][full_name] = {
                        "freq": new_freq,
                        "goal": new_goal.strip() if new_goal.strip() else "Objectif général",
                        "link": new_link.strip(),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    save_db(st.session_state.db)
                    st.success(f"Athlète {full_name} inscrit avec succès !")
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.warning("Veuillez renseigner le nom et le prénom.")

    # Liste des fiches athlètes
    students = st.session_state.db.get("students", {})
    if not students:
        st.info("Aucun athlète dans le registre.")
    else:
        st.markdown("##### 📋 Liste des athlètes actifs")
        for name, details in list(students.items()):
            # Calcul du nombre de séances faites par cet élève
            evals = st.session_state.db.get("evaluations", [])
            student_evals = [e for e in evals if e.get("student") == name]

            st.markdown(f"""
                <div class="cali-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <h4 style="margin:0 0 4px 0; font-size:1.15rem; color:#f8fafc;">👤 {name}</h4>
                            <span class="badge-cyan">{details.get('freq', 'Fréquence non précisée')}</span>
                            <span style="font-size:0.8rem; color:#94a3b8; margin-left:10px;">Inscrit le {details.get('created_at', 'Date inconnue')}</span>
                        </div>
                        <div style="text-align:right;">
                            <span class="badge-lime">{len(student_evals)} Séances validées</span>
                        </div>
                    </div>
                    <div style="margin-top:10px; font-size:0.9rem; color:#cbd5e1; background:rgba(0,0,0,0.25); padding:8px 12px; border-radius:8px;">
                        🎯 <b>Objectif :</b> {details.get('goal', 'Aucun objectif spécifié')}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # Actions par élève si authentifié
            if st.session_state.is_authenticated:
                col_d1, col_d2 = st.columns([1, 6])
                with col_d1:
                    if st.button("🗑️ Supprimer", key=f"del_{name}"):
                        del st.session_state.db["students"][name]
                        save_db(st.session_state.db)
                        st.warning(f"Athlète {name} supprimé.")
                        time.sleep(0.5)
                        st.rerun()


# ==============================================================================
# VUE 4 : PARAMÈTRES & SYNCHRONISATION
# ==============================================================================
elif menu_choice == "⚙️ Paramètres & Synchro":
    st.markdown("""
        <div style="margin-bottom: 1rem;">
            <h2 style="margin:0;">⚙️ Configuration & Synchronisation</h2>
            <p style="margin:0; color:#94a3b8; font-size:0.9rem;">
                Gérez vos intégrations Google Sheets / Forms, vos préférences et la sauvegarde des données.
            </p>
        </div>
    """, unsafe_allow_html=True)

    with st.form("settings_form"):
        st.markdown("##### 🔗 Connecteur Google Forms")
        form_url = st.text_input("URL Google Form (formResponse) :", value=st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL))

        st.markdown("##### 🏷️ Identifiants des champs (Entry IDs)")
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            e_nom = st.text_input("Champ Nom (entry.XXX) :", value=st.session_state.db["settings"].get("entry_nom", DEFAULT_ENTRY_NOM))
            e_tst = st.text_input("Champ TST (entry.XXX) :", value=st.session_state.db["settings"].get("entry_tst", DEFAULT_ENTRY_TST))
        with col_e2:
            e_exo = st.text_input("Champ Exercice (entry.XXX) :", value=st.session_state.db["settings"].get("entry_exo", DEFAULT_ENTRY_EXO))
            e_rpe = st.text_input("Champ RPE (entry.XXX) :", value=st.session_state.db["settings"].get("entry_rpe", DEFAULT_ENTRY_RPE))

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.8rem 0;'>", unsafe_allow_html=True)
        st.markdown("##### ⚡ Ergonomie & Automatisations")
        auto_adv = st.checkbox("Passer automatiquement à la vidéo suivante après validation", value=st.session_state.db["settings"].get("auto_advance", True))
        auto_send = st.checkbox("Synchroniser par défaut avec Google Forms", value=st.session_state.db["settings"].get("send_to_google", True))

        new_admin_pwd = st.text_input("Mot de passe Coach Pro :", value=st.session_state.db["settings"].get("admin_pwd", "admin"), type="password")

        if st.form_submit_button("💾 Enregistrer la configuration", type="primary"):
            st.session_state.db["settings"] = {
                "form_url": form_url.strip(),
                "entry_nom": e_nom.strip(),
                "entry_exo": e_exo.strip(),
                "entry_tst": e_tst.strip(),
                "entry_rpe": e_rpe.strip(),
                "admin_pwd": new_admin_pwd.strip(),
                "auto_advance": auto_adv,
                "send_to_google": auto_send
            }
            save_db(st.session_state.db)
            st.success("Configuration sauvegardée avec succès !")
            time.sleep(0.8)
            st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 1.2rem 0;'>", unsafe_allow_html=True)

    # Sauvegarde & Restauration
    st.markdown("##### 💾 Sauvegarde & Export de la base")
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        json_export = json.dumps(st.session_state.db, indent=2, ensure_ascii=False).encode('utf-8')
        st.download_button(
            "📥 Télécharger la base complète (JSON)",
            data=json_export,
            file_name=f"caliperf_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True
        )
    with col_exp2:
        if st.button("🧪 Tester la connexion Google Form", use_container_width=True):
            test_ok, test_resp = send_to_google_forms(
                st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL),
                st.session_state.db["settings"],
                "Test Connexion",
                "Test Dips",
                15.5,
                7
            )
            if test_ok:
                st.success("Test Google Form réussi (HTTP 200) !")
            else:
                st.error(f"Échec du test ({test_resp}). Vérifiez l'URL et les Entry IDs.")
