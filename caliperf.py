"""
Caliperf V2 - Espace Coaching & Performance
Application responsive Mobile-First & Desktop avec navigation tactile au swipe fluide,
mesure pure du TST & RPE (sans multiplicateurs), et module d'Auto-Track IA pour le comptage de reps et TST.
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

# Import optionnel du SDK Gemini pour l'Auto-Track IA
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

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
# 2. GESTIONNAIRE DE BASE DE DONNÉES (LOGIQUE PURE : TST & RPE)
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
            "sync_mode": "google_forms",  # "google_forms", "gsheet_webhook", "local_only"
            "webhook_url": "",
            "form_url": DEFAULT_FORM_URL,
            "entry_nom": DEFAULT_ENTRY_NOM,
            "entry_exo": DEFAULT_ENTRY_EXO,
            "entry_tst": DEFAULT_ENTRY_TST,
            "entry_rpe": DEFAULT_ENTRY_RPE,
            "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
            "admin_pwd": "admin",
            "auto_advance": True
        }
    }

def load_db():
    """Charge la base JSON avec migration automatique propre."""
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
            if "sync_mode" not in raw["settings"]:
                raw["settings"]["sync_mode"] = "google_forms"
            if "webhook_url" not in raw["settings"]:
                raw["settings"]["webhook_url"] = ""
            if "gemini_api_key" not in raw["settings"]:
                raw["settings"]["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "")

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
# 3. DIRECTION ARTISTIQUE & DESIGN SYSTEM (DARK KINETIC FLUIDE)
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        -webkit-tap-highlight-color: transparent;
        touch-action: pan-y pinch-zoom;
    }

    [data-testid="stAppViewContainer"] {
        background: radial-gradient(circle at 15% 12%, #0e172a 0%, #070d19 45%, #03050a 100%);
        color: #f1f5f9;
        overflow-x: hidden;
    }

    /* PADDING HAUT D'ÉCRAN SÉCURISÉ (NOTCH SMARTPHONE & HEADER STREAMLIT) */
    .block-container {
        padding-top: calc(4.2rem + env(safe-area-inset-top, 0px)) !important;
        padding-bottom: calc(2.5rem + env(safe-area-inset-bottom, 0px)) !important;
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
        max-width: 1240px !important;
    }

    [data-testid="stHeader"] {
        background: rgba(7, 13, 25, 0.85) !important;
        backdrop-filter: blur(14px) !important;
        height: 3.6rem !important;
    }

    @media (min-width: 769px) {
        .block-container {
            padding-top: 2.5rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
    }

    /* VIDÉO RESPONSIVE (40% max sur smartphone pour voir chrono + vidéo ensemble) */
    video {
        max-height: 40vh !important;
        width: 100% !important;
        object-fit: contain !important;
        background: #000 !important;
        border-radius: 14px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5) !important;
    }

    @media (min-width: 769px) {
        video {
            max-height: 56vh !important;
        }
    }

    /* BARRE D'ONGLETS TACTILES STYLE SEGMENTED PILL CONTROLLER */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px !important;
        background: rgba(15, 23, 42, 0.88) !important;
        padding: 5px !important;
        border-radius: 14px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        display: flex !important;
        margin-bottom: 0.8rem !important;
        overflow-x: auto !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
    }

    .stTabs [data-baseweb="tab"] {
        flex: 1 !important;
        min-height: 48px !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        color: #94a3b8 !important;
        background: transparent !important;
        border: none !important;
        text-align: center !important;
        white-space: nowrap !important;
        transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #00f0ff, #0077ff) !important;
        color: #030712 !important;
        font-weight: 800 !important;
        box-shadow: 0 4px 16px rgba(0, 240, 255, 0.4) !important;
    }

    /* ANIMATION FLUIDE D'ENTRÉE DES PANNEAUX (SLIDE DOUX) */
    [data-baseweb="tab-panel"] {
        animation: tabPanelSlideFade 0.28s cubic-bezier(0.16, 1, 0.3, 1) both;
        will-change: transform, opacity;
    }
    @keyframes tabPanelSlideFade {
        0% {
            opacity: 0.2;
            transform: translate3d(24px, 0, 0);
        }
        100% {
            opacity: 1;
            transform: translate3d(0, 0, 0);
        }
    }

    /* CARTES & DESIGN GLASSMORPHISM */
    .cali-card {
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 14px;
        padding: 1rem 1.15rem;
        backdrop-filter: blur(14px);
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

    /* DIGITAL TIMER GÉANT */
    .digital-timer {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.8rem;
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

    /* RPE VISUAL INDICATOR */
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

    /* BOUTONS POUCE (ZONES TACTILES >= 48px) */
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

    /* EN-TÊTE APP */
    .app-brand-banner {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.4rem;
    }

    /* INDICATEUR GUIDE GLISSEMENT MOBILE */
    .swipe-hint-pill {
        text-align: center;
        font-size: 0.72rem;
        color: #64748b;
        margin-top: -0.4rem;
        margin-bottom: 0.6rem;
        letter-spacing: 0.03em;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. GESTIONNAIRE DE GESTE SWIPE MOBILE ROBUSTE (DIRECT DOM & IFRAME COMPLIANT)
# ==============================================================================
# Ce script s'injecte directement dans le DOM principal pour garantir que les gestes
# tactiles fonctionnent sur tous les navigateurs mobiles (iOS Safari, Android Chrome)
# même en environnement Streamlit Cloud.
swipe_engine_code = """
(function() {
    function setupSwipe() {
        var targetWin = window;
        var targetDoc = document;
        try {
            if (window.parent && window.parent.document) {
                targetWin = window.parent;
                targetDoc = window.parent.document;
            }
        } catch(e) {}

        if (targetWin._caliperfSwipeEngineReady) return;
        targetWin._caliperfSwipeEngineReady = true;

        var startX = 0;
        var startY = 0;
        var currentX = 0;
        var isTracking = false;
        var isHorizontal = false;
        var startTime = 0;
        var activePanel = null;

        function getTabs() {
            return Array.from(targetDoc.querySelectorAll('button[data-baseweb="tab"], [role="tab"]'));
        }

        function getPanels() {
            return Array.from(targetDoc.querySelectorAll('div[data-baseweb="tab-panel"]'));
        }

        function getActiveIndex() {
            var tabs = getTabs();
            for (var i = 0; i < tabs.length; i++) {
                if (tabs[i].getAttribute('aria-selected') === 'true') return i;
            }
            return 0;
        }

        targetDoc.addEventListener('touchstart', function(e) {
            if (!e.touches || e.touches.length !== 1) return;
            var t = e.target;
            if (t.closest('input, textarea, select, video, .stVideo, [role="slider"], .stSlider, .stNumberInput, pre, code, button')) {
                return;
            }

            var panels = getPanels();
            var activeIdx = getActiveIndex();
            activePanel = panels[activeIdx] || null;

            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            currentX = startX;
            startTime = Date.now();
            isTracking = true;
            isHorizontal = false;
        }, { passive: true });

        targetDoc.addEventListener('touchmove', function(e) {
            if (!isTracking || !e.touches || e.touches.length !== 1) return;
            currentX = e.touches[0].clientX;
            var currentY = e.touches[0].clientY;
            var diffX = currentX - startX;
            var diffY = currentY - startY;

            if (!isHorizontal) {
                if (Math.abs(diffX) > 10 && Math.abs(diffX) > Math.abs(diffY) * 1.25) {
                    isHorizontal = true;
                } else if (Math.abs(diffY) > 12) {
                    isTracking = false;
                    return;
                }
            }

            if (isHorizontal && activePanel) {
                var dragDist = diffX * 0.35;
                activePanel.style.transform = 'translate3d(' + dragDist + 'px, 0, 0)';
                activePanel.style.transition = 'none';
            }
        }, { passive: true });

        targetDoc.addEventListener('touchend', function(e) {
            if (!isTracking) return;
            isTracking = false;

            if (activePanel) {
                activePanel.style.transform = '';
                activePanel.style.transition = 'transform 0.25s cubic-bezier(0.16, 1, 0.3, 1)';
            }

            if (!isHorizontal) return;
            isHorizontal = false;

            var diffX = currentX - startX;
            var elapsed = Date.now() - startTime;
            var screenW = targetWin.innerWidth || 360;
            var threshold = Math.min(screenW * 0.16, 55);
            var velocity = Math.abs(diffX) / Math.max(elapsed, 1);

            if (Math.abs(diffX) > threshold || (velocity > 0.28 && Math.abs(diffX) > 28)) {
                var tabs = getTabs();
                var activeIdx = getActiveIndex();

                if (diffX < 0 && activeIdx < tabs.length - 1) {
                    // Swipe gauche -> Onglet suivant
                    if (targetWin.navigator && targetWin.navigator.vibrate) {
                        targetWin.navigator.vibrate(15);
                    }
                    tabs[activeIdx + 1].click();
                } else if (diffX > 0 && activeIdx > 0) {
                    // Swipe droite -> Onglet précédent
                    if (targetWin.navigator && targetWin.navigator.vibrate) {
                        targetWin.navigator.vibrate(15);
                    }
                    tabs[activeIdx - 1].click();
                }
            }
        }, { passive: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupSwipe);
    } else {
        setupSwipe();
    }
})();
"""

# Injection double : via image onerror (top-window direct) et components.html (fallback)
escaped_js = swipe_engine_code.replace("\n", " ").replace('"', "'")
st.markdown(f'<img src="x" style="display:none;" onerror="{escaped_js}">', unsafe_allow_html=True)
components.html(f"<script>{swipe_engine_code}</script>", height=0)

# ==============================================================================
# 5. FONCTIONS MÉTIER (LOGIQUE PURE : TST & RPE)
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

def dispatch_sync_evaluation(settings, student, exercise, tst_val, rpe_val, reps_val, notes, date_str):
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
            "reps": reps_val,
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

def get_gemini_api_key():
    """Récupère la clé API Gemini de manière ultra-résiliente (Streamlit Secrets, env, base, session)."""
    try:
        if hasattr(st, "secrets"):
            if "GEMINI_API_KEY" in st.secrets:
                return str(st.secrets["GEMINI_API_KEY"]).strip()
            if "gemini_api_key" in st.secrets:
                return str(st.secrets["gemini_api_key"]).strip()
            if "general" in st.secrets and "gemini_api_key" in st.secrets["general"]:
                return str(st.secrets["general"]["gemini_api_key"]).strip()
    except Exception:
        pass

    env_k = os.getenv("GEMINI_API_KEY", "").strip()
    if env_k:
        return env_k

    db_k = st.session_state.db.get("settings", {}).get("gemini_api_key", "").strip()
    if db_k:
        return db_k

    return st.session_state.get("active_gemini_key", "").strip()

def analyze_video_with_gemini(video_file, api_key):
    """Analyse vidéo par Gemini Vision pour détecter automatiquement le TST et les répétitions."""
    if not HAS_GEMINI:
        return None, "Bibliothèque google-genai non disponible."
    if not api_key:
        return None, "Clé API Gemini manquante. Renseignez-la dans l'onglet Réglages."

    import tempfile

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Tu es un expert en biomécanique et coaching sportif spécialisé en callisthénie, "
            "street workout et musculation au poids du corps.\n\n"
            "ANALYSE CETTE VIDÉO D'ENTRAÎNEMENT en suivant ces étapes PRÉCISÉMENT :\n\n"
            "--- ÉTAPE 1 : COMPTAGE DES RÉPÉTITIONS ---\n"
            "Une répétition = UN cycle complet de mouvement (phase concentrique + phase excentrique).\n"
            "Exemples de cycles complets :\n"
            "  - Traction : corps monte jusqu'au menton au-dessus de la barre, puis redescend bras tendus\n"
            "  - Dips : corps descend puis remonte bras tendus\n"
            "  - Pompe : corps descend vers le sol puis remonte bras tendus\n"
            "  - Muscle-up : corps passe sous la barre puis au-dessus\n"
            "  - Squat : descente + remontée complète\n"
            "Compte TOUTES les répétitions réalisées, peu importe la qualité ou l'amplitude.\n"
            "Un mouvement partiel qui effectue quand même un aller-retour = 1 répétition.\n"
            "Ne compte PAS les positions statiques (maintien, isométrie) comme des répétitions.\n\n"
            "--- ÉTAPE 2 : TEMPS SOUS TENSION (TST) ---\n"
            "Identifie le moment exact (en secondes depuis le début de la vidéo) où :\n"
            "  - La PREMIÈRE répétition COMMENCE (début du premier mouvement actif)\n"
            "  - La DERNIÈRE répétition SE TERMINE (fin du dernier mouvement actif)\n"
            "TST = timestamp_fin - timestamp_début (en secondes, avec 1 décimale).\n"
            "ATTENTION : ne compte PAS le temps avant/après l'effort (préparation, repos).\n\n"
            "--- ÉTAPE 3 : NOTES TECHNIQUES ---\n"
            "Donne un très court retour technique (1-2 phrases max) sur la qualité du mouvement.\n\n"
            "--- FORMAT DE RÉPONSE ---\n"
            "Réponds UNIQUEMENT avec un objet JSON strict, sans texte autour, de la forme :\n"
            '{"tst": 24.5, "reps": 8, "debut_s": 2.1, "fin_s": 26.6, "notes": "Court retour technique."}\n'
            "Les champs debut_s et fin_s sont les timestamps en secondes.\n"
            "IMPORTANT : ne mets AUCUN texte avant ou après le JSON."
        )

        suffix = os.path.splitext(getattr(video_file, 'name', 'video.mp4'))[1] or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            video_file.seek(0)
            tmp.write(video_file.read())
            tmp_path = tmp.name

        try:
            # Upload du fichier vidéo vers l'API Gemini
            uploaded_file = client.files.upload(file=tmp_path)

            # Attente si la vidéo est en cours de traitement
            max_wait = 60
            waited = 0
            while hasattr(uploaded_file, "state") and str(getattr(uploaded_file, "state", "")).upper() == "PROCESSING" and waited < max_wait:
                time.sleep(2)
                waited += 2
                try:
                    uploaded_file = client.files.get(name=uploaded_file.name)
                except Exception:
                    break

            # Modèles actuels (nov 2026) — les anciens (2.5, 2.0, 1.5) sont retirés
            candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
            response = None
            last_err = None
            used_model = None

            for m in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=[uploaded_file, prompt]
                    )
                    if response and response.text:
                        used_model = m
                        break
                    else:
                        last_err = f"Modèle {m} : réponse vide"
                except Exception as model_err:
                    last_err = f"Modèle {m} : {model_err}"
                    response = None
                    continue

            # Nettoyage du fichier distant
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

            if not response or not response.text:
                return None, f"Aucun modèle disponible. Dernière erreur : {last_err}"

            text = response.text.strip()
            # Extraction robuste du JSON même si du texte entoure
            json_match = re.search(r'\{[^{}]*"tst"\s*:[^{}]*\}', text, re.DOTALL)
            if not json_match:
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                # Validation minimale des champs attendus
                if "tst" not in data:
                    data["tst"] = 0.0
                if "reps" not in data:
                    data["reps"] = 0
                data["_model"] = used_model
                return data, "Succès"
            return None, f"Réponse non structurée (modèle {used_model}) : {text[:150]}"

        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    except Exception as e:
        return None, f"Erreur Gemini : {str(e)}"


# ==============================================================================
# 6. EN-TÊTE PRINCIPAL & ONGLETS FLUIDES
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
            <span class="badge-cyan">📲 Glissement Tactile</span>
        </div>
    </div>
    <div class="swipe-hint-pill">👈 Glissez l'écran de gauche à droite pour naviguer 👉</div>
""", unsafe_allow_html=True)

# Les 4 compartiments
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
                    <small style="color:#00f0ff;">Glissez l'écran horizontalement pour voyager entre les sections 👉</small>
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

        existing_students = list(st.session_state.db["students"].keys())
        auto_student, auto_exo = detect_student_and_exercise(current_fname, existing_students)

        if current_fname not in st.session_state.stopwatches:
            st.session_state.stopwatches[current_fname] = {
                "tst_val": 0.0,
                "in_marker": 0.0,
                "out_marker": 0.0,
                "running": False,
                "start_time": 0.0,
                "rpe": 7.5,
                "reps": 0
            }
        sw = st.session_state.stopwatches[current_fname]

        col_video, col_tools = st.columns([1.5, 1.2], gap="medium")

        with col_video:
            st.video(current_file)

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

            # MODULE AUTO-TRACK IA & TEMPO
            with st.expander("🤖 Auto-Track IA : Détection Mouvement & Reps", expanded=False):
                st.markdown("<small style='color:#94a3b8;'>Quantification automatique du temps sous tension et des répétitions.</small>", unsafe_allow_html=True)

                gem_key = get_gemini_api_key()
                if not gem_key:
                    st.markdown("""
                        <div style="background:rgba(245,158,11,0.12); border-left:4px solid #f59e0b; padding:8px 12px; border-radius:8px; margin:8px 0; font-size:0.82rem; color:#fde68a;">
                            🔑 <b>Clé API Gemini requise :</b><br>
                            Collez votre clé Google AI Studio ci-dessous pour activer l'analyse directe.
                        </div>
                    """, unsafe_allow_html=True)
                    quick_k = st.text_input("Collez votre clé Gemini :", type="password", key=f"quick_key_inp_{current_fname}", placeholder="AIzaSy...")
                    if st.button("💾 Enregistrer la clé et débloquer", key=f"btn_save_key_{current_fname}", use_container_width=True, type="primary"):
                        if quick_k.strip():
                            st.session_state.db["settings"]["gemini_api_key"] = quick_k.strip()
                            st.session_state["active_gemini_key"] = quick_k.strip()
                            save_db(st.session_state.db)
                            st.toast("✅ Clé API enregistrée !")
                            st.rerun()
                else:
                    st.markdown('<span class="badge-lime" style="margin-bottom:8px; display:inline-block;">🟢 Clé API Active</span>', unsafe_allow_html=True)
                    if st.button("✨ Lancer l'Auto-Track IA (Vision)", key=f"ai_track_{current_fname}", use_container_width=True, type="primary"):
                        with st.spinner("🔍 Analyse IA du mouvement en cours… (peut prendre 15-30s)"):
                            ai_res, ai_msg = analyze_video_with_gemini(current_file, gem_key)
                            if ai_res:
                                sw["tst_val"] = float(ai_res.get("tst", sw["tst_val"]))
                                sw["reps"] = int(ai_res.get("reps", 0))
                                debut_s = ai_res.get("debut_s", "?")
                                fin_s = ai_res.get("fin_s", "?")
                                notes = ai_res.get("notes", "")
                                model_used = ai_res.get("_model", "?")
                                st.success(
                                    f"✅ **Détection IA réussie** (via `{model_used}`)\n\n"
                                    f"⏱️ **TST** = **{sw['tst_val']}s** (de {debut_s}s à {fin_s}s)\n\n"
                                    f"🔄 **Répétitions** = **{sw['reps']}**\n\n"
                                    f"📝 {notes}"
                                )
                                st.rerun()
                            else:
                                st.error(f"❌ Auto-Track échoué : {ai_msg}")

                c_rep1, c_rep2 = st.columns(2)
                with c_rep1:
                    reps_input = st.number_input("Nombre de répétitions :", min_value=0, max_value=100, value=int(sw.get("reps", 0)), step=1, key=f"reps_inp_{current_fname}")
                    sw["reps"] = reps_input
                with c_rep2:
                    if reps_input > 0 and sw["tst_val"] > 0:
                        tempo_rep = round(sw["tst_val"] / reps_input, 1)
                        st.markdown(f"""
                            <div style="padding-top:14px;">
                                <span style="font-size:0.75rem; color:#94a3b8;">TEMPO MOYEN / REP</span><br>
                                <b style="font-size:1.1rem; color:#00f0ff;">{tempo_rep} s / rep</b>
                            </div>
                        """, unsafe_allow_html=True)

        with col_tools:
            st.markdown('<div class="cali-card">', unsafe_allow_html=True)

            disp_tst = sw["tst_val"]
            st.markdown(f"""
                <div style="text-align: center; padding: 0.1rem 0 0.3rem 0;">
                    <span class="digital-sub">TEMPS SOUS TENSION (TST)</span>
                    <div class="digital-timer">{disp_tst:.2f}<span style="font-size:1.3rem; color:#94a3b8;"> s</span></div>
                </div>
            """, unsafe_allow_html=True)

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

            with st.form(key=f"eval_form_{current_fname}"):
                student_options = existing_students if existing_students else ["Aucun élève"]
                def_student_idx = 0
                if auto_student and auto_student in student_options:
                    def_student_idx = student_options.index(auto_student)

                sel_student = st.selectbox("👤 Athlète :", student_options, index=def_student_idx)
                val_exo = st.text_input("🏋️ Exercice :", value=auto_exo)

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

                st.markdown(f'<div class="rpe-indicator {rpe_class}">{rpe_text}</div>', unsafe_allow_html=True)

                coach_notes = st.text_input("💬 Feedback / Consigne :", placeholder="Ex: Coudes bien verrouillés, bon tempo")

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
                            "reps": int(sw.get("reps", 0)),
                            "video_name": current_fname,
                            "date": now_str,
                            "notes": coach_notes,
                            "synced": False
                        }

                        ok_sync, msg_sync = dispatch_sync_evaluation(
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

                        time.sleep(0.6)
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# COMPARTIMENT 2 : STATS & PROGRESSION PURE (TST & RPE)
# ==============================================================================
with tab_stats:
    st.markdown("### 📊 Statistiques & Suivi TST / RPE")
    evals = st.session_state.db.get("evaluations", [])

    if not evals:
        st.info("Aucune analyse enregistrée. Évaluez vos premières vidéos dans le Studio !")
    else:
        df_evals = pd.DataFrame(evals)

        k1, k2 = st.columns(2)
        with k1:
            st.metric("Total Séances", len(df_evals))
            st.metric("TST Moyen", f"{df_evals['tst'].mean():.1f} s")
        with k2:
            st.metric("Athlètes Suivis", df_evals["student"].nunique())
            st.metric("RPE Moyen", f"{df_evals['rpe'].mean():.1f} / 10")

        st.markdown("<hr style='border-color: rgba(255,255,255,0.08); margin: 0.8rem 0;'>", unsafe_allow_html=True)

        all_students = ["Tous les athlètes"] + sorted(list(df_evals["student"].unique()))
        selected_student = st.selectbox("Filtrer par athlète :", all_students, key="stats_filter_student")
        df_filtered = df_evals if selected_student == "Tous les athlètes" else df_evals[df_evals["student"] == selected_student]

        if HAS_PLOTLY and not df_filtered.empty:
            tab_g1, tab_g2 = st.tabs(["📈 Évolution TST", "🔥 Répartition RPE"])

            with tab_g1:
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
                    plot_bgcolor="rgba(15,23,42,0.6)",
                    font_family="Plus Jakarta Sans",
                    margin=dict(l=10, r=10, t=25, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_tst, use_container_width=True)

            with tab_g2:
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
                    margin=dict(l=10, r=10, t=25, b=20)
                )
                st.plotly_chart(fig_rpe, use_container_width=True)

        st.markdown("##### 📜 Registre des séances")
        cols_present = ["date", "student", "exercise", "tst", "rpe", "notes"]
        df_disp = df_filtered[cols_present].copy()
        df_disp.columns = ["Date", "Athlète", "Exercice", "TST (s)", "RPE", "Notes"]
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
            avg_tst = (sum(e.get("tst", 0) for e in student_evals) / len(student_evals)) if student_evals else 0.0

            st.markdown(f"""
                <div class="cali-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h4 style="margin:0; font-size:1.05rem; color:#f8fafc;">👤 {name}</h4>
                        <span class="badge-lime">{len(student_evals)} Séances (TST moy: {avg_tst:.1f}s)</span>
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
# COMPARTIMENT 4 : RÉGLAGES & CONNECTEURS
# ==============================================================================
with tab_settings:
    st.markdown("### ⚙️ Paramètres & Connecteurs")

    with st.form("settings_full_form"):
        st.markdown("##### 🌐 Mode d'Enregistrement")
        sync_mode = st.radio(
            "Où stocker vos analyses ?",
            [
                ("google_forms", "📝 Google Forms (Méthode actuelle)"),
                ("gsheet_webhook", "🚀 Google Sheets Direct (Sans formulaire)"),
                ("local_only", "💾 Caliperf Local uniquement (100% hors-ligne)")
            ],
            format_func=lambda x: x[1],
            index=0 if st.session_state.db["settings"].get("sync_mode") == "google_forms" else (1 if st.session_state.db["settings"].get("sync_mode") == "gsheet_webhook" else 2)
        )[0]

        if sync_mode == "gsheet_webhook":
            wh_url_input = st.text_input("URL Webhook Google Apps Script :", value=st.session_state.db["settings"].get("webhook_url", ""))
        else:
            wh_url_input = st.session_state.db["settings"].get("webhook_url", "")

        if sync_mode == "google_forms":
            form_url = st.text_input("URL Google Form :", value=st.session_state.db["settings"].get("form_url", DEFAULT_FORM_URL))
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
        st.markdown("##### 🤖 Intelligence Artificielle & Vision")
        gem_key_input = st.text_input(
            "Clé API Gemini (Optionnel, pour l'Auto-Track IA des vidéos) :",
            value=get_gemini_api_key(),
            type="password",
            help="Permet à l'IA d'analyser la vidéo et de détecter le TST et les répétitions automatiquement."
        )

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
                "gemini_api_key": gem_key_input.strip(),
                "admin_pwd": st.session_state.db["settings"].get("admin_pwd", "admin"),
                "auto_advance": auto_adv
            }
            save_db(st.session_state.db)
            st.toast("✅ Configuration sauvegardée !")
            time.sleep(0.5)
            st.rerun()

    with st.expander("📄 Script Google Apps Script pour Google Sheets direct", expanded=False):
        st.markdown("""
        ```javascript
        function doPost(e) {
          var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
          var data = JSON.parse(e.postData.contents);
          sheet.appendRow([data.date, data.student, data.exercise, data.tst, data.rpe, data.reps, data.notes]);
          return ContentService.createTextOutput("OK");
        }
        ```
        """)

    json_bytes = json.dumps(st.session_state.db, indent=2, ensure_ascii=False).encode('utf-8')
    st.download_button(
        "📥 Télécharger la sauvegarde complète (JSON)",
        data=json_bytes,
        file_name=f"caliperf_backup_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json",
        use_container_width=True
    )
