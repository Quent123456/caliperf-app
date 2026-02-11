import streamlit as st
import pandas as pd
import plotly.express as px
import time
import requests
import json
import os
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Caliperf - Coach Pro", layout="wide", page_icon="💪")

# --- 1. CHARGEMENT SÉCURISÉ DES CONFIGURATIONS ---
try:
    # On charge les secrets
    ADMIN_PWD = st.secrets["general"]["admin_password"]
    LINK_UNIQUE = st.secrets["general"]["google_form_url"]
    DELETE_SCRIPT_URL = st.secrets["general"]["delete_script_url"]
    ENTRIES = st.secrets["google_entries"]
except Exception as e:
    # Si ça plante ici, c'est que le fichier secrets.toml est mal écrit
    st.error(f"⚠️ Erreur critique de configuration : {e}")
    st.stop()

DB_FILE = "caliperf_db.json"

# --- 2. FONCTIONS DE GESTION DES DONNÉES ---
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

# --- 3. GESTION DU CHRONO (CALLBACKS) ---
def toggle_timer(video_key):
    timer = st.session_state.timers[video_key]
    if timer['run']:
        # ON PAUSE : On ajoute le temps écoulé au compteur 'acc'
        timer['acc'] += time.time() - timer['start']
        timer['run'] = False
    else:
        # ON START : On définit le nouveau point de départ
        timer['start'] = time.time()
        timer['run'] = True

def reset_timer(video_key):
    st.session_state.timers[video_key] = {'start': 0, 'acc': 0.0, 'run': False}

# --- CSS / STYLE ---
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1f2937; border-radius: 5px; color: white; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; }
    .metric-card { background-color: #262730; padding: 15px; border-radius: 10px; border: 1px solid #4b4b4b; margin-bottom: 10px; }
    .big-time { font-size: 2.5em; font-weight: bold; color: #00FF00; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION SESSION STATE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 
if 'students_data' not in st.session_state: st.session_state.students_data = load_data()

st.title("🏋️ Caliperf : Espace Coaching")

tab_intro, tab_analyse, tab_eleves = st.tabs(["👋 Introduction", "🎥 Analyse Coach", "👥 Mes Élèves (Privé)"])

# =========================================================
# ONGLET 1 : INTRODUCTION
# =========================================================
with tab_intro:
    st.header("Bienvenue dans l'accompagnement ! 🚀")
    
    # Tout ce qui est dans le formulaire doit être aligné
    with st.form("form_intro"):
        col1, col2 = st.columns(2)
        with col1: 
            nom = st.text_input("Nom")
        with col2: 
            prenom = st.text_input("Prénom")
        
        col3, col4 = st.columns(2)
        with col3: 
            freq = st.selectbox("Fréquence", ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "Tous les jours"])
        with col4: 
            experience = st.text_input("Temps de pratique", placeholder="Ex: 2 ans, Débutant...")
        
        objectif = st.text_area("Ton objectif principal")
        
        # Le bouton doit être au même niveau d'alignement que les colonnes
        if st.form_submit_button("✅ Valider mon inscription", type="primary", use_container_width=True):
            if nom and prenom:
                full_name = f"{prenom} {nom}"
                
                # Enregistrement dans la session
                st.session_state.students_data[full_name] = {
                    "link": LINK_UNIQUE, 
                    "freq": freq, 
                    "goal": objectif,
                    "exp": experience
                }
                
                # Sauvegarde dans le fichier JSON
                save_data(st.session_state.students_data)
                
                st.success(f"Dossier créé pour {prenom} !")
                st.balloons()
            else:
                st.warning("Nom et Prénom obligatoires.")

# =========================================================
# ONGLET 2 : ANALYSE COACH
# =========================================================
# Ajoute ceci dans tes imports
import plotly.express as px

# Ajoute ceci dans la section FONCTIONS
@st.cache_data(ttl=60) # Garde les données en mémoire 60 secondes pour aller vite
def fetch_training_data(csv_url):
    try:
        # On lit le CSV publié par Google Sheets
        df = pd.read_csv(csv_url)
        # On renomme les colonnes pour que ce soit propre (adapte selon tes vrais noms)
        # Assure-toi que les noms ici correspondent aux en-têtes de ton Google Sheet
        df.columns = ["Timestamp", "Nom", "Exercice", "TST", "RPE", "Charge"]
        return df
    except Exception as e:
        return pd.DataFrame() # Retourne vide si erreur
with tab_analyse:
    col_up, col_login = st.columns([3, 1])
    with col_up:
        uploaded_files = st.file_uploader("Charger les vidéos", type=['mp4', 'mov', 'avi'], accept_multiple_files=True)
    with col_login:
        password = st.text_input("🔒 Mot de passe Coach", type="password", key="pwd_analyse")

    st.divider()

    # Vérification sécurisée du mot de passe
    if password == ADMIN_PWD:
        if not uploaded_files:
            st.info("⚠️ En attente de fichiers...")
        else:
            files_map = {f.name: f for f in uploaded_files}
            options = [("✅ " if name in st.session_state.processed_files else "⏳ ") + name for name in files_map.keys()]
            selected_option = st.selectbox("Vidéo en cours :", options)
            real_name = selected_option.replace("✅ ", "").replace("⏳ ", "")
            
            # Initialisation du timer pour ce fichier spécifique s'il n'existe pas
            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {'start': 0, 'acc': 0.0, 'run': False}
            
            timer = st.session_state.timers[real_name]

            c_vid, c_tools = st.columns([1.5, 1])
            
            with c_vid:
                st.video(files_map[real_name])
            
            with c_tools:
                st.subheader("⏱️ Analyse TST")
                
                # Zone d'affichage du temps (Placeholder vide au début)
                time_display = st.empty()
                
                # Calcul du temps actuel à afficher
                current_time = timer['acc']
                if timer['run']:
                    current_time += time.time() - timer['start']

                # Affichage statique initial
                time_display.markdown(f'<div class="big-time">{current_time:.2f} s</div>', unsafe_allow_html=True)

                b1, b2 = st.columns(2)
                with b1:
                    # Utilisation du callback on_click pour une gestion d'état parfaite
                    btn_label = "⏸️ PAUSE" if timer['run'] else "▶️ START"
                    st.button(btn_label, key=f"btn_{real_name}", on_click=toggle_timer, args=(real_name,), use_container_width=True)
                with b2:
                    st.button("🗑️ RAZ", key=f"rst_{real_name}", on_click=reset_timer, args=(real_name,), use_container_width=True)

                st.write("---")

                # Formulaire d'envoi
                with st.form(key=f"f_{real_name}"):
                    student_keys = list(st.session_state.students_data.keys())
                    
                    if student_keys:
                        selected_student = st.selectbox("👤 Athlète", student_keys)
                        exo = st.text_input("Exercice", value=real_name.split('.')[0])
                        rpe = st.slider("RPE", 1, 10, 7)
                        
                        if st.form_submit_button("☁️ ENVOYER DONNÉES"):
                            # 1. On recalcule le temps final exact au moment du clic
                            final_time = timer['acc']
                            if timer['run']: 
                                final_time += time.time() - timer['start']
                            
                            if final_time > 0:
                                # 2. CALCUL DE LA CHARGE
                                charge_calc = final_time * rpe
                                
                                # 3. CRÉATION DU PAQUET DE DONNÉES
                                data = {
                                    ENTRIES['nom']: selected_student, 
                                    ENTRIES['exo']: exo,
                                    ENTRIES['tst']: str(round(final_time, 2)).replace('.', ','),
                                    ENTRIES['rpe']: str(rpe),
                                    # C'est ici qu'on ajoute la charge calculée
                                    ENTRIES['charge']: str(round(charge_calc, 2)).replace('.', ',')
                                }
                                
                                try:
                                    # 4. ENVOI
                                    target = LINK_UNIQUE
                                    r = requests.post(target, data=data)
                                    
                                    if r.status_code == 200:
                                        st.success(f"✅ Envoyé ! (Charge: {charge_calc:.1f})")
                                        st.session_state.processed_files.add(real_name)
                                        time.sleep(1)
                                        st.rerun()
                                    else: 
                                        st.error("Erreur Google Forms")
                                except Exception as e: 
                                    st.error(f"Erreur technique : {e}")
                            else: 
                                st.warning("Le chrono est à 0 !")
                    else:
                        st.warning("Aucun élève inscrit. Va dans l'onglet Introduction.")
                        st.divider()
st.subheader(f"📈 Progression de {selected_student}")

# URL CSV DE TON SHEET (À trouver dans Fichier > Partager > Publier sur le Web > CSV)
# Mets ça dans tes secrets.toml idéalement
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/...../pub?output=csv" 

df_history = fetch_training_data(SHEET_CSV_URL)

if not df_history.empty:
    # Filtrer pour l'élève actuel et l'exercice actuel
    mask = (df_history['Nom'] == selected_student) & (df_history['Exercice'] == exo)
    student_data = df_history[mask]

    if not student_data.empty:
        # Créer un graphique interactif
        fig = px.line(student_data, x='Timestamp', y='Charge', markers=True, 
                      title=f"Evolution de la Charge - {exo}")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Pas encore de données pour cet exercice.")

# =========================================================
# ONGLET 3 : MES ÉLÈVES (PRIVÉ)
# =========================================================
with tab_eleves:
    st.header("👥 Gestion et Progression des Athlètes")
    
    # URL CSV DE TON SHEET (Assure-toi de mettre la vraie URL ici ou dans secrets)
    # Exemple: "https://docs.google.com/spreadsheets/d/e/2PACX-..../pub?output=csv"
    SHEET_CSV_URL = st.secrets["general"].get("csv_url", "") # Ou colle ton lien en dur ici si tu n'as pas mis dans secrets
    
    pwd_eleves = st.text_input("🔒 Mot de passe accès privé", type="password", key="pwd_eleves")
    
    if pwd_eleves == ADMIN_PWD:
        # 1. On charge les données d'entraînement UNE SEULE FOIS pour tout le monde
        if SHEET_CSV_URL:
            df_history = fetch_training_data(SHEET_CSV_URL)
            
            # --- NETTOYAGE DES DONNÉES (Crucial pour les virgules françaises) ---
            if not df_history.empty and 'Charge' in df_history.columns:
                # On remplace les virgules par des points et on convertit en nombres
                df_history['Charge'] = df_history['Charge'].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce')
                # On convertit le Timestamp en date
                df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
        else:
            df_history = pd.DataFrame()
            st.warning("⚠️ URL du CSV manquante dans le code.")

        if not st.session_state.students_data:
            st.info("Aucun élève enregistré pour le moment.")
        else:
            # On organise l'affichage sur 2 colonnes
            cols = st.columns(2)
            
            for index, (name, info) in enumerate(st.session_state.students_data.items()):
                # On alterne les colonnes gauche/droite
                with cols[index % 2]:
                    
                    # --- CARTE ÉLÈVE ---
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name}</h3>
                        <p><b>📅 Fréquence :</b> {info.get('freq', 'Non définie')}</p>
                        <p><b>⏳ Expérience :</b> {info.get('exp', 'Non renseignée')}</p>
                        <p><b>🎯 Objectif :</b> {info.get('goal', 'Aucun objectif')}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    # --- ZONE GRAPHIQUE (Dans un expander pour ne pas surcharger) ---
                    with st.expander(f"📈 Voir la progression de {name}"):
                        if not df_history.empty:
                            # Filtrer les données pour CET élève
                            student_df = df_history[df_history['Nom'] == name].copy()
                            
                            if not student_df.empty:
                                # Lister les exercices pratiqués par l'élève
                                liste_exos = student_df['Exercice'].unique()
                                
                                if len(liste_exos) > 0:
                                    # Sélecteur d'exercice spécifique à cet élève
                                    # La clé (key) doit être unique, donc on utilise le nom de l'élève
                                    choix_exo = st.selectbox("Choisir l'exercice :", liste_exos, key=f"sel_{name}")
                                    
                                    # Filtrer par exercice
                                    data_to_plot = student_df[student_df['Exercice'] == choix_exo].sort_values('Timestamp')
                                    
                                    # Création du Graphique
                                    fig = px.line(data_to_plot, x='Timestamp', y='Charge', markers=True,
                                                  title=f"Charge : {choix_exo}")
                                    st.plotly_chart(fig, use_container_width=True)
                                else:
                                    st.info("Données trouvées, mais pas d'exercice identifié.")
                            else:
                                st.info("Pas encore de données d'entraînement enregistrées.")
                        else:
                            st.info("Impossible de charger l'historique global.")

                    # --- BOUTON SUPPRESSION ---
                    if st.button(f"🗑️ Supprimer {name}", key=f"del_{name}"):
                        with st.spinner(f"Suppression de {name} en cours..."):
                            try:
                                response = requests.get(DELETE_SCRIPT_URL, params={"name": name})
                                if response.status_code == 200 and "Succès" in response.text:
                                    del st.session_state.students_data[name]
                                    save_data(st.session_state.students_data)
                                    st.success(f"✅ {name} supprimé !")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Erreur du script : {response.text}")
                            except Exception as e:
                                st.error(f"Impossible de contacter Google Sheets : {e}")
    else:
        st.warning("Veuillez entrer le mot de passe administrateur pour consulter les fiches.")




