"""
core/auth.py - Authentification sécurisée, hachage PBKDF2-HMAC, jetons de session (F5)
et traitement d'avatar pour CaliPerf.

Fonctionnalités :
- Hachage PBKDF2-HMAC-SHA256 avec sel aléatoire 16 octets unique par utilisateur.
- Rétro-compatibilité silencieuse pour migration des anciens comptes SHA-256 hex.
- Jeton de session signé HMAC-SHA256 pour persistance transparente au rafraîchissement (F5).
- Gestion stricte des rôles SQL ('coach' | 'athlete') et des codes d'invitation coach.
- Génération d'avatar Base64 léger (< 10 Ko) et rendu HTML garanti sans indentation >= 4.
"""

import base64
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import time
from typing import Any, Dict, Optional, Tuple

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


PBKDF2_SCHEME = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 200_000
SESSION_TTL_SECONDS = 14 * 24 * 3600

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCAL_SECRET_FILE = os.path.join(_PROJECT_ROOT, "data", ".caliperf_secret")
_CACHED_SECRET: Optional[bytes] = None


# ==============================================================================
# HACHAGE PBKDF2-HMAC (ZERO MOT DE PASSE EN CLAIR)
# ==============================================================================

def hash_password(password: str, salt_hex: Optional[str] = None) -> str:
    """Hache un mot de passe avec PBKDF2-HMAC-SHA256 et sel aléatoire unique."""
    clean_pwd = (password or "").strip().encode("utf-8")
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", clean_pwd, salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_SCHEME}${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def is_modern_password_hash(stored_hash: str) -> bool:
    """Indique si le hash suit le format PBKDF2-HMAC moderne."""
    return isinstance(stored_hash, str) and stored_hash.startswith(f"{PBKDF2_SCHEME}$")


def verify_password(password: str, stored_hash: str) -> bool:
    """Vérifie un mot de passe contre un hash PBKDF2-HMAC (ou SHA-256 legacy en migration)."""
    if not stored_hash or not password:
        return False
    clean_pwd = password.strip()

    if is_modern_password_hash(stored_hash):
        parts = stored_hash.split("$")
        if len(parts) != 4:
            return False
        _, iter_str, salt_hex, expected_hex = parts
        try:
            iterations = int(iter_str)
            salt = bytes.fromhex(salt_hex)
        except Exception:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", clean_pwd.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk.hex(), expected_hex)

    # Repli de migration uniquement sur ancien SHA-256 hex (64 caractères)
    if len(stored_hash) == 64 and all(c in "0123456789abcdef" for c in stored_hash.lower()):
        legacy_sha256 = hashlib.sha256(clean_pwd.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_sha256, stored_hash.lower())

    return False


# ==============================================================================
# JETONS DE SESSION SIGNÉS HMAC POUR PERSISTANCE AU REFRESH (F5)
# ==============================================================================

def get_auth_secret() -> bytes:
    """Récupère ou génère une clé secrète HMAC stable (st.secrets -> env -> fichier local)."""
    global _CACHED_SECRET
    if _CACHED_SECRET is not None:
        return _CACHED_SECRET

    if HAS_STREAMLIT:
        try:
            if hasattr(st, "secrets") and "AUTH_SECRET" in st.secrets:
                val = str(st.secrets["AUTH_SECRET"]).strip()
                if val:
                    _CACHED_SECRET = val.encode("utf-8")
                    return _CACHED_SECRET
        except Exception:
            pass

    env_secret = os.getenv("AUTH_SECRET", "").strip()
    if env_secret:
        _CACHED_SECRET = env_secret.encode("utf-8")
        return _CACHED_SECRET

    try:
        os.makedirs(os.path.dirname(_LOCAL_SECRET_FILE), exist_ok=True)
        if os.path.exists(_LOCAL_SECRET_FILE):
            with open(_LOCAL_SECRET_FILE, "r", encoding="utf-8") as f:
                existing = f.read().strip()
            if len(existing) >= 32:
                _CACHED_SECRET = existing.encode("utf-8")
                return _CACHED_SECRET

        generated = secrets.token_hex(32)
        with open(_LOCAL_SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(generated)
        _CACHED_SECRET = generated.encode("utf-8")
        return _CACHED_SECRET
    except Exception:
        _CACHED_SECRET = secrets.token_bytes(32)
        return _CACHED_SECRET


def create_session_token(user_id: int, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """Crée un jeton signé URL-safe contenant l'ID utilisateur et sa date d'expiration."""
    payload = {"uid": int(user_id), "exp": int(time.time()) + int(ttl_seconds)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(get_auth_secret(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_session_token(token: str) -> Optional[int]:
    """Valide un jeton signé HMAC et retourne user_id s'il est valide et non expiré."""
    if not token or not isinstance(token, str) or "." not in token:
        return None
    parts = token.strip().split(".", 1)
    if len(parts) != 2:
        return None
    b64, sig = parts
    expected_sig = hmac.new(get_auth_secret(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        pad = "=" * ((4 - len(b64) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(b64 + pad).decode("utf-8"))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        uid = int(data["uid"])
        return uid if uid > 0 else None
    except Exception:
        return None


# ==============================================================================
# RÔLES, CODES D'INVITATION & AVATARS
# ==============================================================================

def normalize_role(role: str) -> str:
    """Normalise strictement les rôles applicatifs sur 'coach' ou 'athlete'."""
    r = str(role or "").strip().lower()
    if r in ("coach", "admin", "administrateur", "trainer"):
        return "coach"
    return "athlete"


def is_master_coach(user: Optional[Dict[str, Any]]) -> bool:
    """Identifie le coach administrateur principal propriétaire du catalogue officiel partagé."""
    if not user:
        return False
    return str(user.get("username", "")).strip().lower() == "admin" and normalize_role(user.get("role", "")) == "coach"


def generate_invite_code(prefix: str = "CALI") -> str:
    """Génère un code d'invitation unique court pour rattacher un élève à un coach."""
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def sanitize_username(username: str) -> str:
    """Nettoie un identifiant utilisateur en minuscules alphanumériques."""
    return re.sub(r"[^a-zA-Z0-9_.\-]+", "", (username or "").strip().lower())


def get_role_badge_info(role: str, username: str = "") -> Tuple[str, str, str]:
    """Retourne (label, badge_class, icon) pour le rôle utilisateur."""
    norm = normalize_role(role)
    if norm == "coach":
        return "Coach", "badge-cyan", "🏋️"
    return "Élève", "badge-lime", "🤸"


def process_avatar_image(uploaded_file, max_size: Tuple[int, int] = (128, 128)) -> str:
    """
    Redimensionne et compresse une photo de profil uploadée en JPEG Base64 (< 10 Ko).
    Retourne une URI data:image/jpeg;base64,... prête pour le header.
    """
    if uploaded_file is None:
        return ""

    try:
        bytes_data = b""
        if hasattr(uploaded_file, "getvalue"):
            bytes_data = uploaded_file.getvalue()
        elif isinstance(uploaded_file, bytes):
            bytes_data = uploaded_file
        elif hasattr(uploaded_file, "read"):
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
            bytes_data = uploaded_file.read()
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
        else:
            return ""

        if not bytes_data:
            return ""

        if HAS_PIL:
            img = Image.open(io.BytesIO(bytes_data))
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) / 2
            top = (h - min_dim) / 2
            right = (w + min_dim) / 2
            bottom = (h + min_dim) / 2
            img_cropped = img.crop((left, top, right, bottom))
            img_resized = img_cropped.resize(max_size, Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img_resized.save(buffer, format="JPEG", quality=82, optimize=True)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"

        encoded = base64.b64encode(bytes_data).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return ""


def render_avatar_html(avatar_data: str, name: str, size: int = 34) -> str:
    """Génère le HTML compact sur une seule ligne (0 indentation) pour l'avatar circulaire."""
    clean_name = html.escape(str(name or "").strip() or "Utilisateur", quote=True)
    initial = html.escape((str(name or "").strip() or "U")[0].upper())

    if avatar_data and str(avatar_data).startswith("data:image"):
        safe_src = html.escape(str(avatar_data).strip(), quote=True)
        img_style = (
            f"width:{size}px;height:{size}px;border-radius:50%;object-fit:cover;"
            "border:2px solid rgba(0,229,255,0.45);box-shadow:0 2px 8px rgba(0,0,0,0.35);"
            "display:inline-block;vertical-align:middle;flex-shrink:0;"
        )
        return f'<img src="{safe_src}" alt="{clean_name}" style="{img_style}" />'

    font_size = max(11, int(size * 0.42))
    div_style = (
        f"width:{size}px;height:{size}px;border-radius:50%;"
        "background:linear-gradient(135deg,#00E5FF,#0EA5E9);color:#030712;"
        f"font-weight:800;font-size:{font_size}px;display:inline-flex;"
        "align-items:center;justify-content:center;border:2px solid rgba(255,255,255,0.22);"
        "box-shadow:0 2px 8px rgba(0,229,255,0.28);vertical-align:middle;flex-shrink:0;"
    )
    return f'<div style="{div_style}">{initial}</div>'
