# -*- coding: utf-8 -*-
# Streamlit App: Search Experience (Advanced Tool Manager)
# Features:
# - Add Tool, Delete Selected, Undo Last Delete, Refresh, Set Selected Active
# - Search (name/desc/endpoint), Only active filter
# - Tags (comma-separated), editable in table
# - Per-tool actions: Run Job (simulated), Ping Endpoint, Duplicate, Delete
# - Per-tool Detail & History (timestamp, action, status code, duration, note), export CSV, clear history
# - Export: all tools or only selected
# - Activity Log + Quick Stats
#
# Notes:
# - History is stored in st.session_state['run_history'][tool_key] as list of dicts
# - 'Run Job' is simulated; replace with real calls if desired

import json
import time
from datetime import datetime
from io import StringIO
from typing import List, Dict
import streamlit as st
import pandas as pd

try:
    import requests  # optional for ping
except Exception:
    requests = None

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(
    page_title="Search Experience",
    page_icon="🧰",
    layout="wide"
)
st.title("🔎 Search Experience")

# ===============================
# State & Defaults
# ===============================
DEFAULT_TOOLS = [
    {
        "name": "Example Tool",
        "key": "example_tool",
        "description": "Demo entry to show how it works.",
        "endpoint": "https://httpbin.org/get",
        "active": True,
        "tags": "demo,example"
    }
]

def ensure_state():
    if "tools" not in st.session_state:
        st.session_state.tools = DEFAULT_TOOLS.copy()
    if "selection" not in st.session_state:
        st.session_state.selection = []  # list of tool keys
    if "show_add_modal" not in st.session_state:
        st.session_state.show_add_modal = False
    if "logs" not in st.session_state:
        st.session_state.logs = []  # list of dicts {ts, level, msg}
    if "last_deleted" not in st.session_state:
        st.session_state.last_deleted = []  # stash for undo
    if "run_history" not in st.session_state:
        st.session_state.run_history = {}  # key -> list of events

ensure_state()

# -------------------------------
# Utilities
# -------------------------------
def log(level: str, msg: str):
    st.session_state.logs.append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level.upper(),
        "msg": msg
    })

def get_tools_df() -> pd.DataFrame:
    return pd.DataFrame(st.session_state.tools)

def set_tools_from_df(df: pd.DataFrame):
    expected_cols = ["name", "key", "description", "endpoint", "active", "tags"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = "" if col not in ("active",) else False
    df = df.dropna(subset=["key"])
    df["key"] = df["key"].astype(str).str.strip()
    df = df[df["key"] != ""]
    df = df.drop_duplicates(subset=["key"], keep="first")
    df["active"] = df["active"].astype(bool)
    df["tags"] = df["tags"].fillna("").astype(str)
    st.session_state.tools = df[expected_cols].to_dict(orient="records")

def delete_tools_by_keys(keys: List[str]):
    if not keys:
        return
    stash = [t for t in st.session_state.tools if t.get("key") in keys]
    if stash:
        st.session_state.last_deleted = stash
    st.session_state.tools = [t for t in st.session_state.tools if t.get("key") not in keys]
    st.session_state.selection = []
    log("INFO", f"Deleted {len(keys)} tool(s): {', '.join(keys)}")

def tool_keys() -> List[str]:
    return [t.get("key","") for t in st.session_state.tools]

def find_tool(key: str) -> Dict:
    for t in st.session_state.tools:
        if t.get("key") == key:
            return t
    return {}

def duplicate_tool(key: str):
    t = find_tool(key)
    if not t:
        return
    base = t.copy()
    i = 2
    new_key = f"{base['key']}_{i}"
    existing = set(tool_keys())
    while new_key in existing:
        i += 1
        new_key = f"{base['key']}_{i}"
    base["key"] = new_key
    base["name"] = f"{base['name']} (Copy)"
    st.session_state.tools.append(base)
    log("INFO", f"Duplicated tool '{key}' → '{new_key}'")

def toggle_active(keys: List[str], value: bool):
    changed = 0
    for t in st.session_state.tools:
        if t.get("key") in keys:
            t["active"] = value
            changed += 1
    log("INFO", f"Set active={value} for {changed} tool(s)")

def add_history_event(key: str, action: str, status: str, code: str, duration_ms: float, note: str = ""):
    if key not in st.session_state.run_history:
        st.session_state.run_history[key] = []
    st.session_state.run_history[key].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "status": status,
        "code": code,
        "duration_ms": int(duration_ms),
        "note": note
    })

def ping_endpoint(endpoint: str, timeout: float = 5.0) -> (str, str):
    if not endpoint:
        return "NO_ENDPOINT", "No endpoint set."
    if requests is None:
        return "NO_REQUESTS", "requests not available (skip ping)."
    try:
        r = requests.get(endpoint, timeout=timeout)
        return str(r.status_code), r.reason or ""
    except Exception as e:
        return "ERROR", str(e)

def run_job_sim(key: str) -> (str, str):
    # Simulate doing something
    time.sleep(0.25)
    return "OK", "Simulated job completed"

def get_history_df(key: str) -> pd.DataFrame:
    rows = st.session_state.run_history.get(key, [])
    if not rows:
        return pd.DataFrame(columns=["timestamp","action","status","code","duration_ms","note"])
    return pd.DataFrame(rows)

# -------------------------------
# Controls Container
# -------------------------------
with st.container(border=True):
    st.markdown("### 🧰 Tool Manager")
    st.caption("Add / Delete / Refresh + Search, Tags, Actions, Undo, Detail & History.")

    # Top action bar
    c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
    with c1:
        if st.button("➕ Add Tool", use_container_width=True):
            st.session_state["show_add_modal"] = True
    with c2:
        delete_disabled = len(st.session_state.get("selection", [])) == 0
        if st.button("🗑️ Delete Selected", use_container_width=True, disabled=delete_disabled):
            delete_tools_by_keys(st.session_state.get("selection", []))
            st.success("Ausgewählte Tools gelöscht.")
    with c3:
        if st.button("↩️ Undo Last Delete", use_container_width=True, disabled=len(st.session_state.last_deleted)==0):
            existing = set(tool_keys())
            restored = 0
            for t in st.session_state.last_deleted:
                k = t.get("key")
                if not k or k in existing:
                    i = 2
                    nk = f"{k or 'restored'}_{i}"
                    while nk in existing:
                        i += 1
                        nk = f"{k or 'restored'}_{i}"
                    t = {**t, "key": nk, "name": f"{t.get('name','Tool')} (Restored)"}
                st.session_state.tools.append(t)
                existing.add(t["key"])
                restored += 1
            st.session_state.last_deleted = []
            log("INFO", f"Restored {restored} tool(s)")
            st.success("Wiederhergestellt.")
    with c4:
        if st.button("🔄 Refresh", use_container_width=True):
            st.toast("Refreshed.", icon="✅")
    with c5:
        if st.button("✅ Set Selected Active", use_container_width=True, disabled=delete_disabled):
            toggle_active(st.session_state.get("selection", []), True)

    # Search & Filters
    fc1, fc2 = st.columns([3,1])
    with fc1:
        q = st.text_input("Search (Name, Beschreibung, Endpoint)", placeholder="tippe zum Filtern...").strip().lower()
    with fc2:
        only_active = st.checkbox("Nur aktive", value=False)

    # Add modal
    if st.session_state.get("show_add_modal", False):
        with st.form("add_tool_form", clear_on_submit=True):
            st.subheader("Neues Tool anlegen")
            name = st.text_input("Name", placeholder="z. B. Redirect Mapper")
            key = st.text_input("Key (eindeutig, ohne Leerzeichen)", placeholder="z. B. redirect_mapper").strip()
            description = st.text_area("Beschreibung", placeholder="Kurze Funktionsbeschreibung...")
            endpoint = st.text_input("Endpoint/Pfad", placeholder="https://api.example.com/run")
            tags = st.text_input("Tags (Kommagetrennt)", placeholder="seo,etl,worker")
            active = st.checkbox("Aktiv", value=True)

            cadd, ccancel = st.columns([1,1])
            submitted = cadd.form_submit_button("Hinzufügen")
            cancel = ccancel.form_submit_button("Abbrechen")

            if submitted:
                if not name or not key:
                    st.error("Bitte mindestens **Name** und **Key** ausfüllen.")
                elif key in tool_keys():
                    st.error("Der **Key** existiert bereits. Bitte einen eindeutigen Key wählen.")
                else:
                    st.session_state.tools.append({
                        "name": name,
                        "key": key,
                        "description": description,
                        "endpoint": endpoint,
                        "active": active,
                        "tags": tags.strip()
                    })
                    st.session_state["show_add_modal"] = False
                    log("OK", f"Tool '{name}' hinzugefügt")
                    st.success(f"Tool **{name}** hinzugefügt.")
            elif cancel:
                st.session_state["show_add_modal"] = False

# -------------------------------
# Data Table + Export + Stats
# -------------------------------
with st.container(border=True):
    st.subheader("Tools")
    tools_df = get_tools_df()

    # Apply filters
    if not tools_df.empty:
        mask = pd.Series([True]*len(tools_df))
        if q:
            s = tools_df[["name","description","endpoint"]].fillna("").astype(str).apply(lambda col: col.str.lower())
            mask &= (s["name"].str.contains(q) | s["description"].str.contains(q) | s["endpoint"].str.contains(q))
        if only_active:
            mask &= tools_df["active"] == True  # noqa: E712
        tools_df = tools_df[mask]

    if len(tools_df) == 0:
        st.info("Keine Treffer. Suchbegriff ändern oder **Add Tool** nutzen.")
    else:
        # Selection column
        sel_col = "selected__"
        tools_df = tools_df.copy()
        tools_df[sel_col] = tools_df["key"].isin(st.session_state.get("selection", []))

        # Editable table
        edited = st.data_editor(
            tools_df,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Name"),
                "key": st.column_config.TextColumn("Key"),
                "description": st.column_config.TextColumn("Beschreibung"),
                "endpoint": st.column_config.TextColumn("Endpoint"),
                "tags": st.column_config.TextColumn("Tags (comma-separated)"),
                "active": st.column_config.CheckboxColumn("Aktiv"),
                sel_col: st.column_config.CheckboxColumn("Auswahl")
            }
        )

        # Update selection
        selected_keys = [edited.loc[i, "key"] for i in edited.index if bool(edited.loc[i, sel_col])]
        st.session_state.selection = selected_keys

        # Save edits back (excluding selection column)
        if st.button("💾 Änderungen speichern", type="primary"):
            cleaned = edited.drop(columns=[sel_col])
            set_tools_from_df(cleaned)
            st.success("Änderungen gespeichert.")
            log("OK", "Änderungen gespeichert")

        # Export buttons
        cexp1, cexp2 = st.columns([1,1])
        with cexp1:
            export_all = st.button("⬇️ Export: Alle")
            if export_all:
                export_str = json.dumps(st.session_state.tools, ensure_ascii=False, indent=2)
                st.download_button(
                    label="Download tools_all.json",
                    data=export_str.encode("utf-8"),
                    file_name="tools_all.json",
                    mime="application/json",
                    key="dl_all"
                )
        with cexp2:
            has_sel = len(st.session_state.selection) > 0
            export_sel = st.button("⬇️ Export: Auswahl", disabled=not has_sel)
            if export_sel and has_sel:
                subset = [t for t in st.session_state.tools if t["key"] in st.session_state.selection]
                export_str = json.dumps(subset, ensure_ascii=False, indent=2)
                st.download_button(
                    label="Download tools_selected.json",
                    data=export_str.encode("utf-8"),
                    file_name="tools_selected.json",
                    mime="application/json",
                    key="dl_sel"
                )

# -------------------------------
# Per-Row Actions + Detail & History
# -------------------------------
with st.container(border=True):
    st.subheader("Actions & Details")
    if not st.session_state.tools:
        st.info("Keine Tools vorhanden.")
    else:
        for t in st.session_state.tools:
            # honor current filters in actions list
            if q and not any([
                (t.get("name","").lower().find(q) != -1),
                (t.get("description","").lower().find(q) != -1),
                (t.get("endpoint","").lower().find(q) != -1)
            ]):
                continue
            if only_active and not t.get("active", False):
                continue

            key = t.get("key")
            with st.expander(f"{'🟢' if t.get('active') else '⚪️'} {t.get('name')}  ·  {key}"):
                st.write(t.get("description",""))
                st.code(t.get("endpoint",""), language="text")
                st.caption(f"Tags: {t.get('tags','')}")

                a1, a2, a3, a4 = st.columns([1,1,1,1])
                with a1:
                    if st.button("🔧 Run Job", key=f"run_{key}"):
                        start = time.time()
                        status, note = run_job_sim(key)
                        dur = (time.time() - start) * 1000
                        add_history_event(key, "RUN", status, status, dur, note)
                        st.success("Job ausgeführt.")
                with a2:
                    if st.button("📡 Ping", key=f"ping_{key}"):
                        start = time.time()
                        code, note = ping_endpoint(t.get("endpoint",""))
                        dur = (time.time() - start) * 1000
                        status = "OK" if code.isdigit() and int(code) < 500 else ("WARN" if code.isdigit() else "ERR")
                        add_history_event(key, "PING", status, code, dur, note)
                        st.info(f"Ping: {code} {note}")
                        log("INFO", f"Ping {key}: {code} {note}")
                with a3:
                    if st.button("🧬 Duplicate", key=f"dup_{key}"):
                        duplicate_tool(key)
                        st.success("Dupliziert.")
                with a4:
                    if st.button("🗑️ Delete", key=f"del_{key}"):
                        delete_tools_by_keys([key])
                        st.success("Gelöscht.")

                # Detail & History
                st.markdown("**Details & History**")
                hdf = get_history_df(key)
                if hdf.empty:
                    st.caption("Noch keine History.")
                else:
                    st.dataframe(hdf.iloc[::-1], use_container_width=True)

                    # Export history CSV
                    csv_buf = StringIO()
                    hdf.to_csv(csv_buf, index=False)
                    st.download_button(
                        label="⬇️ Export History CSV",
                        data=csv_buf.getvalue().encode("utf-8"),
                        file_name=f"{key}_history.csv",
                        mime="text/csv",
                        key=f"dl_hist_{key}"
                    )

                    # Clear history
                    if st.button("🧹 Clear History", key=f"clear_hist_{key}"):
                        st.session_state.run_history[key] = []
                        st.success("History geleert.")

# -------------------------------
# Quick Stats + Log
# -------------------------------
with st.container(border=True):
    st.subheader("Quick Stats")
    df = pd.DataFrame(st.session_state.tools)
    total = len(df)
    active_cnt = int(df["active"].sum()) if total else 0
    inactive_cnt = total - active_cnt
    st.write(f"**Total:** {total} · **Active:** {active_cnt} · **Inactive:** {inactive_cnt}")
    # Tag counts
    if total:
        tags_series = (
            df["tags"].fillna("").astype(str).str.split(",")
            .apply(lambda xs: [x.strip().lower() for x in xs if x.strip()])
        )
        tag_counts = {}
        for lst in tags_series:
            for tag in lst:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if tag_counts:
            tag_df = pd.DataFrame(sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])), columns=["Tag","Count"])
            st.dataframe(tag_df, use_container_width=True)
        else:
            st.caption("Keine Tags vergeben.")

with st.container(border=True):
    st.subheader("Activity Log")
    if not st.session_state.logs:
        st.caption("Noch keine Einträge.")
    else:
        log_df = pd.DataFrame(st.session_state.logs).iloc[-50:]
        st.dataframe(log_df, use_container_width=True)

st.caption("Bereit. 'Search Experience' – clean, funktionsstark, ohne Super Template. 🤘")

