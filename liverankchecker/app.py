# -*- coding: utf-8 -*-
import os
import csv
import json
import sqlite3
from datetime import datetime, timedelta

import streamlit as st

# Utils from your project
from utils.utils import read_markdown_file, handle_authentication, logout, apply_claneo_branding as _orig_apply

# ------------------------------------------------
# Safe wrapper for apply_claneo_branding
# ------------------------------------------------
try:
    _ACB_ORIG = _orig_apply
except Exception:
    _ACB_ORIG = None


def apply_claneo_branding(title=None, subtitle=None, **kwargs):
    '''
    Wrapper um apply_claneo_branding aus utils.utils.
    - Funktioniert, egal ob das Original 0 Args oder (title, subtitle, ...) erwartet.
    - Fällt auf eine einfache Branding-Variante zurück, falls irgendwas schiefgeht.
    '''
    try:
        if _ACB_ORIG is None:
            raise TypeError('Original apply_claneo_branding not available')

        # Erst ohne Argumente versuchen (alte Signatur)
        try:
            return _ACB_ORIG()
        except TypeError:
            # Falls das Original doch Parameter erwartet, mitgeben
            return _ACB_ORIG(title, subtitle, **kwargs)
    except Exception:
        # Harmloser Fallback, der niemals die App crashen darf
        try:
            st.logo('https://www.claneo.com/wp-content/uploads/Element-4.svg')
        except Exception:
            pass
        if title:
            st.title(str(title))
        if subtitle:
            st.caption(str(subtitle))


# ------------------------------------------------
# Page Config
# ------------------------------------------------
st.set_page_config(
    page_title='Keywords',
    page_icon='🔑',
    layout='wide',
    menu_items={
        'Get Help': 'https://www.linkedin.com/in/kirchhoff-kevin/',
        'About': 'This is an app for keyword analysis and SERP features.'
    },
)

# ------------------------------------------------
# Constants (aus der großen Datei)
# ------------------------------------------------
LANGUAGES = ["Afrikaans","Albanian","Amharic","Arabic","Armenian","Azerbaijani","Basque","Belarusian","Bengali","Bosnian","Bulgarian","Catalan","Cebuano","Chinese (Simplified)","Chinese (Traditional)","Corsican","Croatian","Czech","Danish","Dutch","English","Esperanto","Estonian","Finnish","French","Frisian","Galician","Georgian","German","Greek","Gujarati","Haitian Creole","Hausa","Hawaiian","Hebrew","Hindi","Hmong","Hungarian","Icelandic","Igbo","Indonesian","Irish","Italian","Japanese","Javanese","Kannada","Kazakh","Khmer","Kinyarwanda","Korean","Kurdish","Kyrgyz","Lao","Latvian","Lithuanian","Luxembourgish","Macedonian","Malagasy","Malay","Malayalam","Maltese","Maori","Marathi","Mongolian","Myanmar (Burmese)","Nepali","Norwegian","Nyanja (Chichewa)","Odia (Oriya)","Pashto","Persian","Polish","Portuguese (Portugal","Punjabi","Romanian","Russian","Samoan","Scots Gaelic","Serbian","Sesotho","Shona","Sindhi","Sinhala (Sinhalese)","Slovak","Slovenian","Somali","Spanish","Sundanese","Swahili","Swedish","Tagalog (Filipino)","Tajik","Tamil","Tatar","Telugu","Thai","Turkish","Turkmen","Ukrainian","Urdu","Uyghur","Uzbek","Vietnamese","Welsh","Xhosa","Yiddish","Yoruba","Zulu"]
COUNTRIES = ["Afghanistan", "Albania", "Antarctica", "Algeria", "American Samoa", "Andorra", "Angola", "Antigua and Barbuda", "Azerbaijan", "Argentina", "Australia", "Austria", "The Bahamas", "Bahrain", "Bangladesh", "Armenia", "Barbados", "Belgium", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Belize", "Solomon Islands", "Brunei", "Bulgaria", "Myanmar (Burma)", "Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Sri Lanka", "Chad", "Chile", "China", "Christmas Island", "Cocos (Keeling) Islands", "Colombia", "Comoros", "Republic of the Congo", "Democratic Republic of the Congo", "Cook Islands", "Costa Rica", "Croatia", "Cyprus", "Czechia", "Benin", "Denmark", "Dominica", "Dominican Republic", "Ecuador", "El Salvador", "Equatorial Guinea", "Ethiopia", "Eritrea", "Estonia", "South Georgia and the South Sandwich Islands", "Fiji", "Finland", "France", "French Polynesia", "French Southern and Antarctic Lands", "Djibouti", "Gabon", "Georgia", "The Gambia", "Germany", "Ghana", "Kiribati", "Greece", "Grenada", "Guam", "Guatemala", "Guinea", "Guyana", "Haiti", "Heard Island and McDonald Islands", "Vatican City", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Kazakhstan", "Jordan", "Kenya", "South Korea", "Kuwait", "Kyrgyzstan", "Laos", "Lebanon", "Lesotho", "Latvia", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Mauritania", "Mauritius", "Mexico", "Monaco", "Mongolia", "Moldova", "Montenegro", "Morocco", "Mozambique", "Oman", "Namibia", "Nauru", "Nepal", "Netherlands", "Curacao", "Sint Maarten", "Caribbean Netherlands", "New Caledonia", "Vanuatu", "New Zealand", "Nicaragua", "Niger", "Nigeria", "Niue", "Norfolk Island", "Norway", "Northern Mariana Islands", "United States Minor Outlying Islands", "Federated States of Micronesia", "Marshall Islands", "Palau", "Pakistan", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Pitcairn Islands", "Poland", "Portugal", "Guinea-Bissau", "Timor-Leste", "Qatar", "Romania", "Rwanda", "Saint Helena, Ascension and Tristan da Cunha", "Saint Kitts and Nevis", "Saint Lucia", "Saint Pierre and Miquelon", "Saint Vincent and the Grenadines", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Vietnam", "Slovenia", "Somalia", "South Africa", "Zimbabwe", "Spain", "Suriname", "Eswatini", "Sweden", "Switzerland", "Tajikistan", "Thailand", "Togo", "Tokelau", "Tonga", "Trinidad and Tobago", "United Arab Emirates", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "North Macedonia", "Egypt", "United Kingdom", "Guernsey", "Jersey", "Tanzania", "United States", "Burkina Faso", "Uruguay", "Uzbekistan", "Venezuela", "Wallis and Futuna", "Samoa", "Yemen", "Zambia"]
DEVICES = ["mobile", "desktop"]

preferred_countries = ["Germany", "Austria", "Switzerland", "United Kingdom", "United States", "France", "Italy", "Netherlands"]
preferred_languages = ["German", "English", "Spanish", "French", "Italian", "Dutch"]


def custom_sort(all_items, preferred_items):
    sorted_items = preferred_items + ["_____________"] + [item for item in all_items if item not in preferred_items]
    return sorted_items


# ------------------------------------------------
# Pfade / README
# ------------------------------------------------
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
markdown_file_path = os.path.join(parent_dir, "information", "Keywords", "README.md")


# ------------------------------------------------
# Authentication
# ------------------------------------------------
auth_result = handle_authentication()

if isinstance(auth_result, tuple) and len(auth_result) == 3:
    name, authentication_status, username = auth_result
else:
    name, authentication_status, username = None, bool(auth_result), None


# ------------------------------------------------
# Session-State Helper
# ------------------------------------------------
def init_session_state():
    '''Nur einmal initialisieren, dann Flag setzen.'''
    if st.session_state.get("_initialized", False):
        return
    st.session_state["_initialized"] = True


# Alias für Legacy-Code
def initsessionstate():
    return init_session_state()


# ------------------------------------------------
# Datenbank-Funktionen (aus der großen Datei)
# ------------------------------------------------
if authentication_status:

    def setup_database():
        '''Setup the database with updated schema (original logic, leicht bereinigt).'''
        try:
            db_dir = os.path.join(".streamlit", "database")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "tasks.db")

            # Schreibtest
            test_file = os.path.join(db_dir, "test_write.tmp")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
            except (IOError, OSError) as e:
                st.error(f"Cannot write to database directory: {str(e)}")
                return None

            conn = None
            try:
                conn = sqlite3.connect(db_path, timeout=20)
                c = conn.cursor()

                c.execute("PRAGMA foreign_keys = ON")
                c.execute("PRAGMA journal_mode = WAL")

                # TASKS-Tabelle
                c.execute(
                    '''CREATE TABLE IF NOT EXISTS tasks
                       (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        domain TEXT,
                        task_type TEXT DEFAULT 'rankings_and_search_volume',
                        keywords TEXT,
                        country TEXT,
                        language TEXT,
                        device TEXT,
                        check_seasonality BOOLEAN DEFAULT 0,
                        check_ai_overviews BOOLEAN DEFAULT 0,
                        competitors TEXT,
                        search_volume_task_ids TEXT,
                        search_volume_results TEXT,
                        serp_task_ids TEXT,
                        serp_results TEXT,
                        processed_sv_tasks TEXT,
                        processed_serp_tasks TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        error_messages TEXT,
                        export_language TEXT DEFAULT 'German',
                        UNIQUE(username, task_id)
                       )'''
                )
                conn.commit()

                # search_volume_results Tabelle
                try:
                    c.execute("PRAGMA foreign_key_list(search_volume_results)")
                    _ = c.fetchall()
                except sqlite3.OperationalError:
                    c.execute(
                        '''CREATE TABLE IF NOT EXISTS search_volume_results
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            task_id TEXT NOT NULL,
                            results TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                           )'''
                    )

                # serp_results Tabelle
                try:
                    c.execute("PRAGMA foreign_key_list(serp_results)")
                    _ = c.fetchall()
                except sqlite3.OperationalError:
                    c.execute(
                        '''CREATE TABLE IF NOT EXISTS serp_results
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            task_id TEXT NOT NULL,
                            results TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                           )'''
                    )

                conn.commit()
                return db_path

            except sqlite3.Error as e:
                st.error(f"SQLite error: {str(e)}")
                return None
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except sqlite3.Error as e:
                        st.error(f"Error closing database connection: {str(e)}")

        except Exception as e:
            st.error(f"Unexpected error setting up database: {str(e)}")
            return None


    def get_db_connection():
        '''Get a database connection with proper timeout and WAL mode'''
        try:
            db_path = os.path.join(".streamlit", "database", "tasks.db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            conn = sqlite3.connect(db_path, timeout=20)
            c = conn.cursor()
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")

            return conn
        except Exception as e:
            st.error(f"Failed to connect to database: {str(e)}")
            return None


    def save_task(username, task_id, domain, keywords, country, language, device,
                  sv_task_ids=None, serp_task_ids=None, task_type="rankings_and_search_volume",
                  check_seasonality=False, check_ai_overviews=False, competitors=None,
                  export_language="German"):
        '''Save a new task to the database'''
        conn = get_db_connection()
        if conn is None:
            return False
        try:
            c = conn.cursor()
            c.execute(
                '''INSERT INTO tasks
                   (username, task_id, domain, task_type, keywords, country, language, device,
                    check_seasonality, check_ai_overviews, competitors,
                    search_volume_task_ids, serp_task_ids, export_language)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    username,
                    task_id,
                    domain,
                    task_type,
                    keywords,
                    country,
                    language,
                    device,
                    check_seasonality,
                    check_ai_overviews,
                    json.dumps(competitors) if competitors else None,
                    json.dumps(sv_task_ids) if sv_task_ids else None,
                    json.dumps(serp_task_ids) if serp_task_ids else None,
                    export_language,
                ),
            )

            # Leere Result-Container nach Bedarf anlegen
            if task_type in ["rankings_and_search_volume", "search_volume_only"]:
                c.execute(
                    '''INSERT INTO search_volume_results (task_id, results)
                       VALUES (?, ?)''',
                    (task_id, json.dumps([])),
                )

            if task_type in ["rankings_and_search_volume", "rankings_only"]:
                c.execute(
                    '''INSERT INTO serp_results (task_id, results)
                       VALUES (?, ?)''',
                    (task_id, json.dumps([])),
                )

            conn.commit()

            c.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,))
            result = c.fetchone()
            return bool(result)
        except sqlite3.Error as e:
            st.error(f"Database error: {str(e)}")
            return False
        finally:
            conn.close()


    def get_user_tasks(username):
        '''Get all tasks for a user'''
        conn = get_db_connection()
        if conn is None:
            return []
        try:
            c = conn.cursor()
            c.execute(
                '''SELECT * FROM tasks
                   WHERE username = ?
                   ORDER BY created_at DESC''',
                (username,),
            )
            columns = [d[0] for d in c.description]
            return [dict(zip(columns, row)) for row in c.fetchall()]
        except sqlite3.Error as e:
            st.error(f"Error retrieving tasks: {str(e)}")
            return []
        finally:
            conn.close()


    def update_task_status(task_id, status, task_data=None):
        '''Update task status and optionally store task data (vereinfacht)'''
        max_retries = 3
        for attempt in range(max_retries):
            conn = get_db_connection()
            if conn is None:
                return False
            try:
                c = conn.cursor()
                if task_data:
                    c.execute(
                        '''UPDATE tasks
                           SET status = ?,
                               completed_at = CURRENT_TIMESTAMP
                           WHERE task_id = ?''',
                        (status, task_id),
                    )
                else:
                    c.execute(
                        '''UPDATE tasks
                           SET status = ?
                           WHERE task_id = ?''',
                        (status, task_id),
                    )

                conn.commit()
                c.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,))
                result = c.fetchone()
                return bool(result)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    import time as _t
                    _t.sleep(0.1 * (attempt + 1))
                    continue
                else:
                    st.error(f"Error updating task: {str(e)}")
                    return False
            except sqlite3.Error as e:
                st.error(f"Error updating task: {str(e)}")
                return False
            finally:
                conn.close()
        return False


    def setup_tracking_folder():
        tracking_dir = os.path.join(parent_dir, ".streamlit", "tracking")
        os.makedirs(tracking_dir, exist_ok=True)
        return tracking_dir


    def log_usage(username: str, tool_name: str = "Keywords"):
        tracking_dir = setup_tracking_folder()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tool_name = "Keywords"

        usage_data = [timestamp, username, tool_name]
        usage_file = os.path.join(tracking_dir, "tool_usage.csv")

        file_exists = os.path.isfile(usage_file)

        with open(usage_file, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Username", "Tool Name"])
            writer.writerow(usage_data)


    def generate_task_id(domain: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{domain.replace('.', '_')}_{timestamp}"


    def check_time_elapsed(created_at_str):
        '''Check if 2 minutes have elapsed since task creation'''
        try:
            created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
            current_time = datetime.now()
            diff = current_time - created_at
            minutes = diff.total_seconds() / 60.0
            return minutes >= 2, minutes
        except (ValueError, TypeError):
            return False, 0.0


    def main():
        '''Bis jetzt: Login + DB + kleines Debug-UI.'''
        apply_claneo_branding("Keyword Research & Analysis", "Step 3: DB & Tracking ready")

        initsessionstate()

        st.markdown(read_markdown_file(markdown_file_path))

        db_path = setup_database()
        if not db_path:
            st.error("Failed to setup database. Please check the error messages above.")
            return

        st.success("✅ Login & Datenbank sind bereit.")
        st.write(f"**DB-Pfad:** `{db_path}`")

        # Tracking einmal ausführen
        log_usage(username or "unknown", "Keywords")

        # Country / Language / Device Auswahl (nur zu Testzwecken)
        st.subheader("Debug: Basic Settings")
        sorted_countries = custom_sort(COUNTRIES, preferred_countries)
        sorted_languages = custom_sort(LANGUAGES, preferred_languages)

        col1, col2, col3 = st.columns(3)
        with col1:
            country = st.selectbox("Country", sorted_countries, index=sorted_countries.index("Germany"))
        with col2:
            language = st.selectbox("Language", sorted_languages, index=sorted_languages.index("German"))
        with col3:
            device = st.selectbox("Device", DEVICES, index=1)

        st.info(f"Aktuelle Auswahl → Country: **{country}**, Language: **{language}**, Device: **{device}**")

        # Tasks vom User anzeigen (falls schon welche existieren)
        st.subheader("Debug: Aufgaben in der Datenbank")
        tasks = get_user_tasks(username)
        if tasks:
            st.write(f"Gefundene Tasks für **{username}**: {len(tasks)}")
            st.dataframe(tasks)
        else:
            st.write("Noch keine Tasks für dich gespeichert.")

else:
    # Falls nicht eingeloggt: einfache Main-Variante,
    # damit main() *immer* definiert ist und kein NameError kommt.
    def main():
        apply_claneo_branding("Keyword Analyse", "Bitte logge dich ein, um das Keyword-Tool zu nutzen.")
        st.warning("Du bist nicht eingeloggt.")


# ------------------------------------------------
# Wrapper für Streamlit-Einstieg
# ------------------------------------------------
def run_authenticated_main():
    '''Main function for authenticated users'''
    main()


if __name__ == "__main__":
    # Streamlit führt das Skript mit __name__ == "__main__" aus
    run_authenticated_main()
