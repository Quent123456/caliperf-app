"""
core/video_io.py - Gestion stricte de la RAM et des fichiers vidéo temporaires (Chantier 5).
Écrit les vidéos uploadées en flux dans tempfile.NamedTemporaryFile, garantit la suppression
immédiate via os.remove() et appelle gc.collect() après chaque vidéo traitée.
"""

from contextlib import contextmanager
import gc
import os
import tempfile
from typing import Iterator


@contextmanager
def temporary_video_file(uploaded_file) -> Iterator[str]:
    """
    Context manager éphémère pour traiter une vidéo uploadée en flux sur disque
    sans accumuler d'images brutes en RAM :
    1. Crée un fichier temporaire unique (tempfile.NamedTemporaryFile)
    2. Écrit le flux binaire par blocs de 1 Mo
    3. Supprime explicitement le fichier (os.remove) et appelle gc.collect() en sortie
    """
    orig_name = getattr(uploaded_file, "name", "video.mp4") or "video.mp4"
    _, ext = os.path.splitext(orig_name)
    safe_ext = ext if ext.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm") else ".mp4"

    tmp_file = tempfile.NamedTemporaryFile(delete=False, prefix="caliperf_", suffix=safe_ext)
    tmp_path = tmp_file.name
    try:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)

        if hasattr(uploaded_file, "read"):
            while True:
                chunk = uploaded_file.read(1024 * 1024)
                if not chunk:
                    break
                tmp_file.write(chunk)
        elif isinstance(uploaded_file, (bytes, bytearray)):
            tmp_file.write(uploaded_file)

        tmp_file.flush()
        tmp_file.close()

        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)

        yield tmp_path
    finally:
        try:
            if not tmp_file.closed:
                tmp_file.close()
        except Exception:
            pass
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        gc.collect()


def cleanup_temp_file_and_gc(file_path: str) -> None:
    """Supprime un fichier temporaire résiduel et déclenche une collecte mémoire."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass
    gc.collect()
