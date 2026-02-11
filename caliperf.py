import streamlit as st
import pandas as pd
import time
import requests
import json
import os
from datetime import datetime

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Caliperf - Coach Pro", layout="wide", page_icon="💪")

# --- 1. CHARGEMENT SÉCURISÉ DES CONFIGURATIONS ---
# On utilise st.secrets pour récupérer les données sensibles
try:
    ADMIN_PWD = st.secrets["general"]["admin_password"]
    LINK_UNIQUE = st.secrets["general"]["google_form_url"]
    ENTRIES = st.secrets["google_entries"]
except FileNotFoundError:
    st.error("⚠️ Fichier .streamlit/secrets.toml introuvable. Configure tes secrets.")
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
# Ces fonctions s'exécutent AVANT le rechargement de la page pour garantir la précision
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
    with st.form("form_intro"):
        col1, col2 = st.columns(2)
        with col1: nom = st.text_input("Nom")
        with col2: prenom = st.text_input("Prénom")
        
        col3, col4 = st.columns(2)
        with col3: freq = st.selectbox("Fréquence", ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "Tous les jours"])
        with col4: experience = st.text_input("Temps de pratique (ex: 2 ans, débutant...)", placeholder="Depuis combien de temps pratiques-tu ?")
        
        objectif = st.text_area("Ton objectif principal")
        
        if st.form_submit_button("✅ Valider mon inscription", type="primary", use_container_width=True):
            if nom and prenom:
                full_name = f"{prenom} {nom}"
                # On ajoute 'exp' dans le dictionnaire de l'élève
                st.session_state.students_data[full_name] = {
                    "link": LINK_UNIQUE, 
                    "freq": freq, 
                    "goal": objectif,
                    "exp": experience
                }
                save_data(st.session_state.students_state)
                st.success(f"Dossier créé pour {prenom} !")
                st.balloons()
            else:
                st.warning("Nom et Prénom obligatoires.")

# =========================================================
# ONGLET 2 : ANALYSE COACH
# =========================================================
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
                                    target = st.session_state.students_data[selected_student]["link"]
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
        # =========================================================
# ONGLET 3 : MES ÉLÈVES (PRIVÉ)
# =========================================================
with tab_eleves:
    st.header("👥 Gestion des Athlètes")
    
    # Vérification du mot de passe pour cet onglet aussi (optionnel mais recommandé)
    pwd_eleves = st.text_input("🔒 Mot de passe accès privé", type="password", key="pwd_eleves")
    
    if pwd_eleves == ADMIN_PWD:
        if not st.session_state.students_data:
            st.info("Aucun élève enregistré pour le moment.")
        else:
            # On peut organiser en colonnes pour faire des "cartes"
            cols = st.columns(2) 
            
            for index, (name, info) in enumerate(st.session_state.students_data.items()):
                # On alterne entre la colonne 0 et 1
                with cols[index % 2]:
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name}</h3>
                        <p><b>📅 Fréquence :</b> {info.get('freq', 'Non définie')}</p>
                        <p><b>⏳ Expérience :</b> {info.get('exp', 'Non renseignée')}</p>
                        <p><b>🎯 Objectif :</b> {info.get('goal', 'Aucun objectif listé')}</p>
                        <hr style='border-color:#4b4b4b;'>
                        <p style='font-size:0.8em; color:gray;'>Lien Google Forms : {info.get('link')[:30]}...</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Optionnel : bouton pour supprimer un élève
                    if st.button(f"Supprimer {name}", key=f"del_{name}"):
                        del st.session_state.students_data[name]
                        save_data(st.session_state.students_data)
                        st.rerun()
    else:
        st.warning("Veuillez entrer le mot de passe administrateur pour consulter les fiches élèves.")
       

