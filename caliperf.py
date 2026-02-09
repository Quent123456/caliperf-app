import streamlit as st
import pandas as pd
import time
import requests
from datetime import datetime

# --- CONFIGURATION ---
URL_GOOGLE_FORM = "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse"

ENTRY_NOM = "entry.1847695661"
ENTRY_EXO = "entry.1595307876"
ENTRY_TST = "entry.549289703"
ENTRY_RPE = "entry.46344190"

st.set_page_config(page_title="Caliperf - App", layout="wide", page_icon="💪")

# --- CSS / STYLE ---
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #1f2937; border-radius: 5px; color: white; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; }
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION DE LA MÉMOIRE (SESSION STATE) ---
# C'est ici qu'on gère le multi-vidéo : chaque fichier aura son propre état
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = set() # Pour se souvenir des vidéos déjà envoyées

if 'timers' not in st.session_state:
    st.session_state.timers = {} # Dictionnaire pour stocker les chronos de CHAQUE vidéo séparément

st.title("🏋️ Caliperf : Street Workout Cloud")

# === CRÉATION DES ONGLETS ===
tab_accueil, tab_analyse = st.tabs(["🏠 Calcul & Accueil", "🎥 Analyse Coach"])

# =========================================================
# ONGLET 1 : ACCUEIL (Ton calculateur)
# =========================================================
with tab_accueil:
    st.header("🧮 Calculateur de Charge")
    st.write("Calcule rapidement le tonnage de ta séance.")
    
    col1, col2, col3 = st.columns(3)
    with col1: series = st.number_input("Séries", 0, 20, 4)
    with col2: reps = st.number_input("Répétitions", 0, 100, 10)
    with col3: poids = st.number_input("Poids (kg)", 0.0, 200.0, 0.0, step=1.0)
    
    total = series * reps * (poids if poids > 0 else 1) 
    
    if total > 0:
        st.info(f"📊 Volume Total : **{total}** kg (théorique)")

# =========================================================
# ONGLET 2 : ANALYSE MULTI-VIDÉOS (CORRIGÉ)
# =========================================================
with tab_analyse:
    st.header("1️⃣ Espace Athlète : Dépôt")
    uploaded_files = st.file_uploader(
        "Déposer les vidéos ici (Sélection multiple possible)", 
        type=['mp4', 'mov', 'avi'], 
        accept_multiple_files=True
    )

    st.divider()

    st.header("2️⃣ Espace Coach : Analyse")
    password = st.text_input("🔒 Mot de passe Coach :", type="password")

    if password == "admin":
        if not uploaded_files:
            st.info("⚠️ Aucune vidéo chargée par l'athlète.")
        else:
            # --- MENU DÉROULANT INTELLIGENT ---
            # On crée un dictionnaire pour retrouver le fichier via son nom
            files_map = {f.name: f for f in uploaded_files}
            
            # On prépare la liste des noms pour le menu déroulant
            # On ajoute un ✅ si la vidéo est dans la liste "processed_files"
            options = []
            for name in files_map.keys():
                prefix = "✅ " if name in st.session_state.processed_files else "⏳ "
                options.append(prefix + name)

            # Le sélecteur permet de choisir UNE vidéo à la fois sans recharger la page
            selected_option = st.selectbox("Choisir la vidéo à corriger :", options)
            
            # On nettoie le nom pour récupérer le fichier original
            real_name = selected_option.replace("✅ ", "").replace("⏳ ", "")
            current_file = files_map[real_name]

            # --- INITIALISATION DU CHRONO SPÉCIFIQUE À CETTE VIDÉO ---
            # Si cette vidéo n'a pas encore de chrono en mémoire, on le crée
            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {
                    'start_time': 0, 
                    'accumulated_time': 0.0, 
                    'is_running': False
                }
            
            # On récupère les données du chrono de CETTE vidéo
            timer_data = st.session_state.timers[real_name]

            st.divider()
            
            # --- AFFICHAGE COLONNES (VIDÉO | OUTILS) ---
            col_vid, col_tools = st.columns([1.5, 1])
            
            with col_vid:
                st.subheader(f"📺 {real_name}")
                st.video(current_file)
            
            with col_tools:
                st.subheader("⏱️ Mesures")
                
                # --- LOGIQUE CHRONOMÈTRE ---
                c1, c2 = st.columns(2)
                with c1:
                    # Bouton START / PAUSE
                    label_btn = "⏸️ PAUSE" if timer_data['is_running'] else "▶️ START"
                    # IMPORTANT : key unique pour éviter les conflits
                    if st.button(label_btn, key=f"btn_start_{real_name}", use_container_width=True):
                        if timer_data['is_running']:
                            # On met en pause : on ajoute le temps écoulé au total
                            timer_data['accumulated_time'] += time.time() - timer_data['start_time']
                            timer_data['is_running'] = False
                        else:
                            # On démarre
                            timer_data['start_time'] = time.time()
                            timer_data['is_running'] = True
                
                with c2:
                    # Bouton RESET
                    if st.button("🗑️ RESET", key=f"btn_reset_{real_name}", use_container_width=True):
                        timer_data['accumulated_time'] = 0.0
                        timer_data['is_running'] = False

                # Calcul du temps à afficher
                display_time = timer_data['accumulated_time']
                if timer_data['is_running']:
                    display_time += time.time() - timer_data['start_time']
                
                # Affichage en gros
                st.metric("Temps sous tension (TST)", f"{display_time:.2f} s")
                
                st.write("---")

                # --- FORMULAIRE D'ENVOI ---
                # Key unique obligatoire ici aussi
                with st.form(key=f"form_{real_name}"):
                    nom = st.text_input("Athlète")
                    # On devine l'exercice via le nom du fichier (ex: "tractions.mp4" -> "tractions")
                    exo_val = real_name.split('.')[0]
                    exo = st.text_input("Exercice", value=exo_val)
                    rpe = st.slider("RPE", 1, 10, 7)
                    
                    submitted = st.form_submit_button("☁️ VALIDER & ENVOYER", type="primary", use_container_width=True)
                    
                    if submitted:
                        if nom and display_time > 0:
                            data = {
                                ENTRY_NOM: nom,
                                ENTRY_EXO: exo,
                                ENTRY_TST: str(round(display_time, 2)).replace('.', ','),
                                ENTRY_RPE: str(rpe)
                            }
                            
                            try:
                                r = requests.post(URL_GOOGLE_FORM, data=data)
                                if r.status_code == 200:
                                    st.success(f"✅ Données pour {real_name} envoyées !")
                                    # On marque la vidéo comme traitée
                                    st.session_state.processed_files.add(real_name)
                                    time.sleep(1)
                                    st.rerun() # On recharge pour mettre à jour la liste
                                else:
                                    st.error("Erreur Google Forms.")
                            except Exception as e:
                                st.error(f"Erreur de connexion: {e}")
                        else:
                            st.warning("⚠️ Renseigne le nom et lance le chrono.")

    elif password:
        st.error("Mot de passe incorrect")
