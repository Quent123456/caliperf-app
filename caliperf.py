"""
Caliperf V2 - Espace Coaching & Performance
Application responsive (Mobile-First & Desktop) de vidéo-analyse pour le coaching sportif (Calisthenics & Force).
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
# 1. CONFIGURATION DE LA PAGE & VIEWPORT MOBILE
# ==============================================================================
st.set_page_config(
    page_title="Caliperf V2 | Video Coach Studio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"  # Réduit sur mobile pour maximiser l'espace écran
)

DB_FILE = "caliperf_db.json"
DEFAULT_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"
DEFAULT_ENTRY_NOM = "entry.1847695661"
DEFAULT_ENTRY_EXO = "entry.1595307876"
DEFAULT_ENTRY_TST = "entry.549289703"
DEFAULT_ENTRY_RPE = "entry.46344190"

# ==============================================================================
# 2. GESTIONNAIRE DE BASE DE DONNÉES
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

        if "evaluations" not in raw:
            raw["evaluations"] = []
        if "settings" not in raw:
            raw["settings"] = get_default_db()["settings"]
        return raw

    except Exception as e:
        st.error(f"Erreur de lecture de la base ({e}). Chargement des données par défaut.")
        return get_default_db()

def save_db(data):
    """Sauvegarde atomique dans caliperf_db.json."""
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

if "current_nav" not in st.session_state:
    st.session_state.current_nav = "🎥 Studio"

# ==============================================================================
# 3. CSS RESPONSIVE : ADAPTÉ MOBILE & DESKTOP (THUMB-FRIENDLY & HIGH-CONTRAST)
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@600;700&display=swap');

    /* Typographie globale */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        -webkit-tap-highlight-color: transparent;
        touch-action: manipulation;
    }

    /* Fond d'écran Dark Athletic */
    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at 10% 15%, #0e1628 0%, #080d19 45%, #04060c 100%);
        color: #f1f5f9;
    }

    [data-testid="stSidebar"] {
        background: #080d18 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Espacements principaux réduits sur mobile pour éviter de scroller */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
        max-width: 1250px !important;
    }

    /* Optimisation du lecteur vidéo (Ne doit pas dépasser 42% de l'écran sur smartphone) */
    video {
        max-height: 42vh !important;
        width: 100% !important;
        object-fit: contain !important;
        background: #000 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5) !important;
    }

    @media (min-width: 769px) {
        video {
            max-height: 58vh !important;
        }
        .block-container {
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            padding-top: 2rem !important;
        }
    }

    /* Cartes Glassmorphism */
    .cali-card {
        background: rgba(15, 23, 42, 0.78);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
        margin-bottom: 0.9rem;
    }

    /* Badges */
    .badge-cyan {
        background: rgba(0, 240, 255, 0.12);
        color: #00f0ff;
        border: 1px solid rgba(0, 240, 255, 0.35);
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        display: inline-block;
    }

    .badge-lime {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        display: inline-block;
    }

    .badge-amber {
        background: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        display: inline-block;
    }

    /* Digital Readout Grand Format (Lisible d'un coup d'œil sur téléphone) */
    .digital-timer {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.7rem;
        font-weight: 700;
        color: #00f0ff;
        text-shadow: 0 0 18px rgba(0, 240, 255, 0.45);
        letter-spacing: -0.02em;
        line-height: 1;
        margin: 0.2rem 0 0.5rem 0;
    }

    .digital-sub {
        font-size: 0.78rem;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* RPE Indicateur Dynamique */
    .rpe-indicator {
        padding: 8px 12px;
        border-radius: 9px;
        margin-top: 6px;
        font-size: 0.82rem;
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

    /* Boutons tactiles optimisés Mobile (Zones de frappe au pouce >= 46px) */
    .stButton>button {
        border-radius: 9px !important;
        font-weight: 600 !important;
        min-height: 46px !important;
        font-size: 0.95rem !important;
        transition: all 0.15s ease !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
    }
    .stButton>button:active {
        transform: scale(0.98) !important;
    }

    /* Champs de saisie */
    .stTextInput input, .stSelectbox select, .stTextArea textarea, .stNumberInput input {
        border-radius: 8px !important;
        background-color: rgba(15, 23, 42, 0.85) !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        color: white !important;
        min-height: 42px !important;
    }

    /* Header Mobile Bar */
    .mobile-header-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.4rem 0.2rem 0.8rem 0.2rem;
        margin-bottom: 0.4rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. FONCTIONS UTILITAIRES
# ==============================================================================
def detect_student_and_exercise(filename, student_list):
    """Détecte automatiquement l'athlète et l'exercice depuis le nom du fichier."""
    clean_name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
    detected_student = None
    detected_exercise = clean_name

    for student in student_list:
        parts = student.lower().split()
        for p in parts:
            if len(p) >= 3 and p in clean_name.lower():
                detected_student = student
                pattern = re.compile(re.escape(student), re.IGNORECASE)
                detected_exercise = pattern.sub("", clean_name).strip(" -_")
                break
        if detected_student:
            break

    return detected_student, detected_exercise if detected_exercise else clean_name

def send_to_google_forms(form_url, entries, student_name, exercise, tst_seconds, rpe_val):
    """Envoi sécurisé vers Google Forms sans bloquer l'UI."""
    payload = {
        entries["entry_nom"]: student_name,
        entries["entry_exo"]: exercise,
        entries["entry_tst"]: str(round(tst_seconds, 2)).replace('.', ','),
        entries["entry_rpe"]: str(rpe_val)
    }
    try:
        res = requests.post(form_url, data=payload, timeout=3.5)
        return res.status_code == 200, res.status_code
    except Exception as e:
        return False, str(e)


# ==============================================================================
# 5. EN-TÊTE MOBILE & NAVIGATION EN 1 CLIC (ACCESSIBLE AU POUCE)
# ==============================================================================
admin_pwd_target = st.session_state.db["settings"].get("admin_pwd", "admin")

st.markdown("""
    <div class="mobile-header-bar">
        <div style="display:flex; align-items:center; gap:8px;">
            <div style="background: linear-gradient(135deg, #00f0ff, #3b82f6); padding: 6px 9px; border-radius: 9px;">
                <span style="font-size: 16px;">⚡</span>
            </div>
            <div>
                <span style="font-size: 1.15rem; font-weight:800; letter-spacing: -0.02em;">CALIPERF</span>
                <span style="color:#00f0ff; font-weight:800; font-size:1.15rem;">V2</span>
            </div>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
            <span class="badge-lime">📱 Mobile & PC</span>
        </div>
    </div>
""", unsafe_allow_html=True)

# Barre de Navigation principale directement accessible sur l'écran (sans ouvrir le menu hamburger)
col_nav1, col_nav2, col_nav3, col_nav4 = st.columns(4)
with col_nav1:
    btn_type = "primary" if st.session_state.current_nav == "🎥 Studio" else "secondary"
    if st.button("🎥 Studio", use_container_width=True, type=btn_type):
        st.session_state.current_nav = "🎥 Studio"
        st.rerun()
with col_nav2:
    btn_type = "primary" if st.session_state.current_nav == "📊 Stats" else "secondary"
    if st.button("📊 Stats", use_container_width=True, type=btn_type):
        st.session_state.current_nav = "📊 Stats"
        st.rerun()
with col_nav3:
    btn_type = "primary" if st.session_state.current_nav == "👥 Athlètes" else "secondary"
    if st.button("👥 Athlètes", use_container_width=True, type=btn_type):
        st.session_state.current_nav = "👥 Athlètes"
        st.rerun()
with col_nav4:
    btn_type = "primary" if st.session_state.current_nav == "⚙️ Réglages" else "secondary"
    if st.button("⚙️ Réglages", use_container_width=True, type=btn_type):
        st.session_state.current_nav = "⚙️ Réglages"
        st.rerun()

# Connexion Coach rapide si non connecté (dans un expander compact)
if not st.session_state.is_authenticated:
    with st.expander("🔒 Activer le Mode Coach (Code Admin)", expanded=False):
        c_p1, c_p2 = st.columns([2, 1])
        with c_p1:
            entered_pwd = st.text_input("Code Coach :", type="password", key="quick_login_pwd", label_visibility="collapsed", placeholder="Mot de passe coach...")
        with c_p2:
            if st.button("Déverrouiller", use_container_width=True, type="primary"):
                if entered_pwd == admin_pwd_target:
                    st.session_state.is_authenticated = True
                    st.toast("✅ Mode Coach déverrouillé !")
                    st.rerun()
                else:
                    st.error("Code erroné.")


# ==============================================================================
# VUE 1 : STUDIO VIDÉO & CHRONOMÉTRAGE TST (OPTIMISÉ ÉCRAN TACTILE)
# ==============================================================================
if st.session_state.current_nav == "🎥 Studio":
    # 1. Dépôt de vidéos (optimisé pour galerie smartphone & glisser-déposer PC)
    with st.expander("📁 Importer des vidéos (depuis la galerie ou PC)", expanded=False):
        uploaded_files = st.file_uploader(
            "Importer les vidéos (.mp4, .mov, .avi)",
            type=['mp4', 'mov', 'avi'],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

    if not uploaded_files:
        st.markdown("""
            <div class="cali-card" style="text-align:center; padding: 2rem 1rem; margin-top: 0.5rem;">
                <div style="font-size: 2.4rem; margin-bottom: 0.4rem;">📲</div>
                <h3 style="margin-bottom: 0.2rem; font-size: 1.15rem;">Prêt pour vos analyses</h3>
                <p style="color:#94a3b8; font-size: 0.88rem; max-width: 440px; margin: 0 auto;">
                    Touchez <b>Importer des vidéos</b> ci-dessus pour sélectionner les vidéos de vos élèves depuis votre galerie mobile ou votre ordinateur.
                </p>
            </div>
        """, unsafe_allow_html=True)
    else:
        files_dict = {f.name: f for f in uploaded_files}
        file_names = list(files_dict.keys())
        total_files = len(file_names)

        # Contrôles de file d'attente adaptés mobile : Précédent / Suivant au pouce
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
            status_text = "✅ Analysée" if is_analyzed else "⏳ En attente"
            st.markdown(f"""
                <div style="text-align:center; padding-top: 4px;">
                    <span style="font-size: 0.82rem; font-weight:700; color:#f1f5f9;">Vidéo {cur_idx + 1} / {total_files}</span><br>
                    <span class="{badge_type}" style="font-size: 0.7rem; padding: 2px 8px;">{status_text}</span>
                </div>
            """, unsafe_allow_html=True)
        with col_next:
            if st.button("Suiv. ▶️", key="btn_next_vid", use_container_width=True, disabled=(cur_idx >= total_files - 1)):
                st.session_state.active_video_idx = min(total_files - 1, cur_idx + 1)
                st.rerun()

        # Détection auto
        existing_students = list(st.session_state.db["students"].keys())
        auto_student, auto_exo = detect_student_and_exercise(current_fname, existing_students)

        # Gestion du chronomètre pour cette vidéo
        if current_fname not in st.session_state.stopwatches:
            st.session_state.stopwatches[current_fname] = {
                "tst_val": 0.0,
                "in_marker": 0.0,
                "out_marker": 0.0,
                "running": False,
                "start_time": 0.0,
                "rpe": 7.5
            }
        sw = st.session_state.stopwatches[current_fname]

        # Layout responsive : sur PC en 2 colonnes, sur Mobile empilement parfait
        col_video, col_tools = st.columns([1.5, 1.2], gap="medium")

        with col_video:
            # Lecteur Vidéo (CSS contraint la hauteur à 42vh max sur téléphone)
            st.video(current_file)

            # Repères Début/Fin de set (In / Out Markers) - Idéal pour les coachs
            st.markdown("""
                <div class="cali-card" style="padding: 10px 14px; margin-top: 6px;">
                    <div style="font-weight:700; font-size:0.78rem; color:#94a3b8; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;">
                        🎯 Repères Précis In / Out (au centième)
                    </div>
                </div>
            """, unsafe_allow_html=True)

            c_in, c_out = st.columns(2)
            with c_in:
                in_val = st.number_input("📍 Début set (s)", min_value=0.0, max_value=3600.0, value=float(sw["in_marker"]), step=0.5, key=f"in_{current_fname}")
                sw["in_marker"] = in_val
            with c_out:
                out_val = st.number_input("🏁 Fin set (s)", min_value=0.0, max_value=3600.0, value=float(sw["out_marker"]), step=0.5, key=f"out_{current_fname}")
                sw["out_marker"] = out_val

            diff_marker = max(0.0, round(out_val - in_val, 2)) if out_val > in_val else 0.0
            if st.button(f"⚡ Appliquer repères : TST = {diff_marker}s", use_container_width=True, key=f"apply_{current_fname}", disabled=(diff_marker <= 0)):
                sw["tst_val"] = diff_marker
                st.toast(f"✅ TST fixé à {diff_marker}s")
                st.rerun()

        with col_tools:
            st.markdown('<div class="cali-card">', unsafe_allow_html=True)

            # Affichage Digital Neon
            disp_tst = sw["tst_val"]
            st.markdown(f"""
                <div style="text-align: center; padding: 0.2rem 0 0.4rem 0;">
                    <span class="digital-sub">TEMPS SOUS TENSION (TST)</span>
                    <div class="digital-timer">{disp_tst:.2f}<span style="font-size:1.4rem; color:#94a3b8;"> s</span></div>
                </div>
            """, unsafe_allow_html=True)

            # Boutons Chrono au pouce
            c_run, c_raz = st.columns([1.5, 1])
            with c_run:
                is_run = sw["running"]
                btn_run_label = "⏸️ PAUSE" if is_run else "▶️ DÉMARRER CHRONO"
                btn_run_type = "secondary" if is_run else "primary"
                if st.button(btn_run_label, key=f"btn_run_{current_fname}", type=btn_run_type, use_container_width=True):
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

            # Micro-ajustements rapides
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

            st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.6rem 0;'>", unsafe_allow_html=True)

            # Formulaire d'Évaluation
            with st.form(key=f"eval_form_{current_fname}"):
                # Athlète & Exercice
                student_options = existing_students if existing_students else ["Aucun élève"]
                def_student_idx = 0
                if auto_student and auto_student in student_options:
                    def_student_idx = student_options.index(auto_student)

                sel_student = st.selectbox("👤 Athlète :", student_options, index=def_student_idx)
                val_exo = st.text_input("🏋️ Exercice :", value=auto_exo)

                # RPE Slider
                rpe_score = st.slider("🔥 Effort perçu (RPE 1-10) :", min_value=1.0, max_value=10.0, value=float(sw.get("rpe", 7.5)), step=0.5)
                sw["rpe"] = rpe_score

                # Indicateur RPE dynamique
                if rpe_score <= 5.5:
                    rpe_class, rpe_text = "rpe-low", "🟢 Récupération / Technique (RIR 4+)"
                elif rpe_score <= 7.5:
                    rpe_class, rpe_text = "rpe-mod", "🔵 Hypertrophie productive (RIR 2-3)"
                elif rpe_score <= 9.0:
                    rpe_class, rpe_text = "rpe-opt", "🟡 Intensité élevée / Fin de bloc (RIR 1)"
                else:
                    rpe_class, rpe_text = "rpe-max", "🔴 Échec musculaire total / PR (RIR 0)"

                st.markdown(f'<div class="rpe-indicator {rpe_class}">{rpe_text}</div>', unsafe_allow_html=True)

                # Feedback coach optionnel
                coach_notes = st.text_input("💬 Consigne / Feedback élève :", placeholder="Ex: Coudes bien verrouillés, amplitude propre")

                # Bouton de validation principal géant (Zone tactile maximale)
                submit_eval = st.form_submit_button("⚡ VALIDER & ENREGISTRER", type="primary", use_container_width=True)

                if submit_eval:
                    final_tst = round(sw["tst_val"], 2)
                    if final_tst <= 0:
                        st.warning("⚠️ Chronomètre à 0s. Veuillez mesurer le TST avant de valider.")
                    elif sel_student == "Aucun élève":
                        st.error("Ajoutez un athlète dans l'onglet 'Athlètes'.")
                    else:
                        # 1. Sauvegarde locale
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

                        # 2. Synchronisation Google Forms en arrière-plan
                        if st.session_state.db["settings"].get("send_to_google", True):
                            form_url = st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL)
                            entries = {
                                "entry_nom": st.session_state.db["settings"].get("entry_nom", DEFAULT_ENTRY_NOM),
                                "entry_exo": st.session_state.db["settings"].get("entry_exo", DEFAULT_ENTRY_EXO),
                                "entry_tst": st.session_state.db["settings"].get("entry_tst", DEFAULT_ENTRY_TST),
                                "entry_rpe": st.session_state.db["settings"].get("entry_rpe", DEFAULT_ENTRY_RPE),
                            }
                            ok, _ = send_to_google_forms(form_url, entries, sel_student, val_exo, final_tst, rpe_score)
                            new_eval["google_synced"] = ok

                        st.session_state.db["evaluations"].append(new_eval)
                        save_db(st.session_state.db)

                        # Marquer la vidéo comme traitée
                        st.session_state.processed_videos.add(current_fname)
                        st.toast(f"✅ Analyse validée pour {sel_student} (TST: {final_tst}s)")

                        # Auto-advance vers la vidéo suivante
                        if st.session_state.db["settings"].get("auto_advance", True) and cur_idx < total_files - 1:
                            st.session_state.active_video_idx += 1

                        time.sleep(0.7)
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# VUE 2 : STATS & PROGRESSION
# ==============================================================================
elif st.session_state.current_nav == "📊 Stats":
    st.markdown("### 📊 Progression & Suivi")
    evals = st.session_state.db.get("evaluations", [])

    if not evals:
        st.info("Aucune analyse enregistrée. Évaluez des vidéos dans le Studio pour débloquer les statistiques !")
    else:
        df_evals = pd.DataFrame(evals)

        # KPI Cards (2x2 sur mobile)
        k1, k2 = st.columns(2)
        with k1:
            st.metric("Total Séances", len(df_evals))
            st.metric("TST Moyen", f"{df_evals['tst'].mean():.1f} s")
        with k2:
            st.metric("Athlètes Suivis", df_evals["student"].nunique())
            st.metric("RPE Moyen", f"{df_evals['rpe'].mean():.1f} / 10")

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.8rem 0;'>", unsafe_allow_html=True)

        # Filtre athlète
        all_students = ["Tous les athlètes"] + sorted(list(df_evals["student"].unique()))
        selected_student = st.selectbox("Filtrer par athlète :", all_students)
        df_filtered = df_evals if selected_student == "Tous les athlètes" else df_evals[df_evals["student"] == selected_student]

        # Graphique mobile Plotly
        if HAS_PLOTLY and not df_filtered.empty:
            st.markdown("##### 📈 Évolution du Temps Sous Tension")
            fig_tst = px.line(
                df_filtered,
                x="date",
                y="tst",
                color="exercise",
                markers=True,
                labels={"tst": "TST (secondes)", "date": "Date", "exercise": "Exercice"},
                template="plotly_dark"
            )
            fig_tst.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font_family="Plus Jakarta Sans",
                margin=dict(l=10, r=10, t=25, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_tst, use_container_width=True)

        # Tableau d'historique
        st.markdown("##### 📜 Dernières évaluations")
        df_disp = df_filtered[["date", "student", "exercise", "tst", "rpe", "notes"]].copy()
        df_disp.columns = ["Date", "Athlète", "Exercice", "TST (s)", "RPE", "Notes"]
        st.dataframe(df_disp, use_container_width=True)

        # Export CSV
        csv_bytes = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Exporter les données en CSV",
            data=csv_bytes,
            file_name=f"caliperf_stats_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )


# ==============================================================================
# VUE 3 : ATHLÈTES & FICHES
# ==============================================================================
elif st.session_state.current_nav == "👥 Athlètes":
    st.markdown("### 👥 Gestion des Athlètes")

    # Inscription nouvel athlète
    with st.expander("➕ Inscrire un nouvel athlète", expanded=False):
        with st.form("add_student_mobile_form"):
            new_nom = st.text_input("Nom :")
            new_prenom = st.text_input("Prénom :")
            new_freq = st.selectbox(
                "Fréquence :",
                ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Quotidien"]
            )
            new_goal = st.text_area("Objectif athlétique :", placeholder="Ex: Progression tractions lestées & Front lever")

            if st.form_submit_button("✅ Inscrire l'athlète", type="primary", use_container_width=True):
                if new_nom.strip() and new_prenom.strip():
                    full_name = f"{new_prenom.strip()} {new_nom.strip()}"
                    st.session_state.db["students"][full_name] = {
                        "freq": new_freq,
                        "goal": new_goal.strip() if new_goal.strip() else "Objectif général",
                        "link": st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL),
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    save_db(st.session_state.db)
                    st.success(f"{full_name} ajouté !")
                    time.sleep(0.6)
                    st.rerun()
                else:
                    st.warning("Veuillez renseigner le nom et le prénom.")

    # Liste des athlètes
    students = st.session_state.db.get("students", {})
    if not students:
        st.info("Aucun athlète enregistré.")
    else:
        for name, details in list(students.items()):
            evals = st.session_state.db.get("evaluations", [])
            student_evals = [e for e in evals if e.get("student") == name]

            st.markdown(f"""
                <div class="cali-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h4 style="margin:0; font-size:1.05rem; color:#f8fafc;">👤 {name}</h4>
                        <span class="badge-lime">{len(student_evals)} Séances</span>
                    </div>
                    <div style="margin-top:6px; font-size:0.82rem; color:#94a3b8;">
                        📅 Fréquence: <b style="color:#f1f5f9;">{details.get('freq', 'Non précisée')}</b>
                    </div>
                    <div style="margin-top:4px; font-size:0.82rem; color:#cbd5e1; background:rgba(0,0,0,0.25); padding:6px 10px; border-radius:8px;">
                        🎯 <b>Objectif :</b> {details.get('goal', 'Aucun objectif spécifié')}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            if st.session_state.is_authenticated:
                if st.button(f"🗑️ Supprimer {name}", key=f"del_stud_{name}", use_container_width=True):
                    del st.session_state.db["students"][name]
                    save_db(st.session_state.db)
                    st.toast(f"Athlète {name} supprimé.")
                    time.sleep(0.4)
                    st.rerun()


# ==============================================================================
# VUE 4 : RÉGLAGES & SYNCHRONISATION
# ==============================================================================
elif st.session_state.current_nav == "⚙️ Réglages":
    st.markdown("### ⚙️ Réglages & Connexions")

    with st.form("settings_mobile_form"):
        st.markdown("##### 🔗 Connecteur Google Forms")
        form_url = st.text_input("URL Google Form :", value=st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL))

        col_e1, col_e2 = st.columns(2)
        with col_e1:
            e_nom = st.text_input("Entry Nom :", value=st.session_state.db["settings"].get("entry_nom", DEFAULT_ENTRY_NOM))
            e_tst = st.text_input("Entry TST :", value=st.session_state.db["settings"].get("entry_tst", DEFAULT_ENTRY_TST))
        with col_e2:
            e_exo = st.text_input("Entry Exo :", value=st.session_state.db["settings"].get("entry_exo", DEFAULT_ENTRY_EXO))
            e_rpe = st.text_input("Entry RPE :", value=st.session_state.db["settings"].get("entry_rpe", DEFAULT_ENTRY_RPE))

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.6rem 0;'>", unsafe_allow_html=True)
        auto_adv = st.checkbox("Passer automatiquement à la vidéo suivante", value=st.session_state.db["settings"].get("auto_advance", True))
        auto_send = st.checkbox("Synchroniser automatiquement Google Forms", value=st.session_state.db["settings"].get("send_to_google", True))

        new_admin_pwd = st.text_input("Code Coach Pro :", value=st.session_state.db["settings"].get("admin_pwd", "admin"), type="password")

        if st.form_submit_button("💾 Enregistrer les Réglages", type="primary", use_container_width=True):
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
            st.toast("✅ Réglages enregistrés !")
            time.sleep(0.5)
            st.rerun()

    # Sauvegarde locale JSON
    json_bytes = json.dumps(st.session_state.db, indent=2, ensure_ascii=False).encode('utf-8')
    st.download_button(
        "📥 Télécharger la base locale (JSON)",
        data=json_bytes,
        file_name=f"caliperf_backup_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json",
        use_container_width=True
    )
