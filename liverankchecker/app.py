# -*- coding: utf-8 -*-
import os
import csv
import json
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from utils.utils import (
    read_markdown_file,
    handle_authentication,
    logout,
    apply_claneo_branding as _orig_apply_claneo_branding,
)

# =============================================================================
#  ACB_COMPAT_WRAPPER – apply_claneo_branding kompatibel machen
# =============================================================================
def apply_claneo_branding(title=None, subtitle=None, **kwargs):
    """
    Kompatibler Wrapper um utils.utils.apply_claneo_branding:
    - Funktioniert sowohl ohne Argumente als auch mit title/subtitle.
    - Darf niemals die App crashen.
    """
    try:
        # 1) Erst versuchen wir die alte No-Arg-Signatur
        try:
            _orig_apply_claneo_branding()
            if title:
                st.title(str(title))
            if subtitle:
                st.caption(str(subtitle))
            return
        except TypeError:
            # 2) Falls das Original doch Argumente akzeptiert
            try:
                _orig_apply_claneo_branding(title=title, subtitle=subtitle, **kwargs)
                return
            except Exception:
                pass
    except Exception:
        pass

    # 3) Fallback: Minimal-Branding, falls alles andere scheitert
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
        # Branding darf nie hart crashen
        pass


# =============================================================================
#  Streamlit Grundkonfiguration
# =============================================================================
st.set_page_config(
    page_title="Keywords",
    page_icon="🔑",
    layout="wide",
    menu_items={
        "Get Help": "https://www.linkedin.com/in/kirchhoff-kevin/",
        "About": "This is an app for keyword analysis and SERP features.",
    },
)

CWD = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CWD)
MARKDOWN_FILE_PATH = os.path.join(PARENT_DIR, "information", "Keywords", "README.md")


# =============================================================================
#  Authentifizierung
# =============================================================================
auth_result = handle_authentication()

if isinstance(auth_result, tuple) and len(auth_result) == 3:
    NAME, AUTHENTICATION_STATUS, USERNAME = auth_result
else:
    NAME, AUTHENTICATION_STATUS, USERNAME = None, bool(auth_result), None


# =============================================================================
#  Session-State Initialisierung
# =============================================================================
def init_session_state():
    """Initialisiert zentrale Session-State-Werte einmalig."""
    if st.session_state.get("_initialized", False):
        return

    st.session_state["_initialized"] = True
    st.session_state.setdefault("confirmed_preview", False)
    st.session_state.setdefault("selected_task_type", "rankings_and_search_volume")


def initsessionstate():
    """Alias für Alt-Code-Kompatibilität."""
    return init_session_state()


# =============================================================================
#  Datenbank- & Tracking-Funktionen
# =============================================================================
def get_db_path() -> str:
    """
    Pfad zur SQLite-DB im .streamlit/database-Ordner.
    """
    db_dir = os.path.join(PARENT_DIR, ".streamlit", "database")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "tasks.db")


def _ensure_task_table_columns(c: sqlite3.Cursor):
    """
    Stellt sicher, dass alle benötigten Spalten existieren.
    (sanfte Migration, falls es schon eine ältere tasks-Tabelle gibt)
    """
    # task_type nachziehen, falls alte DB existiert
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT DEFAULT 'rankings_and_search_volume'")
    except sqlite3.OperationalError:
        # Spalte existiert bereits -> ignorieren
        pass

    # settings_json für Search-Settings nachziehen
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN settings_json TEXT")
    except sqlite3.OperationalError:
        # Spalte existiert bereits -> ignorieren
        pass


def setup_database():
    """
    Legt eine tasks-Tabelle an, falls noch nicht vorhanden,
    und sorgt für minimale Migration (task_type / settings_json).
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, timeout=20)
        c = conn.cursor()

        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")

        # Basis-Tabellenstruktur
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                task_id TEXT NOT NULL,
                domain TEXT,
                raw_keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                task_type TEXT DEFAULT 'rankings_and_search_volume',
                settings_json TEXT
            )
            """
        )

        # Migration für ältere DBs
        _ensure_task_table_columns(c)

        conn.commit()
        conn.close()
        return db_path
    except sqlite3.Error as e:
        st.error(f"SQLite error while setting up database: {e}")
        return None
    except Exception as e:
        st.error(f"Unexpected error while setting up database: {e}")
        return None


def get_db_connection():
    """
    Liefert eine DB-Connection auf die tasks-Tabelle.
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, timeout=20)
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        return conn
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None


def generate_task_id(domain: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_domain = (domain or "no-domain").replace(".", "_").replace(" ", "_")
    return f"{safe_domain}_{ts}"


def save_task(
    username: str,
    task_id: str,
    domain: str,
    raw_keywords: str,
    task_type: str,
    settings_json: Optional[str] = None,
) -> bool:
    """
    Speichert einen Task-Eintrag inkl. task_type & settings_json.
    (Später hängen wir die komplette DataForSEO-Logik daran.)
    """
    conn = get_db_connection()
    if conn is None:
        return False
    try:
        c = conn.cursor()

        # Sicherstellen, dass die Spalten existieren (Migration für sehr alte DBs)
        _ensure_task_table_columns(c)

        c.execute(
            """
            INSERT INTO tasks (username, task_id, domain, raw_keywords, status, task_type, settings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, task_id, domain, raw_keywords, "pending", task_type, settings_json),
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Database error while saving task: {e}")
        return False
    finally:
        conn.close()


def get_user_tasks(username: str):
    """
    Holt alle Tasks eines Users aus der tasks-Tabelle.
    """
    conn = get_db_connection()
    if conn is None:
        return []
    try:
        c = conn.cursor()
        _ensure_task_table_columns(c)

        c.execute(
            """
            SELECT id, task_id, domain, raw_keywords, created_at, status, task_type, settings_json
            FROM tasks
            WHERE username = ?
            ORDER BY created_at DESC
            """,
            (username,),
        )
        rows = c.fetchall()
        tasks = []
        for row in rows:
            task = {
                "id": row[0],
                "task_id": row[1],
                "domain": row[2],
                "raw_keywords": row[3],
                "created_at": row[4],
                "status": row[5],
                "task_type": row[6] if len(row) > 6 and row[6] else "rankings_and_search_volume",
                "settings_json": row[7] if len(row) > 7 else None,
            }
            tasks.append(task)
        return tasks
    except sqlite3.Error as e:
        st.error(f"Error retrieving tasks: {e}")
        return []
    finally:
        conn.close()


def delete_task(task_id: str) -> bool:
    """
    Löscht einen Task aus der DB.
    """
    conn = get_db_connection()
    if conn is None:
        return False
    try:
        c = conn.cursor()
        c.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Error deleting task: {e}")
        return False
    finally:
        conn.close()


def setup_tracking_folder():
    """
    Legt einen .streamlit/tracking-Ordner an.
    """
    tracking_dir = os.path.join(PARENT_DIR, ".streamlit", "tracking")
    os.makedirs(tracking_dir, exist_ok=True)
    return tracking_dir


def log_usage(username: str, tool_name: str = "Keywords"):
    """
    Loggt die Nutzung ganz simpel in tool_usage.csv.
    """
    tracking_dir = setup_tracking_folder()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    usage_file = os.path.join(tracking_dir, "tool_usage.csv")

    file_exists = os.path.isfile(usage_file)
    with open(usage_file, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Username", "Tool Name"])
        writer.writerow([timestamp, username or "", tool_name])


# =============================================================================
#  Kleine Helfer
# =============================================================================
def text_to_df(text: str, column_name: str = "Keyword") -> pd.DataFrame:
    """
    Wandelt Text (Zeilen/Kommas) in ein DataFrame um.
    """
    items = [item.strip() for item in text.splitlines() if item.strip()]
    if not items:
        return pd.DataFrame(columns=[column_name])
    return pd.DataFrame(items, columns=[column_name])


def parse_settings(settings_json: Optional[str]) -> dict:
    """
    Settings-JSON in Dict umwandeln, defensiv.
    """
    if not settings_json:
        return {}
    try:
        data = json.loads(settings_json)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


# =============================================================================
#  Haupt-UI
# =============================================================================
def main():
    # Branding oben
    apply_claneo_branding(
        "Keyword Research & Analysis",
        "Erfassung der Keywords und Anlage der Tasks.",
    )

    # README anzeigen (falls vorhanden)
    with st.expander("Before using this app"):
        try:
            st.markdown(read_markdown_file(MARKDOWN_FILE_PATH))
        except Exception:
            st.info("README konnte nicht geladen werden – das ist nur informativ.")

    # Session-State initialisieren
    initsessionstate()

    # Auth-Status prüfen
    if not AUTHENTICATION_STATUS:
        st.warning("Bitte logge dich ein, um das Keyword-Tool zu nutzen.")
        return

    # DB vorbereiten
    db_path = setup_database()
    if not db_path:
        st.error("Datenbank konnte nicht initialisiert werden. Bitte Logs prüfen.")
        return

    # Benutzung loggen
    log_usage(USERNAME or "unknown", "Keywords")

    # Tabs
    tab_create, tab_results = st.tabs(["Create Task", "View Results"])

    # -------------------------------------------------------------------------
    # TAB 1: Create Task
    # -------------------------------------------------------------------------
    with tab_create:
        st.subheader("Create Keyword Task")

        # Task-Typ (wird in der DB gespeichert -> Vorbereitung für Hauptlogik)
        task_type = st.selectbox(
            "Task type",
            options=[
                "rankings_and_search_volume",
                "search_volume_only",
                "rankings_only",
            ],
            format_func=lambda x: {
                "rankings_and_search_volume": "Rankings + Search Volume",
                "search_volume_only": "Only Search Volume",
                "rankings_only": "Only Rankings",
            }.get(x, x),
            key="task_type_select",
        )

        domain = st.text_input(
            "Domain (optional, e.g. example.com)",
            key="domain_input",
        )

        st.markdown("### Search settings")

        col1, col2 = st.columns(2)
        with col1:
            search_engine = st.selectbox(
                "Search engine",
                options=[
                    "google.de",
                    "google.com",
                    "google.co.uk",
                    "google.fr",
                    "google.es",
                    "google.it",
                ],
                index=0,
                key="search_engine_select",
            )

            device = st.selectbox(
                "Device",
                options=["desktop", "mobile"],
                index=0,
                key="device_select",
            )

        with col2:
            location_name = st.text_input(
                "Location name (e.g. Germany, Berlin, United States)",
                value="Germany",
                key="location_name_input",
            )
            language_code = st.text_input(
                "Language code (e.g. de, en, fr)",
                value="de",
                key="language_code_input",
            )

        results_per_keyword = st.slider(
            "Results per keyword (planned SERP depth)",
            min_value=10,
            max_value=100,
            step=10,
            value=20,
            key="results_per_keyword_slider",
        )

        st.write("You can provide keywords either via file upload or manual input.")

        uploaded_file = st.file_uploader(
            "Upload Excel file with keywords (optional)", type=["xlsx", "xls"]
        )

        keywords_df = None
        if uploaded_file is not None:
            try:
                df_raw = pd.read_excel(uploaded_file)
                first_col = df_raw.columns[0]
                keywords_df = pd.DataFrame(df_raw[first_col].values, columns=["Keyword"])
                keywords_df = keywords_df.dropna(subset=["Keyword"])
                keywords_df = keywords_df[keywords_df["Keyword"].astype(str).str.strip() != ""]
                st.write(f"Detected {len(keywords_df)} keywords from file.")
                st.dataframe(keywords_df.head(20))
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")

        manual_keywords_text = st.text_area(
            "Or enter keywords manually (one per line):",
            key="manual_keywords_input",
        )

        if keywords_df is None and manual_keywords_text.strip():
            keywords_df = text_to_df(manual_keywords_text, "Keyword")
            st.write(f"Detected {len(keywords_df)} keywords from manual input.")
            st.dataframe(keywords_df.head(20))

        if keywords_df is not None and not keywords_df.empty:
            st.info(
                "In this stage, we store the task including the selected task type and "
                "search settings in the database. "
                "Die eigentliche API-Logik aus der Hauptdatei hängen wir anschließend wieder dran."
            )

            # Settings für diesen Task zusammenbauen
            settings = {
                "search_engine": search_engine,
                "device": device,
                "location_name": location_name,
                "language_code": language_code,
                "results_per_keyword": results_per_keyword,
            }
            settings_json = json.dumps(settings, ensure_ascii=False)

            if st.button("Create task", type="primary"):
                raw_keywords_json = keywords_df.to_json(orient="records", force_ascii=False)
                task_id = generate_task_id(domain or "no-domain")
                ok = save_task(
                    USERNAME or "unknown",
                    task_id,
                    domain or "",
                    raw_keywords_json,
                    task_type,
                    settings_json=settings_json,
                )
                if ok:
                    st.success(
                        f"Task '{task_id}' wurde in der DB angelegt "
                        f"(Status: pending, Type: {task_type})."
                    )
                else:
                    st.error("Task konnte nicht gespeichert werden.")
        else:
            st.info("Bitte gib Keywords ein oder lade eine Datei hoch, um einen Task anzulegen.")

    # -------------------------------------------------------------------------
    # TAB 2: View Results
    # -------------------------------------------------------------------------
    with tab_results:
        st.subheader("View Tasks")

        tasks = get_user_tasks(USERNAME or "unknown")
        if not tasks:
            st.info("Keine Tasks gefunden. Lege im Tab „Create Task“ einen Task an.")
        else:
            # Übersichtstabelle oben
            overview_rows = []
            for t in tasks:
                settings = parse_settings(t.get("settings_json"))
                overview_rows.append(
                    {
                        "Created": t["created_at"],
                        "Task ID": t["task_id"],
                        "Domain": t["domain"],
                        "Status": t["status"],
                        "Task type": t.get("task_type", "rankings_and_search_volume"),
                        "Search engine": settings.get("search_engine", ""),
                        "Device": settings.get("device", ""),
                    }
                )
            overview_df = pd.DataFrame(overview_rows)
            st.dataframe(overview_df)

            # Detail-Expander
            for task in tasks:
                settings = parse_settings(task.get("settings_json"))

                label = (
                    f"{task['created_at']} | {task['task_id']} | "
                    f"{task.get('task_type', 'rankings_and_search_volume')} | {task['status']}"
                )
                with st.expander(label):
                    st.write(f"**Domain:** {task['domain'] or '-'}")
                    st.write(f"**Created:** {task['created_at']}")
                    st.write(f"**Status:** {task['status']}")
                    st.write(
                        f"**Task type:** {task.get('task_type', 'rankings_and_search_volume')}"
                    )

                    st.markdown("#### Search settings")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.write(f"- **Search engine:** {settings.get('search_engine', '-')}")
                        st.write(f"- **Device:** {settings.get('device', '-')}")
                    with col_b:
                        st.write(f"- **Location:** {settings.get('location_name', '-')}")
                        st.write(f"- **Language:** {settings.get('language_code', '-')}")
                        st.write(
                            f"- **Results per keyword:** "
                            f"{settings.get('results_per_keyword', '-')}"
                        )

                    st.markdown("#### Keywords (preview)")
                    # Keywords nur als Preview
                    try:
                        kw_list = json.loads(task["raw_keywords"])
                        kw_df = pd.DataFrame(kw_list)
                        st.write("**First 50 keywords:**")
                        st.dataframe(kw_df.head(50))
                    except Exception:
                        st.write("Raw keywords:", task["raw_keywords"][:500])

                    col_del, col_download = st.columns([1, 1])

                    # Delete
                    with col_del:
                        if st.button("🗑️ Delete task", key=f"delete_{task['task_id']}"):
                            if delete_task(task["task_id"]):
                                st.success("Task deleted.")
                                st.experimental_rerun()

                    # Download als CSV
                    with col_download:
                        try:
                            kw_list = json.loads(task["raw_keywords"])
                            kw_df = pd.DataFrame(kw_list)
                            csv_bytes = kw_df.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                "⬇️ Download keywords (CSV)",
                                data=csv_bytes,
                                file_name=f"{task['task_id']}_keywords.csv",
                                mime="text/csv",
                                key=f"dl_{task['task_id']}",
                            )
                        except Exception:
                            st.write("Download not available (invalid keyword payload).")


# =============================================================================
#  Entry Point für Streamlit
# =============================================================================
if __name__ == "__main__":
    main()