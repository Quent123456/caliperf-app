import streamlit as st
import pandas as pd
import time
import requests
from datetime import datetime

st.set_page_config(page_title="Caliperf - Coach Pro", layout="wide", page_icon="💪")

# --- 1. CONFIGURATION DES ÉLÈVES (TES LIENS SONT ICI) ---
STUDENTS_DB = {
    "Élève Test": "https://docs.google.com/forms/d/e/1FAIpQLSe-eaoZyDbe2ZTl_NfNKbkeDYKyEdRX_zchoK-Xjef7tGZGIA/formResponse",
    "Lucas": "https://docs.google.com/forms/d/e/1FAIpQLSfI3cJ1SpZF59IVYnDDaWrDoIbYXRiaaUAkVJgoBgYZ22KZw/formResponse",
    "Sarah": "https://docs.google.com/forms/d/e/1FAIpQLSf9av0xM-bwlyD5gSK1oT4eyblJrsnlWFRv_93bV444MBQbYA/formResponse",
}

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
    </style>
""", unsafe_allow_html=True)

# --- INITIALISATION MÉMOIRE ---
if 'processed_files' not in st.session_state: st.session_state.processed_files = set()
if 'timers' not in st.session_state: st.session_state.timers = {} 

st.title("🏋️ Caliperf : Gestion & Analyse")

# === CRÉATION DES ONGLETS ===
tab_accueil, tab_analyse, tab_eleves = st.tabs(["🏠 Calcul Rapide", "🎥 Analyse Coach", "👥 Mes Élèves"])

# =========================================================
# ONGLET 1 : CALCULATEUR
# =========================================================
with tab_accueil:
    st.header("🧮 Calculateur de Charge")
    col1, col2, col3 = st.columns(3)
    with col1: series = st.number_input("Séries", 0, 20, 4)
    with col2: reps = st.number_input("Répétitions", 0, 100, 10)
    with col3: poids = st.number_input("Poids (kg)", 0.0, 200.0, 0.0, step=1.0)
    
    total = series * reps * (poids if poids > 0 else 1) 
    if total > 0: st.info(f"📊 Volume Total : **{total}** kg")

# =========================================================
# ONGLET 2 : ANALYSE MULTI-VIDÉOS
# =========================================================
with tab_analyse:
    st.header("1️⃣ Dépôt Vidéos")
    uploaded_files = st.file_uploader("Charger les vidéos", type=['mp4', 'mov', 'avi'], accept_multiple_files=True)
    st.divider()

    st.header("2️⃣ Analyse Coach")
    password = st.text_input("🔒 Mot de passe :", type="password")

    if password == "admin":
        if not uploaded_files:
            st.info("⚠️ En attente de fichiers...")
        else:
            # Sélecteur de Vidéo
            files_map = {f.name: f for f in uploaded_files}
            options = [("✅ " if name in st.session_state.processed_files else "⏳ ") + name for name in files_map.keys()]
            selected_option = st.selectbox("Vidéo en cours :", options)
            real_name = selected_option.replace("✅ ", "").replace("⏳ ", "")
            current_file = files_map[real_name]

            # Init Chrono
            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {'start': 0, 'acc': 0.0, 'run': False}
            timer = st.session_state.timers[real_name]

            # Interface
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

                # --- FORMULAIRE INTELLIGENT ---
                with st.form(key=f"f_{real_name}"):
                    # SÉLECTION DE L'ÉLÈVE
                    selected_student = st.selectbox("👤 Sélectionner l'élève", list(STUDENTS_DB.keys()))
                    target_url = STUDENTS_DB[selected_student]
                    
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
# ONGLET 3 : GESTION DES ÉLÈVES
# =========================================================
with tab_eleves:
    st.header("👥 Répertoire")
    df_students = pd.DataFrame(list(STUDENTS_DB.items()), columns=["Nom", "Lien Form"])
    st.dataframe(df_students, use_container_width=True)
