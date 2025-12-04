"""
Minimal Utility-Shim für Standalone-Deployments ohne externe Abhängigkeiten.
Die Funktionen sind absichtlich defensiv implementiert, damit fehlende
Bibliotheken oder Dateien die App nicht crashen.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple, Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover - sollte in Streamlit laufen
    st = None  # type: ignore


def read_markdown_file(path: str) -> str:
    """Liest eine Markdown-Datei oder gibt einen leeren String zurück."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def set_page_config(**kwargs):
    """Wrapper für st.set_page_config, crash-sicher."""
    if st is None:
        return
    try:
        st.set_page_config(**kwargs)
    except Exception:
        pass


def handle_authentication() -> Tuple[Optional[str], bool, Optional[str]]:
    """
    Simple Auth-Attrappe: gibt immer authentifiziert zurück.
    Returns (name, authentication_status, username)
    """
    if st:
        st.session_state.setdefault("auth_name", "demo")
        st.session_state.setdefault("auth_username", "demo")
    return ("demo", True, "demo")


def logout():
    """Leert relevante Session-Keys, ohne hart zu crashen."""
    if not st:
        return
    try:
        for k in ("authentication_status", "authed", "username", "user", "email", "name", "display_name", "user_name"):
            st.session_state.pop(k, None)
        try:
            st.query_params.clear()
        except Exception:
            pass
    except Exception:
        pass


def apply_claneo_branding(title=None, subtitle=None, **kwargs):
    """
    Minimal-Branding: optional Logo/Title/Subtitle setzen, ohne Crash.
    """
    if not st:
        return
    try:
        try:
            st.logo("https://www.claneo.com/wp-content/uploads/Element-4.svg")
        except Exception:
            pass
        if title:
            st.title(str(title))
        if subtitle:
            st.caption(str(subtitle))
    except Exception:
        pass
