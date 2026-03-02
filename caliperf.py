import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.express as px
import plotly.graph_objects as go
import time
from PIL import Image
import requests
import json
import os
import mediapipe as mp
from datetime import datetime
import hashlib
import cv2
import numpy as np
import tempfile
from streamlit_image_coordinates import streamlit_image_coordinates

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Caliperf - Coach Pro", layout="wide", page_icon="💪")
# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Caliperf - Coach Pro", layout="wide", page_icon="💪")

# --- 1. CHARGEMENT SÉCURISÉ DES CONFIGURATIONS ---
try:
    ADMIN_PWD = st.secrets["general"]["admin_password"]
    LINK_UNIQUE = st.secrets["general"]["google_form_url"]
    DELETE_SCRIPT_URL = st.secrets["general"]["delete_script_url"]
    ENTRIES = st.secrets["google_entries"]
    CSV_URL_SECRET = st.secrets["general"].get("csv_url", "")
    UPLOAD_LINK = st.secrets["general"].get("upload_link", "https://drive.google.com/") 
except Exception as e:
    st.error(f"⚠️ Erreur critique de configuration : {e}")
    st.stop()

DB_FILE = "caliperf_db.json"

# --- 2. FONCTIONS DE GESTION DES DONNÉES (VERSION CLOUD) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300) # Garde en cache pendant 5 minutes
def get_users_data():
    """Récupère les données de l'onglet 'Users'"""
    try:
        return conn.read(worksheet="Users", ttl=0) # Le ttl=0 ici force la lecture, mais la fonction entière est gérée par st.cache_data
    except Exception:
        return pd.DataFrame()

def add_new_user(user_dict):
    """Ajoute un nouvel utilisateur dans le Cloud"""
    try:
        df_actuel = get_users_data()
        new_row = pd.DataFrame([user_dict])
        
        if not df_actuel.empty:
            df_updated = pd.concat([df_actuel, new_row], ignore_index=True)
        else:
            df_updated = new_row
            
        conn.update(worksheet="Users", data=df_updated)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

def add_training_data(training_dict):
    """Ajoute une ligne d'entraînement dans l'onglet 'Trainings' du Google Sheet"""
    try:
        try:
            # On essaie de lire l'onglet existant
            df_actuel = conn.read(worksheet="Trainings", ttl=0)
        except Exception:
            # Si l'onglet est vide, on crée une base vide
            df_actuel = pd.DataFrame(columns=["Timestamp", "Nom", "Exercice", "TST", "RPE", "Charge"])
            
        new_row = pd.DataFrame([training_dict])
        
        if not df_actuel.empty:
            df_updated = pd.concat([df_actuel, new_row], ignore_index=True)
        else:
            df_updated = new_row
            
        conn.update(worksheet="Trainings", data=df_updated)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde de l'entraînement : {e}")
        return False

def save_figures_to_cloud(fullname, figures_dict):
    """Sauvegarde le dictionnaire de figures d'un élève dans le Google Sheet"""
    try:
        df = get_users_data()
        if not df.empty and "Fullname" in df.columns:
            if "Figures" not in df.columns:
                df["Figures"] = "{}"
            
            json_str = json.dumps(figures_dict)
            df.loc[df["Fullname"] == fullname, "Figures"] = json_str
            
            conn.update(worksheet="Users", data=df)
            st.cache_data.clear()
            return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde Cloud : {e}")
        return False

@st.cache_data(ttl=60)
def fetch_training_data():
    """Récupère l'historique des entraînements sans passer par un CSV public"""
    try:
        df = conn.read(worksheet="Trainings", ttl=0)
        return df
    except Exception as e:
        return pd.DataFrame()

# --- 3. GESTION DU CHRONO ---
def toggle_timer(video_key):
    timer = st.session_state.timers[video_key]
    if timer['run']:
        timer['acc'] += time.time() - timer['start']
        timer['run'] = False
    else:
        timer['start'] = time.time()
        timer['run'] = True

def reset_timer(video_key):
    st.session_state.timers[video_key] = {'start': 0, 'acc': 0.0, 'run': False, 'holds': []}

def capture_hold(video_key):
    """Capture le temps actuel comme une isométrie et remet le chrono à zéro pour la suite"""
    timer = st.session_state.timers[video_key]
    if 'holds' not in timer:
        timer['holds'] = []
    
    # Calcul du temps actuel
    curr = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
    
    if curr > 0:
        timer['holds'].append(round(curr, 2)) # Sauvegarde (ex: 5.3s)
        # Remise à zéro fluide pour mesurer la figure suivante
        timer['start'] = time.time() if timer['run'] else 0
        timer['acc'] = 0.0

# --- CSS / STYLE ATMOSPHÉRIQUE NOIR & BLEU ÉLECTRIQUE (Style de référence) ---
st.markdown("""
    <style>
    /* Importation des polices futuristes depuis Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;500;600;700&display=swap');

    /* --- FOND D'ÉCRAN PERSONNALISÉ (Inspiré de ta référence) --- */
    [data-testid="stAppViewContainer"] {
        /* Utilisation d'une image de brouillard urbain nocturne avec lumières bleues */
        background-image: linear-gradient(to top, rgba(5, 1, 31, 1) 0%, rgba(16, 10, 44, 0.8) 50%, rgba(22, 10, 44, 0.4) 100%), 
                          url("https://images.unsplash.com/photo-1563089145-599997674d42?q=80&w=2070&auto=format&fit=crop");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
        color: #e0e6ed;
    }
    
    /* Rendre le header (la barre du haut) transparent pour voir le fond */
    [data-testid="stHeader"] {
        background-color: rgba(0,0,0,0);
    }

    /* Rendre la sidebar encore plus "fumée" avec un effet verre (Glassmorphism renforcé) */
    [data-testid="stSidebar"] {
        background-color: rgba(15, 5, 30, 0.8) !important;
        backdrop-filter: blur(15px);
        border-right: 1px solid rgba(176, 38, 255, 0.3);
    }

    /* Typographie des titres */
    h1, h2, h3, h4 { 
        font-family: 'Orbitron', sans-serif !important; 
        text-transform: uppercase; 
        letter-spacing: 2px; 
        color: #00f3ff; /* Cyan Néon (électric) */
        text-shadow: 0 0 10px rgba(0, 243, 255, 0.5), 0 0 20px rgba(0, 243, 255, 0.3);
    }

    /* Typographie du texte classique */
    p, span, div, label {
        font-family: 'Rajdhani', sans-serif !important;
        font-size: 1.15rem;
        /* Ajout d'une ombre légère sur le texte pour la lisibilité sur le fond atmosphérique */
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
    }

    /* Boutons génériques (Glow Cyberpunk) */
    div.stButton > button { 
        border-radius: 4px; 
        font-weight: bold; 
        font-family: 'Orbitron', sans-serif;
        background-color: transparent;
        color: #00f3ff;
        border: 1px solid #00f3ff;
        box-shadow: inset 0 0 10px rgba(0,243,255,0.1), 0 0 10px rgba(0,243,255,0.2);
        transition: all 0.3s ease; 
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    div.stButton > button:hover { 
        background-color: rgba(0, 243, 255, 0.15); 
        box-shadow: inset 0 0 20px rgba(0,243,255,0.3), 0 0 25px rgba(0,243,255,0.7);
        transform: translateY(-2px); 
        color: #fff;
    }

    /* Boutons "Primary" (Ex: Envoi de formulaires) */
    div.stButton > button[kind="primary"] {
        border: 1px solid #b026ff;
        color: #f0f0f0;
        background: rgba(176, 38, 255, 0.15);
        box-shadow: inset 0 0 10px rgba(176,38,255,0.3), 0 0 15px rgba(176,38,255,0.4);
    }
    div.stButton > button[kind="primary"]:hover {
        background: rgba(176, 38, 255, 0.4);
        box-shadow: inset 0 0 20px rgba(176,38,255,0.6), 0 0 25px rgba(176,38,255,0.8);
        border-color: #d475ff;
    }

    /* --- OPTION NUCLÉAIRE : SUPPRESSION DÉFINITIVE DU TEXTE NATIF --- */

    /* 1. On désintègre TOUT le contenu interne (adieu le span avec le texte dégueulasse) */
    [data-testid="collapsedControl"] button *,
    [data-testid="stSidebarCollapseButton"] * {
        display: none !important;
    }

    /* 2. On s'assure que les conteneurs n'ont plus aucune trace de texte fantôme */
    [data-testid="collapsedControl"] button,
    [data-testid="stSidebarCollapseButton"] {
        color: transparent !important;
        font-size: 0px !important;
        background: transparent !important;
    }

    /* 3. On fait spawn notre propre icône Hamburger toute propre */
    [data-testid="collapsedControl"] button::after,
    [data-testid="stSidebarCollapseButton"]::after {
        content: "☰" !important;
        display: block !important;
        font-size: 32px !important;
        color: #00f3ff !important;
        text-shadow: 0 0 10px rgba(0, 243, 255, 0.5), 0 0 15px rgba(0, 243, 255, 0.3) !important;
        visibility: visible !important;
        transition: all 0.3s ease-in-out;
    }

    /* 4. L'effet néon au toucher */
    [data-testid="collapsedControl"] button:hover::after,
    [data-testid="stSidebarCollapseButton"]:hover::after {
        color: #b026ff !important;
        transform: scale(1.1);
        text-shadow: 0 0 15px rgba(176, 38, 255, 0.6) !important;
    }
    /* Cartes de métriques (Glassmorphism + Neon Border) */
    .metric-card { 
        background: rgba(15, 5, 30, 0.6); 
        backdrop-filter: blur(15px); 
        border: 1px solid rgba(176, 38, 255, 0.3); 
        padding: 20px; 
        border-radius: 8px; 
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5); 
        transition: all 0.3s; 
        border-left: 4px solid #b026ff;
    }
    .metric-card:hover { 
        transform: scale(1.02); 
        border-left-color: #00f3ff; 
        border-right: 4px solid #00f3ff;
        box-shadow: 0 0 20px rgba(176, 38, 255, 0.4); 
    }

    /* Stylisation du gros Chrono */
    .big-time {
        font-size: 3.5rem;
        font-family: 'Orbitron', sans-serif;
        font-weight: 900;
        color: #00f3ff;
        text-shadow: 0 0 10px rgba(0,243,255,0.5), 0 0 20px rgba(0,243,255,0.3);
        text-align: center;
        background: rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(0, 243, 255, 0.3);
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 15px;
    }

    /* Inputs (Text, Number, Select) */
    .stTextInput input, .stNumberInput input {
        background-color: rgba(15, 5, 30, 0.8) !important;
        border: 1px solid rgba(176, 38, 255, 0.4) !important;
        color: #00f3ff !important;
        font-family: 'Rajdhani', sans-serif !important;
        font-size: 1.2rem !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #00f3ff !important;
        box-shadow: 0 0 10px rgba(0,243,255,0.4) !important;
    }
    </style>
""", unsafe_allow_html=True)

def hash_password(password):
    """Transforme un mot de passe en texte clair en un hachage sécurisé SHA-256 avec un sel"""
    # On récupère le sel dans les secrets (ou on en met un par défaut si oublié)
    salt = st.secrets["general"].get("password_salt", "Caliperf_Secret_Salt_2024!")
    
    # On mélange le mot de passe de l'élève avec notre sel secret
    password_with_salt = password + salt
    
    # On crypte le tout
    return hashlib.sha256(str.encode(password_with_salt)).hexdigest()

# --- INITIALISATION SESSION STATE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 
if 'students_data' not in st.session_state:
    df_users = get_users_data()
    st.session_state.students_data = {}
    
    if not df_users.empty and "Fullname" in df_users.columns:
        for _, row in df_users.iterrows():
            user_dict = row.to_dict()
            
            if "Figures" in user_dict and pd.notna(user_dict["Figures"]) and str(user_dict["Figures"]).strip() != "":
                try:
                    user_dict["Figures"] = json.loads(str(user_dict["Figures"]))
                except:
                    user_dict["Figures"] = {"Mouvement basique": 1}
            else:
                user_dict["Figures"] = {"Mouvement basique": 1}
                
            st.session_state.students_data[row["Fullname"]] = user_dict
    else:
        st.session_state.students_data = {}

st.title("🏋️ Caliperf : Espace Coaching")

# --- MENU DE NAVIGATION DANS LA SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎛️ MENU PRINCIPAL")
    page_choisie = st.radio(
        "Navigation",
        ["👋 Profil", "🎥 Espace Vidéo", "📊 Mon Suivi", "⚡ Analyse Vitesse (VBT)"],
        label_visibility="collapsed"
    )
    st.write("---")
    st.caption("Caliperf - Coach Pro v2.0")
# =========================================================
# COMPOSANT PARTAGÉ : BIBLIOTHÈQUE DE FIGURES
# =========================================================
def render_figure_manager(athlete_name):
    """Affiche l'interface de gestion de la bibliothèque de mouvements pour un élève"""
    st.markdown("### 📚 Ma Bibliothèque de Mouvements")
    st.caption("Ajoute tes figures et détermine leur difficulté (1 = Simple, 5 = Extrême) pour calculer ton combo.")
    
    dict_figures = st.session_state.students_data[athlete_name].get('Figures', {"Mouvement basique": 1})

    c_nom, c_diff, c_btn = st.columns([2, 1, 1])
    with c_nom:
        new_fig_name = st.text_input("Nom de la figure", key=f"fig_name_{athlete_name}")
    with c_diff:
        new_fig_diff = st.number_input("Difficulté", min_value=1, max_value=5, value=3, key=f"fig_diff_{athlete_name}")
    with c_btn:
        st.write("")
        st.write("")
        if st.button("➕ Enregistrer", key=f"btn_add_{athlete_name}"):
            if new_fig_name:
                st.session_state.students_data[athlete_name]['Figures'][new_fig_name] = new_fig_diff
                if save_figures_to_cloud(athlete_name, st.session_state.students_data[athlete_name]['Figures']):
                    st.success(f"✅ {new_fig_name} (Niveau {new_fig_diff}) sauvegardé dans le Cloud !")
                    time.sleep(1)
                    st.rerun()

    if dict_figures:
        df_figs = pd.DataFrame(list(dict_figures.items()), columns=["Figure", "Niveau de Difficulté"])
        st.dataframe(df_figs, hide_index=True, use_container_width=True)

# =========================================================
# ONGLET 1 : INSCRIPTION / PROFIL
# =========================================================
if page_choisie == "👋 Profil":
    st.header("Création ou Mise à jour du Profil 🚀")
    st.caption("Remplis ce formulaire pour créer ton compte ou mettre à jour tes informations.")
    
    with st.form("form_intro", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: nom = st.text_input("Nom")
        with col2: prenom = st.text_input("Prénom")
        
        st.write("---")
        pwd_eleve = st.text_input("🔒 Crée ton mot de passe personnel (pour accéder à tes stats)", type="password")
        st.write("---")

        col3, col4 = st.columns(2)
        with col3: freq = st.selectbox("Fréquence", ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "Tous les jours"])
        with col4: experience = st.text_input("Temps de pratique", placeholder="Ex: 2 ans, Débutant...")
        
        c_poids, c_taille, c_sexe = st.columns(3)
        with c_poids: poids = st.number_input("Poids (kg)", 30.0, 150.0, step=0.5, value=70.0)
        with c_taille: taille = st.number_input("Taille (cm)", 100, 230, step=1, value=175)
        with c_sexe: sexe = st.radio("Sexe", ["Homme", "Femme"], horizontal=True)
        
        objectif = st.text_area("Ton objectif principal")
        
        if st.form_submit_button("✅ Créer / Mettre à jour mon compte", type="primary", use_container_width=True):
            if nom and prenom and pwd_eleve:
                new_user_data = {
                    "Fullname": f"{prenom} {nom}",
                    "Nom": nom,
                    "Prenom": prenom,
                    "Password": hash_password(pwd_eleve),
                    "Frequence": freq,
                    "Experience": experience,
                    "Poids": poids,
                    "Taille": taille,
                    "Sexe": sexe,
                    "Objectif": objectif,
                    "Date": datetime.now().strftime("%Y-%m-%d")
                }
                if add_new_user(new_user_data):
                    st.success(f"Compte créé pour {prenom} ! 🎉")
                    st.balloons()
            else:
                st.warning("Nom, Prénom et Mot de passe sont obligatoires.")

# =========================================================
# ONGLET 2 : ANALYSE VIDÉO
# =========================================================
elif page_choisie == "🎥 Espace Vidéo":
    col_titre, col_login = st.columns([3, 1])
    with col_titre:
        st.caption("Espace d'échange et d'analyse technique.")
    with col_login:
        password = st.text_input("🔒 Accès Coach (Analyse)", type="password", key="pwd_analyse")

    st.divider()

    # --- MODE COACH ---
    if password == ADMIN_PWD:
        st.success("🔓 Mode Coach activé")
        
        with st.expander("🛌 Enregistrement Rapide : REPOS / ABSENCE", expanded=True):
            c_rep1, c_rep2 = st.columns([2, 1])
            with c_rep1:
                keys = list(st.session_state.students_data.keys())
                eleve_repos = st.selectbox("Sélectionner l'élève :", keys, key="sel_repos") if keys else None
            with c_rep2:
                st.write("")
                st.write("")
                if eleve_repos and st.button("💤 VALIDER REPOS", type="primary", use_container_width=True):
                    # 1. On prépare le dictionnaire avec les colonnes exactes de Google Sheets
                    nouveau_repos = {
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Nom": eleve_repos,
                        "Exercice": "Repos",
                        "TST": "0",
                        "RPE": "0",
                        "Charge": "0"
                    }
                    
                    # 2. On utilise ta nouvelle fonction centralisée
                    if add_training_data(nouveau_repos):
                        st.success(f"💤 Jour de repos validé pour {eleve_repos} !")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("⚠️ Erreur lors de l'enregistrement du repos dans Google Sheets.")

        st.divider()
        
        uploaded_file = st.file_uploader("📥 Charger la vidéo à analyser (1 à la fois)", type=['mp4', 'mov', 'avi'], accept_multiple_files=False)

        if uploaded_file:
            real_name = uploaded_file.name
            if real_name in st.session_state.processed_files:
                st.success(f"✅ {real_name} déjà traitée !")
            else:
                st.info(f"⏳ Analyse en cours : {real_name}")
            
            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {'start': 0, 'acc': 0.0, 'run': False}
            timer = st.session_state.timers[real_name]

            c_vid, c_tools = st.columns([1.5, 1])
            with c_vid: st.video(uploaded_file)
            with c_tools:
                st.subheader("⏱️ Chrono")
                curr = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                st.markdown(f'<div class="big-time">{curr:.2f} s</div>', unsafe_allow_html=True)
                
                # --- AFFICHAGE DU CHRONO ---
                b1, b2 = st.columns(2)
                with b1: st.button("⏸️ PAUSE" if timer['run'] else "▶️ START", key=f"btn_{real_name}", on_click=toggle_timer, args=(real_name,), use_container_width=True)
                with b2: st.button("🗑️ RAZ", key=f"rst_{real_name}", on_click=reset_timer, args=(real_name,), use_container_width=True)

                st.write("---")
                
                # --- FORMULAIRE ET SÉLECTION DE L'ATHLÈTE ---
                s_keys = list(st.session_state.students_data.keys())
                
                if s_keys:
                    s_student = st.selectbox("Athlète", s_keys, key=f"sel_athlete_{real_name}")
                    
                    with st.form(key=f"f_{real_name}", clear_on_submit=True):
                        c_rpe, c_info = st.columns([2, 1])
                        with c_rpe:
                            rpe = st.slider("Intensité globale (RPE)", 1, 10, 7)
                        with c_info:
                            # On se base directement sur le temps du chrono
                            total_time_calc = curr
                            st.info(f"⏱️ Temps chrono : {total_time_calc:.2f} s")

                        st.write("---")
                        st.markdown("🔥 **Construction du Combo**")
                        st.caption("Définis chaque étape. Pour l'isométrie (Statique), indique la durée en secondes dans 'Val'.")

                        athlete_figures = st.session_state.students_data[s_student].get('Figures', {"Mouvement basique": 1})
                        options_figures = ["-- Aucune --"] + list(athlete_figures.keys())
                        
                        combo_selections = []
                        
                        # --- LES 5 LIGNES DYNAMIQUES DU COMBO ---
                        for i in range(5):
                            c_cat, c_fig, c_type, c_val = st.columns([1.2, 2, 1.2, 1])
                            
                            with c_cat:
                                cat = st.selectbox("Catégorie", ["Push", "Pull", "Mixte"], key=f"cat_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                            
                            with c_fig:
                                default_idx = 1 if i == 0 else 0 
                                fig = st.selectbox("Figure", options_figures, index=default_idx, key=f"fig_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                            
                            with c_type:
                                etype = st.selectbox("Type", ["Dynamique", "Statique"], key=f"etype_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                            
                            with c_val:
                                val = st.number_input("Val (reps/sec)", min_value=0.1, step=0.5, value=1.0, key=f"val_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                                
                            combo_selections.append({"Cat": cat, "Figure": fig, "Type": etype, "Valeur": val})

                        st.write("---")

                        if st.form_submit_button("☁️ ENVOYER DONNÉES", type="primary", use_container_width=True):
                            total_coeff = 0
                            noms_figures_realisees = []

                            for item in combo_selections:
                                fig_name = item["Figure"]
                                if fig_name != "-- Aucune --":
                                    cat = item["Cat"]
                                    etype = item["Type"]
                                    val = item["Valeur"]
                                    
                                    diff = athlete_figures.get(fig_name, 1)
                                    multiplicateur_unitaire = 1.0 + (diff - 1) * 0.25
                                    
                                    if etype == "Statique":
                                        reps_virtuelles = val 
                                        bonus_intensite = 1.0 if rpe < 8 else (rpe / 7.0) 
                                        total_coeff += (multiplicateur_unitaire * reps_virtuelles * bonus_intensite)
                                        noms_figures_realisees.append(f"[{cat}] {fig_name} ({val}s)")
                                    else:
                                        total_coeff += (multiplicateur_unitaire * val)
                                        noms_figures_realisees.append(f"[{cat}] {int(val)}x {fig_name}")

                            if not noms_figures_realisees:
                                st.error("⚠️ Tu dois sélectionner au moins une figure !")
                            else:
                                nom_exo_final = " + ".join(noms_figures_realisees)
                                charge = total_time_calc * rpe * total_coeff

                                if charge > 0:
                                    new_training = {
                                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "Nom": s_student,
                                        "Exercice": nom_exo_final,
                                        "TST": round(total_time_calc, 2), # Nombre pur
                                        "RPE": int(rpe),                  # Nombre pur
                                        "Charge": round(charge, 2)        # Nombre pur
                                    }
                                    
                                    # --- NOUVEAU : Le spinner avec la bonne indentation ---
                                    with st.spinner("⏳ Enregistrement dans le Cloud..."):
                                        if add_training_data(new_training):
                                            st.toast(f"✅ Combo enregistré ! (Charge: {charge:.1f} | Coeff: x{total_coeff:.2f})")
                                            st.session_state.processed_files.add(real_name)
                                            time.sleep(1)
                                            st.rerun()
                                        else: 
                                            st.error("Erreur lors de l'enregistrement dans Google Sheets")
                                            
                                else:
                                    st.warning("⚠️ La charge calculée est de 0 (le chrono était peut-être à 0) !")
                                    
                            
                else:
                    st.warning("Aucun élève enregistré.")
        else:
            st.info("📂 En attente de vidéos à analyser...")
    # --- MODE ÉLÈVE ---
    else:
        st.subheader("📤 Envoyer mes vidéos au Coach")
        st.markdown("Pour que ton coach puisse analyser tes mouvements, il faut lui envoyer tes vidéos.")
        col_send1, col_send2 = st.columns([1, 2])
        with col_send1:
            st.info("👇 Clique ici pour déposer tes fichiers")
            st.link_button("📂 Ouvrir le dossier de dépôt", UPLOAD_LINK, type="primary", use_container_width=True)
        with col_send2:
            st.caption("Une fois tes vidéos déposées, préviens ton coach ! Il les récupérera pour les analyser ici même.")

# =========================================================
# ONGLET 3 : MON SUIVI (SÉCURISÉ)
# =========================================================
elif page_choisie == "📊 Mon Suivi":
    st.header("📊 Suivi des Performances")
    
    SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTABZd8nfqjdUzGUBjb57ntk8ACmBIPg7CM5VBMjGSdXJtiAN1ZJhwpGUb2EJvQZOrJ55s9eE2c8exn/pub?output=csv"
    if SHEET_CSV_URL:
        df_history = fetch_training_data()
        if not df_history.empty and 'Charge' in df_history.columns:
            df_history['Charge'] = df_history['Charge'].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce')
            df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
            df_history['Date'] = df_history['Timestamp'].dt.date
    else:
        df_history = pd.DataFrame()

    mode_connexion = st.radio("Qui êtes-vous ?", ["👤 Je suis Élève", "🧢 Je suis le Coach"], horizontal=True)
    st.write("---")

    # ----------------------------------------------------------------
    # MODE 1 : LE COACH (Accès Total)
    # ----------------------------------------------------------------
    if "Coach" in mode_connexion:
        pwd_input = st.text_input("Mot de passe Coach", type="password", key="pwd_coach_suivi")
        
        if pwd_input == ADMIN_PWD:
            st.success("Accès Administrateur ✅")
            
            if st.session_state.students_data:
                cols = st.columns(2)
                
                for index, (name, info) in enumerate(list(st.session_state.students_data.items())):
                    with cols[index % 2]:
                        emoji_sexe = "♂️" if info.get('Sexe') == "Homme" else "♀️"
                        pwd_user = info.get('Password', '⚠️ Non défini')
                        
                        st.markdown(f"""
                        <div class="metric-card">
                            <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name} {emoji_sexe}</h3>
                            <p><b>🔑 Mot de passe:</b> {pwd_user}</p>
                            <p><b>📏 Morpho:</b> {info.get('Taille','?')}cm | {info.get('Poids','?')}kg</p>
                        </div>""", unsafe_allow_html=True)

                        with st.expander(f"📈 Stats de {name}"):
                            if not df_history.empty:
                                s_df = df_history[df_history['Nom'] == name].copy()
                                if not s_df.empty:
                                    s_df['TST_Val'] = pd.to_numeric(s_df['TST'], errors='coerce').fillna(0)
                                    s_df['Date'] = pd.to_datetime(s_df['Date'])
                                    
                                    daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'})
                                    daily = daily.resample('D').asfreq().fillna({'Charge': 0, 'TST_Val': 0})
                                    daily['MA_Ch'] = daily['Charge'].rolling(window=3, min_periods=1).mean()
                                    daily['MA_Vol'] = daily['TST_Val'].rolling(window=3, min_periods=1).mean()
                                    
                                    daily = daily.reset_index()
                                    daily_train = daily[daily['Charge'] > 0]

                                    fig_c = go.Figure()
                                    fig_c.add_trace(go.Scatter(x=daily_train['Date'], y=daily_train['Charge'], mode='markers', marker=dict(color=daily_train['RPE'], colorscale='RdYlGn_r', size=10), name='Séance'))
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange', width=2), name='Tendance 3J'))
                                    fig_c.update_layout(title="Charge", template="plotly_dark", height=250, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)
                                    
                                    fig_v = go.Figure()
                                    fig_v.add_trace(go.Bar(x=daily_train['Date'], y=daily_train['TST_Val'], marker=dict(color='#3366CC'), name='Vol'))
                                    fig_v.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Vol'], mode='lines', line=dict(dash='dot', color='white'), name='Tend.'))
                                    fig_v.update_layout(title="Volume", template="plotly_dark", height=250, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)

                                    c1, c2 = st.columns(2)
                                    with c1: sc = st.plotly_chart(fig_c, use_container_width=True, on_select="rerun", key=f"c_{name}")
                                    with c2: sv = st.plotly_chart(fig_v, use_container_width=True, on_select="rerun", key=f"v_{name}")

                                    sel = sc if sc and sc["selection"]["points"] else sv if sv and sv["selection"]["points"] else None
                                    if sel:
                                        dt = sel["selection"]["points"][0]["x"]
                                        st.markdown(f"**🔎 Détail du {dt}**")
                                        det = s_df[s_df['Date'].astype(str)==dt].copy()
                                        st.dataframe(det[['Exercice','TST','RPE','Charge']], use_container_width=True, hide_index=True)
                                else: st.info("Pas de données.")
                            else: st.error("Erreur données.")

                        with st.expander(f"📚 Gérer les figures de {name}"):
                            render_figure_manager(name)

                st.write("---")
                st.subheader("🚨 Zone de Danger : Gérer les élèves")
                
                cd, ct = st.columns([1, 2])
                with cd:
                    # 1. On crée un menu déroulant pour choisir qui supprimer
                    eleve_a_supprimer = st.selectbox(
                        "Sélectionner l'élève à supprimer :", 
                        ["-- Choisir --"] + list(st.session_state.students_data.keys()), 
                        key="sel_del_student"
                    )
                    
                    # 2. Le vrai bouton d'action
                    if st.button("🗑️ Supprimer définitivement", type="primary", use_container_width=True):
                        if eleve_a_supprimer != "-- Choisir --":
                            try:
                                # --- 1. SUPPRESSION DU PROFIL (Onglet 'Users') ---
                                df_users = get_users_data()
                                df_updated = df_users[df_users['Fullname'] != eleve_a_supprimer]
                                conn.update(worksheet="Users", data=df_updated)
                                
                                # --- 2. SUPPRESSION DE L'HISTORIQUE (Onglet 'Trainings') ---
                                try:
                                    # On lit les entraînements
                                    df_trainings = conn.read(worksheet="Trainings", ttl=0)
                                    if not df_trainings.empty and 'Nom' in df_trainings.columns:
                                        # On garde toutes les lignes SAUF celles de l'élève supprimé
                                        df_trainings_updated = df_trainings[df_trainings['Nom'] != eleve_a_supprimer]
                                        # On met à jour l'onglet Trainings
                                        conn.update(worksheet="Trainings", data=df_trainings_updated)
                                except Exception as e_train:
                                    print(f"Erreur nettoyage Trainings: {e_train}")
                                
                                # --- 3. NETTOYAGE DU CACHE ET DE L'INTERFACE ---
                                st.cache_data.clear()
                                if eleve_a_supprimer in st.session_state.students_data:
                                    del st.session_state.students_data[eleve_a_supprimer]
                                
                                st.success(f"✅ Le profil ET les données de {eleve_a_supprimer} ont été supprimés !")
                                time.sleep(1.5)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Erreur lors de la suppression : {e}")
                        else:
                            st.warning("⚠️ Merci de sélectionner un élève dans la liste d'abord.")
            else:
                st.warning("La base de données des élèves est vide. Si tu viens d'ajouter un élève, rafraîchis la page.")
        else:
            if pwd_input: st.error("Mot de passe incorrect.")

    # ----------------------------------------------------------------
    # MODE 2 : L'ÉLÈVE (Accès Sécurisé)
    # ----------------------------------------------------------------
    elif "Élève" in mode_connexion:
        st.info("Connecte-toi pour voir tes progrès.")
        
        all_students = list(st.session_state.students_data.keys())
        if all_students:
            selected_name = st.selectbox("Je m'appelle :", ["-- Choisir --"] + all_students)
            
            if selected_name != "-- Choisir --":
                info = st.session_state.students_data[selected_name]
                stored_password = info.get('Password')

                if not stored_password:
                    st.warning("⚠️ Tu n'as pas encore défini de mot de passe.")
                    st.markdown("Va dans l'onglet **'👋 Création Compte / Profil'**, remets ton nom/prénom et crée un mot de passe.")
                else:
                    input_pwd = st.text_input("Mon mot de passe :", type="password", key=f"pwd_{selected_name}")
                    
                    # --- NOUVEAU : Hachage du mot de passe tapé ---
                    hashed_input = hash_password(input_pwd) if input_pwd else ""
                    
                    if st.button("Se connecter 🔓", key=f"btn_log_{selected_name}") or hashed_input == stored_password:
                        if hashed_input == stored_password:
                            st.success(f"Bon retour, {selected_name} !")
                            
                            emoji_sexe = "♂️" if info.get('Sexe') == "Homme" else "♀️"
                            st.markdown(f"""
                            <div class="metric-card">
                                <h3 style='margin-top:0; color:#ff4b4b;'>Bonjour {selected_name} ! {emoji_sexe}</h3>
                                <p><b>📏 Tes mensurations:</b> {info.get('Taille','?')}cm | {info.get('Poids','?')}kg</p>
                                <p><b>🎯 Ton Objectif:</b> {info.get('Objectif', 'N/A')}</p>
                            </div>""", unsafe_allow_html=True)
                            
                            st.subheader("📈 Tes Graphiques")

                            if not df_history.empty:
                                s_df = df_history[df_history['Nom'] == selected_name].copy()
                                if not s_df.empty:
                                    s_df['TST_Val'] = pd.to_numeric(s_df['TST'], errors='coerce').fillna(0)
                                    s_df['Date'] = pd.to_datetime(s_df['Date'])
                                    
                                    daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'})
                                    daily = daily.resample('D').asfreq().fillna({'Charge': 0, 'TST_Val': 0})
                                    daily['MA_Ch'] = daily['Charge'].rolling(window=3, min_periods=1).mean()
                                    daily['MA_Vol'] = daily['TST_Val'].rolling(window=3, min_periods=1).mean()
                                    
                                    daily = daily.reset_index()
                                    daily_train = daily[daily['Charge'] > 0]

                                    fig_c = go.Figure()
                                    fig_c.add_trace(go.Scatter(x=daily_train['Date'], y=daily_train['Charge'], mode='markers', marker=dict(color=daily_train['RPE'], colorscale='RdYlGn_r', size=10), name='Séance'))
                                    fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange', width=2), name='Tendance 3J'))
                                    fig_c.update_layout(title="Ta Charge d'entraînement", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)
                                    
                                    fig_v = go.Figure()
                                    fig_v.add_trace(go.Bar(x=daily_train['Date'], y=daily_train['TST_Val'], marker=dict(color='#3366CC'), name='Vol'))
                                    fig_v.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Vol'], mode='lines', line=dict(dash='dot', color='white'), name='Tend.'))
                                    fig_v.update_layout(title="Ton Volume (TST / Reps)", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)

                                    c1, c2 = st.columns(2)
                                    with c1: sc = st.plotly_chart(fig_c, use_container_width=True, on_select="rerun", key=f"c_student_{selected_name}")
                                    with c2: sv = st.plotly_chart(fig_v, use_container_width=True, on_select="rerun", key=f"v_student_{selected_name}")

                                    sel = sc if sc and sc["selection"]["points"] else sv if sv and sv["selection"]["points"] else None
                                    if sel:
                                        dt = sel["selection"]["points"][0]["x"]
                                        st.markdown(f"**🔎 Détail de ta séance du {dt}**")
                                        det = s_df[s_df['Date'].astype(str)==dt].copy()
                                        st.dataframe(det[['Exercice','TST','RPE','Charge']], use_container_width=True, hide_index=True)
                                else: st.info("Pas encore de données d'entraînement. Envoie tes vidéos !")
                            else: st.error("Impossible de récupérer l'historique.")
                            
                            st.write("---")
                            render_figure_manager(selected_name)
                            
                        else:
                            st.error("Mot de passe incorrect ❌")
        else:
            st.warning("Aucun élève inscrit dans la base.")
            
elif page_choisie == "⚡ Analyse Vitesse (VBT)":
    st.header("⚡ Analyse Biomécanique IA (VBT)")
    st.markdown("L'IA détecte tes articulations. Analyse la vitesse absolue de ton mouvement (ex: montée des pieds en Planche Press).")

    vbt_file = st.file_uploader("📥 Charger la vidéo", type=['mp4', 'mov'], key="vbt_uploader")

    if vbt_file:
        if 'vbt_path' not in st.session_state or st.session_state.get('vbt_name') != vbt_file.name:
            tfile = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            tfile.write(vbt_file.read())
            st.session_state.vbt_path = tfile.name
            st.session_state.vbt_name = vbt_file.name
            
        video_path = st.session_state.vbt_path

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        st.subheader("⏱️ Étape 1 : Isole le mouvement")
        st.video(video_path)
        
        st.markdown("**Ajuste les extrémités du curseur pour isoler ta répétition :**")
        
        if 'frame_range' not in st.session_state or st.session_state.get('vbt_name') != vbt_file.name:
            st.session_state.frame_range = (0, max(0, total_frames - 1))

        selected_range = st.slider(
            "Début et Fin de la vidéo", 
            0, max(0, total_frames - 1), 
            st.session_state.frame_range, 
            label_visibility="collapsed"
        )
        
        st.session_state.frame_range = selected_range
        start_frame, end_frame = selected_range

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        ret, frame = cap.read()
        if ret:
            max_width = 350
            ratio = max_width / orig_w if orig_w > max_width else 1.0
            new_h = int(orig_h * ratio)
            frame_resized = cv2.resize(frame, (max_width, new_h))
            frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
            st.image(frame_rgb, caption=f"📸 Aperçu de l'image de départ (Frame {start_frame})")

        st.write("---")
        st.subheader("🎯 Étape 2 : Que veut-on analyser ?")
        
        POINTS_ANATOMIQUES = {
            "Chevilles (ex: Planche Press)": (27, 28),
            "Bassin / Pubis (ex: Front Lever Pull-Up)": (23, 24),
            "Épaules": (11, 12),
            "Poignets": (15, 16)
        }

        pt_mobile = st.selectbox("🏃 Articulation à suivre", list(POINTS_ANATOMIQUES.keys()), index=0)

        st.write("---")
        st.subheader("📏 Étape 2.5 : Calibration de l'échelle")
        st.caption("Sélectionne l'athlète pour utiliser sa taille enregistrée, ou saisis-la manuellement.")
        
        # 1. On prépare la liste des élèves disponibles
        liste_eleves = list(st.session_state.students_data.keys())
        options_eleves = ["-- Profil manuel --"] + liste_eleves

        # 2. Le menu déroulant pour choisir
        eleve_choisi = st.selectbox("👤 Qui est sur la vidéo ?", options_eleves)

        # 3. On détermine la taille par défaut
        taille_defaut = 175 # Valeur de base si profil manuel ou erreur
        if eleve_choisi != "-- Profil manuel --":
            try:
                # On récupère la taille dans les données de la session
                taille_sauvegardee = st.session_state.students_data[eleve_choisi].get("Taille", 175)
                taille_defaut = int(float(taille_sauvegardee)) # On s'assure que c'est bien un nombre
            except Exception:
                taille_defaut = 175

        # 4. Le champ se pré-remplit tout seul, mais reste modifiable au cas où !
        taille_cm = st.number_input("📏 Taille (cm)", min_value=100, max_value=230, value=taille_defaut)
        taille_m = taille_cm / 100.0
        
        if st.button("🚀 Lancer l'analyse 3D", type="primary", use_container_width=True):
            st.info("L'IA scanne ton squelette... 🤖")
            progress_bar = st.progress(0)

            mp_pose = mp.solutions.pose
            mp_drawing = mp.solutions.drawing_utils

            # Définition de la résolution cible (Standardisation)
            TARGET_HEIGHT = 720
            scale_factor = TARGET_HEIGHT / orig_h if orig_h > TARGET_HEIGHT else 1.0
            work_w = int(orig_w * scale_factor)
            work_h = int(orig_h * scale_factor)

            out_path = tempfile.NamedTemporaryFile(delete=False, suffix='.webm').name
            fourcc = cv2.VideoWriter_fourcc(*'vp80')
            out = cv2.VideoWriter(out_path, fourcc, fps, (work_w, work_h))

            times = []
            speeds = []
            prev_c_mobile = None
            ratio_m_px = None
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            frames_processed = 0
            frames_to_process = end_frame - start_frame

            try:
                with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
                    while True:  # <--- C'EST CETTE BOUCLE QUI MANQUAIT OU ÉTAIT MAL ALIGNÉE
                        ret, raw_frame = cap.read()
                        if not ret or frames_processed > frames_to_process:
                            break  # <--- Maintenant le "break" est bien dans sa boucle !
                        
                        # --- DOWNSAMPLING : On compresse la frame à la volée ---
                        work_frame = cv2.resize(raw_frame, (work_w, work_h))
                        frame_rgb = cv2.cvtColor(work_frame, cv2.COLOR_BGR2RGB)
                        results = pose.process(frame_rgb)

                        if results.pose_landmarks:
                            landmarks = results.pose_landmarks.landmark
                            
                            # --- CALIBRATION MULTI-ANGLES ---
                            if ratio_m_px is None:
                                x_nez = landmarks[0].x * work_w
                                y_nez = landmarks[0].y * work_h
                                x_chevilles = (landmarks[27].x + landmarks[28].x) / 2 * work_w
                                y_chevilles = (landmarks[27].y + landmarks[28].y) / 2 * work_h
                                
                                # Distance Euclidienne exacte (Pythagore)
                                hauteur_pixels = np.sqrt((x_chevilles - x_nez)**2 + (y_chevilles - y_nez)**2)
                                
                                if hauteur_pixels > 0:
                                    ratio_m_px = taille_m / hauteur_pixels

                            idx_mob_1, idx_mob_2 = POINTS_ANATOMIQUES[pt_mobile]
                            
                            x = int((landmarks[idx_mob_1].x + landmarks[idx_mob_2].x) / 2 * work_w)
                            y = int((landmarks[idx_mob_1].y + landmarks[idx_mob_2].y) / 2 * work_h)
                            c_mobile = (x, y)

                            cv2.circle(work_frame, c_mobile, 15, (0, 0, 255), -1) 
                            
                            mp_drawing.draw_landmarks(
                                work_frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                                mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                                mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)
                            )
                            
                            # Calcul de la vitesse
                            if prev_c_mobile is not None and ratio_m_px is not None:
                                dist_pixel = np.linalg.norm(np.array(c_mobile) - np.array(prev_c_mobile))
                                current_speed_ms = (dist_pixel * ratio_m_px) * fps 
                                speeds.append(current_speed_ms)
                            else:
                                speeds.append(0) 
                                
                            times.append(frames_processed / fps)
                            prev_c_mobile = c_mobile
                            
                        else:
                            # Si l'IA perd le corps de vue, on met la vitesse à 0
                            speeds.append(0)
                            times.append(frames_processed / fps)

                        # Écriture de la vidéo et progression
                        out.write(work_frame)
                        frames_processed += 1
                        
                        if frames_to_process > 0:
                            progress_bar.progress(min(frames_processed / frames_to_process, 1.0))

            finally:
                # --- GARBAGE COLLECTION : Le serveur respire ---
                cap.release()
                out.release()
                if os.path.exists(video_path):
                    try:
                        os.remove(video_path)
                    except Exception as e:
                        print(f"Erreur lors de la suppression du cache : {e}")

            # --- Affichage des résultats (inchangé) ---
            st.success("✅ Vidéo scannée et optimisée avec succès !")
            # ... st.video(video_bytes) et tracé du graphique ...

            st.subheader("🎥 Replay Biomécanique")
            with open(out_path, 'rb') as video_file:
                video_bytes = video_file.read()
                st.video(video_bytes, format="video/webm")

            if os.path.exists(out_path):
                os.remove(out_path) 
            
            if len(speeds) > 1:
                df_vbt = pd.DataFrame({"Temps (s)": times, "Vitesse (m/s)": speeds})
                # On lisse un peu plus pour éviter les pics parasites liés aux micro-erreurs de l'IA
                df_vbt["Vitesse_lisse"] = df_vbt["Vitesse (m/s)"].rolling(window=5, center=True).mean().fillna(0)
                
                # --- NOUVEAU DESIGN DU GRAPHIQUE ---
                fig = px.line(df_vbt, x="Temps (s)", y="Vitesse_lisse", title=f"VITESSE ABSOLUE : {pt_mobile}")
                fig.update_traces(line_color='#00f3ff', line_width=3)
                fig.update_layout(
                    template="plotly_dark", 
                    yaxis_title="Vitesse (m/s)",
                    plot_bgcolor='rgba(0,0,0,0)', 
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                
                v_max = df_vbt["Vitesse_lisse"].max()
                fig.add_hline(
                    y=v_max, 
                    line_dash="dot", 
                    line_color="#b026ff", 
                    annotation_text=f"Vmax: {v_max:.2f} m/s", 
                    annotation_font_color="#b026ff"
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("⚠️ L'IA n'a pas réussi à voir ton corps entier sur cette séquence.")



































