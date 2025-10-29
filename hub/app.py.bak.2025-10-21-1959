#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import requests
import subprocess
from typing import Dict, Tuple, List

import streamlit as st

# -----------------------------
# Konfiguration: Tools & Routing
# -----------------------------

TOOLS: List[Dict] = [
    {
        "slug": "redirectmapper",
        "name": "RedirectMapper",
        "desc": "URL-Mapping & Bulk-Redirects prüfen",
        "port": 8501,
        "emoji": "🗺️",
    },
    {
        "slug": "linkchecker",
        "name": "LinkChecker",
        "desc": "Links prüfen & Berichte erzeugen",
        "port": 8504,
        "emoji": "🔗",
    },
    {
        "slug": "metadatacreator",
        "name": "MetadataCreator",
        "desc": "Title/Description/H1 mit LLM generieren",
        "port": 8505,
        "emoji": "✍️",
    },
    {
        "slug": "contentgapper",
        "name": "ContentGapper",
        "desc": "Gaps auf Basis echter Userdaten finden",
        "port": 8506,
        "emoji": "🎯",
    },
]

# Absoluter Pfad zum Control-Script (damit kein Permission/Path-Fehler)
CTL_BIN = "/usr/local/bin/streamlit-toolctl"


# -----------------------------
# Hilfsfunktionen
# -----------------------------

def _assert_ctl_exists():
    """Sicherstellen, dass das Control-Tool existiert & ausführbar ist."""
    if not os.path.exists(CTL_BIN):
        return False, f"{CTL_BIN} nicht gefunden"
    if not os.access(CTL_BIN, os.X_OK):
        return False, f"{CTL_BIN} ist nicht ausführbar (chmod +x nötig)"
    return True, ""


def run_ctl(args: List[str]) -> Tuple[bool, str]:
    """
    /usr/local/bin/streamlit-toolctl mit Args aufrufen.
    Gibt (ok, output) zurück. Output ist nie None/leer (wir füllen zur Not).
    """
    ok, msg = _assert_ctl_exists()
    if not ok:
        return False, f"[toolctl] {msg}"

    cmd = [CTL_BIN] + args
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=25)
        out = (out or "").strip()
        return True, out if out else "(kein Output vom Tool)"
    except subprocess.CalledProcessError as e:
        body = (e.output or "").strip()
        if not body:
            body = f"Exit {e.returncode}"
        return False, f"(Fehler) {body}"
    except PermissionError:
        return False, "Permission denied beim Ausführen von streamlit-toolctl (chmod +x / Pfad prüfen)"
    except FileNotFoundError:
        return False, f"{CTL_BIN} nicht gefunden (Pfad prüfen)"
    except Exception as e:
        return False, f"Unerwarteter Fehler: {e}"


def safe_toast(ok: bool, out: str, action: str, slug: str):
    """Nie leeren Toast anzeigen – Streamlit verlangt non-empty."""
    msg = (out or "").strip()
    if not msg:
        msg = f"{action} {slug} " + ("✔️ erfolgreich" if ok else "❌ fehlgeschlagen")
    st.toast(msg, icon="✅" if ok else "❌")


@st.cache_data(ttl=10, show_spinner=False)
def check_health(port: int, slug: str, timeout: float = 1.5) -> Tuple[bool, float]:
    """
    Prüft Streamlit-Health hinter BasePath:
    http://127.0.0.1:{port}/tools/{slug}/_stcore/health
    HEAD → Fallback GET, misst Latenz in ms.
    """
    url = f"http://127.0.0.1:{port}/tools/{slug}/_stcore/health"
    t0 = time.perf_counter()
    try:
        try:
            r = requests.head(url, timeout=timeout)
        except Exception:
            r = requests.get(url, timeout=timeout)
        ok = (r.status_code == 200)
    except Exception:
        ok = False
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return ok, latency_ms


def status_badge(is_up: bool, latency_ms: float) -> str:
    if is_up:
        color = "#22c55e"  # green
        label = "UP"
    else:
        color = "#ef4444"  # red
        label = "DOWN"
    latency = f"{latency_ms:.0f}ms" if latency_ms > 0 else "—"
    return f"""
    <span style="
        display:inline-flex;align-items:center;gap:.35rem;
        padding:.15rem .5rem;border-radius:999px;
        background:{color}1A;color:{color};font-weight:600;
        font-size:.85rem;">
        ● {label} · {latency}
    </span>
    """


def tool_card(tool: Dict, base_href: str):
    slug = tool["slug"]
    name = tool["name"]
    desc = tool.get("desc", "")
    emoji = tool.get("emoji", "🧩")
    port = tool["port"]
    href = f"{base_href}/{slug}/"  # relativ: /tools/<slug>/

    up, lat = check_health(port, slug)

    # Kachel
    with st.container(border=True):
        c1, c2 = st.columns([0.75, 0.25], vertical_alignment="center")
        with c1:
            st.markdown(f"### {emoji} [{name}]({href})", unsafe_allow_html=True)
            st.caption(desc)
        with c2:
            st.markdown(status_badge(up, lat), unsafe_allow_html=True)

        # Buttons
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("Start", key=f"start-{slug}"):
            ok_, out = run_ctl(["start", slug])
            safe_toast(ok_, out, "Start", slug)
            check_health.clear()  # Health neu prüfen
            st.rerun()
        if b2.button("Stop", key=f"stop-{slug}"):
            ok_, out = run_ctl(["stop", slug])
            safe_toast(ok_, out, "Stop", slug)
            check_health.clear()
            st.rerun()
        if b3.button("Restart", key=f"restart-{slug}"):
            ok_, out = run_ctl(["restart", slug])
            safe_toast(ok_, out, "Restart", slug)
            check_health.clear()
            st.rerun()
        if b4.button("Status", key=f"status-{slug}"):
            ok_, out = run_ctl(["status", slug])
            st.code(out or "(keine Ausgabe)")
            safe_toast(ok_, out, "Status", slug)


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(
    page_title="Tools Hub",
    page_icon="🧰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧰 Search Experience – Tools Hub")

# Hinweisleiste
ok_ctl, msg_ctl = _assert_ctl_exists()
if not ok_ctl:
    st.error(
        f"Control-Script Problem: {msg_ctl}\n\n"
        f"Erwartet: `{CTL_BIN}`\n"
        "→ Lösung: Datei anlegen und ausführbar machen:\n"
        "```\n"
        "tee /usr/local/bin/streamlit-toolctl >/dev/null <<'EOF'\n"
        "#!/usr/bin/env bash\n"
        "# hier euer start/stop/restart/status-Logic …\n"
        "EOF\n"
        "chmod +x /usr/local/bin/streamlit-toolctl\n"
        "```\n"
    )

# Sidebar – Verwaltungsaktionen
with st.sidebar:
    st.header("⚙️ Verwaltung")

    if st.button("🔄 Health neu prüfen"):
        check_health.clear()
        st.rerun()

    st.divider()
    st.subheader("Tool Control (CLI)")
    st.caption("Direkte Ausführung von streamlit-toolctl (Debug)")

    action = st.selectbox("Aktion", ["status", "start", "stop", "restart"], index=0)
    slug = st.selectbox("Tool", [t["slug"] for t in TOOLS], index=0)
    if st.button("Ausführen"):
        ok_, out = run_ctl([action, slug])
        st.code(out or "(keine Ausgabe)")
        safe_toast(ok_, out, action.capitalize(), slug)
        if action != "status":
            check_health.clear()
            st.rerun()

st.markdown("## 🚀 Schnellzugriff")
st.caption("Direktstart der wichtigsten Apps. Status wird alle ~10s automatisch aktualisiert (Cache).")

# Basis-HREF für Links (relativ zur Domain)
BASE_HREF = "/tools"

# Kacheln im Grid (2 Reihen à 2 Spalten bei 4 Tools)
for i in range(0, len(TOOLS), 2):
    cols = st.columns(2)
    for j, tool in enumerate(TOOLS[i:i+2]):
        with cols[j]:
            tool_card(tool, base_href=BASE_HREF)

st.markdown("---")
st.markdown("### ℹ️ Hinweise")
st.markdown(
    "- Health-Check pingt intern `127.0.0.1:<port>/tools/<slug>/_stcore/health`.\n"
    "- Buttons nutzen `/usr/local/bin/streamlit-toolctl` (Start/Stop/Restart/Status)."
)
