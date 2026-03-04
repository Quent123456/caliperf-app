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
# --- 1. CHARGEMENT SÉCURISÉ DES CONFIGURATIONS ---
try:
    ADMIN_PWD = st.secrets["general"]["admin_password"]
    # ... tes autres secrets ...
except Exception as e:
    st.error(f"⚠️ Erreur critique de configuration : {e}")
    st.stop()

# --- 2. FONCTIONS DE GESTION DES DONNÉES (VERSION CLOUD CENTRALISÉE) ---
# On initialise la connexion UNE SEULE FOIS
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300) # Garde en cache 5 min. Le clear() sera appelé lors d'une modif.
def get_users_data():
    """Récupère les données de l'onglet 'Users'"""
    try:
        # On utilise le cache de st.cache_data, pas besoin de forcer ttl=0 ici en permanence
        return conn.read(worksheet="Users") 
    except Exception as e:
        st.error(f"Erreur lecture Users: {e}")
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
        st.cache_data.clear() # On vide le cache pour forcer l'actualisation
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde utilisateur : {e}")
        return False

def add_training_data(training_dict):
    """Ajoute ou met à jour l'entraînement du jour dans le Google Sheet central 'Trainings'"""
    try:
        try:
            df_actuel = conn.read(worksheet="Trainings", ttl=0) # ttl=0 pour être sûr d'avoir la dernière version avant d'écrire
        except Exception:
            df_actuel = pd.DataFrame(columns=["Timestamp", "Nom", "Exercice", "TST", "RPE", "Charge", "Details"])

        if "Details" not in df_actuel.columns:
            df_actuel["Details"] = None

        date_str = training_dict["Timestamp"][:10]  
        nom = training_dict["Nom"]
        charge_individuelle = round(float(training_dict["TST"]) * int(training_dict["RPE"]), 2)
        
        nouveau_detail = {
            "Exercice": training_dict["Exercice"],
            "TST": float(training_dict["TST"]),
            "RPE": int(training_dict["RPE"]),
            "Charge": charge_individuelle
        }

        if not df_actuel.empty and "Timestamp" in df_actuel.columns:
            df_actuel['Date_temp'] = df_actuel['Timestamp'].astype(str).str[:10]
            mask = (df_actuel['Nom'] == nom) & (df_actuel['Date_temp'] == date_str)

            if mask.any():
                idx = df_actuel[mask].index[0]
                
                old_tst = float(df_actuel.loc[idx, "TST"]) if pd.notna(df_actuel.loc[idx, "TST"]) else 0.0
                old_rpe = int(df_actuel.loc[idx, "RPE"]) if pd.notna(df_actuel.loc[idx, "RPE"]) else 0
                old_exo = str(df_actuel.loc[idx, "Exercice"])
                old_details_str = df_actuel.loc[idx, "Details"]
                
                try:
                    if pd.notna(old_details_str) and str(old_details_str).strip() != "":
                        liste_details = json.loads(str(old_details_str))
                    else:
                        liste_details = [{"Exercice": old_exo, "TST": old_tst, "RPE": old_rpe, "Charge": round(old_tst * old_rpe, 2)}]
                except Exception:
                    liste_details = []
                
                liste_details.append(nouveau_detail)

                new_tst = old_tst + float(training_dict["TST"])
                new_rpe = old_rpe + int(training_dict["RPE"]) # Attention: sommer les RPE n'a pas toujours de sens physio, une moyenne serait peut-être mieux ?
                new_charge = new_tst * new_rpe
                
                new_exo = old_exo + " | " + str(training_dict["Exercice"]) if training_dict["Exercice"] != "Repos" else old_exo

                df_actuel.loc[idx, "Exercice"] = new_exo
                df_actuel.loc[idx, "TST"] = round(new_tst, 2)
                df_actuel.loc[idx, "RPE"] = new_rpe
                df_actuel.loc[idx, "Charge"] = round(new_charge, 2)
                df_actuel.loc[idx, "Timestamp"] = training_dict["Timestamp"]
                df_actuel.loc[idx, "Details"] = json.dumps(liste_details)

                df_actuel = df_actuel.drop(columns=['Date_temp'])
                conn.update(worksheet="Trainings", data=df_actuel)
                st.cache_data.clear()
                return True
            else:
                df_actuel = df_actuel.drop(columns=['Date_temp'])

        # Si aucune ligne pour aujourd'hui
        training_dict["Charge"] = charge_individuelle
        training_dict["Details"] = json.dumps([nouveau_detail])
        new_row = pd.DataFrame([training_dict])
        
        df_updated = pd.concat([df_actuel, new_row], ignore_index=True) if not df_actuel.empty else new_row
            
        conn.update(worksheet="Trainings", data=df_updated)
        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"Erreur de sauvegarde de l'entraînement : {e}")
        return False

@st.cache_data(ttl=60)
def fetch_training_data(nom_eleve=None):
    """Récupère l'historique et filtre directement pour un élève précis si demandé"""
    try:
        df = conn.read(worksheet="Trainings")
        if nom_eleve and not df.empty and "Nom" in df.columns:
            df = df[df["Nom"] == nom_eleve]
        return df
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données : {e}")
        return pd.DataFrame()

def save_figures_to_cloud(athlete_name, new_figures_dict):
    """Met à jour le dictionnaire de figures d'un élève dans l'onglet Users"""
    try:
        df_users = get_users_data()
        if not df_users.empty and "Fullname" in df_users.columns:
            mask = df_users["Fullname"] == athlete_name
            if mask.any():
                idx = df_users[mask].index[0]
                df_users.loc[idx, "Figures"] = json.dumps(new_figures_dict)
                conn.update(worksheet="Users", data=df_users)
                st.cache_data.clear()
                return True
        return False
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde des figures : {e}")
        return False

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

# --- CSS / STYLE ATMOSPHÉRIQUE NOIR & BLEU ÉLECTRIQUE ---
st.markdown("""
    <style>
    /* Importation des polices futuristes depuis Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;500;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');

    /* --- FOND D'ÉCRAN PERSONNALISÉ --- */
    [data-testid="stAppViewContainer"] {
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

    /* Rendre la sidebar encore plus "fumée" avec un effet verre */
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
        color: #00f3ff; 
        text-shadow: 0 0 10px rgba(0, 243, 255, 0.5), 0 0 20px rgba(0, 243, 255, 0.3);
    }

    /* Typographie du texte classique */
    p, span, div, label {
        font-family: 'Rajdhani', sans-serif !important;
        font-size: 1.15rem;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
    }

    /* --- RÉPARATION DE L'ICÔNE SIDEBAR (EXCLUSION DU RAJDHANI) --- */
    span.material-symbols-rounded, 
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="collapsedControl"] span {
        font-family: 'Material Symbols Rounded' !important;
        font-size: 28px !important;
        text-shadow: 0 0 10px rgba(0, 243, 255, 0.5) !important;
        color: #00f3ff !important;
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
        
        # --- MODIFICATION ICI : accept_multiple_files=True ---
        uploaded_files = st.file_uploader("📥 Charger les vidéos à analyser (Multiples possibles)", type=['mp4', 'mov', 'avi'], accept_multiple_files=True)

        if uploaded_files:
            # On boucle sur chaque vidéo chargée
            for uploaded_file in uploaded_files:
                real_name = uploaded_file.name
                
                # On détermine si l'expander doit être ouvert par défaut (ouvert si non traité, fermé si déjà traité)
                is_processed = real_name in st.session_state.processed_files
                
                with st.expander(f"🎬 Vidéo : {real_name}", expanded=not is_processed):
                    
                    if is_processed:
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
                        
                        st.write("---")
                        
                        # --- 1. GESTION DU NOMBRE DE LIGNES DYNAMIQUES (+/-) ---
                        num_lines_key = f"num_lines_{real_name}"
                        if num_lines_key not in st.session_state:
                            st.session_state[num_lines_key] = 1

                        st.markdown("🔥 **Construction du Combo**")
                        st.caption("Définis chaque étape. Utilise les boutons ci-dessous pour ajouter ou retirer des lignes.")

                        # Les boutons SONT EN DEHORS du formulaire
                        c_btn_add, c_btn_sub, _ = st.columns([1, 1, 2])
                        with c_btn_add:
                            if st.button("➕ Ajouter un exo", key=f"add_{real_name}"):
                                st.session_state[num_lines_key] += 1
                                st.rerun()
                        with c_btn_sub:
                            if st.button("➖ Retirer un exo", key=f"sub_{real_name}"):
                                if st.session_state[num_lines_key] > 1:
                                    st.session_state[num_lines_key] -= 1
                                    st.rerun()

                        # --- 2. LE SEUL ET UNIQUE FORMULAIRE D'ENREGISTREMENT ---
                        with st.form(key=f"f_{real_name}", clear_on_submit=True):
                            c_rpe, c_info = st.columns([2, 1])
                            with c_rpe:
                                rpe = st.slider("Intensité globale (RPE)", 1, 10, 7, key=f"rpe_{real_name}")
                            with c_info:
                                total_time_calc = curr
                                st.info(f"⏱️ Temps chrono : {total_time_calc:.2f} s")

                            st.write("---")

                            athlete_figures = st.session_state.students_data[s_student].get('Figures', {"Mouvement basique": 1})
                            options_figures = ["-- Aucune --"] + list(athlete_figures.keys())
                            
                            combo_selections = []
                            
                            # --- LIGNES DYNAMIQUES ---
                            for i in range(st.session_state[num_lines_key]):
                                c_cat, c_fig, c_type, c_val = st.columns([1.2, 2, 1.2, 1])
                                with c_cat:
                                    cat = st.selectbox("Catégorie", ["Push", "Pull", "Mixte"], key=f"cat_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                                with c_fig:
                                    default_idx = 1 if i == 0 and len(options_figures) > 1 else 0 
                                    fig = st.selectbox("Figure", options_figures, index=default_idx, key=f"fig_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                                with c_type:
                                    etype = st.selectbox("Type", ["Dynamique", "Statique"], key=f"etype_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                                with c_val:
                                    val = st.number_input("Val (reps/sec)", min_value=0.1, step=0.5, value=1.0, key=f"val_{real_name}_{s_student}_{i}", label_visibility="collapsed")
                                    
                                combo_selections.append({"Cat": cat, "Figure": fig, "Type": etype, "Valeur": val})

                            st.write("---")

                            # --- 3. BOUTON VALIDATION (Bien à l'intérieur du form) ---
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
                                            "TST": round(total_time_calc, 2), 
                                            "RPE": int(rpe),                  
                                            "Charge": round(charge, 2)        
                                        }
                                        
                                        with st.spinner("⏳ Enregistrement dans le Cloud..."):
                                            if add_training_data(new_training):
                                                st.toast(f"✅ Combo enregistré ! (Charge: {charge:.1f} | Coeff: x{total_coeff:.2f})")
                                                st.session_state.processed_files.add(real_name)
                                                st.session_state[num_lines_key] = 1 
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
                        s_df = fetch_training_data(name) 
                        
                        if not s_df.empty and 'TST' in s_df.columns and 'Charge' in s_df.columns:
                            s_df['Date'] = pd.to_datetime(s_df['Timestamp'], errors='coerce').dt.normalize()
                            s_df['TST_Val'] = pd.to_numeric(s_df['TST'], errors='coerce').fillna(0)
                            
                            daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'})
                            daily = daily.resample('D').asfreq().fillna({'Charge': 0, 'TST_Val': 0})
                            daily['MA_Ch'] = daily['Charge'].rolling(window=3, min_periods=1).mean()
                            daily['MA_Vol'] = daily['TST_Val'].rolling(window=3, min_periods=1).mean()
                            
                            daily = daily.reset_index()
                            daily_train = daily[daily['Charge'] > 0]

                            fig_c = go.Figure()
                            # On ajoute le hovertemplate et la colorbar
                            fig_c.add_trace(go.Scatter(
                                x=daily_train['Date'], 
                                y=daily_train['Charge'], 
                                mode='markers', 
                                marker=dict(
                                    color=daily_train['RPE'], 
                                    colorscale='RdYlGn_r', 
                                    size=12,
                                    colorbar=dict(title="Score d'Intensité") 
                                ), 
                                name='Séance',
                                hovertemplate="<b>Date:</b> %{x}<br><b>Charge:</b> %{y}<br><b>Score d'Intensité:</b> %{marker.color}<extra></extra>"
                            ))

                            fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange', width=2), name='Tendance 3J'))
                            fig_c.update_layout(title="Charge & Intensité d'entraînement", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)

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
                                st.markdown(f"**🔎 Détail des exercices du {dt}**")
                                det = s_df[s_df['Date'].astype(str)==dt].copy()
                                                                        
                                if 'Details' in det.columns and pd.notna(det.iloc[0]['Details']) and str(det.iloc[0]['Details']).strip() != "":
                                    try:
                                        liste_details = json.loads(str(det.iloc[0]['Details']))
                                        df_details = pd.DataFrame(liste_details)
                                        
                                        # --- C'EST ICI QU'ON RENOMME LES COLONNES ---
                                        df_details = df_details.rename(columns={
                                            "TST": "TST (s)", 
                                            "Charge": "Charge (Unité)",
                                            "RPE": "Score d'Intensité"
                                        })
                                        
                                        st.dataframe(df_details[['Exercice', 'TST (s)', "Score d'Intensité", 'Charge (Unité)']], use_container_width=True, hide_index=True)
                                    except Exception:
                                        det_renamed = det.rename(columns={"RPE": "Score d'Intensité"})
                                        st.dataframe(det_renamed[['Exercice', 'TST', "Score d'Intensité", 'Charge']], use_container_width=True, hide_index=True)
                                else:
                                    det_renamed = det.rename(columns={"RPE": "Score d'Intensité"})
                                    st.dataframe(det_renamed[['Exercice', 'TST', "Score d'Intensité", 'Charge']], use_container_width=True, hide_index=True)
                        else:
                            st.info("Pas de données.")
                    
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

                            # On récupère les données filtrées pour l'élève connecté
                            s_df = fetch_training_data(selected_name)

                            if not s_df.empty and 'TST' in s_df.columns and 'Charge' in s_df.columns:
                                s_df['TST_Val'] = pd.to_numeric(s_df['TST'], errors='coerce').fillna(0)
                                s_df['Date'] = pd.to_datetime(s_df['Timestamp'], errors='coerce').dt.normalize()
                                
                                # TOUT CE QUI SUIT EST ALIGNÉ SOUS LE 's_df' CI-DESSUS
                                daily = s_df.groupby('Date').agg({'Charge':'sum', 'TST_Val':'sum', 'RPE':'mean'})
                                daily = daily.resample('D').asfreq().fillna({'Charge': 0, 'TST_Val': 0})
                                daily['MA_Ch'] = daily['Charge'].rolling(window=3, min_periods=1).mean()
                                daily['MA_Vol'] = daily['TST_Val'].rolling(window=3, min_periods=1).mean()
                                
                                daily = daily.reset_index()
                                daily_train = daily[daily['Charge'] > 0]

                                fig_c = go.Figure()

# On ajoute le hovertemplate et la colorbar
fig_c.add_trace(go.Scatter(
    x=daily_train['Date'], 
    y=daily_train['Charge'], 
    mode='markers', 
    marker=dict(
        color=daily_train['RPE'], 
        colorscale='RdYlGn_r', 
        size=12,
        colorbar=dict(title="Score d'Intensité") # Affiche la barre de couleur
    ), 
    name='Séance',
    hovertemplate="<b>Date:</b> %{x}<br><b>Charge:</b> %{y}<br><b>Score d'Intensité:</b> %{marker.color}<extra></extra>"
))

fig_c.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Ch'], mode='lines', line=dict(dash='dot', color='orange', width=2), name='Tendance 3J'))
fig_c.update_layout(title="Charge & Intensité d'entraînement", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)
                                
                                fig_v = go.Figure()
                                fig_v.add_trace(go.Bar(x=daily_train['Date'], y=daily_train['TST_Val'], marker=dict(color='#3366CC'), name='Vol'))
                                fig_v.add_trace(go.Scatter(x=daily['Date'], y=daily['MA_Vol'], mode='lines', line=dict(dash='dot', color='white'), name='Tend.'))
                                fig_v.update_layout(title="Ton Volume (TST / Reps)", template="plotly_dark", height=300, margin=dict(t=30,b=10,l=10,r=10), showlegend=False)

                                c1, c2 = st.columns(2)
                                with c1: sc = st.plotly_chart(fig_c, use_container_width=True, on_select="rerun", key=f"c_student_{selected_name}")
                                with c2: sv = st.plotly_chart(fig_v, use_container_width=True, on_select="rerun", key=f"v_student_{selected_name}")

                                sel = sc if sc and sc["selection"]["points"] else sv if sv and sv["selection"]["points"] else None
                                
                                # --- DÉTAIL AU CLIC (Aligné exactement sous 'sel = ...') ---
                                if sel:
                                    dt = sel["selection"]["points"][0]["x"]
                                    st.markdown(f"**🔎 Détail de ta séance du {dt}**")
                                    det = s_df[s_df['Date'].astype(str) == dt].copy()
                                    
                                    if not det.empty and 'Details' in det.columns and pd.notna(det.iloc[0]['Details']) and str(det.iloc[0]['Details']).strip() != "":
                                        try:
                                            liste_details = json.loads(str(det.iloc[0]['Details']))
                                            df_details = pd.DataFrame(liste_details)
                                            df_details = df_details.rename(columns={"TST": "TST (s)", "Charge": "Charge (Unité)"})
                                            st.dataframe(df_details[['Exercice', 'TST (s)', 'RPE', 'Charge (Unité)']], use_container_width=True, hide_index=True)
                                        except Exception:
                                            st.dataframe(det[['Exercice','TST','RPE','Charge']], use_container_width=True, hide_index=True)
                                    else:
                                        st.dataframe(det[['Exercice','TST','RPE','Charge']], use_container_width=True, hide_index=True)

                                # --- LE JOURNAL DÉTAILLÉ AVEC RECHERCHE PAR DATE ---
                                st.write("---")
                                st.subheader("📓 Journal détaillé de tes séances")
                                
                                # 1. On récupère toutes les dates uniques, triées
                                dates_disponibles = sorted(s_df['Date'].astype(str).unique(), reverse=True)
                                
                                # 2. Création du menu déroulant
                                date_choisie = st.selectbox("📅 Sélectionne une date pour voir les détails :", dates_disponibles)
                                
                                # 3. Filtre
                                df_jour = s_df[s_df['Date'].astype(str) == date_choisie]
                                st.write("")
                                
                                # 4. Affichage
                                for _, row in df_jour.iterrows():
                                    st.markdown(f"### 🎯 Bilan du {date_choisie}")
                                    raw_details = row.get('Details')
                                    
                                    if pd.notna(raw_details) and str(raw_details).strip() not in ["", "None", "nan"]:
                                        try:
                                            details_json = json.loads(str(raw_details))
                                            if isinstance(details_json, list) and len(details_json) > 0:
                                                nb_exos = len(details_json)
                                                st.caption(f"🏋️ **Nombre d'exos :** {nb_exos} | ⚡ **Charge Totale :** {row.get('Charge', 0)} | ⏱️ **TST Total :** {row.get('TST', 0)}s | 🧠 **Score d'Intensité :** {row.get('RPE', 0)}")
                                                
                                                df_show = pd.DataFrame(details_json)
                                                df_show = df_show.rename(columns={"TST": "TST (s)", "Charge": "Charge (Unité)"})
                                                st.dataframe(df_show, use_container_width=True, hide_index=True)
                                            else:
                                                st.info(f"Détails : {row.get('Exercice', 'N/A')}")
                                        except Exception:
                                            st.caption(f"⚡ Charge Totale : {row.get('Charge', 0)} | ⏱️ TST : {row.get('TST', 0)}s")
                                            st.info(f"Résumé de la séance : {row.get('Exercice', 'N/A')}")
                                    else:
                                        st.caption(f"⚡ Charge Totale : {row.get('Charge', 0)} | ⏱️ TST : {row.get('TST', 0)}s")
                                        st.info(f"Résumé de la séance : {row.get('Exercice', 'N/A')}")
                                        
                                    st.divider()
                                    
                            else:
                                st.info("ℹ️ Aucune séance n'est encore enregistrée. Il faut que ton coach analyse tes vidéos !")
                                
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

    # TOUT DOIT ÊTRE ALIGNÉ SOUS CE IF 👇
    if vbt_file:
        if 'vbt_path' not in st.session_state or st.session_state.get('vbt_name') != vbt_file.name:
            tfile = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            tfile.write(vbt_file.read())
            st.session_state.vbt_path = tfile.name
            st.session_state.vbt_name = vbt_file.name
            
        video_path = st.session_state.vbt_path

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # --- SÉCURITÉ FPS BIEN À L'ABRI ---
        import numpy as np # On le remet ici au cas où il aurait sauté en haut du fichier
        if fps == 0 or np.isnan(fps):
            fps = 30.0
            
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























































































