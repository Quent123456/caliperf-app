import streamlit as st
import pandas as pd
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
    # On charge les secrets
    ADMIN_PWD = st.secrets["general"]["admin_password"]
    LINK_UNIQUE = st.secrets["general"]["google_form_url"]
    DELETE_SCRIPT_URL = st.secrets["general"]["delete_script_url"]
    ENTRIES = st.secrets["google_entries"]
    # On essaie de récupérer l'URL du CSV depuis les secrets
    CSV_URL_SECRET = st.secrets["general"].get("csv_url", "")
except Exception as e:
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

@st.cache_data(ttl=60)
def fetch_training_data(csv_url):
    try:
        if not csv_url: return pd.DataFrame()
        df = pd.read_csv(csv_url)
        # Renommage des colonnes (adapte si nécessaire selon ton Google Sheet)
        # Assure-toi que l'ordre correspond à ton Google Form
        # Timestamp, Nom, Exercice, TST(Perf), RPE, Charge
        df.columns = ["Timestamp", "Nom", "Exercice", "TST", "RPE", "Charge"]
        return df
    except Exception as e:
        return pd.DataFrame()

# --- 3. GESTION DU CHRONO (CALLBACKS) ---
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
        with col1: 
            nom = st.text_input("Nom")
        with col2: 
            prenom = st.text_input("Prénom")
        
        col3, col4 = st.columns(2)
        with col3: 
            freq = st.selectbox("Fréquence", ["2x / semaine", "3x / semaine", "4x / semaine", "5x / semaine", "Tous les jours"])
        with col4: 
            experience = st.text_input("Temps de pratique", placeholder="Ex: 2 ans, Débutant...")
        
        # Ajout du poids de corps pour futurs calculs
        poids = st.number_input("Poids du corps (kg)", min_value=30.0, max_value=150.0, step=0.5)
        
        objectif = st.text_area("Ton objectif principal")
        
        if st.form_submit_button("✅ Valider mon inscription", type="primary", use_container_width=True):
            if nom and prenom:
                full_name = f"{prenom} {nom}"
                st.session_state.students_data[full_name] = {
                    "link": LINK_UNIQUE, 
                    "freq": freq, 
                    "goal": objectif,
                    "exp": experience,
                    "weight": poids
                }
                save_data(st.session_state.students_data)
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

    if password == ADMIN_PWD:
        if not uploaded_files:
            st.info("⚠️ En attente de fichiers...")
        else:
            files_map = {f.name: f for f in uploaded_files}
            options = [("✅ " if name in st.session_state.processed_files else "⏳ ") + name for name in files_map.keys()]
            selected_option = st.selectbox("Vidéo en cours :", options)
            real_name = selected_option.replace("✅ ", "").replace("⏳ ", "")
            
            if real_name not in st.session_state.timers:
                st.session_state.timers[real_name] = {'start': 0, 'acc': 0.0, 'run': False}
            
            timer = st.session_state.timers[real_name]

            c_vid, c_tools = st.columns([1.5, 1])
            
            with c_vid:
                st.video(files_map[real_name])
            
            with c_tools:
                st.subheader("⏱️ Analyse")
                
                time_display = st.empty()
                current_time = timer['acc']
                if timer['run']:
                    current_time += time.time() - timer['start']

                time_display.markdown(f'<div class="big-time">{current_time:.2f} s</div>', unsafe_allow_html=True)

                b1, b2 = st.columns(2)
                with b1:
                    btn_label = "⏸️ PAUSE" if timer['run'] else "▶️ START"
                    st.button(btn_label, key=f"btn_{real_name}", on_click=toggle_timer, args=(real_name,), use_container_width=True)
                with b2:
                    st.button("🗑️ RAZ", key=f"rst_{real_name}", on_click=reset_timer, args=(real_name,), use_container_width=True)

                st.write("---")

                # --- FORMULAIRE D'ENVOI DES DONNÉES ---
                with st.form(key=f"f_{real_name}"):
                    student_keys = list(st.session_state.students_data.keys())
                    
                    if student_keys:
                        col_a, col_b = st.columns(2)
                        with col_a:
                            selected_student = st.selectbox("👤 Athlète", student_keys)
                        with col_b:
                            # CHOIX DU TYPE D'EFFORT
                            type_effort = st.radio("Type", ["Statique ⏱️", "Dynamique 🔁"], horizontal=True)

                        exo = st.text_input("Exercice", value=real_name.split('.')[0])
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            rpe = st.slider("RPE (Intensité)", 1, 10, 7)
                        
                        reps = 0
                        
                        with c2:
                            if type_effort == "Dynamique 🔁":
                                reps = st.number_input("Répétitions", min_value=1, value=10)
                            else:
                                st.info(f"Temps retenu : {current_time:.2f} s")

                        if st.form_submit_button("☁️ ENVOYER DONNÉES"):
                            final_time = timer['acc']
                            if timer['run']: 
                                final_time += time.time() - timer['start']
                            
                            # LOGIQUE DE CALCUL
                            charge_calc = 0
                            valeur_principale = ""
                            
                            if type_effort == "Statique ⏱️":
                                if final_time > 0:
                                    charge_calc = final_time * rpe
                                    valeur_principale = f"{round(final_time, 2)} s"
                                else:
                                    st.warning("Chrono à 0 !")
                            else:
                                # Pour le dynamique, on utilise Reps * RPE (simplifié)
                                charge_calc = reps * rpe
                                valeur_principale = f"{reps} reps"

                            if charge_calc > 0:
                                data = {
                                    ENTRIES['nom']: selected_student, 
                                    ENTRIES['exo']: exo,
                                    ENTRIES['tst']: str(valeur_principale).replace('.', ','),
                                    ENTRIES['rpe']: str(rpe),
                                    ENTRIES['charge']: str(round(charge_calc, 2)).replace('.', ',')
                                }
                                
                                try:
                                    r = requests.post(LINK_UNIQUE, data=data)
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
                                st.warning("Données invalides (Charge = 0)")

                    else:
                        st.warning("Aucun élève inscrit.")

# =========================================================
# ONGLET 3 : MES ÉLÈVES (PRIVÉ)
# =========================================================
with tab_eleves:
    st.header("👥 Gestion et Progression des Athlètes")
    
    # URL CSV : À mettre dans secrets.toml de préférence, sinon ici
    SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTABZd8nfqjdUzGUBjb57ntk8ACmBIPg7CM5VBMjGSdXJtiAN1ZJhwpGUb2EJvQZOrJ55s9eE2c8exn/pub?output=csv"
    
    pwd_eleves = st.text_input("🔒 Mot de passe accès privé", type="password", key="pwd_eleves")
    
    if pwd_eleves == ADMIN_PWD:
        # Chargement des données globales
        if SHEET_CSV_URL:
            df_history = fetch_training_data(SHEET_CSV_URL)
            if not df_history.empty and 'Charge' in df_history.columns:
                df_history['Charge'] = df_history['Charge'].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce')
                df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
                # Création colonne Date sans heure pour le regroupement
                df_history['Date'] = df_history['Timestamp'].dt.date
        else:
            df_history = pd.DataFrame()
            st.warning("⚠️ URL du CSV non configurée.")

        if not st.session_state.students_data:
            st.info("Aucun élève enregistré pour le moment.")
        else:
            cols = st.columns(2)
            
            for index, (name, info) in enumerate(st.session_state.students_data.items()):
                with cols[index % 2]:
                    
                    # --- CARTE ÉLÈVE ---
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name}</h3>
                        <p><b>📅 Fréquence :</b> {info.get('freq', 'Non définie')}</p>
                        <p><b>⚖️ Poids :</b> {info.get('weight', 'N/A')} kg</p>
                        <p><b>🎯 Objectif :</b> {info.get('goal', 'Aucun objectif')}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    # --- ZONE GRAPHIQUE INTELLIGENTE (DRILL-DOWN) ---
                    with st.expander(f"📈 Voir la progression de {name}"):
                        if not df_history.empty:
                            student_df = df_history[df_history['Nom'] == name].copy()
                            
                            if not student_df.empty:
                                # 1. PRÉPARATION VUE MACRO (Par Jour)
                                daily_stats = student_df.groupby('Date').agg({
                                    'Charge': 'sum',
                                    'RPE': 'mean',
                                    'Exercice': 'count'
                                }).reset_index().sort_values('Date')
                                
                                # Moyenne mobile pour la tendance
                                daily_stats['MA_3'] = daily_stats['Charge'].rolling(window=3).mean()

                                # 2. GRAPHIQUE GLOBAL
                                fig_main = go.Figure()

                                fig_main.add_trace(go.Scatter(
                                    x=daily_stats['Date'], y=daily_stats['Charge'],
                                    mode='lines+markers', name='Charge Séance',
                                    line=dict(color='#00CC96', width=3),
                                    marker=dict(size=10, color=daily_stats['RPE'], colorscale='RdYlGn_r', showscale=True, colorbar=dict(title="RPE")),
                                    hovertemplate="<b>Date :</b> %{x}<br><b>Charge Totale :</b> %{y:.0f}<br><b>RPE :</b> %{marker.color:.1f}<extra></extra>"
                                ))
                                
                                fig_main.add_trace(go.Scatter(
                                    x=daily_stats['Date'], y=daily_stats['MA_3'],
                                    mode='lines', name='Tendance',
                                    line=dict(color='orange', width=2, dash='dot'), hoverinfo='skip'
                                ))

                                fig_main.update_layout(
                                    title="📅 Charge Globale (Clique sur un point pour zoomer)",
                                    yaxis_title="Volume Total", template="plotly_dark",
                                    height=350, margin=dict(l=10, r=10, t=40, b=10),
                                    clickmode='event+select'
                                )

                                st.caption("👇 Clique sur un point ci-dessous pour voir le détail de la séance.")
                                
                                # INTERACTION
                                selection = st.plotly_chart(fig_main, use_container_width=True, on_select="rerun", selection_mode="points", key=f"chart_{name}")

                                # 3. ZOOM SUR LA SÉANCE SÉLECTIONNÉE
                                if selection and len(selection["selection"]["points"]) > 0:
                                    point_data = selection["selection"]["points"][0]
                                    selected_date_str = point_data["x"] # Format string YYYY-MM-DD
                                    
                                    st.divider()
                                    st.markdown(f"#### 🔎 Détail du : **{selected_date_str}**")
                                    
                                    # Filtrage des données brutes
                                    detail_df = student_df[student_df['Date'].astype(str) == selected_date_str].copy()
                                    
                                    if not detail_df.empty:
                                        # Petit tableau propre
                                        display_table = detail_df[['Timestamp', 'Exercice', 'TST', 'RPE', 'Charge']].copy()
                                        display_table['Heure'] = display_table['Timestamp'].dt.strftime('%H:%M')
                                        st.dataframe(
                                            display_table[['Heure', 'Exercice', 'TST', 'RPE', 'Charge']].style.background_gradient(subset=['RPE'], cmap='RdYlGn_r', vmin=1, vmax=10),
                                            use_container_width=True, hide_index=True
                                        )
                            else:
                                st.info("Pas encore de données pour cet élève.")
                        else:
                            st.error("Problème de connexion aux données.")

                    # --- BOUTON SUPPRESSION ---
                    st.write("---")
                    col_del, col_txt = st.columns([1, 3])
                    with col_del:
                        if st.button(f"🗑️ Supprimer", key=f"del_{name}", type="secondary"):
                            with st.spinner("Suppression..."):
                                try:
                                    response = requests.get(DELETE_SCRIPT_URL, params={"name": name})
                                    if response.status_code == 200:
                                        del st.session_state.students_data[name]
                                        save_data(st.session_state.students_data)
                                        st.success("Supprimé !")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Erreur Script")
                                except Exception:
                                    st.error("Erreur Connexion")
                    
    else:
        st.warning("Veuillez entrer le mot de passe administrateur.")
