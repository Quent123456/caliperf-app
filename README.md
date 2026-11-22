# ⚡ Caliperf V2 - Studio de Vidéo-Coaching & Analyse TST

Caliperf V2 est une application haute vélocité dédiée aux coachs sportifs (Calisthenics, Street Lifting, Force Athlétique, Musculation) pour chronométrer le Temps Sous Tension (TST) et évaluer le RPE des athlètes avec un maximum de fluidité sur mobile et ordinateur.

---

## 🚀 Fonctionnalités Clés

### 1. 📱 Expérience Mobile Fluid Swipe (Glissement en continu)
- **Transition tactile continue** : Glissez votre doigt sur l'écran pour voyager entre les sections (`Studio`, `Stats`, `Athlètes`, `Réglages`). La page suivante glisse progressivement sous votre doigt en temps réel avec une physique naturelle.
- **Interface adaptée aux encoches (Safe Area)** : Le haut de l'écran est parfaitement dimensionné pour ne jamais être masqué par la barre d'état ou l'encoche de votre smartphone.
- **Vidéo optimisée (40% de l'écran max)** : Permet de regarder l'athlète tout en manipulant le chronomètre et les repères sans défilement vertical inutile.

### 2. 🎯 Logique Pure : Temps Sous Tension (TST) & RPE
- **Aucun multiplicateur complexe** : L'application se concentre sur les fondamentaux réels du coaching :
  - **TST** : Temps Sous Tension précis au centième de seconde.
  - **RPE** : Échelle de perception de l'effort de 1 à 10 avec indicateur visuel de réserve (RIR).
  - **Répétitions & Tempo** : Calcul automatique du tempo moyen par répétition ($TST / Reps$).

### 3. 🤖 Module Auto-Track IA (Vision & Mouvement)
- **Détection automatique par IA** : Grâce à l'intégration de Gemini Vision, l'application peut analyser la vidéo pour détecter automatiquement le début de l'effort, la fin du mouvement, le TST et le nombre de répétitions valides.
- Prépare le terrain vers l'automatisation complète de vos analyses.

### 4. 🌐 Enregistrement & Synchronisation
- **Local d'abord** : Fonctionne 100% hors-ligne dans la salle de sport grâce à `caliperf_db.json`.
- **Google Sheets Direct** : Synchronisation en direct via Webhook sans passer par un formulaire intermédiaire.
- **Google Forms Legacy** : Prise en charge de votre ancien formulaire Google si vous souhaitez conserver votre flux existant.
- **Export CSV** : Téléchargement de l'historique complet en 1 clic.

---

## 🛠️ Démarrage Rapide

```powershell
streamlit run caliperf.py
```
Accès depuis votre navigateur : `http://localhost:8501`.
