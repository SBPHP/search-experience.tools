from __future__ import annotations
import os, subprocess, time
from typing import Tuple, Dict, Any, List

import streamlit as st

# ---------- Hilfen ----------
def _get_tools() -> List[Dict[str, Any]]:
    # Bevorzuge zur Laufzeit geladene Tools
    try:
        ss_tools = st.session_state.get("tools")
        if ss_tools: return list(ss_tools)
    except Exception:
        pass
    # Fallback: globale TOOLS im app.py
    try:
        return list(globals().get("TOOLS") or [])
    except Exception:
        return []

def _check_health_safe(port: int, slug: str, timeout: float = 1.8) -> Tuple[bool, float]:
    # Nutze vorhandene check_health() aus app.py, sonst sehr einfacher HTTP-Fallback
    try:
        ch = globals().get("check_health")
        if callable(ch):
            return ch(port, slug, timeout=timeout)
    except Exception:
        pass
    # Minimaler Fallback: HEAD /_stcore/health
    try:
        import requests, time as _t
        start = _t.perf_counter()
        for url in (
            f"http://127.0.0.1:{port}/_stcore/health",
            f"http://127.0.0.1:{port}/healthz",
            f"http://127.0.0.1:{port}/",
        ):
            try:
                r = requests.head(url, timeout=timeout, allow_redirects=False)
                if 200 <= r.status_code < 400:
                    return True, (_t.perf_counter() - start)*1000.0
            except Exception:
                pass
            try:
                r = requests.get(url, timeout=timeout, allow_redirects=False)
                if 200 <= r.status_code < 400:
                    return True, (_t.perf_counter() - start)*1000.0
            except Exception:
                pass
        return False, (_t.perf_counter() - start)*1000.0
    except Exception:
        return False, 0.0

def _run_ctl(action: str, slug: str) -> Tuple[bool, str]:
    bin_ = "/usr/local/bin/streamlit-toolctl"
    if not os.path.exists(bin_):
        return False, f"{bin_} nicht gefunden"
    try:
        out = subprocess.check_output([bin_, action, slug], text=True, stderr=subprocess.STDOUT, timeout=8)
        return True, (out or "").strip()
    except subprocess.CalledProcessError as e:
        return False, (e.output or f"Exit {e.returncode}").strip()
    except Exception as e:
        return False, f"Fehler: {e}"

def status_badge(up: bool, latency_ms: float) -> str:
    color = "#22c55e" if up else "#ef4444"
    label = "UP" if up else "DOWN"
    lat_s = f"{latency_ms:.0f}ms" if latency_ms else "—"
    return (
        f"<span style='display:inline-flex;align-items:center;gap:.35rem;"
        f"padding:.1rem .45rem;border-radius:999px;background:{color}1A;"
        f"color:{color};font-weight:700;font-size:.78rem;'>● {label} · {lat_s}</span>"
    )

def _clear_health_cache():
    try:
        globals().get("check_health").cache_clear()  # @st.cache_data
    except Exception:
        try:
            globals().get("check_health").clear()
        except Exception:
            pass

# ---------- Sidebar (Logout oben, Health-Refresh, Tools-Liste, Add/Delete) ----------
def render_sidebar_bits():
    with st.sidebar:
        # Konto
        st.markdown("### 👤 Konto")
        if st.button("Logout", key="logout_btn_fixed", use_container_width=True):
            for k in ("name", "username", "authentication_status"):
                if k in st.session_state: del st.session_state[k]
            st.toast("Abgemeldet", icon="✅")
            st.rerun()
        user = st.session_state.get("name") or st.session_state.get("username") or "Admin"
        st.caption(f"**Eingeloggt als:** {user}")
        st.markdown("---")

        # Verwaltung
        st.markdown("### ⚙️ Verwaltung")
        if st.button("🔄 Health neu prüfen", use_container_width=True):
            _clear_health_cache()
            st.rerun()
        live = st.toggle("Live-Status (1s)", value=False, key="live_status_on",
                         help="Aktualisiert die Status-Badges jede Sekunde")
        st.markdown("---")

        # Tools Liste
        st.markdown("### 🧰 Tools")
        for t in _get_tools():
            slug = t.get("slug","")
            name = t.get("name", slug or "—")
            port = int(t.get("port",0) or 0)
            emoji = t.get("emoji","") or ""
            try:
                up, lat = _check_health_safe(port, slug)
            except Exception:
                up, lat = (False, 0.0)
            href = f"/tools/{slug}/" if slug and slug != "hub" else "/tools/"
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"padding:.35rem .5rem;border-radius:.5rem;'>"
                f"<div><span style='margin-right:.35rem'>{emoji}</span>"
                f"<a href='{href}' style='text-decoration:none;font-weight:600'>{name}</a></div>"
                f"{status_badge(up,lat)}"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown("---")

        # Tool hinzufügen
        st.markdown("### ➕ Tool hinzufügen")
        with st.form("add_tool_form", clear_on_submit=True):
            c1,c2 = st.columns(2)
            name = c1.text_input("Name", placeholder="Mein Tool")
            slug = c2.text_input("Slug", placeholder="meintool")
            c3,c4 = st.columns(2)
            port = c3.number_input("Port", min_value=1, max_value=65535, step=1, value=8507)
            emoji = c4.text_input("Emoji", placeholder="🧩")
            health_path = st.text_input("Health-Path (optional)", placeholder="/_stcore/health oder /tools/<slug>/_stcore/health")
            submitted = st.form_submit_button("Hinzufügen", type="primary", use_container_width=True)
        if submitted:
            ok, msg = add_tool({"name":name.strip(),"slug":slug.strip(),"port":int(port),"emoji":emoji.strip(),"health_path":health_path.strip()})
            (st.success if ok else st.error)(msg)
            if ok:
                _clear_health_cache()
                st.rerun()

        # Tool löschen
        st.markdown("### 🗑️ Tool löschen")
        tools = _get_tools()
        choices = [t.get("slug") for t in tools if t.get("slug")]
        sel = st.selectbox("Slug wählen", choices, index=0 if choices else None, key="del_sel")
        if st.button("Löschen", disabled=not bool(sel), use_container_width=True, key="del_btn"):
            ok, msg = delete_tool(sel)
            (st.success if ok else st.error)(msg)
            if ok:
                _clear_health_cache()
                st.rerun()

# ---------- Start/Stop/Restart/Status Kacheln ----------
def render_tiles():
    st.markdown("## 🚀 Schnellzugriff")
    for t in _get_tools():
        slug = t.get("slug","")
        name = t.get("name", slug or "—")
        port = int(t.get("port",0) or 0)
        emoji = t.get("emoji","") or ""
        up, lat = _check_health_safe(port, slug)
        with st.container(border=True):
            c1, c2 = st.columns([0.7, 0.3])
            with c1:
                st.markdown(f"### {emoji} {name}")
                st.caption(f"`:{port}` · Slug: `{slug or '—'}`")
            with c2:
                st.markdown(f"<div style='text-align:right'>{status_badge(up,lat)}</div>", unsafe_allow_html=True)

            c3, c4, c5, c6 = st.columns(4)
            if c3.button("Start", key=f"start_{slug}"):  _ctl_toast("start", slug)
            if c4.button("Stop", key=f"stop_{slug}"):    _ctl_toast("stop", slug)
            if c5.button("Restart", key=f"restart_{slug}"): _ctl_toast("restart", slug)
            if c6.button("Status", key=f"status_{slug}"):
                ok, out = _run_ctl("status", slug)
                st.toast(out if out else ("OK" if ok else "Fehler"), icon="✅" if ok else "❌")

def _ctl_toast(action: str, slug: str):
    ok, out = _run_ctl(action, slug)
    st.toast(out if out else ("OK" if ok else "Fehler"), icon="✅" if ok else "❌")
    _clear_health_cache()
    st.rerun()

# ---------- SEO Quick Audit ----------
def render_seo_quick():
    st.markdown("## 🔎 SEO Quick Audit")
    with st.form("seo_quick_audit"):
        url = st.text_input("URL prüfen", placeholder="https://www.deine-domain.tld/")
        submitted = st.form_submit_button("Analysieren", type="primary")
    if submitted and url:
        res = _seo_extract(url.strip())
        if not res.get("ok"):
            st.error(res.get("error","Unbekannter Fehler"))
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("HTTP Status", res["status"])
            c2.metric("Latency", f"{res['latency_ms']:.0f} ms")
            c3.metric("Title-Zeichen", len(res["title"] or ""))
            c4.metric("Desc.-Zeichen", len(res["description"] or ""))
            st.write(f"**Title:** {res['title'] or '—'}")
            st.write(f"**Description:** {res['description'] or '—'}")
            st.write(f"**H1:** {res['h1'] or '—'}")
            st.write(f"**Canonical:** {res['canonical'] or '—'}")
            st.write(f"**X-Robots-Tag:** {res['robots'] or '—'}")
            if res.get("issues"):
                st.warning("**Hinweise/Issues:**\n- " + "\n- ".join(res["issues"]))
            else:
                st.success("Keine offensichtlichen Issues erkannt.")

def _seo_extract(url: str) -> Dict[str, Any]:
    import re
    try:
        import requests
    except Exception:
        return {"ok": False, "error": "requests nicht installiert"}
    try:
        from bs4 import BeautifulSoup
    except Exception:
        BeautifulSoup = None

    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent":"Search-Experience/1.0"})
    except Exception as e:
        return {"ok": False, "error": f"Fetch-Fehler: {e}"}
    latency_ms = (time.perf_counter() - t0) * 1000.0

    html = r.text or ""
    title = desc = h1 = canon = ""
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        t = soup.find("title"); title = (t.text or "").strip() if t else ""
        md = soup.find("meta", attrs={"name":"description"})
        desc = (md.get("content") or "").strip() if md else ""
        h1tag = soup.find("h1"); h1 = (h1tag.text or "").strip() if h1tag else ""
        link_c = soup.find("link", attrs={"rel":["canonical","Canonical"]})
        canon = (link_c.get("href") or "").strip() if link_c else ""
    else:
        m = re.search(r"<title>(.*?)</title>", html, re.I|re.S); title = (m.group(1).strip() if m else "")
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html, re.I|re.S); desc = (m.group(1).strip() if m else "")
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I|re.S); h1 = (m.group(1).strip() if m else "")
        m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']', html, re.I|re.S); canon = (m.group(1).strip() if m else "")

    robots = (r.headers.get("X-Robots-Tag","") or "").strip()
    issues = []
    if len(title) < 10 or len(title) > 65: issues.append(f"Title-Länge suboptimal ({len(title)} Zeichen)")
    if not desc or len(desc) < 50 or len(desc) > 160: issues.append(f"Description-Länge prüfen ({len(desc)} Zeichen)")
    if not h1: issues.append("Kein H1 gefunden")
    if canon and not canon.startswith("http"): issues.append("Canonical ist relativ – absolut setzen")
    if "noindex" in robots.lower(): issues.append("X-Robots-Tag enthält noindex")
    if r.status_code >= 400: issues.append(f"HTTP {r.status_code}")

    return {
        "ok": True, "status": r.status_code, "latency_ms": latency_ms,
        "title": title, "description": desc, "h1": h1, "canonical": canon,
        "robots": robots, "issues": issues, "final_url": str(getattr(r, "url", "")),
    }

# ---------- Tools verwalten (Add/Delete) ----------
def _persist_tools(tools: List[Dict[str,Any]]):
    st.session_state["tools"] = tools

def add_tool(t: Dict[str,Any]):
    req = ("name","slug","port")
    for k in req:
        if not str(t.get(k,"")).strip():
            return False, f"Feld '{k}' fehlt."
    tools = _get_tools()
    if any(x.get("slug")==t["slug"] for x in tools):
        return False, "Slug existiert bereits."
    tools.append({
        "name": t["name"].strip(),
        "slug": t["slug"].strip(),
        "port": int(t["port"]),
        "emoji": t.get("emoji","").strip(),
        "health_path": t.get("health_path","").strip(),
    })
    _persist_tools(tools)
    return True, f"Tool '{t['slug']}' hinzugefügt."

def delete_tool(slug: str):
    tools = _get_tools()
    new = [x for x in tools if x.get("slug") != slug]
    if len(new)==len(tools):
        return False, f"Slug '{slug}' nicht gefunden."
    _persist_tools(new)
    return True, f"Tool '{slug}' gelöscht."
