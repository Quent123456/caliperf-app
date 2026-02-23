import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.express as px
import plotly.graph_objects as go
import time
import requests
import json
import os
from datetime import datetime

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
# Connexion au Sheet grâce à tes secrets
conn = st.connection("gsheets", type=GSheetsConnection)

def get_users_data():
    """Récupère les données de l'onglet 'Users'"""
    try:
        # ttl=0 pour toujours avoir les données fraîches
        return conn.read(worksheet="Users", ttl=0)
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

@st.cache_data(ttl=60)
def fetch_training_data(csv_url):
    try:
        if not csv_url: return pd.DataFrame()
        df = pd.read_csv(csv_url)
        # On s'assure d'avoir les bonnes colonnes pour éviter les bugs
        # Si tes colonnes dans le CSV sont différentes, adapte cette liste !
        if len(df.columns) >= 6:
            df.columns = ["Timestamp", "Nom", "Exercice", "TST", "RPE", "Charge"]
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
    st.session_state.timers[video_key] = {'start': 0, 'acc': 0.0, 'run': False}

# --- CSS / STYLE ---
st.markdown("""
    <style>
    /* Fond global plus sombre */
    .stApp {
        background-color: #0e1117;
    }
    
    /* Titres en majuscules et police plus impactante */
    h1, h2, h3 {
        font-family: 'Helvetica Neue', sans-serif;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Style des onglets plus moderne */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
        font-weight: 600;
    }
    
    /* Cards métriques avec effet de verre (Glassmorphism) */
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-5px);
        border-color: #ff4b4b;
    }
    
    /* Boutons plus ronds */
    div.stButton > button {
        border-radius: 20px;
        font-weight: bold;
        border: none;
        transition: all 0.3s ease;
    }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION SESSION STATE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 
if 'students_data' not in st.session_state:
    # 1. On récupère les données du Cloud
    df_users = get_users_data()
    
    # 2. Si on a des données, on les convertit au format que ton application connaît déjà (Dictionnaire)
    if not df_users.empty:
        # On vérifie si la colonne 'Fullname' existe (créée à l'inscription)
        if "Fullname" in df_users.columns:
            st.session_state.students_data = df_users.set_index("Fullname").to_dict(orient="index")
        else:
            # Si c'est vide ou pas encore formaté
            st.session_state.students_data = {}
    else:
        st.session_state.students_data = {}

st.title("🏋️ Caliperf : Espace Coaching")

tab_intro, tab_analyse, tab_eleves = st.tabs(["👋 Création Compte / Profil", "🎥 Espace Vidéo", "📊 Mon Suivi (Connexion)"])

# =========================================================
# ONGLET 1 : INSCRIPTION / PROFIL
# =========================================================
with tab_intro:
    st.header("Création ou Mise à jour du Profil 🚀")
    st.caption("Remplis ce formulaire pour créer ton compte ou mettre à jour tes informations.")
    
    with st.form("form_intro"):
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
                # Préparation des données
                new_user_data = {
                    "Fullname": f"{prenom} {nom}",
                    "Nom": nom,
                    "Prenom": prenom,
                    "Password": pwd_eleve,
                    "Frequence": freq,
                    "Experience": experience,
                    "Poids": poids,
                    "Taille": taille,
                    "Sexe": sexe,
                    "Objectif": objectif,
                    "Date": datetime.now().strftime("%Y-%m-%d")
                }
                
                # Envoi vers Google Sheets
                if add_new_user(new_user_data):
                    st.success(f"Compte créé pour {prenom} ! 🎉")
                    st.balloons()
            else:
                st.warning("Nom, Prénom et Mot de passe sont obligatoires.")

# =========================================================
# ONGLET 2 : ANALYSE VIDÉO
# =========================================================
with tab_analyse:
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
                    data_repos = {
                        ENTRIES['nom']: eleve_repos, ENTRIES['exo']: "Repos",
                        ENTRIES['tst']: "0", ENTRIES['rpe']: "0", ENTRIES['charge']: "0"
                    }
                    try:
                        requests.post(LINK_UNIQUE, data=data_repos)
                        st.success(f"Repos noté pour {eleve_repos}")
                        time.sleep(1)
                        st.rerun()
                    except: st.error("Erreur envoi")

        st.divider()

        # accept_multiple_files=False empêche la surcharge de la RAM
        uploaded_file = st.file_uploader("📥 Charger la vidéo à analyser (1 à la fois)", type=['mp4', 'mov', 'avi'], accept_multiple_files=False)

        if uploaded_file:
            real_name = uploaded_file.name
            
            # Affichage du statut
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
                
                b1, b2 = st.columns(2)
                with b1: st.button("⏸️ PAUSE" if timer['run'] else "▶️ START", key=f"btn_{real_name}", on_click=toggle_timer, args=(real_name,), use_container_width=True)
                with b2: st.button("🗑️ RAZ", key=f"rst_{real_name}", on_click=reset_timer, args=(real_name,), use_container_width=True)

                st.write("---")
                
                # --- FORMULAIRE SIMPLIFIÉ (TST UNIQUEMENT) ---
                with st.form(key=f"f_{real_name}"):
                    s_keys = list(st.session_state.students_data.keys())
                    if s_keys:
                        s_student = st.selectbox("Athlète", s_keys)
                        exo = st.text_input("Exercice", value=real_name.split('.')[0])
                        
                        c_rpe, c_info = st.columns([2, 1])
                        with c_rpe:
                            rpe = st.slider("Intensité (RPE)", 1, 10, 7)
                        with c_info:
                             st.info(f"⏱️ Temps retenu : {curr:.2f} s")

                        if st.form_submit_button("☁️ ENVOYER DONNÉES "):
                            f_time = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                            
                            charge = f_time * rpe
                            val_princ = f"{round(f_time, 2)} s"

                            if charge > 0:
                                d_send = {
                                    ENTRIES['nom']: s_student, 
                                    ENTRIES['exo']: exo,
                                    ENTRIES['tst']: str(val_princ).replace('.', ','),
                                    ENTRIES['rpe']: str(rpe), 
                                    ENTRIES['charge']: str(round(charge, 2)).replace('.', ',')
                                }
                                try:
                                    if requests.post(LINK_UNIQUE, data=d_send).status_code == 200:
                                        st.success(f"✅ Données envoyées ! (Charge: {charge:.1f})")
                                        st.session_state.processed_files.add(real_name)
                                        time.sleep(1)
                                        st.rerun()
                                    else: st.error("Erreur Forms")
                                except Exception as e: st.error(f"Erreur: {e}")
                            else:
                                st.warning("Le chrono est à 0 !")
                    else: st.warning("Aucun élève.")
        else:
            st.info("📂 En attente de vidéos à analyser...")

    # --- MODE ÉLÈVE ---
    else:
        st.subheader("📤 Envoyer mes vidéos au Coach")
        st.markdown("""
        Pour que ton coach puisse analyser tes mouvements, il faut lui envoyer tes vidéos.
        """)
        col_send1, col_send2 = st.columns([1, 2])
        with col_send1:
            st.info("👇 Clique ici pour déposer tes fichiers")
            st.link_button("📂 Ouvrir le dossier de dépôt", UPLOAD_LINK, type="primary", use_container_width=True)
        with col_send2:
            st.caption("Une fois tes vidéos déposées, préviens ton coach ! Il les récupérera pour les analyser ici même.")
            st.image("https://cdn-icons-png.flaticon.com/512/2983/2983067.png", width=100)

# =========================================================
# ONGLET 3 : MON SUIVI (SÉCURISÉ)
# =========================================================
with tab_eleves:
    st.header("📊 Suivi des Performances")
    
    SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTABZd8nfqjdUzGUBjb57ntk8ACmBIPg7CM5VBMjGSdXJtiAN1ZJhwpGUb2EJvQZOrJ55s9eE2c8exn/pub?output=csv"
    if SHEET_CSV_URL:
        df_history = fetch_training_data(SHEET_CSV_URL)
        if not df_history.empty and 'Charge' in df_history.columns:
            df_history['Charge'] = df_history['Charge'].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce')
            df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
            df_history['Date'] = df_history['Timestamp'].dt.date
    else:
        df_history = pd.DataFrame()

    mode_connexion = st.radio("Qui êtes-vous ?", ["👤 Je suis Élève", "🧢 Je suis le Coach"], horizontal=True)
