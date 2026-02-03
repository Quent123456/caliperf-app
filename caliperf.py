import streamlit as st

st.set_page_config(page_title="Caliperf - Suivi d'Entraînement", layout="centered")

st.title("🏋️ Caliperf : Gestion de Séance")

# Section 1 : Prise de notes
st.subheader("Notes de la séance")
notes = st.text_area("Note tes observations ici (sensations, fatigue...) :", placeholder="Ex: Séance pectoraux, bonne forme aujourd'hui.")

# Section 2 : Calcul du Volume Total de Travail (VTT)
st.subheader("Calculateur de Volume")

col1, col2, col3 = st.columns(3)

with col1:
    series = st.number_input("Séries", min_value=0, step=1)
with col2:
    reps = st.number_input("Répétitions", min_value=0, step=1)
with col3:
    poids = st.number_input("Poids (kg)", min_value=0.0, step=0.5)

# Calcul automatique
vtt = series * reps * poids

if vtt > 0:
    st.success(f"Le volume total pour cet exercice est de : **{vtt} kg**")