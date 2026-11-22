"""
Caliperf V2 - Espace Coaching & Performance
Application responsive Mobile-First & Desktop avec navigation tactile au swipe,
calcul automatique de la Charge d'Entraînement (TST x RPE), et synchronisation moderne Google Sheets / Webhook.
"""

import os
import json
import time
import re
from datetime import datetime
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

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
    initial_sidebar_state="collapsed"
)

DB_FILE = "caliperf_db.json"
DEFAULT_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"
DEFAULT_ENTRY_NOM = "entry.1847695661"
DEFAULT_ENTRY_EXO = "entry.1595307876"
DEFAULT_ENTRY_TST = "entry.549289703"
DEFAULT_ENTRY_RPE = "entry.46344190"

# ==============================================================================
# 2. GESTIONNAIRE DE BASE DE DONNÉES (AVEC CALCUL DE CHARGE TST x RPE)
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
            "sync_mode": "google_forms",  # "local_only", "google_forms", "gsheet_webhook"
            "webhook_url": "",
            "form_url": DEFAULT_FORM_URL,
            "entry_nom": DEFAULT_ENTRY_NOM,
            "entry_exo": DEFAULT_ENTRY_EXO,
            "entry_tst": DEFAULT_ENTRY_TST,
            "entry_rpe": DEFAULT_ENTRY_RPE,
            "admin_pwd": "admin",
            "auto_advance": True
        }
    }

def load_db():
    """Charge la base JSON avec migration automatique si ancien format."""
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
        else:
            # Compatibilité anciens réglages
            if "sync_mode" not in raw["settings"]:
                raw["settings"]["sync_mode"] = "google_forms"
            if "webhook_url" not in raw["settings"]:
                raw["settings"]["webhook_url"] = ""

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

# ==============================================================================
# 3. CSS RESPONSIVE & MOBILE SAFE-AREA FIX
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        -webkit-tap-highlight-color: transparent;
        touch-action: manipulation;
    }

    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at 10% 12%, #0e172a 0%, #070d19 45%, #03050a 100%);
        color: #f1f5f9;
    }

    /* FIX CRITIQUE DU HAUT D'ÉCRAN MOBILE (NOTCH & HEADER STREAMLIT) */
    .block-container {
        padding-top: calc(4.2rem + env(safe-area-inset-top, 0px)) !important;
        padding-bottom: calc(2.5rem + env(safe-area-inset-bottom, 0px)) !important;
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
        max-width: 1250px !important;
    }

    [data-testid="stHeader"] {
        background: rgba(7, 13, 25, 0.88) !important;
        backdrop-filter: blur(12px) !important;
        height: 3.5rem !important;
    }

    @media (min-width: 769px) {
        .block-container {
            padding-top: 2.5rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
    }

    /* LECTEUR VIDÉO RESPONSIVE (Ne bloque pas l'écran sur mobile) */
    video {
        max-height: 40vh !important;
        width: 100% !important;
        object-fit: contain !important;
        background: #000 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5) !important;
    }

    @media (min-width: 769px) {
        video {
            max-height: 56vh !important;
        }
    }

    /* ONGLETS / TABS TACTILES STYLE SEGMENTED CONTROL */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px !important;
        background: rgba(15, 23, 42, 0.85) !important;
        padding: 6px !important;
        border-radius: 14px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        display: flex !important;
        margin-bottom: 1rem !important;
        overflow-x: auto !important;
    }

    .stTabs [data-baseweb="tab"] {
        flex: 1 !important;
        min-height: 48px !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        color: #94a3b8 !important;
        background: transparent !important;
        border: none !important;
        text-align: center !important;
        white-space: nowrap !important;
        transition: all 0.2s ease !important;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #00f0ff, #0088ff) !important;
        color: #030712 !important;
        font-weight: 800 !important;
        box-shadow: 0 4px 16px rgba(0, 240, 255, 0.4) !important;
    }

    /* CARTES & BADGES */
    .cali-card {
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 14px;
        padding: 1rem 1.15rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
        margin-bottom: 0.9rem;
    }

    .badge-cyan {
        background: rgba(0, 240, 255, 0.12);
        color: #00f0ff;
        border: 1px solid rgba(0, 240, 255, 0.35);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        display: inline-block;
    }

    .badge-lime {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        display: inline-block;
    }

    .badge-amber {
        background: rgba(245, 158, 11, 0.15);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        display: inline-block;
    }

    /* DIGITAL TIMER */
    .digital-timer {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.7rem;
        font-weight: 700;
        color: #00f0ff;
        text-shadow: 0 0 18px rgba(0, 240, 255, 0.45);
        letter-spacing: -0.02em;
        line-height: 1;
        margin: 0.2rem 0 0.4rem 0;
    }

    .digital-sub {
        font-size: 0.76rem;
        color: #94a3b8;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* CHARGE D'ENTRAÎNEMENT CARTOUCHE */
    .charge-card {
        background: linear-gradient(135deg, rgba(0, 240, 255, 0.08), rgba(59, 130, 246, 0.12));
        border: 1px solid rgba(0, 240, 255, 0.25);
        border-radius: 10px;
        padding: 8px 12px;
        margin: 8px 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    /* RPE INDICATOR */
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
    .rpe-low { background: rgba(16, 185, 129, 0.15); border-left: 4px solid #10b981; color: #6ee7b7; }
    .rpe-mod { background: rgba(59, 130, 246, 0.15); border-left: 4px solid #3b82f6; color: #93c5fd; }
    .rpe-opt { background: rgba(245, 158, 11, 0.15); border-left: 4px solid #f59e0b; color: #fde68a; }
    .rpe-max { background: rgba(239, 68, 68, 0.2); border-left: 4px solid #ef4444; color: #fca5a5; }

    /* BOUTONS POUCE (TACTILE) */
    .stButton>button {
        border-radius: 9px !important;
        font-weight: 600 !important;
        min-height: 48px !important;
        font-size: 0.95rem !important;
        transition: all 0.15s ease !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
    }
    .stButton>button:active {
        transform: scale(0.97) !important;
    }

    /* HEADER APP BANNER */
    .app-brand-banner {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.6rem;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. GESTIONNAIRE DE GESTE SWIPE MOBILE (JAVASCRIPT CLIENT-SIDE)
# ==============================================================================
swipe_gesture_js = """
<script>
(function() {
    try {
        const doc = (window.parent && window.parent.document) ? window.parent.document : document;
        let startX = 0;
        let startY = 0;
        let startTime = 0;

        function getTabButtons() {
            return doc.querySelectorAll('button[data-baseweb="tab"], [role="tab"]');
        }

        doc.addEventListener('touchstart', function(e) {
            if (!e.changedTouches || e.changedTouches.length === 0) return;
            const target = e.target;
            // Ne pas intercepter si on touche un champ, slider, vidéo ou bouton de réglage
            if (target.closest('input, textarea, select, video, [role="slider"], .stSlider, .stNumberInput, .stVideo')) {
                return;
            }
            startX = e.changedTouches[0].clientX;
            startY = e.changedTouches[0].clientY;
            startTime = Date.now();
        }, { passive: true });

        doc.addEventListener('touchend', function(e) {
            if (!e.changedTouches || e.changedTouches.length === 0) return;
            const target = e.target;
            if (target.closest('input, textarea, select, video, [role="slider"], .stSlider, .stNumberInput, .stVideo')) {
                return;
            }
            const endX = e.changedTouches[0].clientX;
            const endY = e.changedTouches[0].clientY;
            const elapsed = Date.now() - startTime;

            const deltaX = endX - startX;
            const deltaY = endY - startY;

            // Swipe horizontal valide : distance >= 55px, temps < 800ms, direction nettement horizontale
            if (elapsed < 800 && Math.abs(deltaX) > 55 && Math.abs(deltaX) > Math.abs(deltaY) * 1.4) {
                const tabs = getTabButtons();
                if (!tabs || tabs.length < 2) return;

                let activeIdx = 0;
                for (let i = 0; i < tabs.length; i++) {
                    if (tabs[i].getAttribute('aria-selected') === 'true' || tabs[i].classList.contains('active')) {
                        activeIdx = i;
                        break;
                    }
                }

                if (deltaX < 0 && activeIdx < tabs.length - 1) {
                    // Glisser vers la gauche -> Onglet Suivant
                    tabs[activeIdx + 1].click();
                    if (navigator.vibrate) navigator.vibrate(18);
                } else if (deltaX > 0 && activeIdx > 0) {
                    // Glisser vers la droite -> Onglet Précédent
                    tabs[activeIdx - 1].click();
                    if (navigator.vibrate) navigator.vibrate(18);
                }
            }
        }, { passive: true });
    } catch(e) {
        console.warn("Swipe gesture init info:", e);
    }
})();
</script>
"""
components.html(swipe_gesture_js, height=0)

# ==============================================================================
# 5. SYNCHRONISATION MODERNE (GOOGLE SHEETS WEBHOOK / GOOGLE FORMS)
# ==============================================================================
def detect_student_and_exercise(filename, student_list):
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

def dispatch_sync_evaluation(settings, student, exercise, tst_val, rpe_val, charge_val, notes, date_str):
    """
    Envoi des données selon le mode configuré par le coach :
    1. 'gsheet_webhook' : Webhook direct Google Sheets (JSON structuré avec calcul de Charge)
    2. 'google_forms' : Formulaire Google Forms legacy
    3. 'local_only' : Sauvegarde interne uniquement
    """
    mode = settings.get("sync_mode", "google_forms")

    if mode == "gsheet_webhook":
        wh_url = settings.get("webhook_url", "").strip()
        if not wh_url:
            return False, "URL Webhook vide"
        payload = {
            "date": date_str,
            "student": student,
            "exercise": exercise,
            "tst": tst_val,
            "rpe": rpe_val,
            "charge": charge_val,
            "notes": notes
        }
        try:
            r = requests.post(wh_url, json=payload, timeout=4)
            return r.status_code == 200, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)

    elif mode == "google_forms":
        form_url = settings.get("form_url", DEFAULT_FORM_URL)
        payload = {
            settings.get("entry_nom", DEFAULT_ENTRY_NOM): student,
            settings.get("entry_exo", DEFAULT_ENTRY_EXO): exercise,
            settings.get("entry_tst", DEFAULT_ENTRY_TST): str(round(tst_val, 2)).replace('.', ','),
            settings.get("entry_rpe", DEFAULT_ENTRY_RPE): str(rpe_val)
        }
        try:
            r = requests.post(form_url, data=payload, timeout=4)
            return r.status_code == 200, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)

    return True, "Mode local"


# ==============================================================================
# 6. EN-TÊTE PRINCIPAL & ONGLETIS GESTIONNAIRE DE VUE (SWIPABLE)
# ==============================================================================
st.markdown("""
    <div class="app-brand-banner">
        <div style="display:flex; align-items:center; gap:8px;">
            <div style="background: linear-gradient(135deg, #00f0ff, #0077ff); padding: 6px 10px; border-radius: 10px;">
                <span style="font-size: 17px;">⚡</span>
            </div>
            <div>
                <span style="font-size: 1.25rem; font-weight:800; letter-spacing: -0.02em;">CALIPERF</span>
                <span style="color:#00f0ff; font-weight:800; font-size:1.25rem;">PRO</span>
            </div>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
            <span class="badge-cyan">📲 Swipe Actif</span>
        </div>
    </div>
""", unsafe_allow_html=True)

# Les 4 compartiments principaux sous forme d'onglets réactifs
tab_studio, tab_stats, tab_athletes, tab_settings = st.tabs([
    "🎥 Studio",
    "📊 Stats",
    "👥 Athlètes",
    "⚙️ Réglages"
])


# ==============================================================================
# COMPARTIMENT 1 : STUDIO VIDÉO & CHRONOMÉTRAGE TST
# ==============================================================================
with tab_studio:
    # 1. Zone d'importation
    with st.expander("📁 Importer des vidéos (Galerie Smartphone ou PC)", expanded=False):
        uploaded_files = st.file_uploader(
            "Importer les vidéos (.mp4, .mov, .avi)",
            type=['mp4', 'mov', 'avi'],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

    if not uploaded_files:
        st.markdown("""
            <div class="cali-card" style="text-align:center; padding: 2rem 1rem; margin-top: 0.4rem;">
                <div style="font-size: 2.3rem; margin-bottom: 0.3rem;">📲</div>
                <h3 style="margin-bottom: 0.2rem; font-size: 1.15rem;">Studio Prêt</h3>
                <p style="color:#94a3b8; font-size: 0.88rem; max-width: 440px; margin: 0 auto;">
                    Touchez <b>Importer des vidéos</b> pour charger vos séances.<br>
                    <small style="color:#00f0ff;">Astuce : glissez l'écran vers la gauche pour voir les Stats ou les Athlètes 👉</small>
                </p>
            </div>
        """, unsafe_allow_html=True)
    else:
        files_dict = {f.name: f for f in uploaded_files}
        file_names = list(files_dict.keys())
        total_files = len(file_names)

        cur_idx = min(st.session_state.active_video_idx, total_files - 1)
        st.session_state.active_video_idx = cur_idx
        current_fname = file_names[cur_idx]
        current_file = files_dict[current_fname]

        # File d'attente ergonomique
        col_prev, col_status, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀️ Préc.", key="btn_prev_vid", use_container_width=True, disabled=(cur_idx == 0)):
                st.session_state.active_video_idx = max(0, cur_idx - 1)
                st.rerun()
        with col_status:
            is_analyzed = current_fname in st.session_state.processed_videos
            badge_type = "badge-lime" if is_analyzed else "badge-amber"
            status_text = "✅ Validée" if is_analyzed else "⏳ En attente"
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

        # Détection automatique de l'athlète et de l'exercice
        existing_students = list(st.session_state.db["students"].keys())
        auto_student, auto_exo = detect_student_and_exercise(current_fname, existing_students)

        # Chronomètre de la vidéo
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

        col_video, col_tools = st.columns([1.5, 1.2], gap="medium")

        with col_video:
            st.video(current_file)

            # Repères temporels In / Out
            st.markdown("""
                <div class="cali-card" style="padding: 9px 12px; margin-top: 6px;">
                    <div style="font-weight:700; font-size:0.75rem; color:#94a3b8; text-transform:uppercase; letter-spacing:0.04em;">
                        🎯 Repères Début/Fin du Set (Précision Cadre)
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
            if st.button(f"⚡ Appliquer : TST = {diff_marker}s", use_container_width=True, key=f"apply_{current_fname}", disabled=(diff_marker <= 0)):
                sw["tst_val"] = diff_marker
                st.toast(f"✅ TST fixé à {diff_marker}s")
                st.rerun()

        with col_tools:
            st.markdown('<div class="cali-card">', unsafe_allow_html=True)

            disp_tst = sw["tst_val"]
            st.markdown(f"""
                <div style="text-align: center; padding: 0.1rem 0 0.3rem 0;">
                    <span class="digital-sub">TEMPS SOUS TENSION (TST)</span>
                    <div class="digital-timer">{disp_tst:.2f}<span style="font-size:1.3rem; color:#94a3b8;"> s</span></div>
                </div>
            """, unsafe_allow_html=True)

            # Contrôles Chrono
            c_run, c_raz = st.columns([1.5, 1])
            with c_run:
                is_run = sw["running"]
                btn_label = "⏸️ PAUSE" if is_run else "▶️ DÉMARRER CHRONO"
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

            # Ajustements rapides
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

            st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.5rem 0;'>", unsafe_allow_html=True)

            # Formulaire d'Évaluation
            with st.form(key=f"eval_form_{current_fname}"):
                student_options = existing_students if existing_students else ["Aucun élève"]
                def_student_idx = 0
                if auto_student and auto_student in student_options:
                    def_student_idx = student_options.index(auto_student)

                sel_student = st.selectbox("👤 Athlète :", student_options, index=def_student_idx)
                val_exo = st.text_input("🏋️ Exercice :", value=auto_exo)

                # Slider RPE
                rpe_score = st.slider("🔥 Effort perçu (RPE 1-10) :", min_value=1.0, max_value=10.0, value=float(sw.get("rpe", 7.5)), step=0.5)
                sw["rpe"] = rpe_score

                # Calcul en direct de la Charge d'Entraînement
                calc_charge = round(disp_tst * rpe_score, 1)

                st.markdown(f"""
                    <div class="charge-card">
                        <span style="font-size:0.8rem; color:#94a3b8; font-weight:600;">⚡ CHARGE DU SET (TST × RPE)</span>
                        <span style="font-size:1.15rem; font-weight:800; color:#00f0ff;">{calc_charge} <small style="font-size:0.75rem; color:#cbd5e1;">UA</small></span>
                    </div>
                """, unsafe_allow_html=True)

                if rpe_score <= 5.5:
                    rpe_class, rpe_text = "rpe-low", "🟢 Récupération / Technique (RIR 4+)"
                elif rpe_score <= 7.5:
                    rpe_class, rpe_text = "rpe-mod", "🔵 Hypertrophie productive (RIR 2-3)"
                elif rpe_score <= 9.0:
                    rpe_class, rpe_text = "rpe-opt", "🟡 Intensité élevée / Fin de bloc (RIR 1)"
                else:
                    rpe_class, rpe_text = "rpe-max", "🔴 Échec musculaire total / PR (RIR 0)"

                st.markdown(f'<div class="rpe-indicator {rpe_class}">{rpe_text}</div>', unsafe_allow_html=True)

                coach_notes = st.text_input("💬 Feedback / Consigne :", placeholder="Ex: Coudes bien verrouillés, tempo respecté")

                submit_eval = st.form_submit_button("⚡ VALIDER & ENREGISTRER", type="primary", use_container_width=True)

                if submit_eval:
                    final_tst = round(sw["tst_val"], 2)
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
                            "charge": calc_charge,
                            "video_name": current_fname,
                            "date": now_str,
                            "notes": coach_notes,
                            "synced": False
                        }

                        # Envoi selon le connecteur choisi
                        ok_sync, msg_sync = dispatch_sync_evaluation(
                            st.session_state.db["settings"],
                            sel_student,
                            val_exo,
                            final_tst,
                            rpe_score,
                            calc_charge,
                            coach_notes,
                            now_str
                        )
                        new_eval["synced"] = ok_sync

                        st.session_state.db["evaluations"].append(new_eval)
                        save_db(st.session_state.db)

                        st.session_state.processed_videos.add(current_fname)
                        st.toast(f"✅ Séance validée : {sel_student} (Charge: {calc_charge} UA)")

                        if st.session_state.db["settings"].get("auto_advance", True) and cur_idx < total_files - 1:
                            st.session_state.active_video_idx += 1

                        time.sleep(0.6)
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# COMPARTIMENT 2 : STATS, CHARGE D'ENTRAÎNEMENT & HISTORIQUE
# ==============================================================================
with tab_stats:
    st.markdown("### 📊 Statistiques & Suivi de Charge")
    evals = st.session_state.db.get("evaluations", [])

    if not evals:
        st.info("Aucune analyse enregistrée. Évaluez vos premières vidéos dans le Studio !")
    else:
        df_evals = pd.DataFrame(evals)
        if "charge" not in df_evals.columns:
            df_evals["charge"] = (df_evals["tst"] * df_evals["rpe"]).round(1)

        # 4 KPIs
        k1, k2 = st.columns(2)
        with k1:
            st.metric("Total Séances", len(df_evals))
            st.metric("TST Moyen", f"{df_evals['tst'].mean():.1f} s")
        with k2:
            st.metric("Charge Moyenne", f"{df_evals['charge'].mean():.1f} UA")
            st.metric("RPE Moyen", f"{df_evals['rpe'].mean():.1f} / 10")

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.8rem 0;'>", unsafe_allow_html=True)

        all_students = ["Tous les athlètes"] + sorted(list(df_evals["student"].unique()))
        selected_student = st.selectbox("Filtrer par athlète :", all_students, key="stats_filter_student")
        df_filtered = df_evals if selected_student == "Tous les athlètes" else df_evals[df_evals["student"] == selected_student]

        if HAS_PLOTLY and not df_filtered.empty:
            tab_g1, tab_g2 = st.tabs(["📈 Évolution TST", "⚡ Charge d'Entraînement"])

            with tab_g1:
                fig_tst = px.line(
                    df_filtered,
                    x="date",
                    y="tst",
                    color="exercise",
                    markers=True,
                    labels={"tst": "TST (s)", "date": "Date", "exercise": "Exercice"},
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

            with tab_g2:
                fig_charge = px.bar(
                    df_filtered,
                    x="date",
                    y="charge",
                    color="exercise",
                    labels={"charge": "Charge (TST x RPE)", "date": "Date"},
                    template="plotly_dark"
                )
                fig_charge.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(15,23,42,0.6)",
                    font_family="Plus Jakarta Sans",
                    margin=dict(l=10, r=10, t=25, b=20)
                )
                st.plotly_chart(fig_charge, use_container_width=True)

        # Tableau d'historique
        st.markdown("##### 📜 Registre des séances")
        df_disp = df_filtered[["date", "student", "exercise", "tst", "rpe", "charge", "notes"]].copy()
        df_disp.columns = ["Date", "Athlète", "Exercice", "TST (s)", "RPE", "Charge (UA)", "Notes"]
        st.dataframe(df_disp, use_container_width=True)

        csv_bytes = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Exporter les données (CSV / Excel)",
            data=csv_bytes,
            file_name=f"caliperf_stats_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )


# ==============================================================================
# COMPARTIMENT 3 : ATHLÈTES & FICHES
# ==============================================================================
with tab_athletes:
    st.markdown("### 👥 Dossiers Athlètes")

    with st.expander("➕ Inscrire un nouvel athlète", expanded=False):
        with st.form("add_student_tab_form"):
            new_nom = st.text_input("Nom :")
            new_prenom = st.text_input("Prénom :")
            new_freq = st.selectbox(
                "Fréquence hebdomadaire :",
                ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Quotidien"]
            )
            new_goal = st.text_area("Objectif principal :", placeholder="Ex: Débloquer le Front lever & séries de Dips à +30kg")

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
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning("Veuillez renseigner le nom et le prénom.")

    students = st.session_state.db.get("students", {})
    if not students:
        st.info("Aucun athlète dans la base.")
    else:
        for name, details in list(students.items()):
            evals = st.session_state.db.get("evaluations", [])
            student_evals = [e for e in evals if e.get("student") == name]
            total_charge = sum(e.get("charge", round(e.get("tst", 0)*e.get("rpe", 0), 1)) for e in student_evals)

            st.markdown(f"""
                <div class="cali-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h4 style="margin:0; font-size:1.05rem; color:#f8fafc;">👤 {name}</h4>
                        <span class="badge-lime">{len(student_evals)} Séances ({total_charge:.0f} UA)</span>
                    </div>
                    <div style="margin-top:6px; font-size:0.82rem; color:#94a3b8;">
                        📅 Fréquence: <b style="color:#f1f5f9;">{details.get('freq', 'Non précisée')}</b>
                    </div>
                    <div style="margin-top:4px; font-size:0.82rem; color:#cbd5e1; background:rgba(0,0,0,0.25); padding:6px 10px; border-radius:8px;">
                        🎯 <b>Objectif :</b> {details.get('goal', 'Aucun objectif spécifié')}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            if st.button(f"🗑️ Supprimer {name}", key=f"del_stud_{name}", use_container_width=True):
                del st.session_state.db["students"][name]
                save_db(st.session_state.db)
                st.toast(f"Athlète {name} supprimé.")
                time.sleep(0.4)
                st.rerun()


# ==============================================================================
# COMPARTIMENT 4 : RÉGLAGES & CONNECTEURS CLOUD
# ==============================================================================
with tab_settings:
    st.markdown("### ⚙️ Paramètres & Synchronisation")

    with st.form("settings_full_form"):
        st.markdown("##### 🌐 Mode de Synchronisation des Données")
        sync_mode = st.radio(
            "Comment souhaitez-vous enregistrer vos données d'analyse ?",
            [
                ("google_forms", "📝 Google Forms (Méthode actuelle avec entry IDs)"),
                ("gsheet_webhook", "🚀 Google Sheets Direct (Sans formulaire, via Webhook Apps Script)"),
                ("local_only", "💾 Caliperf Local uniquement (100% hors-ligne, zéro latence)")
            ],
            format_func=lambda x: x[1],
            index=0 if st.session_state.db["settings"].get("sync_mode") == "google_forms" else (1 if st.session_state.db["settings"].get("sync_mode") == "gsheet_webhook" else 2)
        )[0]

        if sync_mode == "gsheet_webhook":
            st.markdown("""
                <div style="background:rgba(0,240,255,0.08); padding:10px; border-radius:8px; font-size:0.82rem; color:#cbd5e1; margin-bottom:8px;">
                    💡 <b>Pourquoi c'est mieux que Google Forms ?</b><br>
                    Les données sont insérées directement dans votre Google Sheet en temps réel, sans passer par un formulaire intermédiaire, et la Charge d'Entraînement (TST x RPE) est automatiquement calculée !
                </div>
            """, unsafe_allow_html=True)
            wh_url_input = st.text_input("URL Webhook Google Apps Script :", value=st.session_state.db["settings"].get("webhook_url", ""))
        else:
            wh_url_input = st.session_state.db["settings"].get("webhook_url", "")

        if sync_mode == "google_forms":
            form_url = st.text_input("URL Google Form (formResponse) :", value=st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL))
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                e_nom = st.text_input("Entry Nom :", value=st.session_state.db["settings"].get("entry_nom", DEFAULT_ENTRY_NOM))
                e_tst = st.text_input("Entry TST :", value=st.session_state.db["settings"].get("entry_tst", DEFAULT_ENTRY_TST))
            with col_e2:
                e_exo = st.text_input("Entry Exo :", value=st.session_state.db["settings"].get("entry_exo", DEFAULT_ENTRY_EXO))
                e_rpe = st.text_input("Entry RPE :", value=st.session_state.db["settings"].get("entry_rpe", DEFAULT_ENTRY_RPE))
        else:
            form_url = st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL)
            e_nom = st.session_state.db["settings"].get("entry_nom", DEFAULT_ENTRY_NOM)
            e_tst = st.session_state.db["settings"].get("entry_tst", DEFAULT_ENTRY_TST)
            e_exo = st.session_state.db["settings"].get("entry_exo", DEFAULT_ENTRY_EXO)
            e_rpe = st.session_state.db["settings"].get("entry_rpe", DEFAULT_ENTRY_RPE)

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.8rem 0;'>", unsafe_allow_html=True)
        st.markdown("##### ⚡ Ergonomie du Studio")
        auto_adv = st.checkbox("Passer automatiquement à la vidéo suivante après validation", value=st.session_state.db["settings"].get("auto_advance", True))

        if st.form_submit_button("💾 Enregistrer la configuration", type="primary", use_container_width=True):
            st.session_state.db["settings"] = {
                "sync_mode": sync_mode,
                "webhook_url": wh_url_input.strip(),
                "form_url": form_url.strip(),
                "entry_nom": e_nom.strip(),
                "entry_exo": e_exo.strip(),
                "entry_tst": e_tst.strip(),
                "entry_rpe": e_rpe.strip(),
                "admin_pwd": st.session_state.db["settings"].get("admin_pwd", "admin"),
                "auto_advance": auto_adv
            }
            save_db(st.session_state.db)
            st.toast("✅ Configuration sauvegardée !")
            time.sleep(0.5)
            st.rerun()

    # Guide de mise en place Webhook Google Sheet
    with st.expander("📄 Voir le script pour connecter un Google Sheet en 1 minute", expanded=False):
        st.markdown("""
        Si vous voulez vous débarrasser définitivement de Google Forms, collez ce petit script dans votre Google Sheet (*Extensions > Apps Script*) puis cliquez sur **Déployer > Nouveau déploiement (Application Web, accès Tout le monde)** :

        ```javascript
        function doPost(e) {
          var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
          var data = JSON.parse(e.postData.contents);
          sheet.appendRow([data.date, data.student, data.exercise, data.tst, data.rpe, data.charge, data.notes]);
          return ContentService.createTextOutput("OK");
        }
        ```
        Collez ensuite l'URL fournie dans le champ Webhook ci-dessus !
        """)

    # Sauvegarde locale JSON
    json_bytes = json.dumps(st.session_state.db, indent=2, ensure_ascii=False).encode('utf-8')
    st.download_button(
        "📥 Télécharger la sauvegarde complète (JSON)",
        data=json_bytes,
        file_name=f"caliperf_backup_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json",
        use_container_width=True
    )
