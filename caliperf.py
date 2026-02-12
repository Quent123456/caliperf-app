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
    # On essaie de récupérer l'URL du CSV depuis les secrets, sinon vide
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
        
        objectif = st.text_area("Ton objectif principal")
        
        if st.form_submit_button("✅ Valider mon inscription", type="primary", use_container_width=True):
            if nom and prenom:
                full_name = f"{prenom} {nom}"
                st.session_state.students_data[full_name] = {
                    "link": LINK_UNIQUE, 
                    "freq": freq, 
                    "goal": objectif,
                    "exp": experience
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
                st.subheader("⏱️ Analyse TST")
                
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

                with st.form(key=f"f_{real_name}"):
                    student_keys = list(st.session_state.students_data.keys())
                    
                    if student_keys:
                        selected_student = st.selectbox("👤 Athlète", student_keys)
                        exo = st.text_input("Exercice", value=real_name.split('.')[0])
                        rpe = st.slider("RPE", 1, 10, 7)
                        
                        if st.form_submit_button("☁️ ENVOYER DONNÉES"):
                            final_time = timer['acc']
                            if timer['run']: 
                                final_time += time.time() - timer['start']
                            
                            if final_time > 0:
                                charge_calc = final_time * rpe
                                data = {
                                    ENTRIES['nom']: selected_student, 
                                    ENTRIES['exo']: exo,
                                    ENTRIES['tst']: str(round(final_time, 2)).replace('.', ','),
                                    ENTRIES['rpe']: str(rpe),
                                    ENTRIES['charge']: str(round(charge_calc, 2)).replace('.', ',')
                                }
                                
                                try:
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

# =========================================================
# ONGLET 3 : MES ÉLÈVES (PRIVÉ) - CORRIGÉ
# =========================================================
with tab_eleves:
    st.header("👥 Gestion et Progression des Athlètes")
    
    # URL de ton CSV (Récupérée des secrets ou en dur)
    SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTABZd8nfqjdUzGUBjb57ntk8ACmBIPg7CM5VBMjGSdXJtiAN1ZJhwpGUb2EJvQZOrJ55s9eE2c8exn/pub?output=csv"
    
    pwd_eleves = st.text_input("🔒 Mot de passe accès privé", type="password", key="pwd_eleves")
    
    if pwd_eleves == ADMIN_PWD:
        # Chargement des données
        if SHEET_CSV_URL:
            df_history = fetch_training_data(SHEET_CSV_URL)
            if not df_history.empty and 'Charge' in df_history.columns:
                df_history['Charge'] = df_history['Charge'].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce')
                df_history['Timestamp'] = pd.to_datetime(df_history['Timestamp'], errors='coerce')
        else:
            df_history = pd.DataFrame()
            st.warning("⚠️ URL du CSV non configurée.")

        if not st.session_state.students_data:
            st.info("Aucun élève enregistré pour le moment.")
        else:
            cols = st.columns(2)
            
            # --- BOUCLE SUR LES ÉLÈVES ---
            for index, (name, info) in enumerate(st.session_state.students_data.items()):
                with cols[index % 2]:
                    
                    # 1. CARTE D'IDENTITÉ
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3 style='margin-top:0; color:#ff4b4b;'>👤 {name}</h3>
                        <p><b>📅 Fréquence :</b> {info.get('freq', 'Non définie')}</p>
                        <p><b>⏳ Expérience :</b> {info.get('exp', 'Non renseignée')}</p>
                        <p><b>🎯 Objectif :</b> {info.get('goal', 'Aucun objectif')}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    # 2. GRAPHIQUE OPTIMISÉ (Dans l'expander)
                   # ... (Dans la boucle for, à l'intérieur de st.expander)

if not df_history.empty:
    student_df = df_history[df_history['Nom'] == name].copy()
    
    if not student_df.empty:
        # Création d'une colonne 'Date' (sans l'heure) pour le regroupement
        student_df['Date'] = student_df['Timestamp'].dt.date
        
        # --- 1. PRÉPARATION DES DONNÉES AGRÉGÉES (VUE MACRO) ---
        daily_stats = student_df.groupby('Date').agg({
            'Charge': 'sum',        # Charge Totale de la séance
            'RPE': 'mean',          # RPE Moyen de la séance
            'Exercice': 'count',    # Nombre d'exos
            'Timestamp': 'max'      # Juste pour garder un format datetime si besoin
        }).reset_index().sort_values('Date')

        # Calcul de la moyenne mobile sur la charge totale
        daily_stats['MA_3'] = daily_stats['Charge'].rolling(window=3).mean()

        # --- 2. GRAPHIQUE PRINCIPAL (GLOBAL) ---
        import plotly.graph_objects as go
        
        fig_main = go.Figure()

        # Courbe de Charge Totale
        fig_main.add_trace(go.Scatter(
            x=daily_stats['Date'],
            y=daily_stats['Charge'],
            mode='lines+markers',
            name='Charge Séance',
            line=dict(color='#00CC96', width=3),
            marker=dict(
                size=10,
                color=daily_stats['RPE'],
                colorscale='RdYlGn_r',
                showscale=True,
                colorbar=dict(title="Intensité Moyenne (RPE)")
            ),
            # Ce qui s'affiche au survol
            hovertemplate="<b>Date :</b> %{x}<br><b>Charge Totale :</b> %{y:.0f}<br><b>RPE Moyen :</b> %{marker.color:.1f}<extra></extra>"
        ))
        
        # Courbe de Tendance
        fig_main.add_trace(go.Scatter(
            x=daily_stats['Date'],
            y=daily_stats['MA_3'],
            mode='lines',
            name='Tendance',
            line=dict(color='orange', width=2, dash='dot'),
            hoverinfo='skip'
        ))

        fig_main.update_layout(
            title="📅 Charge par Séance (Clique sur un point pour le détail)",
            yaxis_title="Volume Total (UA)",
            xaxis_title="",
            template="plotly_dark",
            hovermode="closest",
            height=350,
            margin=dict(l=10, r=10, t=40, b=10),
            clickmode='event+select' # Active la sélection
        )

        # --- 3. AFFICHAGE ET INTERACTION ---
        st.caption("👇 Clique sur un point de la courbe ci-dessous pour voir le détail de la séance.")
        
        # C'est ici que la magie opère : on récupère l'événement de sélection
        selection = st.plotly_chart(
            fig_main, 
            use_container_width=True, 
            on_select="rerun",  # Recharge la page au clic
            selection_mode="points",
            key=f"chart_{name}"
        )

        # --- 4. ZOOM / DÉTAIL DE LA SÉANCE SÉLECTIONNÉE ---
        selected_date = None
        
        # On vérifie si un point a été cliqué
        if selection and len(selection["selection"]["points"]) > 0:
            # Plotly renvoie la date sous forme de string, on la récupère
            point_data = selection["selection"]["points"][0]
            selected_date_str = point_data["x"]
            
            st.divider()
            st.markdown(f"### 🔎 Zoom sur la séance du : **{selected_date_str}**")
            
            # On filtre les données brutes pour cette date précise
            # Attention : conversion de string à date pour matcher
            detail_df = student_df[student_df['Date'].astype(str) == selected_date_str].copy()
            
            if not detail_df.empty:
                # Métriques résumées
                m1, m2, m3 = st.columns(3)
                m1.metric("Volume Total", f"{detail_df['Charge'].sum():.0f}")
                m2.metric("Intensité Moyenne", f"{detail_df['RPE'].mean():.1f}/10")
                m3.metric("Exercices", f"{len(detail_df)}")

                # Tableau détaillé propre
                st.markdown("#### Détail des exercices")
                
                # On prépare un tableau propre pour l'affichage
                display_table = detail_df[['Timestamp', 'Exercice', 'TST', 'RPE', 'Charge']].copy()
                display_table['Heure'] = display_table['Timestamp'].dt.strftime('%H:%M')
                display_table = display_table[['Heure', 'Exercice', 'TST', 'RPE', 'Charge']]
                
                # Affichage avec style (RPE élevé en rouge)
                st.dataframe(
                    display_table.style.background_gradient(subset=['RPE'], cmap='RdYlGn_r', vmin=1, vmax=10),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Petit graph en barres pour comparer les exos de la séance
                fig_bar = px.bar(
                    detail_df, 
                    x='Exercice', 
                    y='Charge', 
                    color='RPE',
                    color_continuous_scale='RdYlGn_r',
                    title="Répartition de la charge par exercice"
                )
                fig_bar.update_layout(template="plotly_dark", height=300)
                st.plotly_chart(fig_bar, use_container_width=True)
                
            else:
                st.warning("Erreur : Impossible de retrouver les détails de cette date.")
        
        else:
            st.info("💡 Clique sur un point du graphique ci-dessus pour afficher le détail des exercices de ce jour-là.")

    else:
        st.info("Pas encore de données pour cet élève.")
else:
    st.error("Problème de connexion aux données.")

                    # 3. BOUTON DE SUPPRESSION (RESTAURÉ ICI)
                    st.write("---") # Séparateur visuel pour éviter les clics accidentels
                    col_del_btn, col_del_txt = st.columns([1, 2])
                    
                    with col_del_btn:
                        if st.button(f"🗑️ Supprimer", key=f"del_{name}", type="secondary"):
                            with st.spinner(f"Suppression de {name}..."):
                                try:
                                    # Appel au script Google Apps Script
                                    response = requests.get(DELETE_SCRIPT_URL, params={"name": name})
                                    
                                    if response.status_code == 200 and "Succès" in response.text:
                                        # Suppression locale
                                        del st.session_state.students_data[name]
                                        save_data(st.session_state.students_data)
                                        st.success(f"Au revoir {name} !")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"Erreur script : {response.text}")
                                except Exception as e:
                                    st.error(f"Erreur connexion : {e}")
                    
                    with col_del_txt:
                        st.caption(f"Action irréversible pour {name}")

    else:
        st.warning("Veuillez entrer le mot de passe administrateur.")

