import streamlit as st
import pandas as pd
import time
import requests
from datetime import datetime

st.set_page_config(page_title="Caliperf - Coach Pro", layout="wide", page_icon="💪")

# --- 1. CONFIGURATION ---
LINK_UNIQUE = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"

# --- 2. CONFIGURATION DES CHAMPS ---
ENTRY_NOM = "entry.1847695661"
ENTRY_EXO = "entry.1595307876"
ENTRY_TST = "entry.549289703"
ENTRY_RPE = "entry.46344190"

# --- CSS / STYLE ---
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #1f2937; border-radius: 5px; color: white; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; }
    .metric-card { background-color: #262730; padding: 15px; border-radius: 10px; border: 1px solid #4b4b4b; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION MÉMOIRE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 

# NOUVEAU : On stocke maintenant un DICTIONNAIRE complet d'infos pour chaque élève
if 'students_data' not in st.session_state:
    st.session_state.students_data = {
        "Élève Test": {
            "link": LINK_UNIQUE, 
            "freq": "Non renseigné", 
            "goal": "Compte de démonstration"
        },
        "Lucas": {
            "link": LINK_UNIQUE, 
            "freq": "4x / semaine", 
            "goal": "Muscle Up propre"
        }
    }

st.title("🏋️ Caliperf : Espace Coaching")

# === CRÉATION DES 3 ONGLETS ===
tab_intro, tab_analyse, tab_eleves = st.tabs(["👋 Introduction", "🎥 Analyse Coach", "👥 Mes Élèves (Privé)"])

# =========================================================
# ONGLET 1 : INTRODUCTION (INSCRIPTION AVEC DÉTAILS)
# =========================================================
with tab_intro:
    st.header("Bienvenue dans l'accompagnement ! 🚀")
    st.write("Merci de remplir cette fiche pour activer ton dossier.")
    
    with st.form("form_intro"):
        col1, col2 = st.columns(2)
        with col1: nom = st.text_input("Nom")
        with col2: prenom = st.text_input("Prénom")
            
        freq = st.selectbox("Fréquence d'entraînement habituelle", 
            ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "6x / semaine", "Tous les jours"])
        
        objectif = st.text_area("Ton objectif principal")
        
        submitted = st.form_submit_button("✅ Valider mon inscription", type="primary", use_container_width=True)
        
        if submitted:
            if nom and prenom:
                full_name = f"{prenom} {nom}"
                
                # 1. ENREGISTREMENT COMPLET DANS LA MÉMOIRE DU COACH
                st.session_state.students_data[full_name] = {
                    "link": LINK_UNIQUE,
                    "freq": freq,
                    "goal": objectif
                }
                
                # 2. ENVOI SIMPLE VERS GOOGLE SHEETS (Pour notifier l'inscription)
                data_inscription = {
                    ENTRY_NOM: full_name,
                    ENTRY_EXO: "INSCRIPTION", 
                    ENTRY_TST: "0",          
                    ENTRY_RPE: ""             
                }
                
                try:
                    r = requests.post(LINK_UNIQUE, data=data_inscription)
                    if r.status_code == 200:
                        st.success(f"Bienvenue {prenom} ! Inscription validée.")
                        st.balloons()
                    else:
                        st.error("Erreur technique (Google).")
                except:
                    st.error("Problème de connexion.")
            else:
                st.warning("Nom et Prénom obligatoires.")

# =========================================================
# ONGLET 2 : ANALYSE COACH (ADAPTÉ À LA NOUVELLE STRUCTURE)
# =========================================================
with tab_analyse:
    st.header("1️⃣ Dépôt Vidéos")
    uploaded_files = st.file_uploader("Charger les vidéos", type=['mp4', 'mov', 'avi'], accept_multiple_files=True)
    st.divider()

    st.header("2️⃣ Analyse Coach")
    password = st.text_input("🔒 Mot de passe :", type="password", key="pwd_analyse")

    if password == "admin":
        if not uploaded_files:
            st.info("⚠️ En attente de fichiers...")
        else:
            files_map = {f.name: f for f in uploaded_files}
            options = [("✅ " if name in st.session_state.processed_files else "⏳ ") + name for name in files_map.keys()]
            selected_option = st.selectbox("Vidéo en cours :", options)
            real_name = selected_option.replace("✅ ", "").replace("⏳ ", "")
            current_file = files_map[real_name]

            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {'start': 0, 'acc': 0.0, 'run': False}
            timer = st.session_state.timers[real_name]

            c_vid, c_tools = st.columns([1.5, 1])
            with c_vid: st.video(current_file)
            with c_tools:
                st.subheader("⏱️ Chrono")
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("⏸️ PAUSE" if timer['run'] else "▶️ START", key=f"s_{real_name}", use_container_width=True):
                        if timer['run']: 
                            timer['acc'] += time.time() - timer['start']
                            timer['run'] = False
                        else: 
                            timer['start'] = time.time()
                            timer['run'] = True
                with b2:
                    if st.button("🗑️ RAZ", key=f"r_{real_name}", use_container_width=True):
                        timer['acc'] = 0.0
                        timer['run'] = False
                
                disp_time = timer['acc'] + (time.time() - timer['start'] if timer['run'] else 0)
                st.metric("Temps (TST)", f"{disp_time:.2f} s")
                
                st.write("---")

                with st.form(key=f"f_{real_name}"):
                    # Liste des noms (clés du dictionnaire)
                    student_names = list(st.session_state.students_data.keys())
                    selected_student = st.selectbox("👤 Sélectionner l'élève", student_names)
                    
                    # On récupère le lien spécifique dans les infos de l'élève
                    target_url = st.session_state.students_data[selected_student]["link"]
                    
                    exo = st.text_input("Exercice", value=real_name.split('.')[0])
                    rpe = st.slider("RPE", 1, 10, 7)
                    
                    if st.form_submit_button("☁️ ENVOYER"):
                        if disp_time > 0:
                            data = {
                                ENTRY_NOM: selected_student, 
                                ENTRY_EXO: exo,
                                ENTRY_TST: str(round(disp_time, 2)).replace('.', ','),
                                ENTRY_RPE: str(rpe)
                            }
                            try:
                                r = requests.post(target_url, data=data)
                                if r.status_code == 200:
                                    st.success(f"Données envoyées pour {selected_student} !")
                                    st.session_state.processed_files.add(real_name)
                                    time.sleep(1)
                                    st.rerun()
                                else: st.error("Erreur Google Forms")
                            except: st.error("Erreur Connexion")
                        else: st.warning("Chrono à 0 !")

    elif password: st.error("Mot de passe incorrect")

# =========================================================
# ONGLET 3 : FICHE ÉLÈVE DÉTAILLÉE (NOUVEAU)
# =========================================================
with tab_eleves:
    st.header("🔐 Gestion Athlètes")
    
    admin_pwd = st.text_input("🔒 Mot de passe Admin :", type="password", key="pwd_admin")
    
    if admin_pwd == "admin":
        st.success("Accès autorisé")
        
        st.divider()
        
        # SÉLECTEUR D'ÉLÈVE
        all_students = list(st.session_state.students_data.keys())
        choice = st.selectbox("🔍 Rechercher une fiche élève :", all_students)
        
        if choice:
            # On récupère les infos de l'élève choisi
            infos = st.session_state.students_data[choice]
            
            # AFFICHAGE DE LA CARTE D'IDENTITÉ
            st.markdown(f"### 👤 Fiche de : {choice}")
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"""
                <div class="metric-card">
                    <h4>📅 Fréquence</h4>
                    <p style="font-size: 1.2em; color: #4dabcf;">{infos['freq']}</p>
                </div>
                """, unsafe_allow_html=True)
                
            with c2:
                st.markdown(f"""
                <div class="metric-card">
                    <h4>🎯 Objectif Principal</h4>
                    <p style="font-size: 1.2em; color: #ffbd45;">{infos['goal']}</p>
                </div>
                """, unsafe_allow_html=True)
            
            st.info(f"🔗 Lien Formulaire actif : ...{infos['link'][-20:]}")

    elif admin_pwd:
        st.error("⛔ Accès refusé.")
    else:
        st.info("Identification requise.")
