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
        # On s'assure d'avoir les bonnes colonnes
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
    /* Style pour le bouton Repos */
    div.stButton > button:first-child { border-radius: 8px; }
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
        
        # --- DONNÉES PHYSIO ---
        c_poids, c_taille, c_sexe = st.columns(3)
        with c_poids:
            poids = st.number_input("Poids (kg)", min_value=30.0, max_value=150.0, step=0.5, value=70.0)
        with c_taille:
            taille = st.number_input("Taille (cm)", min_value=100, max_value=230, step=1, value=175)
        with c_sexe:
            sexe = st.radio("Sexe", ["Homme", "Femme"], horizontal=True)
        
        objectif = st.text_area("Ton objectif principal")
        
        if st.form_submit_button("✅ Valider mon inscription", type="primary", use_container_width=True):
            if nom and prenom:
                full_name = f"{prenom} {nom}"
                st.session_state.students_data[full_name] = {
                    "link": LINK_UNIQUE, 
                    "freq": freq, 
                    "goal": objectif,
                    "exp": experience,
                    "weight": poids,
                    "height": taille,
                    "sex": sexe
                }
                save_data(st.session_state.students_data)
                st.success(f"Dossier créé pour {prenom} !")
                st.balloons()
            else:
                st.warning("Nom et Prénom obligatoires.")

# =========================================================
# ONGLET 2 : ANALYSE COACH (Modifié avec Bouton Repos)
# =========================================================
with tab_analyse:
    col_up, col_login = st.columns([3, 1])
    with col_up:
        # On garde le file uploader, mais on peut s'en servir après
        st.caption("Espace de travail")
    with col_login:
        password = st.text_input("🔒 Mot de passe Coach", type="password", key="pwd_analyse")

    st.divider()

    if password == ADMIN_PWD:
        
        # --- NOUVEAU : BOUTON REPOS (SANS VIDÉO) ---
        with st.expander("🛌 Enregistrement Rapide : REPOS / ABSENCE", expanded=True):
            cols_repos = st.columns([2, 1])
            with cols_repos[0]:
                student_keys = list(st.session_state.students_data.keys())
                if student_keys:
                    eleve_repos = st.selectbox("Sélectionner l'élève au repos :", student_keys, key="sel_repos")
                else:
                    eleve_repos = None
                    st.warning("Aucun élève inscrit.")
            
            with cols_repos[1]:
                st.write("") # Espace pour aligner
                st.write("")
                if eleve_repos:
                    if st.button("💤 VALIDER REPOS (Journée à 0)", type="primary", use_container_width=True):
                        # Envoi des données à 0
                        data_repos = {
                            ENTRIES['nom']: eleve_repos,
                            ENTRIES['exo']: "Repos",   # Le nom de l'exercice sera "Repos"
                            ENTRIES['tst']: "0",       # TST nul
                            ENTRIES['rpe']: "0",       # RPE nul
                            ENTRIES['charge']: "0"     # Charge nulle
                        }
                        try:
                            r = requests.post(LINK_UNIQUE, data=data_repos)
                            if r.status_code == 200:
                                st.success(f"✅ Jour de repos noté pour {eleve_repos} !")
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error("Erreur Google Forms")
                        except Exception as e:
                            st.error(f"Erreur technique : {e}")

        st.divider()

        # --- SECTION VIDÉO CLASSIQUE ---
        uploaded_files = st.file_uploader("Charger les vidéos pour analyse", type=['mp4', 'mov', 'avi'], accept_multiple_files=True)

        if not uploaded_files:
            st.info("📂 Charge une vidéo pour commencer une analyse technique.")
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

                # --- FORMULAIRE ENVOI DONNÉES VIDÉO ---
                with st.form(key=f"f_{real_name}"):
                    # student_keys déjà récupéré plus haut
                    if student_keys:
                        col_a, col_b = st.columns(2)
                        with col_a:
                            selected_student = st.selectbox("👤 Athlète", student_keys, key=f"sel_std_{real_name}")
                        with col_b:
                            type_effort = st.radio("Type", ["Statique ⏱️", "Dynamique 🔁"], horizontal=True)

                        exo = st.text_input("Exercice", value=real_name.split('.')[0])
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            rpe = st.slider("RPE", 1, 10, 7)
                        
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
                            
                            charge_calc = 0
                            valeur_principale = ""
                            
                            if type_effort == "Statique ⏱️":
                                if final_time > 0:
                                    charge_calc = final_time * rpe
                                    valeur_principale = f"{round(final_time, 2)} s"
                                else:
                                    st.warning("Chrono à 0 !")
                            else:
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
                                st.warning("Données invalides.")
                    else:
                        st.warning("Aucun élève inscrit.")

# =========================================================
# ONGLET 3 : MES ÉLÈVES (PRIVÉ)
# =========================================================
with tab_eleves:
    st.header("👥 Gestion et Progression des Athlètes")
    
    # URL CSV (À mettre dans secrets si possible, sinon ici)
    SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTABZd8nfqjdUzGUBjb57ntk8ACmBIPg7CM5VBMjGSdXJtiAN1ZJhwpGUb2EJvQZOrJ55s9eE2c8exn/pub?output=csv"
    
    pwd_eleves = st.text_input("🔒 Mot de passe accès privé", type="password", key="pwd_eleves")
    
    if pwd_eleves == ADMIN_PWD:
        # --- CHARGEMENT DONNÉES ---
        if SHEET_CSV_URL:
            df_history = fetch_training_data(SHEET_CSV_URL)
            if not df_history.empty and 'Charge' in df_history.columns:
                df_history['Charge'] = df_history['Charge'].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce')
                df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
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
                    
                    # --- 1. CARTE IDENTITÉ ---
                    emoji_sexe = "♂️" if info.get('sex') == "Homme" else "♀️"
                    poids_user = info.get('weight', 'N/A')
                    taille_user = info.get('height', 'N/A')

                    st.markdown(f"""
                    <div class="metric-card">
                        <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name} <span style="font-size:0.8em;">{emoji_sexe}</span></h3>
                        <p><b>📅 Fréquence :</b> {info.get('freq', 'Non définie')}</p>
                        <p><b>📏 Physio :</b> {taille_user} cm | {poids_user} kg</p>
                        <p><b>⏳ Expérience :</b> {info.get('exp', 'Non renseignée')}</p>
                        <div style="margin-top:10px; padding-top:10px; border-top:1px solid #444;">
                            <b>🎯 Objectif :</b><br>
                            <span style="font-style:italic; color:#ccc;">{info.get('goal', 'Aucun objectif')}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # --- 2. GRAPHIQUES ET ANALYSE ---
                    with st.expander(f"📈 Voir la progression de {name}"):
                        if not df_history.empty:
                            student_df = df_history[df_history['Nom'] == name].copy()
                            
                            if not student_df.empty:
                                # Nettoyage TST
                                student_df['TST_Value'] = student_df['TST'].astype(str).str.extract(r'(\d+[.,]?\d*)')[0].str.replace(',', '.', regex=False).astype(float).fillna(0)
                                
                                # Regroupement par jour
                                daily_stats = student_df.groupby('Date').agg({
                                    'Charge': 'sum',
                                    'TST_Value': 'sum',
                                    'RPE': 'mean',
                                    'Exercice': 'count'
                                }).reset_index().sort_values('Date')
                                
                                daily_stats['MA_Charge'] = daily_stats['Charge'].rolling(window=3).mean()
                                daily_stats['MA_TST'] = daily_stats['TST_Value'].rolling(window=3).mean()

                                # Création des Graphs
                                fig_charge = go.Figure()
                                fig_charge.add_trace(go.Scatter(
                                    x=daily_stats['Date'], y=daily_stats['Charge'],
                                    mode='lines+markers', line=dict(color='#00CC96', width=3),
                                    marker=dict(size=8, color=daily_stats['RPE'], colorscale='RdYlGn_r', showscale=False),
                                    name='Charge'
                                ))
                                fig_charge.add_trace(go.Scatter(x=daily_stats['Date'], y=daily_stats['MA_Charge'], mode='lines', line=dict(color='orange', dash='dot'), hoverinfo='skip'))
                                fig_charge.update_layout(title="⚡ Charge (0 = Repos)", template="plotly_dark", height=300, margin=dict(l=10, r=10, t=30, b=10), showlegend=False, clickmode='event+select')

                                fig_tst = go.Figure()
                                fig_tst.add_trace(go.Bar(
                                    x=daily_stats['Date'], y=daily_stats['TST_Value'],
                                    marker=dict(color='#3366CC'), name='Volume'
                                ))
                                fig_tst.add_trace(go.Scatter(x=daily_stats['Date'], y=daily_stats['MA_TST'], mode='lines', line=dict(color='white', dash='dot'), hoverinfo='skip'))
                                fig_tst.update_layout(title="⏱️ Volume", template="plotly_dark", height=300, margin=dict(l=10, r=10, t=30, b=10), showlegend=False, clickmode='event+select')

                                st.caption("👇 Clique sur un graphique pour voir le détail.")
                                col_g1, col_g2 = st.columns(2)
                                with col_g1:
                                    sel_charge = st.plotly_chart(fig_charge, use_container_width=True, on_select="rerun", selection_mode="points", key=f"c_ch_{name}")
                                with col_g2:
                                    sel_tst = st.plotly_chart(fig_tst, use_container_width=True, on_select="rerun", selection_mode="points", key=f"c_tst_{name}")

                                # Logique de sélection
                                selection = None
                                if sel_charge and len(sel_charge["selection"]["points"]) > 0: selection = sel_charge
                                elif sel_tst and len(sel_tst["selection"]["points"]) > 0: selection = sel_tst

                                if selection:
                                    point_data = selection["selection"]["points"][0]
                                    selected_date_str = point_data["x"]
                                    
                                    st.divider()
                                    st.markdown(f"#### 🔎 Détail du : **{selected_date_str}**")
                                    
                                    detail_df = student_df[student_df['Date'].astype(str) == selected_date_str].copy()
                                    
                                    if not detail_df.empty:
                                        detail_df['TST_Clean'] = detail_df['TST'].astype(str).str.extract(r'(\d+[.,]?\d*)')[0].str.replace(',', '.', regex=False).astype(float).fillna(0)
                                        
                                        k1, k2, k3, k4, k5 = st.columns(5)
                                        k1.metric("⚡ Charge", f"{detail_df['Charge'].sum():.0f}")
                                        k2.metric("⏱️ Volume", f"{detail_df['TST_Clean'].sum():.0f}")
                                        k3.metric("🥵 RPE Tot", f"{detail_df['RPE'].sum():.0f}")
                                        k4.metric("⚖️ RPE Moy", f"{detail_df['RPE'].mean():.1f}")
                                        k5.metric("🏋️ Exos", f"{len(detail_df)}")

                                        st.write("---")

                                        display_table = detail_df[['Timestamp', 'Exercice', 'TST', 'RPE', 'Charge']].copy()
                                        display_table['Heure'] = display_table['Timestamp'].dt.strftime('%H:%M')
                                        
                                        st.dataframe(
                                            display_table[['Heure', 'Exercice', 'TST', 'RPE', 'Charge']],
                                            use_container_width=True,
                                            hide_index=True,
                                            column_config={
                                                "RPE": st.column_config.ProgressColumn("RPE", min_value=0, max_value=10, format="%d"),
                                                "Charge": st.column_config.NumberColumn("Charge", format="%.1f")
                                            }
                                        )
                            else:
                                st.info("Pas encore de données.")
                        else:
                            st.error("Données inaccessibles.")

                    # --- 3. BOUTON SUPPRESSION ---
                    st.write("---")
                    col_del, col_txt = st.columns([1, 3])
                    with col_del:
                        if st.button(f"🗑️ Supprimer", key=f"del_{name}", type="secondary"):
                            with st.spinner("..."):
                                try:
                                    response = requests.get(DELETE_SCRIPT_URL, params={"name": name})
                                    if response.status_code == 200:
                                        del st.session_state.students_data[name]
                                        save_data(st.session_state.students_data)
                                        st.rerun()
                                    else:
                                        st.error("Erreur API")
                                except:
                                    st.error("Erreur Connexion")
    else:
        st.warning("Mot de passe requis.")
