import streamlit as st
import pandas as pd
import base64
import io
import re
try:
    import tldextract  # type: ignore
except ImportError:
    # Fallback, damit die App ohne tldextract wenigstens startet
    import urllib.parse

    class _ExtractResult:
        def __init__(self, subdomain: str, domain: str, suffix: str):
            self.subdomain = subdomain
            self.domain = domain
            self.suffix = suffix

        @property
        def top_domain_under_public_suffix(self) -> str:
            if self.domain and self.suffix:
                return f"{self.domain}.{self.suffix}"
            return self.domain or ""

    def _fallback_extract(url: str) -> _ExtractResult:
        parsed = urllib.parse.urlparse(url if "://" in url else f"http://{url}")
        host = parsed.hostname or ""
        parts = host.split(".") if host else []
        subdomain = ".".join(parts[:-2]) if len(parts) > 2 else ""
        domain = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
        suffix = parts[-1] if len(parts) >= 2 else ""
        return _ExtractResult(subdomain, domain, suffix)

    class _TldExtractShim:
        def extract(self, url: str) -> _ExtractResult:
            return _fallback_extract(url)

    tldextract = _TldExtractShim()  # type: ignore
    import streamlit as st

    st.warning("Falle auf vereinfachten Domain-Parser zurück – bitte 'tldextract' installieren.", icon="⚠️")
import aiohttp
import asyncio
from base64 import b64encode
from json import loads, dumps
import os
from datetime import datetime, timedelta
import csv
import sqlite3
import json
from http.client import HTTPSConnection
from utils.utils import read_markdown_file, set_page_config, handle_authentication, logout, apply_claneo_branding
from utils.keyword_validator import validate_keywords_for_task_type, format_validation_report, KeywordValidator, APIEndpoint, get_api_rules_summary
import time
from urllib.parse import urlparse

# -------------
# Constants
# -------------
LANGUAGES = ["Afrikaans","Albanian","Amharic","Arabic","Armenian","Azerbaijani","Basque","Belarusian","Bengali","Bosnian","Bulgarian","Catalan","Cebuano","Chinese (Simplified)","Chinese (Traditional)","Corsican","Croatian","Czech","Danish","Dutch","English","Esperanto","Estonian","Finnish","French","Frisian","Galician","Georgian","German","Greek","Gujarati","Haitian Creole","Hausa","Hawaiian","Hebrew","Hindi","Hmong","Hungarian","Icelandic","Igbo","Indonesian","Irish","Italian","Japanese","Javanese","Kannada","Kazakh","Khmer","Kinyarwanda","Korean","Kurdish","Kyrgyz","Lao","Latvian","Lithuanian","Luxembourgish","Macedonian","Malagasy","Malay","Malayalam","Maltese","Maori","Marathi","Mongolian","Myanmar (Burmese)","Nepali","Norwegian","Nyanja (Chichewa)","Odia (Oriya)","Pashto","Persian","Polish","Portuguese (Portugal","Punjabi","Romanian","Russian","Samoan","Scots Gaelic","Serbian","Sesotho","Shona","Sindhi","Sinhala (Sinhalese)","Slovak","Slovenian","Somali","Spanish","Sundanese","Swahili","Swedish","Tagalog (Filipino)","Tajik","Tamil","Tatar","Telugu","Thai","Turkish","Turkmen","Ukrainian","Urdu","Uyghur","Uzbek","Vietnamese","Welsh","Xhosa","Yiddish","Yoruba","Zulu"]
COUNTRIES = ["Afghanistan", "Albania", "Antarctica", "Algeria", "American Samoa", "Andorra", "Angola", "Antigua and Barbuda", "Azerbaijan", "Argentina", "Australia", "Austria", "The Bahamas", "Bahrain", "Bangladesh", "Armenia", "Barbados", "Belgium", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Belize", "Solomon Islands", "Brunei", "Bulgaria", "Myanmar (Burma)", "Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Sri Lanka", "Chad", "Chile", "China", "Christmas Island", "Cocos (Keeling) Islands", "Colombia", "Comoros", "Republic of the Congo", "Democratic Republic of the Congo", "Cook Islands", "Costa Rica", "Croatia", "Cyprus", "Czechia", "Benin", "Denmark", "Dominica", "Dominican Republic", "Ecuador", "El Salvador", "Equatorial Guinea", "Ethiopia", "Eritrea", "Estonia", "South Georgia and the South Sandwich Islands", "Fiji", "Finland", "France", "French Polynesia", "French Southern and Antarctic Lands", "Djibouti", "Gabon", "Georgia", "The Gambia", "Germany", "Ghana", "Kiribati", "Greece", "Grenada", "Guam", "Guatemala", "Guinea", "Guyana", "Haiti", "Heard Island and McDonald Islands", "Vatican City", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Kazakhstan", "Jordan", "Kenya", "South Korea", "Kuwait", "Kyrgyzstan", "Laos", "Lebanon", "Lesotho", "Latvia", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Mauritania", "Mauritius", "Mexico", "Monaco", "Mongolia", "Moldova", "Montenegro", "Morocco", "Mozambique", "Oman", "Namibia", "Nauru", "Nepal", "Netherlands", "Curacao", "Sint Maarten", "Caribbean Netherlands", "New Caledonia", "Vanuatu", "New Zealand", "Nicaragua", "Niger", "Nigeria", "Niue", "Norfolk Island", "Norway", "Northern Mariana Islands", "United States Minor Outlying Islands", "Federated States of Micronesia", "Marshall Islands", "Palau", "Pakistan", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Pitcairn Islands", "Poland", "Portugal", "Guinea-Bissau", "Timor-Leste", "Qatar", "Romania", "Rwanda", "Saint Helena, Ascension and Tristan da Cunha", "Saint Kitts and Nevis", "Saint Lucia", "Saint Pierre and Miquelon", "Saint Vincent and the Grenadines", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Vietnam", "Slovenia", "Somalia", "South Africa", "Zimbabwe", "Spain", "Suriname", "Eswatini", "Sweden", "Switzerland", "Tajikistan", "Thailand", "Togo", "Tokelau", "Tonga", "Trinidad and Tobago", "United Arab Emirates", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "North Macedonia", "Egypt", "United Kingdom", "Guernsey", "Jersey", "Tanzania", "United States", "Burkina Faso", "Uruguay", "Uzbekistan", "Venezuela", "Wallis and Futuna", "Samoa", "Yemen", "Zambia"]
DEVICES = ["mobile", "desktop"]

# -------------
# Variables
# -------------

preferred_countries = ["Germany", "Austria", "Switzerland", "United Kingdom", "United States", "France", "Italy", "Netherlands"]
preferred_languages = ["German", "English", "Spanish", "French", "Italian", "Dutch"]

# -------------
# Classes
# -------------

class AsyncRestClient:
    domain = "api.dataforseo.com"

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.auth_header = f"Basic {b64encode(f'{username}:{password}'.encode('ascii')).decode('ascii')}"

    async def request(self, path, method, data=None, session=None):
        """Async HTTP request method"""
        url = f"https://{self.domain}{path}"
        headers = {
            'Authorization': self.auth_header,
            'Content-Encoding': 'gzip'
        }

        # Use provided session or create new one
        if session is None:
            async with aiohttp.ClientSession() as session:
                return await self._make_request(session, url, method, headers, data)
        else:
            return await self._make_request(session, url, method, headers, data)

    async def _make_request(self, session, url, method, headers, data):
        """Make the actual HTTP request"""
        try:
            if method.upper() == 'GET':
                async with session.get(url, headers=headers) as response:
                    response_text = await response.text()
                    return loads(response_text)
            elif method.upper() == 'POST':
                if isinstance(data, str):
                    data_str = data
                else:
                    data_str = dumps(data)
                async with session.post(url, headers=headers, data=data_str) as response:
                    response_text = await response.text()
                    return loads(response_text)
        except Exception as e:
            return {"status_code": 50000, "status_message": f"Request failed: {str(e)}"}

    async def get(self, path, session=None):
        return await self.request(path, 'GET', session=session)

    async def post(self, path, data, session=None):
        return await self.request(path, 'POST', data, session=session)

# Legacy RestClient for backward compatibility
class RestClient:
    domain = "api.dataforseo.com"

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def request(self, path, method, data=None):
        connection = HTTPSConnection(self.domain)
        try:
            base64_bytes = b64encode(
                ("%s:%s" % (self.username, self.password)).encode("ascii")
                ).decode("ascii")
            headers = {'Authorization' : 'Basic %s' %  base64_bytes, 'Content-Encoding' : 'gzip'}
            connection.request(method, path, headers=headers, body=data)
            response = connection.getresponse()
            return loads(response.read().decode())
        finally:
            connection.close()

    def get(self, path):
        return self.request(path, 'GET')

    def post(self, path, data):
        if isinstance(data, str):
            data_str = data
        else:
            data_str = dumps(data)
        return self.request(path, 'POST', data_str)


# -------------
# Streamlit App Configuration
# -------------
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
st.logo("https://www.claneo.com/wp-content/uploads/Element-4.svg")
markdown_file_path = os.path.join(parent_dir, 'information', 'Keywords', 'README.md')
set_page_config(
    page_title="Keywords",
    page_icon="🔑",
    layout="wide",
    menu_items={
        'Get Help': 'https://www.linkedin.com/in/kirchhoff-kevin/',
        'About': "This is an app for keyword analysis and SERP features."
    }
)

def setup_streamlit():
    st.title("🔑 Get Keyword Data")
    with st.expander("Before using this app"):
        st.markdown(read_markdown_file(markdown_file_path))


# Use the new authentication utility
name, authentication_status, username = handle_authentication()

# Check the authentication status
if authentication_status:
    def setup_database():
        """Setup the database with updated schema"""
        try:
            # Create database directory with proper permissions
            db_dir = os.path.join('.streamlit', 'database')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, 'tasks.db')

            # Check if we can write to the directory
            test_file = os.path.join(db_dir, 'test_write.tmp')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
            except (IOError, OSError) as e:
                st.error(f"Cannot write to database directory: {str(e)}")
                return None

            conn = None
            try:
                # Add timeout to handle locked database
                conn = sqlite3.connect(db_path, timeout=20)
                c = conn.cursor()

                # Enable foreign keys and set journal mode to WAL for better concurrency
                c.execute("PRAGMA foreign_keys = ON")
                c.execute("PRAGMA journal_mode = WAL")

                # Create tasks table if it doesn't exist first
                c.execute('''CREATE TABLE IF NOT EXISTS tasks
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
                             competitors TEXT,  -- JSON array of competitors
                             search_volume_task_ids TEXT,  -- JSON array of task IDs
                             search_volume_results TEXT,    -- JSON results when completed
                             serp_task_ids TEXT,           -- JSON array of task IDs
                             serp_results TEXT,            -- JSON results when completed
                             processed_sv_tasks TEXT,      -- JSON array of processed SV task IDs
                             processed_serp_tasks TEXT,    -- JSON array of processed SERP task IDs
                             status TEXT DEFAULT 'pending',
                             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                             completed_at TIMESTAMP,
                             error_messages TEXT,          -- JSON array of error messages
                             export_language TEXT DEFAULT 'German',
                             UNIQUE(username, task_id))''')
                conn.commit()

                # Check if search_volume_results table exists and has foreign keys
                try:
                    c.execute("PRAGMA foreign_key_list(search_volume_results)")
                    foreign_keys = c.fetchall()
                    if foreign_keys:
                        # Table exists with foreign keys - backup data and recreate
                        c.execute("SELECT * FROM search_volume_results")
                        sv_data = c.fetchall()
                        c.execute("DROP TABLE search_volume_results")
                        c.execute('''CREATE TABLE search_volume_results
                                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                     task_id TEXT NOT NULL,
                                     results TEXT NOT NULL,
                                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                        # Restore data
                        for row in sv_data:
                            c.execute("INSERT INTO search_volume_results (task_id, results, created_at, updated_at) VALUES (?, ?, ?, ?)",
                                    (row[1], row[2], row[3], row[4]))
                except sqlite3.OperationalError:
                    # Table doesn't exist - create it
                    c.execute('''CREATE TABLE IF NOT EXISTS search_volume_results
                                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 task_id TEXT NOT NULL,
                                 results TEXT NOT NULL,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

                # Check if serp_results table exists and has foreign keys
                try:
                    c.execute("PRAGMA foreign_key_list(serp_results)")
                    foreign_keys = c.fetchall()
                    if foreign_keys:
                        # Table exists with foreign keys - backup data and recreate
                        c.execute("SELECT * FROM serp_results")
                        serp_data = c.fetchall()
                        c.execute("DROP TABLE serp_results")
                        c.execute('''CREATE TABLE serp_results
                                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                     task_id TEXT NOT NULL,
                                     results TEXT NOT NULL,
                                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                        # Restore data
                        for row in serp_data:
                            c.execute("INSERT INTO serp_results (task_id, results, created_at, updated_at) VALUES (?, ?, ?, ?)",
                                    (row[1], row[2], row[3], row[4]))
                except sqlite3.OperationalError:
                    # Table doesn't exist - create it
                    c.execute('''CREATE TABLE IF NOT EXISTS serp_results
                                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 task_id TEXT NOT NULL,
                                 results TEXT NOT NULL,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

                conn.commit()
                # Check if task_type column exists
                try:
                    c.execute("SELECT task_type FROM tasks LIMIT 1")
                except sqlite3.OperationalError:
                    # Add task_type column with default value
                    c.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT DEFAULT 'rankings_and_search_volume'")
                    # Update existing rows to have the default value
                    c.execute("UPDATE tasks SET task_type = 'rankings_and_search_volume' WHERE task_type IS NULL")
                    conn.commit()
                    st.success("Database schema updated with task_type column")

                # Check if check_seasonality column exists
                try:
                    c.execute("SELECT check_seasonality FROM tasks LIMIT 1")
                except sqlite3.OperationalError:
                    c.execute("ALTER TABLE tasks ADD COLUMN check_seasonality BOOLEAN DEFAULT 0")
                    conn.commit()
                    st.success("Database schema updated with check_seasonality column")

                # Check if check_ai_overviews column exists
                try:
                    c.execute("SELECT check_ai_overviews FROM tasks LIMIT 1")
                except sqlite3.OperationalError:
                    c.execute("ALTER TABLE tasks ADD COLUMN check_ai_overviews BOOLEAN DEFAULT 0")
                    conn.commit()
                    st.success("Database schema updated with check_ai_overviews column")

                # Check if competitors column exists
                try:
                    c.execute("SELECT competitors FROM tasks LIMIT 1")
                except sqlite3.OperationalError:
                    c.execute("ALTER TABLE tasks ADD COLUMN competitors TEXT")
                    conn.commit()
                    st.success("Database schema updated with competitors column")

                # Check if export_language column exists
                try:
                    c.execute("SELECT export_language FROM tasks LIMIT 1")
                except sqlite3.OperationalError:
                    c.execute("ALTER TABLE tasks ADD COLUMN export_language TEXT DEFAULT 'German'")
                    conn.commit()
                    st.success("Database schema updated with export_language column")

                # Check if processed tasks columns exist
                try:
                    c.execute("SELECT processed_sv_tasks FROM tasks LIMIT 1")
                except sqlite3.OperationalError:
                    c.execute("ALTER TABLE tasks ADD COLUMN processed_sv_tasks TEXT")
                    c.execute("ALTER TABLE tasks ADD COLUMN processed_serp_tasks TEXT")
                    conn.commit()
                    st.success("Database schema updated with processed tasks columns")

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
        """Get a database connection with proper timeout and WAL mode"""
        try:
            db_path = os.path.join('.streamlit', 'database', 'tasks.db')
            # Ensure the database directory exists
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

            # Add timeout to handle locked database
            conn = sqlite3.connect(db_path, timeout=20)
            c = conn.cursor()

            # Enable foreign keys and set journal mode to WAL for better concurrency
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("PRAGMA journal_mode = WAL")

            return conn
        except Exception as e:
            st.error(f"Failed to connect to database: {str(e)}")
            return None

    def save_task(username, task_id, domain, keywords, country, language, device, sv_task_ids=None, serp_task_ids=None, task_type='rankings_and_search_volume', check_seasonality=False, check_ai_overviews=False, competitors=None, export_language='German'):
        """Save a new task to the database"""
        conn = get_db_connection()
        try:
            c = conn.cursor()

            c.execute('''INSERT INTO tasks
                        (username, task_id, domain, task_type, keywords, country, language, device,
                         check_seasonality, check_ai_overviews, competitors, search_volume_task_ids, serp_task_ids, export_language)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (username, task_id, domain, task_type, keywords, country, language, device,
                         check_seasonality,
                         check_ai_overviews,
                         json.dumps(competitors) if competitors else None,
                         json.dumps(sv_task_ids) if sv_task_ids else None,
                         json.dumps(serp_task_ids) if serp_task_ids else None,
                         export_language))

            # Create empty entries in results tables based on task type
            if task_type in ['rankings_and_search_volume', 'search_volume_only']:
                # Only create search_volume_results for tasks that need search volume
                c.execute('''INSERT INTO search_volume_results (task_id, results)
                            VALUES (?, ?)''', (task_id, json.dumps([])))

            if task_type in ['rankings_and_search_volume', 'rankings_only']:
                # Only create serp_results for tasks that need SERP data
                c.execute('''INSERT INTO serp_results (task_id, results)
                            VALUES (?, ?)''', (task_id, json.dumps([])))

            conn.commit()

            # Verify the insert
            c.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
            result = c.fetchone()
            return bool(result)

        except sqlite3.Error as e:
            st.error(f"Database error: {str(e)}")
            return False
        finally:
            conn.close()

    def get_user_tasks(username):
        """Get all tasks for a user"""
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute('''SELECT * FROM tasks
                        WHERE username = ?
                        ORDER BY created_at DESC''', (username,))
            columns = [description[0] for description in c.description]
            tasks = [dict(zip(columns, row)) for row in c.fetchall()]
            return tasks
        except sqlite3.Error as e:
            st.error(f"Error retrieving tasks: {str(e)}")
            return []
        finally:
            conn.close()

    def update_task_status(task_id, status, task_data=None):
        """Update task status and optionally store task data with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            conn = get_db_connection()
            try:
                c = conn.cursor()
                if task_data:
                    # Check if we're updating task IDs (initial task creation) or results
                    if 'sv_task_ids' in task_data or 'serp_task_ids' in task_data:
                        # Updating task IDs (initial task creation)
                        c.execute('''UPDATE tasks
                                    SET status = ?,
                                        search_volume_task_ids = ?,
                                        serp_task_ids = ?,
                                        completed_at = CURRENT_TIMESTAMP
                                    WHERE task_id = ?''',
                                    (status,
                                     json.dumps(task_data.get('sv_task_ids', [])),
                                     json.dumps(task_data.get('serp_task_ids', [])),
                                     task_id))
                    else:
                        # Updating results (partial or complete) - save to separate tables
                        c.execute('''UPDATE tasks
                                    SET status = ?,
                                        completed_at = CURRENT_TIMESTAMP
                                    WHERE task_id = ?''',
                                    (status, task_id))

                        # Save search volume results to separate table (inline to avoid multiple connections)
                        if 'search_volume_results' in task_data:
                            print(f"🔍 DEBUG: update_task_status - Speichere search_volume_results für task_id: {task_id}")
                            try:
                                # Temporarily disable foreign key constraints
                                c.execute('PRAGMA foreign_keys = OFF')

                                # Update existing record (entry was created during task creation)
                                c.execute('''UPDATE search_volume_results SET results = ? WHERE task_id = ?''',
                                        (json.dumps(task_data['search_volume_results']), task_id))

                                # Keep foreign keys disabled for now
                                # c.execute('PRAGMA foreign_keys = ON')

                                print("✅ DEBUG: search_volume_results erfolgreich gespeichert")
                            except sqlite3.Error as e:
                                print(f"❌ DEBUG: Fehler beim Speichern von search_volume_results: {str(e)}")
                                st.error(f"Error saving search volume results: {str(e)}")

                        # Save SERP results to separate table (inline to avoid multiple connections)
                        if 'serp_results' in task_data:
                            print(f"🔍 DEBUG: update_task_status - Speichere serp_results für task_id: {task_id}")
                            try:
                                # Temporarily disable foreign key constraints
                                c.execute('PRAGMA foreign_keys = OFF')

                                # Update existing record (entry was created during task creation)
                                c.execute('''UPDATE serp_results SET results = ? WHERE task_id = ?''',
                                        (json.dumps(task_data['serp_results']), task_id))

                                # Keep foreign keys disabled for now
                                # c.execute('PRAGMA foreign_keys = ON')

                                print("✅ DEBUG: serp_results erfolgreich gespeichert")
                            except sqlite3.Error as e:
                                print(f"❌ DEBUG: Fehler beim Speichern von serp_results: {str(e)}")
                                st.error(f"Error saving SERP results: {str(e)}")
                else:
                    c.execute('''UPDATE tasks
                                SET status = ?
                                WHERE task_id = ?''', (status, task_id))

                conn.commit()

                # Verify the update
                c.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
                result = c.fetchone()
                if result:
                    return True
                return False

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
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

    def custom_sort(all_items, preferred_items):
        sorted_items = preferred_items + ["_____________"] + [item for item in all_items if item not in preferred_items]
        return sorted_items

    def setup_tracking_folder():
        # parent_dir is defined globally and points to the project root.
        tracking_dir = os.path.join(parent_dir, '.streamlit', 'tracking')
        os.makedirs(tracking_dir, exist_ok=True)
        return tracking_dir

    def log_usage(username: str, tool_name: str = "Keywords"):
        tracking_dir = setup_tracking_folder()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tool_name = "Keywords"

        usage_data = [timestamp, username, tool_name]

        usage_file = os.path.join(tracking_dir, 'tool_usage.csv')

        file_exists = os.path.isfile(usage_file)

        with open(usage_file, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Username', 'Tool Name'])
            writer.writerow(usage_data)

    def generate_task_id(domain):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{domain.replace('.', '_')}_{timestamp}"

    def clean_keyword(keyword):
        if not isinstance(keyword, str):
            return keyword

        # Remove commas (automatic removal and ignore)
        cleaned = keyword.replace(',', '')

        # Remove site: and search: operators
        cleaned = re.sub(r'(site|search):', '', cleaned)

        # Strip whitespace and convert to lowercase for consistency
        cleaned = cleaned.strip().lower()

        return cleaned

    def clean_keyword_for_search_volume(keyword):
        """Clean keyword specifically for search volume API by removing question marks"""
        if not isinstance(keyword, str):
            return keyword

        # Remove commas (automatic removal and ignore)
        cleaned = keyword.replace(',', '')

        # Remove invalid symbols for search volume API (including comma)
        invalid_symbols = r'[,!@%^()={};\~`<>?\\|―]'
        cleaned = re.sub(invalid_symbols, '', cleaned)

        # Remove site: and search: operators
        cleaned = re.sub(r'(site|search):', '', cleaned)

        # Strip whitespace and convert to lowercase for consistency
        cleaned = cleaned.strip().lower()

        return cleaned


    def clean_keyword_for_serp(keyword):
        """Clean keyword specifically for SERP API - all symbols are allowed"""
        if not isinstance(keyword, str):
            return keyword

        # Remove commas (automatic removal and ignore)
        cleaned = keyword.replace(',', '')

        # Remove site: and search: operators
        cleaned = re.sub(r'(site|search):', '', cleaned)

        # Strip whitespace and convert to lowercase for consistency
        cleaned = cleaned.strip().lower()

        return cleaned

    async def get_search_volume_async(df_chunk, _client, country_name, language_name, device, check_seasonality, session=None):
        """
        Creates search volume tasks for a chunk of keywords (up to 1000) - Async version
        Returns: List of task IDs from DataForSEO
        """
        # Clean keywords specifically for search volume API
        df_chunk_copy = df_chunk.copy()
        original_keywords = df_chunk_copy[df_chunk_copy.columns[0]].tolist()

        df_chunk_copy[df_chunk_copy.columns[0]] = df_chunk_copy[df_chunk_copy.columns[0]].apply(clean_keyword_for_search_volume)

        keywords_list = df_chunk_copy[df_chunk_copy.columns[0]].to_list()

        post_data = [{
            "location_name": country_name,
            "language_name": language_name,
            "keywords": keywords_list,
            "device": device
        }]

        try:
            response = await _client.post("/v3/keywords_data/google_ads/search_volume/task_post", post_data, session=session)

            if response["status_code"] == 20000:
                task_ids = []
                for task in response["tasks"]:
                    if task.get("status_code") in [20000, 20100]:  # Include both success codes
                        task_ids.append(task["id"])
                    else:
                        # Log task-level errors
                        error_msg = f"Search volume task failed: Status {task.get('status_code')} - {task.get('status_message')} for keywords: {keywords_list}"
                        st.error(error_msg)
                        return [], [error_msg]

                if task_ids:
                    return task_ids, []
                else:
                    return [], [f"No task IDs were returned for keywords: {keywords_list}"]
            else:
                error_msg = f"API Error: {response.get('status_message')} for keywords: {keywords_list}"
                st.error(error_msg)
                return [], [error_msg]

        except Exception as e:
            error_msg = f"Exception during task creation: {str(e)}"
            st.error(error_msg)
            return [], [error_msg]

    @st.cache_data
    def get_search_volume(df_chunk, _client, country_name, language_name, device, check_seasonality):
        """
        Creates search volume tasks for a chunk of keywords (up to 1000) - Sync wrapper
        Returns: List of task IDs from DataForSEO
        """
        # For backward compatibility, run async function in sync context
        return asyncio.run(get_search_volume_async(df_chunk, _client, country_name, language_name, device, check_seasonality))

    def optimize_serp_results(serp_results, check_ai_overviews=False, domain=None, competitors=None):
        """
        Optimiert die SERP-Ergebnisse für die Speicherung, behält nur die wichtigen Felder.
        Behält AI Overview Daten wenn check_ai_overviews=True ist.
        Berechnet Rankings für Domain und Competitors wenn angegeben.
        """
        optimized_results = []

        for result in serp_results:
            if not isinstance(result, dict):
                continue

            # Wichtige Felder behalten, aber items und item_types für die Verarbeitung beibehalten
            optimized_result = {
                'keyword': result.get('keyword', ''),
                'items': result.get('items', []),  # Wichtig für process_serp_results
                'item_types': result.get('item_types', []),  # Wichtig für SERP Features
                'search_volume': result.get('search_volume')
            }

            # Berechne Rankings für Domain und Competitors wenn angegeben
            if domain:
                # Analysiere alle organischen Ergebnisse für Top 20 Ranking-Berechnung
                all_organic_items = [item for item in result.get('items', []) if isinstance(item, dict) and item.get('type') == 'organic']

                # Domain-Information extrahieren
                domain_parts = tldextract.extract(domain)
                domain_name_only = f"{domain_parts.domain}.{domain_parts.suffix}"

                # Competitors bereinigen (optional)
                cleaned_competitors = []
                if competitors:
                    for comp in competitors:
                        comp_parts = tldextract.extract(comp)
                        comp_domain = f"{comp_parts.domain}.{comp_parts.suffix}"
                        cleaned_competitors.append(comp_domain)

                # Rankings berechnen
                own_ranking = None
                own_ranking_url = None
                competitor_rankings = {comp: None for comp in cleaned_competitors}
                competitor_urls = {comp: None for comp in cleaned_competitors}

                # Durchlaufe alle verfügbaren organischen Ergebnisse
                for i, item in enumerate(all_organic_items):
                    try:
                        url = item.get('url', '')
                        extracted = tldextract.extract(url)
                        if hasattr(extracted, 'top_domain_under_public_suffix'):
                            result_domain = extracted.top_domain_under_public_suffix
                        else:
                            result_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.domain and extracted.suffix else url

                        # Prüfe eigene Domain
                        if result_domain == domain_name_only and own_ranking is None:
                            own_ranking = i + 1  # Position 1-100
                            own_ranking_url = url

                        # Prüfe Competitors
                        for competitor_domain in cleaned_competitors:
                            if result_domain == competitor_domain and competitor_rankings[competitor_domain] is None:
                                competitor_rankings[competitor_domain] = i + 1  # Position 1-100
                                competitor_urls[competitor_domain] = url
                    except Exception:
                        continue

                # Speichere Rankings und URLs in optimized_result
                optimized_result['own_ranking'] = own_ranking
                optimized_result['own_ranking_url'] = own_ranking_url
                optimized_result['competitor_rankings'] = competitor_rankings
                optimized_result['competitor_urls'] = competitor_urls

                # Berechne in_top für Competitors (vereinfacht ohne max_results)
                competitor_in_top = {}
                for comp_domain, comp_ranking in competitor_rankings.items():
                    competitor_in_top[comp_domain] = comp_ranking is not None
                optimized_result['competitor_in_top'] = competitor_in_top

                # in_top = true nur wenn eigene Domain gefunden wurde
                optimized_result['in_top'] = own_ranking is not None

            # Berechne und speichere Ranking-Positionen für alle organischen Ergebnisse
            all_organic_items = [item for item in result.get('items', []) if isinstance(item, dict) and item.get('type') == 'organic']
            for i, organic_item in enumerate(all_organic_items, 1):
                organic_item['ranking_position'] = i

            # Keine max_results Logik mehr nötig - nur Datum-basierte Unterscheidung

            # Speichere die ersten 20 organischen Ergebnisse (kompatibel mit Migration-Script)
            top_20_organic = all_organic_items[:20]

            # Sammle alle Competitor-Items (auch außerhalb Top 20)
            competitor_items = []
            if domain:
                domain_parts = tldextract.extract(domain)
                domain_name_only = f"{domain_parts.domain}.{domain_parts.suffix}"

                cleaned_competitors = []
                if competitors:
                    for comp in competitors:
                        comp_parts = tldextract.extract(comp)
                        comp_domain = f"{comp_parts.domain}.{comp_parts.suffix}"
                        cleaned_competitors.append(comp_domain)

                # Finde alle Competitor-Items (auch außerhalb Top 20)
                for item in all_organic_items:
                    item_url = item.get('url', '')
                    if item_url:
                        # Prüfe eigene Domain
                        if domain_name_only in item_url:
                            competitor_items.append(item)

                        # Prüfe Competitors
                        for comp_domain in cleaned_competitors:
                            if comp_domain in item_url:
                                competitor_items.append(item)
                                break  # Nur einmal hinzufügen

            # Entferne Duplikate (Items die bereits in Top 20 sind)
            competitor_items_unique = []
            top_20_urls = {item.get('url', '') for item in top_20_organic}
            for item in competitor_items:
                if item.get('url', '') not in top_20_urls:
                    competitor_items_unique.append(item)

            # Behalte alle anderen SERP-Features (Ads, Featured Snippets, PAA, AI Overviews, etc.)
            non_organic_items = [item for item in result.get('items', []) if isinstance(item, dict) and item.get('type') != 'organic']

            # Kombiniere: Top 20 organische + Competitor-Items + alle anderen SERP-Features
            optimized_result['items'] = top_20_organic + competitor_items_unique + non_organic_items

            # Debug: Zeige Anzahl der verschiedenen Ergebnisse
            original_organic_count = len(all_organic_items)
            total_saved_items = len(top_20_organic) + len(competitor_items_unique) + len(non_organic_items)

            if original_organic_count > 20 or competitor_items_unique:
                ranking_info = ""
                competitor_info = ""
                if domain:
                    if optimized_result.get('own_ranking'):
                        ranking_info += f" | Own: #{optimized_result['own_ranking']}"
                    for comp, rank in optimized_result.get('competitor_rankings', {}).items():
                        if rank:
                            ranking_info += f" | {comp}: #{rank}"

                if competitor_items_unique:
                    competitor_info = f" + {len(competitor_items_unique)} Competitor-Items"

                own_ranking = optimized_result.get('own_ranking')
                domain_status = f"Position #{own_ranking}" if own_ranking else "nicht gefunden"

                # Competitor in_top_100 Status
                competitor_top_100_info = ""
                if optimized_result.get('competitor_in_top_100'):
                    for comp, in_top_100 in optimized_result['competitor_in_top_100'].items():
                        status = "✅" if in_top_100 else "❌"
                        competitor_top_100_info += f" | {comp}: {status}"

                print(f"🔍 Keyword '{result.get('keyword', '')}': {original_organic_count} organische → {total_saved_items} Items gespeichert (Top 20{competitor_info}) + Rankings{ranking_info} + in_top_100={optimized_result['in_top_100']} (eigene Domain: {domain_status}){competitor_top_100_info}")

            # Behalte alle ursprünglichen item_types für SERP-Funktionen Spalte
            optimized_result['item_types'] = result.get('item_types', [])

            # Optimiere die items, behalte nur die notwendigen Felder
            if optimized_result['items']:
                optimized_items = []
                for item in optimized_result['items']:
                    if isinstance(item, dict):
                        # Basis-Felder für Rankings und Features
                        optimized_item = {
                            'type': item.get('type', ''),
                            'url': item.get('url', ''),
                            'title': item.get('title', ''),
                            'snippet': item.get('snippet', ''),
                            'rank_group': item.get('rank_group'),
                            'rank_absolute': item.get('rank_absolute'),
                            'ranking_position': item.get('ranking_position')  # Neue Ranking-Position
                        }

                        # AI Overview spezifische Felder hinzufügen wenn aktiviert
                        if check_ai_overviews and item.get('type') == 'ai_overview':
                            # Behalte alle AI Overview relevanten Felder
                            optimized_item.update({
                                'asynchronous_ai_overview': item.get('asynchronous_ai_overview', False),
                                'references': item.get('references', [])
                            })

                            # Behalte AI Overview Elemente mit allen Details
                            if item.get('items'):
                                optimized_item['items'] = []
                                for overview_item in item.get('items', []):
                                    if isinstance(overview_item, dict) and overview_item.get('type') == 'ai_overview_element':
                                        optimized_overview_item = {
                                            'type': overview_item.get('type', ''),
                                            'title': overview_item.get('title', ''),
                                            'text': overview_item.get('text', ''),
                                            'references': overview_item.get('references', [])
                                        }
                                        optimized_item['items'].append(optimized_overview_item)

                        # PAA (People Also Ask) Felder für Features
                        elif item.get('type') == 'people_also_ask' and item.get('items'):
                            optimized_item['items'] = []
                            for paa_item in item.get('items', []):
                                if isinstance(paa_item, dict):
                                    optimized_paa_item = {
                                        'type': paa_item.get('type', ''),
                                        'title': paa_item.get('title', ''),
                                        'url': paa_item.get('url', '')
                                    }
                                    optimized_item['items'].append(optimized_paa_item)

                        optimized_items.append(optimized_item)
                optimized_result['items'] = optimized_items

            optimized_results.append(optimized_result)

        return optimized_results

    async def check_tasks_ready_async(_client, sv_task_ids, serp_task_ids, processed_sv_tasks=None, processed_serp_tasks=None, session=None, check_ai_overviews=False, domain=None, competitors=None):
        """
        Gets results directly from get endpoint, only for tasks that haven't been processed yet. - Async version
        Returns: Tuple of (is_ready, errors, results, processed_sv_tasks, processed_serp_tasks)
        """
        if not sv_task_ids and not serp_task_ids:
            return False, ["No task IDs provided"], None, set(), set()

        errors = []
        all_results = {"sv_results": [], "serp_results": []}
        processed_sv_tasks = processed_sv_tasks or set()
        processed_serp_tasks = processed_serp_tasks or set()

        # Process search volume tasks concurrently
        if sv_task_ids:
            try:
                # Create tasks for concurrent processing
                sv_tasks = []
                for task_id in sv_task_ids:
                    if task_id not in processed_sv_tasks:
                        sv_tasks.append(_client.get(f"/v3/keywords_data/google_ads/search_volume/task_get/{task_id}", session=session))

                # Execute all search volume tasks concurrently
                if sv_tasks:
                    sv_results = await asyncio.gather(*sv_tasks, return_exceptions=True)

                    for i, task_result in enumerate(sv_results):
                        task_id = sv_task_ids[i]
                        if isinstance(task_result, Exception):
                            errors.append(f"Error getting search volume results for task {task_id}: {str(task_result)}")
                            processed_sv_tasks.add(task_id)
                            continue

                        if task_result['status_code'] == 20000:
                            task_data = task_result['tasks'][0]
                            if task_data.get('result'):
                                # Debug: Log the structure of the result
                                print(f"DEBUG: Search volume task {task_id} result structure: {type(task_data['result'])}, length: {len(task_data['result']) if hasattr(task_data['result'], '__len__') else 'N/A'}")
                                if task_data['result']:
                                    print(f"DEBUG: First result item: {task_data['result'][0] if task_data['result'] else 'Empty'}")

                                for keyword_data in task_data['result']:
                                    print(f"DEBUG: Processing keyword data: {keyword_data.get('keyword', 'NO_KEYWORD')} with search volume: {keyword_data.get('search_volume', 'NO_SV')}")
                                    all_results["sv_results"].append({
                                        'keyword': keyword_data['keyword'],
                                        'search_volume': keyword_data.get('search_volume', 0),
                                        'competition': keyword_data.get('competition'),
                                        'cpc': keyword_data.get('cpc'),
                                        'low_top_of_page_bid': keyword_data.get('low_top_of_page_bid'),
                                        'high_top_of_page_bid': keyword_data.get('high_top_of_page_bid'),
                                        'monthly_searches': keyword_data.get('monthly_searches', [])
                                    })
                                processed_sv_tasks.add(task_id)
                            else:
                                # Task completed but no results - this might be an issue
                                errors.append(f"Search volume task {task_id} completed but returned no results. Task data: {task_data}")
                                processed_sv_tasks.add(task_id)  # Mark as processed to avoid checking again
                        elif task_result['status_code'] == 40602:
                            # Task is still in queue - this is normal, not an error
                            pass  # Don't add to processed tasks, will check again next time
                        else:
                            errors.append(f"Failed to get search volume results for task {task_id}: Status {task_result.get('status_code')} - {task_result.get('status_message', 'Unknown error')}")
                            processed_sv_tasks.add(task_id)  # Mark as processed to avoid checking again

            except Exception as e:
                errors.append(f"Error processing search volume tasks: {str(e)}")

        # Process SERP tasks concurrently
        if serp_task_ids:
            try:
                # Create tasks for concurrent processing
                serp_tasks = []
                for task_id in serp_task_ids:
                    if task_id not in processed_serp_tasks:
                        serp_tasks.append(_client.get(f"/v3/serp/google/organic/task_get/advanced/{task_id}", session=session))

                # Execute all SERP tasks concurrently
                if serp_tasks:
                    serp_results = await asyncio.gather(*serp_tasks, return_exceptions=True)

                    for i, task_result in enumerate(serp_results):
                        task_id = serp_task_ids[i]
                        if isinstance(task_result, Exception):
                            errors.append(f"Error getting SERP results for task {task_id}: {str(task_result)}")
                            processed_serp_tasks.add(task_id)
                            continue

                        if task_result['status_code'] == 20000:
                            task_data = task_result['tasks'][0]
                            if task_data.get('result'):
                                # Optimiere die SERP-Ergebnisse vor dem Speichern
                                optimized_results = optimize_serp_results(task_data['result'], check_ai_overviews, domain, competitors)
                                all_results["serp_results"].extend(optimized_results)
                                processed_serp_tasks.add(task_id)
                            else:
                                # Task completed but no results - this might be an issue
                                errors.append(f"SERP task {task_id} completed but returned no results. Task data: {task_data}")
                                processed_serp_tasks.add(task_id)  # Mark as processed to avoid checking again
                        elif task_result['status_code'] == 40602:
                            # Task is still in queue - this is normal, not an error
                            pass  # Don't add to processed tasks, will check again next time
                        else:
                            errors.append(f"Failed to get SERP results for task {task_id}: Status {task_result.get('status_code')} - {task_result.get('status_message', 'Unknown error')}")
                            processed_serp_tasks.add(task_id)  # Mark as processed to avoid checking again

            except Exception as e:
                errors.append(f"Error processing SERP tasks: {str(e)}")

        # Check if all tasks have been processed
        all_sv_processed = len(processed_sv_tasks) == len(sv_task_ids) if sv_task_ids else True
        all_serp_processed = len(processed_serp_tasks) == len(serp_task_ids) if serp_task_ids else True

        # Add informative notification if not all tasks are processed
        if not (all_sv_processed and all_serp_processed):
            pending_sv = len(sv_task_ids) - len(processed_sv_tasks) if sv_task_ids else 0
            pending_serp = len(serp_task_ids) - len(processed_serp_tasks) if serp_task_ids else 0

            if pending_sv > 0 and pending_serp > 0:
                errors.append(f"Tasks still in progress: {pending_sv} search volume tasks and {pending_serp} SERP tasks are still in queue. Please check again in 2 minutes.")
            elif pending_sv > 0:
                errors.append(f"Tasks still in progress: {pending_sv} search volume tasks are still in queue. Please check again in 2 minutes.")
            elif pending_serp > 0:
                errors.append(f"Tasks still in progress: {pending_serp} SERP tasks are still in queue. Please check again in 2 minutes.")

        # Additional check: For rankings_and_search_volume tasks, we should have both types of results
        # unless one type explicitly failed
        is_ready = all_sv_processed and all_serp_processed

        # Add warning if we're missing expected results
        if is_ready and sv_task_ids and not all_results["sv_results"]:
            errors.append("Warning: Search volume tasks completed but returned no results. This may indicate an issue with the keywords or API.")
        if is_ready and serp_task_ids and not all_results["serp_results"]:
            errors.append("Warning: SERP tasks completed but returned no results. This may indicate an issue with the keywords or API.")



        return is_ready, errors, all_results, processed_sv_tasks, processed_serp_tasks

    @st.cache_data
    def check_tasks_ready(_client, sv_task_ids, serp_task_ids, processed_sv_tasks=None, processed_serp_tasks=None):
        """
        Gets results directly from get endpoint, only for tasks that haven't been processed yet. - Sync wrapper
        Returns: Tuple of (is_ready, errors, results, processed_sv_tasks, processed_serp_tasks)
        """
        # For backward compatibility, run async function in sync context
        return asyncio.run(check_tasks_ready_async(_client, sv_task_ids, serp_task_ids, processed_sv_tasks, processed_serp_tasks, check_ai_overviews=False))

    def text_to_df(text, column_name):
        items = [item.strip() for item in re.split(r',|\n', text) if item.strip()]
        df = pd.DataFrame(items, columns=[column_name])
        return df

    async def get_ranking_positions_async(_client, df_chunk, country, language, device, check_ai_overviews=False, session=None):
        """
        Creates SERP tasks for each keyword (max 100 pro API-Call) - Async version
        Returns: List of task IDs from DataForSEO
        """
        # Clean keywords specifically for SERP API
        df_chunk_copy = df_chunk.copy()
        original_keywords = df_chunk_copy[df_chunk_copy.columns[0]].tolist()

        df_chunk_copy[df_chunk_copy.columns[0]] = df_chunk_copy[df_chunk_copy.columns[0]].apply(clean_keyword_for_serp)

        # Falls df_chunk mehr als 100 Keywords enthält, splitte in 100er-Chunks
        def chunk_list(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        keywords = list(df_chunk_copy[df_chunk_copy.columns[0]])
        all_task_ids = []
        errors = []

        # Create all post data first
        all_post_data = []
        for keyword_chunk in chunk_list(keywords, 100):
            post_data = []
            for keyword in keyword_chunk:
                task_data = {
                    "location_name": country,
                    "language_name": language,
                    "keyword": keyword,
                    "device": device,
                    "depth": 100
                }
                # Add load_async_ai_overview parameter if AI overviews should be checked
                if check_ai_overviews:
                    task_data["load_async_ai_overview"] = True
                post_data.append(task_data)
            all_post_data.append(post_data)

        # Process all chunks concurrently
        try:
            # Create tasks for concurrent processing
            serp_tasks = []
            for post_data in all_post_data:
                serp_tasks.append(_client.post("/v3/serp/google/organic/task_post", post_data, session=session))

            # Execute all SERP tasks concurrently
            if serp_tasks:
                responses = await asyncio.gather(*serp_tasks, return_exceptions=True)

                for response in responses:
                    if isinstance(response, Exception):
                        error_msg = f"Exception during SERP task creation: {str(response)}"
                        errors.append(error_msg)
                        continue

                    if response["status_code"] == 20000:
                        for task in response["tasks"]:
                            if task.get("status_code") in [20000, 20100]:
                                all_task_ids.append(task["id"])
                    else:
                        error_msg = f"API Error: {response.get('status_message')}"
                        errors.append(error_msg)
        except Exception as e:
            error_msg = f"Exception during SERP task creation: {str(e)}"
            errors.append(error_msg)

        if all_task_ids:
            return all_task_ids, errors
        else:
            return [], errors if errors else ["No task IDs were returned"]

    @st.cache_data
    def get_ranking_positions(_client, df_chunk, country, language, device, check_ai_overviews=False):
        """
        Creates SERP tasks for each keyword (max 100 pro API-Call) - Sync wrapper
        Returns: List of task IDs from DataForSEO
        """
        # For backward compatibility, run async function in sync context
        return asyncio.run(get_ranking_positions_async(_client, df_chunk, country, language, device, check_ai_overviews))

    def process_serp_results(serp_results, sv_df_full, domain, competitors, check_ai_overviews=False, export_language='German', check_seasonality=False, rankings_only=False, task_created_at=None):
        """Process SERP results and create report and SERP DataFrames"""

        try:
            # Create a mapping between keywords with and without invalid symbols
            keyword_mapping = {}
            if not sv_df_full.empty:
                # Define invalid symbols that are removed for Search Volume API (including comma)
                invalid_symbols_pattern = r'[,!@%^()={};\~`<>?\\|―]'

                # Create a reverse mapping from cleaned keywords to original keywords
                cleaned_to_original = {}
                for serp_result in serp_results:
                    if serp_result and isinstance(serp_result, dict):
                        keyword_with_symbols = serp_result.get('keyword', '')
                        keyword_with_symbols_cleaned = re.sub(invalid_symbols_pattern, '', keyword_with_symbols)
                        cleaned_to_original[keyword_with_symbols_cleaned] = keyword_with_symbols

                for idx, row in sv_df_full.iterrows():
                    keyword_without_symbols = row.get('keyword', '')
                    # Check if this cleaned keyword exists in our reverse mapping
                    if keyword_without_symbols in cleaned_to_original:
                        original_keyword = cleaned_to_original[keyword_without_symbols]
                        keyword_mapping[original_keyword] = keyword_without_symbols

            domain_parts = tldextract.extract(domain)
            domain_name_only = f"{domain_parts.domain}.{domain_parts.suffix}"

            cleaned_competitors = []
            if competitors:
                for competitor in competitors:
                    if competitor:
                        competitor_parts = tldextract.extract(competitor)
                        cleaned_competitor = f"{competitor_parts.domain}.{competitor_parts.suffix}"
                        cleaned_competitors.append(cleaned_competitor)

            # Determine all unique monthly headers only if seasonality is checked and not rankings_only
            all_monthly_headers = set()
            if check_seasonality and not rankings_only and not sv_df_full.empty and 'monthly_searches' in sv_df_full.columns:
                for _idx, sv_row in sv_df_full.iterrows():
                    try:
                        monthly_list = sv_row.get('monthly_searches')
                        if isinstance(monthly_list, list):
                            for month_data in monthly_list:
                                if isinstance(month_data, dict) and 'year' in month_data and 'month' in month_data:
                                    header = f"{month_data['year']}-{str(month_data['month']).zfill(2)}"
                                    all_monthly_headers.add(header)
                    except Exception as e:
                        continue

            sorted_monthly_headers = sorted(list(all_monthly_headers))

            serp_data_for_df = []
            report_data = []



            for result_item in serp_results:
                try:
                    if not result_item or not isinstance(result_item, dict):
                        continue

                    keyword = result_item.get('keyword', '')
                    items = result_item.get('items', [])



                    if not items:
                        continue

                    # Extract SERP features directly from item_types (much more efficient and reliable)
                    item_types = result_item.get('item_types', [])
                    keyword_features = set(item_types) if item_types else set()
                    # Remove 'organic' from SERP features as it's not a special feature
                    keyword_features.discard('organic')

                    # Initialize report_row for this keyword
                    if rankings_only:
                        report_row = {'keyword': keyword}
                    else:
                        report_row = {'keyword': keyword, 'search_volume': None}

                    # Get SV, monthly, and seasonality data from sv_df_full for this keyword (only if not rankings_only)
                    if not rankings_only and not sv_df_full.empty:
                        # Use the mapping to find the correct keyword without invalid symbols
                        keyword_without_symbols = keyword_mapping.get(keyword, keyword)
                        sv_keyword_data_row = sv_df_full[sv_df_full['keyword'] == keyword_without_symbols]
                        if not sv_keyword_data_row.empty:
                            sv_data = sv_keyword_data_row.iloc[0]
                            report_row['search_volume'] = sv_data.get('search_volume')
                            report_row['competition'] = sv_data.get('competition')
                            report_row['cpc'] = sv_data.get('cpc')

                            # Add monthly search data only if seasonality is checked
                            if check_seasonality:
                                for header in sorted_monthly_headers:
                                    report_row[header] = None

                                monthly_list_for_keyword = sv_data.get('monthly_searches')
                                if isinstance(monthly_list_for_keyword, list):
                                    for month_data_item in monthly_list_for_keyword:
                                        if isinstance(month_data_item, dict) and 'year' in month_data_item and 'month' in month_data_item:
                                            header = f"{month_data_item['year']}-{str(month_data_item['month']).zfill(2)}"
                                            report_row[header] = month_data_item.get('search_volume')

                            # Add seasonality data if present in sv_df_full
                            if 'seasonality' in sv_data:
                                report_row['seasonality'] = sv_data.get('seasonality')
                                report_row['max_sv'] = sv_data.get('max_sv')
                                report_row['min_sv'] = sv_data.get('min_sv') if 'min_sv' in sv_data else None
                                months_max = sv_data.get('months_max_sv')
                                if isinstance(months_max, list):
                                    report_row['months_max_sv'] = str(sorted(months_max))
                                else:
                                    report_row['months_max_sv'] = months_max
                    elif not rankings_only:
                        # No SV data available (but not rankings_only)
                        report_row['search_volume'] = None
                        report_row['competition'] = None
                        report_row['cpc'] = None
                        if check_seasonality:
                            for header in sorted_monthly_headers:
                                report_row[header] = None
                        if 'seasonality' in sv_df_full.columns:
                            report_row['seasonality'] = None
                            report_row['max_sv'] = None
                            report_row['months_max_sv'] = None

                    # Hole gespeicherte Rankings aus den optimierten SERP-Ergebnissen
                    own_ranking = None
                    own_ranking_url = None
                    competitor_rankings = {comp: None for comp in cleaned_competitors}
                    competitor_urls = {comp: None for comp in cleaned_competitors}
                    competitor_in_top_100 = {comp: False for comp in cleaned_competitors}
                    in_top_100 = False

                    # Prüfe ob Rankings bereits in den SERP-Ergebnissen gespeichert sind
                    if isinstance(serp_results, list):
                        for result_item in serp_results:
                            if isinstance(result_item, dict) and result_item.get('keyword') == keyword:
                                # Hole gespeicherte Rankings und URLs
                                own_ranking = result_item.get('own_ranking')
                                own_ranking_url = result_item.get('own_ranking_url')
                                competitor_rankings = result_item.get('competitor_rankings', {})
                                competitor_urls = result_item.get('competitor_urls', {})
                                competitor_in_top_100 = result_item.get('competitor_in_top_100', {})
                                in_top_100 = result_item.get('in_top_100', False)
                                break

                    keyword_features_owned = set()
                    ai_overview_text, ai_sources, ai_source_texts, paa_questions = [], [], [], []
                    ai_overview_async = False
                    organic_result_count = 0

                    # Track URLs for each feature type to determine ownership
                    feature_urls = {}


                    for item in items:
                        try:
                            if not item or not isinstance(item, dict):
                                continue

                            item_type = item.get("type")
                            if not item_type:
                                continue


                            if item_type == "organic":
                                organic_result_count += 1


                                try:
                                    url = item.get("url", "")
                                    extracted = tldextract.extract(url)
                                    # Handle different tldextract versions
                                    if hasattr(extracted, 'top_domain_under_public_suffix'):
                                        result_domain = extracted.top_domain_under_public_suffix
                                    elif hasattr(extracted, 'registered_domain'):
                                        result_domain = extracted.registered_domain
                                    else:
                                        # Fallback: construct domain manually
                                        result_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.domain and extracted.suffix else url

                                    # Truncate URL for Excel compatibility
                                    truncated_url = url[:200] + "..." if len(url) > 200 else url

                                    # Get search volume safely
                                    search_volume_value = report_row.get('search_volume') if 'search_volume' in report_row else None

                                    serp_entry = {
                                        'keyword': keyword,
                                        'search_volume': search_volume_value,
                                        'position': organic_result_count,
                                        'position_with_serp-features': item.get("rank_absolute"),
                                        'url': truncated_url
                                    }

                                    serp_data_for_df.append(serp_entry)

                                except Exception as organic_error:
                                    continue
                                # Rankings und URLs werden bereits aus optimierten SERP-Ergebnissen gelesen
                                # Keine zusätzliche URL-Berechnung mehr nötig
                                if organic_result_count >= 100:
                                    break
                            elif item_type == "people_also_ask":
                                for paa_item in item.get("items", []):
                                    if paa_item.get("type") == "people_also_ask_element":
                                        question = paa_item.get("title", "")
                                        if question:
                                            paa_questions.append(question)
                                        # Track URL for ownership check
                                        if paa_item.get("url"):
                                            if item_type not in feature_urls:
                                                feature_urls[item_type] = []
                                            feature_urls[item_type].append(paa_item.get("url"))
                            elif item_type == "ai_overview" and check_ai_overviews:

                                # Check if this is an asynchronous AI overview
                                ai_overview_async = item.get("asynchronous_ai_overview", False)

                                # Track processed URLs to avoid duplicates
                                processed_urls = set()

                                # Extract text from AI overview elements
                                for overview_item in item.get("items", []):
                                    if overview_item.get("type") == "ai_overview_element":
                                        if overview_item.get("title"):
                                            ai_overview_text.append(overview_item["title"])
                                        if overview_item.get("text"):
                                            ai_overview_text.append(overview_item["text"])

                                        # Extract references from each element
                                        if overview_item.get("references"):
                                            for ref in overview_item.get("references", []):
                                                if ref and ref.get("type") == "ai_overview_reference":
                                                    url = ref.get("url")
                                                    if url and url not in processed_urls:
                                                        ai_sources.append(url)
                                                        processed_urls.add(url)

                                                        # Track URL for ownership check
                                                        if item_type not in feature_urls:
                                                            feature_urls[item_type] = []
                                                        feature_urls[item_type].append(url)

                                                        # Get text content for this source
                                                        text_content = ref.get("text", "")
                                                        if not text_content:
                                                            # Fallback to title if no text
                                                            text_content = ref.get("title", "")
                                                        if text_content:
                                                            ai_source_texts.append(text_content)

                                # Extract references from main AI overview item
                                for ref in item.get("references", []):
                                    if ref and ref.get("type") == "ai_overview_reference":
                                        url = ref.get("url")
                                        if url and url not in processed_urls:
                                            ai_sources.append(url)
                                            processed_urls.add(url)

                                            # Track URL for ownership check
                                            if item_type not in feature_urls:
                                                feature_urls[item_type] = []
                                            feature_urls[item_type].append(url)

                                            # Get text content for this source
                                            text_content = ref.get("text", "")
                                            if not text_content:
                                                # Fallback to title if no text
                                                text_content = ref.get("title", "")
                                            if text_content:
                                                ai_source_texts.append(text_content)
                            # Check for owned SERP features (features that link to our domain)
                            if item_type and item_type != "organic" and item.get("url"):
                                extracted = tldextract.extract(item.get("url"))
                                # Handle different tldextract versions
                                if hasattr(extracted, 'top_domain_under_public_suffix'):
                                    result_domain = extracted.top_domain_under_public_suffix
                                else:
                                    # Fallback: construct domain manually
                                    result_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.domain and extracted.suffix else item.get("url")
                                if result_domain == domain_name_only:
                                    keyword_features_owned.add(item_type)

                            # Track URL for features that don't have direct URLs
                            if item_type and item_type != "organic" and item.get("url"):
                                if item_type not in feature_urls:
                                    feature_urls[item_type] = []
                                feature_urls[item_type].append(item.get("url"))
                        except Exception as e:
                            continue

                    # Check all collected URLs to determine owned features
                    for feature_type, urls in feature_urls.items():
                        for url in urls:
                            try:
                                extracted = tldextract.extract(url)
                                # Handle different tldextract versions
                                if hasattr(extracted, 'top_domain_under_public_suffix'):
                                    result_domain = extracted.top_domain_under_public_suffix
                                else:
                                    # Fallback: construct domain manually
                                    result_domain = f"{extracted.domain}.{extracted.suffix}" if extracted.domain and extracted.suffix else url
                                if result_domain == domain_name_only:
                                    keyword_features_owned.add(feature_type)
                                    break  # Once we find one URL from our domain, we can mark this feature as owned
                            except Exception:
                                continue



                    # Datum-basierte Unterscheidung zwischen alten und neuen Tasks
                    not_in_top_str = "Nicht in Top 20" if export_language == "German" else "Not in Top 20"  # Standard für neue Tasks

                    if task_created_at:
                        try:
                            from datetime import datetime
                            created_date = datetime.strptime(task_created_at, '%Y-%m-%d %H:%M:%S')
                            # Annahme: Tasks vor dem 8. Oktober 2025 hatten depth 100
                            cutoff_date = datetime(2025, 10, 8)
                            if created_date < cutoff_date:
                                not_in_top_str = "Nicht in Top 100" if export_language == "German" else "Not in Top 100"
                        except (ValueError, TypeError):
                            # Fallback: Bei Datum-Parsing-Fehlern Standard verwenden (Top 20)
                            pass
                    # Rankings as integers instead of strings (except "Not in Top" text)
                    report_row[f'{domain_name_only}_ranking'] = not_in_top_str if own_ranking is None else own_ranking
                    # Truncate ranking URLs to prevent Excel issues
                    if own_ranking_url is None:
                        report_row[f'{domain_name_only}_ranking_url'] = None
                    else:
                        truncated_url = own_ranking_url[:200] + "..." if len(own_ranking_url) > 200 else own_ranking_url
                        report_row[f'{domain_name_only}_ranking_url'] = truncated_url
                    report_row['SERP_features'] = list(keyword_features) if keyword_features else None
                    report_row['SERP_features_owned'] = list(keyword_features_owned) if keyword_features_owned else None

                    for comp_domain in cleaned_competitors:
                        # Rankings as integers instead of strings (except "Not in Top" text)
                        report_row[f'{comp_domain}_ranking'] = not_in_top_str if competitor_rankings[comp_domain] is None else competitor_rankings[comp_domain]
                        # Truncate competitor URLs to prevent Excel issues
                        if competitor_urls[comp_domain] is None:
                            report_row[f'{comp_domain}_ranking_url'] = None
                        else:
                            truncated_comp_url = competitor_urls[comp_domain][:200] + "..." if len(competitor_urls[comp_domain]) > 200 else competitor_urls[comp_domain]
                            report_row[f'{comp_domain}_ranking_url'] = truncated_comp_url

                    if paa_questions:
                        # Truncate PAA questions to prevent Excel issues
                        paa_joined = '\\n'.join(paa_questions)
                        report_row['people_also_ask'] = paa_joined[:15000] + "...[TRUNCATED]" if len(paa_joined) > 15000 else paa_joined
                    if check_ai_overviews:
                        # Truncate AI content to prevent Excel issues
                        ai_overview_joined = '\\n\\n'.join(ai_overview_text) if ai_overview_text else None
                        if ai_overview_joined is not None and len(ai_overview_joined) > 15000:
                            ai_overview_joined = ai_overview_joined[:15000] + "...[TRUNCATED]"
                        report_row['ai_overview'] = ai_overview_joined

                        # Truncate AI source URLs - limit both individual URLs and total length
                        if ai_sources:
                            truncated_sources = []
                            for url in ai_sources:
                                # Truncate individual URLs to 200 characters
                                truncated_url = url[:200] + "..." if len(url) > 200 else url
                                truncated_sources.append(truncated_url)
                            # Join and check total length
                            ai_sources_joined = ', '.join(truncated_sources)
                            if len(ai_sources_joined) > 10000:
                                ai_sources_joined = ai_sources_joined[:10000] + "...[TRUNCATED]"
                            report_row['ai_source_urls'] = ai_sources_joined
                        else:
                            report_row['ai_source_urls'] = None

                        # Truncate AI source texts
                        ai_texts_joined = '\\n\\n'.join(ai_source_texts) if ai_source_texts else None
                        if ai_texts_joined is not None and len(ai_texts_joined) > 15000:
                            ai_texts_joined = ai_texts_joined[:15000] + "...[TRUNCATED]"
                        report_row['ai_source_texts'] = ai_texts_joined

                        report_row['ai_overview_async'] = ai_overview_async

                    # Füge die Spalte hinzu
                    report_row['AIO vorhanden'] = 'Ja' if any(item.get('type') == 'ai_overview' for item in items) else 'Nein'
                    # Füge Citations-Spalte hinzu
                    # Extrahiere Domain ohne Subdomain
                    def domain_in_url(url, domain):
                        try:
                            parsed = urlparse(url)
                            return domain in parsed.netloc
                        except Exception:
                            return False
                    citations_found = False
                    own_domain_urls = []
                    if 'ai_source_urls' in report_row and report_row['ai_source_urls']:
                        # ai_source_urls ist ein String mit URLs durch Komma getrennt
                        urls = str(report_row['ai_source_urls']).split(', ')
                        # domain_name_only ist die zu analysierende Domain (z.B. example.com)
                        for url in urls:
                            if domain and domain_name_only in url:
                                citations_found = True
                                own_domain_urls.append(url)
                    report_row['Citations vorhanden'] = 'Ja' if citations_found else 'Nein'

                    # Füge eigene Domain URLs Spalte hinzu
                    if own_domain_urls:
                        # Truncate URLs to prevent Excel issues
                        truncated_own_urls = []
                        for url in own_domain_urls:
                            truncated_url = url[:200] + "..." if len(url) > 200 else url
                            truncated_own_urls.append(truncated_url)
                        own_urls_joined = '\\n'.join(truncated_own_urls)
                        if len(own_urls_joined) > 10000:
                            own_urls_joined = own_urls_joined[:10000] + "...[TRUNCATED]"
                        report_row['Eigene_Domain_URLs'] = own_urls_joined
                    else:
                        report_row['Eigene_Domain_URLs'] = None

                    report_data.append(report_row)
                except Exception as e:
                    continue

            if not report_data:
                st.warning("No report data generated")
                return pd.DataFrame(), pd.DataFrame()

            report_df = pd.DataFrame(report_data)
            serp_df_final = pd.DataFrame(serp_data_for_df) if serp_data_for_df else pd.DataFrame()

            # Define column order more robustly
            if rankings_only:
                core_cols = ['keyword']
                monthly_cols_ordered = []
                sv_metrics_cols = []
            else:
                core_cols = ['keyword', 'search_volume']
                monthly_cols_ordered = sorted_monthly_headers if check_seasonality else []
                sv_metrics_cols = ['competition', 'cpc']

            domain_ranking_cols = [f'{domain_name_only}_ranking', f'{domain_name_only}_ranking_url']

            competitor_ranking_cols_ordered = []
            for comp_domain in cleaned_competitors:
                competitor_ranking_cols_ordered.extend([f'{comp_domain}_ranking', f'{comp_domain}_ranking_url'])

            feature_cols_ordered = ['SERP_features']
            if 'people_also_ask' in report_df.columns:
                feature_cols_ordered.append('people_also_ask')

            ai_cols_ordered = []
            if check_ai_overviews and 'ai_overview' in report_df.columns:
                ai_cols_ordered = ['ai_overview', 'ai_source_urls', 'ai_source_texts', 'ai_overview_async']

            seasonality_cols_ordered = []
            if not rankings_only and 'seasonality' in report_df.columns:
                seasonality_cols_ordered = ['seasonality', 'max_sv', 'min_sv', 'months_max_sv']

            # Build the full desired column order
            final_column_order = core_cols
            if not rankings_only:
                final_column_order.extend(sv_metrics_cols)
            final_column_order.extend(domain_ranking_cols)
            if competitor_ranking_cols_ordered:
                final_column_order.extend(competitor_ranking_cols_ordered)
            # SERP_features und SERP_features_owned
            if 'SERP_features' in feature_cols_ordered:
                idx = len(final_column_order)
                final_column_order.extend(feature_cols_ordered)
                if 'SERP_features_owned' not in final_column_order:
                    final_column_order.insert(final_column_order.index('SERP_features') + 1, 'SERP_features_owned')
                # Füge AIO-Spalte nach SERP_features_owned ein
                aio_col = None
                if 'AIO vorhanden' in report_df.columns:
                    aio_col = 'AIO vorhanden'
                elif 'AIO present' in report_df.columns:
                    aio_col = 'AIO present'
                if aio_col and 'SERP_features_owned' in final_column_order:
                    insert_idx = final_column_order.index('SERP_features_owned') + 1
                    if aio_col not in final_column_order:
                        final_column_order.insert(insert_idx, aio_col)
                # Füge Citations-Spalte nach AIO-Spalte ein
                citations_col = None
                if 'Citations vorhanden' in report_df.columns:
                    citations_col = 'Citations vorhanden'
                elif 'Citations present' in report_df.columns:
                    citations_col = 'Citations present'
                if citations_col and aio_col in final_column_order:
                    insert_idx = final_column_order.index(aio_col) + 1
                    if citations_col not in final_column_order:
                        final_column_order.insert(insert_idx, citations_col)
                # Füge eigene Domain URLs Spalte nach Citations-Spalte ein
                own_urls_col = None
                if 'Eigene_Domain_URLs' in report_df.columns:
                    own_urls_col = 'Eigene_Domain_URLs'
                elif 'Own_Domain_URLs' in report_df.columns:
                    own_urls_col = 'Own_Domain_URLs'
                if own_urls_col and citations_col in final_column_order:
                    insert_idx = final_column_order.index(citations_col) + 1
                    if own_urls_col not in final_column_order:
                        final_column_order.insert(insert_idx, own_urls_col)
            else:
                final_column_order.extend(feature_cols_ordered)
                if 'SERP_features_owned' not in final_column_order:
                    final_column_order.append('SERP_features_owned')
                # Füge AIO-Spalte nach SERP_features_owned ein
                aio_col = None
                if 'AIO vorhanden' in report_df.columns:
                    aio_col = 'AIO vorhanden'
                elif 'AIO present' in report_df.columns:
                    aio_col = 'AIO present'
                if aio_col and 'SERP_features_owned' in final_column_order:
                    insert_idx = final_column_order.index('SERP_features_owned') + 1
                    if aio_col not in final_column_order:
                        final_column_order.insert(insert_idx, aio_col)
                # Füge Citations-Spalte nach AIO-Spalte ein
                citations_col = None
                if 'Citations vorhanden' in report_df.columns:
                    citations_col = 'Citations vorhanden'
                elif 'Citations present' in report_df.columns:
                    citations_col = 'Citations present'
                if citations_col and aio_col in final_column_order:
                    insert_idx = final_column_order.index(aio_col) + 1
                    if citations_col not in final_column_order:
                        final_column_order.insert(insert_idx, citations_col)
                # Füge eigene Domain URLs Spalte nach Citations-Spalte ein
                own_urls_col = None
                if 'Eigene_Domain_URLs' in report_df.columns:
                    own_urls_col = 'Eigene_Domain_URLs'
                elif 'Own_Domain_URLs' in report_df.columns:
                    own_urls_col = 'Own_Domain_URLs'
                if own_urls_col and citations_col in final_column_order:
                    insert_idx = final_column_order.index(citations_col) + 1
                    if own_urls_col not in final_column_order:
                        final_column_order.insert(insert_idx, own_urls_col)
            if ai_cols_ordered:
                final_column_order.extend(ai_cols_ordered)
            if seasonality_cols_ordered:
                final_column_order.extend(seasonality_cols_ordered)
            # Add monthly search columns at the end (only if not rankings_only)
            if not rankings_only and monthly_cols_ordered:
                final_column_order.extend(monthly_cols_ordered)

            # Ensure all columns exist in report_df, fill with None if missing, then reindex
            if 'SERP_features_owned' not in report_df.columns:
                report_df['SERP_features_owned'] = None
            if 'Eigene_Domain_URLs' not in report_df.columns:
                report_df['Eigene_Domain_URLs'] = None
            for col in final_column_order:
                if col not in report_df.columns:
                    report_df[col] = None
            report_df = report_df.reindex(columns=final_column_order)

            if not serp_df_final.empty:
                if rankings_only:
                    serp_df_final = serp_df_final.reindex(columns=['keyword', 'position', 'position_with_serp-features', 'url'])
                else:
                    serp_df_final = serp_df_final.reindex(columns=['keyword', 'search_volume', 'position', 'position_with_serp-features', 'url'])

            # Nach Erstellung des report_df: Booleans in ja/nein oder yes/no umwandeln
            bool_map = {'English': {True: 'yes', False: 'no'}, 'German': {True: 'ja', False: 'nein'}}
            for col in report_df.columns:
                if report_df[col].dtype == bool or (report_df[col].dropna().isin([True, False]).all() and report_df[col].notna().any()):
                    report_df[col] = report_df[col].map(bool_map.get(export_language, bool_map['English']))

            return report_df, serp_df_final

        except Exception as e:
            return pd.DataFrame(), pd.DataFrame()

    def transpose_serp_results(serp_df, rankings_only=False):
        """
        Transpose SERP results into a wide format showing top 10 positions.
        """
        # Check if DataFrame is None, empty, or missing required columns
        if serp_df is None or len(serp_df) == 0 or 'position' not in list(serp_df.columns):
            # Return empty DataFrame with expected structure
            if rankings_only:
                empty_columns = ['keyword']
            else:
                empty_columns = ['keyword', 'search_volume']
            for pos in range(1, 11):
                empty_columns.extend([
                    f"{pos}_position_with_serp-features",
                    f"{pos}_url"
                ])
            return pd.DataFrame(columns=empty_columns)

        # Filter to top 10 results and sort by position
        try:
            # Ensure position column is numeric
            serp_df_copy = serp_df.copy()
            serp_df_copy['position'] = pd.to_numeric(serp_df_copy['position'], errors='coerce')

            # Filter to top 10 and remove any rows with NaN positions
            top10serp_df = serp_df_copy[serp_df_copy["position"] <= 10].copy()
            top10serp_df = top10serp_df.dropna(subset=['position'])

            # Check if we have any data left
            if len(top10serp_df) == 0:
                # Return empty DataFrame with expected structure
                if rankings_only:
                    empty_columns = ['keyword']
                else:
                    empty_columns = ['keyword', 'search_volume']
                for pos in range(1, 11):
                    empty_columns.extend([
                        f"{pos}_position_with_serp-features",
                        f"{pos}_url"
                    ])
                return pd.DataFrame(columns=empty_columns)

            top10serp_df = top10serp_df.sort_values(["keyword", "position"])

            # Ensure required columns exist
            if not rankings_only and 'search_volume' not in top10serp_df.columns:
                top10serp_df['search_volume'] = None
            if 'position_with_serp-features' not in top10serp_df.columns:
                top10serp_df['position_with_serp-features'] = top10serp_df['position']

            # Create pivot table
            if rankings_only:
                transposed_df = pd.pivot_table(
                    top10serp_df,
                    index=['keyword'],
                    columns='position',
                    values=['position_with_serp-features', 'url'],
                    aggfunc='first'
                ).reset_index()
            else:
                transposed_df = pd.pivot_table(
                    top10serp_df,
                    index=['keyword', 'search_volume'],
                    columns='position',
                    values=['position_with_serp-features', 'url'],
                    aggfunc='first'
                ).reset_index()

        except Exception as e:
            # Return empty DataFrame with expected structure
            empty_columns = ['keyword', 'search_volume']
            for pos in range(1, 11):
                empty_columns.extend([
                    f"{pos}_position_with_serp-features",
                    f"{pos}_url"
                ])
            return pd.DataFrame(columns=empty_columns)

        # Flatten column names
        transposed_df.columns = [
            col[0] if col[1] == '' else f"{int(col[1])}_{col[0]}"
            for col in transposed_df.columns
        ]

        # Ensure all position columns exist (1-10)
        for pos in range(1, 11):
            for suffix in ['position_with_serp-features', 'url']:
                col_name = f"{pos}_{suffix}"
                if col_name not in transposed_df.columns:
                    transposed_df[col_name] = None

        # Define column order
        if rankings_only:
            column_order = ['keyword']
        else:
            column_order = ['keyword', 'search_volume']
        for pos in range(1, 11):
            column_order.extend([
                f"{pos}_position_with_serp-features",
                f"{pos}_url"
            ])

        # Reorder columns and clean nan values
        transposed_df = transposed_df.reindex(columns=column_order, fill_value=None)
        transposed_df = clean_nan_values(transposed_df)

        # For Streamlit compatibility, ensure position columns are strings
        for col in transposed_df.columns:
            if col.endswith('_position_with_serp-features'):
                transposed_df[col] = transposed_df[col].astype(str).replace('nan', None)

        # Format Top 10 SERP position columns as string with integer formatting
        for pos in range(1, 11):
            col_name = f"{pos}_position_with_serp-features"
            if col_name in transposed_df.columns:
                def to_str_int(val):
                    if pd.isna(val):
                        return ""
                    try:
                        return str(int(float(val)))
                    except (ValueError, TypeError):
                        return str(val)
                transposed_df[col_name] = transposed_df[col_name].apply(to_str_int)

        return transposed_df


    def clean_up_string(s):
        if not isinstance(s, str):
            return s # Return the original value if it's not a string

        # Remove the '@@' separators
        cleaned = s.replace('@@', '\n')
        # Split by newline to get individual elements
        elements = [elem.strip() for elem in cleaned.split('\n') if elem.strip()]
        return ' '.join(elements) # Joining the elements back into a single string

    def list_to_str(val):
        if isinstance(val, list):
            return ', '.join(map(str, val))
        return val

    def format_number_german(value):
        """Format numbers in German locale (1.500 instead of 1,500.00)"""
        if value is None or pd.isna(value):
            return None
        try:
            if isinstance(value, (int, float)) and not pd.isna(value):
                # Format integers without decimals, floats with minimal decimals
                if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
                    return f"{int(value):,}".replace(',', '.')
                else:
                    # Format floats with up to 2 decimal places, removing trailing zeros
                    formatted = f"{value:.2f}".rstrip('0').rstrip('.')
                    # Add thousand separators
                    if '.' in formatted:
                        integer_part, decimal_part = formatted.split('.')
                        integer_part = f"{int(integer_part):,}".replace(',', '.')
                        return f"{integer_part},{decimal_part}"
                    else:
                        return f"{int(float(formatted)):,}".replace(',', '.')
            return value
        except (ValueError, TypeError):
            return value

    def clean_nan_values(df):
        """Replace nan values with None/empty cells"""
        if df is None or df.empty:
            return df

        df_cleaned = df.copy()

        # Replace various nan representations with None
        for col in df_cleaned.columns:
            # Skip boolean columns to avoid type conflicts
            if df_cleaned[col].dtype == 'bool':
                continue

            df_cleaned[col] = df_cleaned[col].replace({
                'nan': None,
                'NaN': None,
                'NAN': None,
                pd.NA: None,
                float('nan'): None
            })

            # Also handle cases where pandas shows nan as string (but not for boolean columns)
            if df_cleaned[col].dtype != 'bool':
                try:
                    mask = df_cleaned[col].astype(str).str.lower() == 'nan'
                    df_cleaned.loc[mask, col] = None
                except (TypeError, AttributeError):
                    # Skip if conversion to string fails
                    continue

        return df_cleaned

    def prepare_dataframe_for_streamlit(df):
        """
        Prepare dataframe for Streamlit display by converting ranking columns to strings
        to avoid PyArrow serialization issues with mixed data types
        """
        if df is None or df.empty:
            return df

        df_streamlit = df.copy()

        # Convert all ranking columns to string for display, formatting integers without decimals
        for col in df_streamlit.columns:
            if col.endswith('_ranking') or col.endswith('_Ranking'):
                def to_str_int_or_special(val):
                    if pd.isna(val):
                        return ""
                    if str(val).startswith("Nicht in Top") or str(val).startswith("Not in Top"):
                        return str(val)
                    try:
                        return str(int(float(val)))
                    except (ValueError, TypeError):
                        return str(val)
                df_streamlit[col] = df_streamlit[col].apply(to_str_int_or_special)

        return df_streamlit

    def get_column_translations(df, export_language='German', is_top10serp=False):
        """
        Returns the appropriate column translations based on language and dataframe type.
        Returns: Dictionary of column translations
        """
        # Define German column names (default)
        report_translations = {
            'keyword': 'Keyword',
            'search_volume': 'Suchvolumen',
            'SERP_features': 'SERP-Funktionen',
            'SERP_features_owned': 'SERP-Funktionen (eigen)',
            'people_also_ask': 'Nutzer fragen auch',
            'ai_overview': 'AI-Übersicht',
            'ai_source_urls': 'AI-Quellen-URLs',
            'ai_source_texts': 'AI-Quellentexte',
            'ai_overview_async': 'AI-Übersicht-Asynchron',
            'seasonality': 'Saisonalität',
            'max_sv': 'Max_Suchvolumen',
            'min_sv': 'Min_Suchvolumen',
            'months_max_sv': 'Monate_Max_Suchvolumen',
            'competition': 'Wettbewerb',
            'cpc': 'CPC',
            'AIO present': 'AIO vorhanden',
            'Citations present': 'Citations vorhanden',
            'Own_Domain_URLs': 'Eigene Domain URLs',
        }

        # Dynamically add domain and competitor columns to translations
        if df is not None:
            for col in df.columns:
                if col.endswith('_ranking') and not col.endswith('_url_ranking'):
                    base_name = col.replace('_ranking', '')
                    report_translations[col] = f'{base_name}_Ranking'
                elif col.endswith('_ranking_url'):
                    base_name = col.replace('_ranking_url', '')
                    report_translations[col] = f'{base_name}_Ranking_URL'

        if export_language == 'English':
            # Translate German to English
            english_translations = {
                'Keyword': 'Keyword',
                'Suchvolumen': 'Search Volume',
                'SERP-Funktionen': 'SERP Features',
                'SERP-Funktionen (eigen)': 'SERP Features (owned)',
                'Nutzer fragen auch': 'People Also Ask',
                'AI-Übersicht': 'AI Overview',
                'AI-Quellen-URLs': 'AI Source URLs',
                'AI-Quellentexte': 'AI Source Texts',
                'AI-Übersicht-Asynchron': 'AI Overview Async',
                'Saisonalität': 'Seasonality',
                'Max_Suchvolumen': 'Max Search Volume',
                'Min_Suchvolumen': 'Min Search Volume',
                'Monate_Max_Suchvolumen': 'Months Max Search Volume',
                'Wettbewerb': 'Competition',
                'CPC': 'CPC',
                'AIO present': 'AIO present',
                'Citations vorhanden': 'Citations present',
                'Eigene Domain URLs': 'Own Domain URLs',
            }

            if is_top10serp:
                top10_translations = {
                    'Keyword': 'Keyword',
                    'Suchvolumen': 'Search Volume'
                }
                for col in df.columns:
                    if col.endswith('_Position_mit_SERP_Funktionen'):
                        prefix = col.split('_')[0]
                        top10_translations[col] = f'{prefix}_Position_with_SERP_Features'
                    elif col.endswith('_URL') and not col.startswith('Keyword') and not col.startswith('Suchvolumen'):
                        prefix = col.split('_')[0]
                        if prefix.isdigit():
                            top10_translations[col] = f'{prefix}_URL'
                return {'german': report_translations, 'english': top10_translations}
            else:
                return {'german': report_translations, 'english': english_translations}
        else:
            # Use German translations
            if is_top10serp:
                top10_translations = {
                    'keyword': 'Keyword',
                    'search_volume': 'Suchvolumen'
                }
                for col in df.columns:
                    if col.endswith('_position_with_serp-features'):
                        prefix = col.split('_')[0]
                        top10_translations[col] = f'{prefix}_Position_mit_SERP_Funktionen'
                    elif col.endswith('_url') and not col.startswith('keyword') and not col.startswith('search_volume'):
                        prefix = col.split('_')[0]
                        if prefix.isdigit():
                            top10_translations[col] = f'{prefix}_URL'
                return {'german': top10_translations}
            else:
                return {'german': report_translations}

    def truncate_cell_content(content, max_length=32767):
        """Truncate cell content to fit within Excel's limits"""
        if content is None:
            return None

        content_str = str(content)
        if len(content_str) <= max_length:
            return content_str

        # Truncate and add indication
        return content_str[:max_length-10] + "...[TRUNCATED]"

    def truncate_urls_in_dataframe(df):
        """Truncate URLs and long content in dataframe to fit Excel limits"""
        if df is None or df.empty:
            return df

        df_copy = df.copy()

        # Spezielle Behandlung für URLs mit mehreren URLs pro Zelle - jede einzelne URL begrenzen
        multi_url_columns = [col for col in df_copy.columns if any(multi_col in col.lower() for multi_col in ['eigene_domain_urls', 'own_domain_urls', 'ai_source_urls'])]
        for col in multi_url_columns:
            def truncate_individual_urls(cell_content):
                if cell_content is None or pd.isna(cell_content):
                    return cell_content

                # URLs sind durch \n oder Komma getrennt (je nach Spalte)
                if 'ai_source_urls' in col.lower():
                    # AI Source URLs sind durch Komma getrennt
                    urls = str(cell_content).split(', ')
                else:
                    # Eigene Domain URLs sind durch \n getrennt
                    urls = str(cell_content).split('\\n')
                truncated_urls = []

                for url in urls:
                    # Jede einzelne URL bis zum #:~:text= Teil begrenzen
                    if '#:~:text=' in url:
                        truncated_url = url.split('#:~:text=')[0]
                    else:
                        truncated_url = url
                    truncated_urls.append(truncated_url)

                # URLs wieder zusammenfügen
                if 'ai_source_urls' in col.lower():
                    # AI Source URLs mit Komma zusammenfügen
                    return ', '.join(truncated_urls)
                else:
                    # Eigene Domain URLs mit \n zusammenfügen
                    return '\\n'.join(truncated_urls)

            df_copy[col] = df_copy[col].apply(truncate_individual_urls)

        # Normale URL-Spalten behandeln (aber Multi-URL-Spalten ausschließen)
        url_columns = [col for col in df_copy.columns if ('url' in col.lower() or 'ai_source' in col.lower()) and
                      not any(multi_col in col.lower() for multi_col in ['eigene_domain_urls', 'own_domain_urls', 'ai_source_urls'])]
        for col in url_columns:
            df_copy[col] = df_copy[col].apply(lambda x: truncate_cell_content(x, max_length=250) if x is not None else None)

        return df_copy

    def download_excel_link(report_df, top10serp_df, name, export_language='German'):
        excel_buffer = io.BytesIO()

        # Create copies to avoid modifying original DFs
        report_df_copy = report_df.copy() if report_df is not None else None
        top10serp_df_copy = top10serp_df.copy() if top10serp_df is not None else None

        # Clean nan values and apply German number formatting
        if report_df_copy is not None:
            report_df_copy = clean_nan_values(report_df_copy)
            report_df_copy = truncate_urls_in_dataframe(report_df_copy)

            # Convert ranking columns back to numeric for Excel export
            for col in report_df_copy.columns:
                if col.endswith('_ranking') or col.endswith('_Ranking'):
                    # Convert rankings back to numeric, keeping text values for "Not in Top" texts
                    def is_not_in_top_text(value):
                        return str(value).startswith("Nicht in Top") or str(value).startswith("Not in Top")

                    def convert_ranking_to_numeric(value):
                        if is_not_in_top_text(value) or pd.isna(value) or value is None:
                            return value  # Keep text values as they are
                        try:
                            return int(float(str(value)))  # Convert to integer
                        except (ValueError, TypeError):
                            return value  # Keep original if conversion fails

                    report_df_copy[col] = report_df_copy[col].apply(convert_ranking_to_numeric)

            # Convert numeric columns to proper types (but don't apply German formatting yet)
            # This keeps them as numbers for Excel, formatting will be applied via Excel formatting
            for col in report_df_copy.columns:
                if ('search_volume' in col.lower() or 'suchvolumen' in col.lower() or
                    col.lower().endswith('_sv') or 'max_sv' in col.lower() or 'min_sv' in col.lower() or
                    col.startswith(('2023-', '2024-', '2025-'))):
                    # Process search volume columns to ensure they are integers
                    def ensure_integer(value):
                        if pd.isna(value) or value is None:
                            return value
                        try:
                            if isinstance(value, int):
                                return value
                            if isinstance(value, float):
                                return int(round(value))
                            if isinstance(value, str):
                                # Extrahiere nur Ziffern
                                digits = ''.join(filter(str.isdigit, value))
                                if digits == '':
                                    return None
                                return int(digits)
                            return int(value)
                        except (ValueError, TypeError, OverflowError):
                            return value
                    report_df_copy[col] = report_df_copy[col].apply(ensure_integer)
                elif 'cpc' in col.lower():
                    # Keep CPC as float with 2 decimal places
                    def ensure_float(value):
                        if pd.isna(value) or value is None:
                            return value
                        try:
                            if isinstance(value, str):
                                cleaned = value.replace('.', '').replace(',', '.')
                                return round(float(cleaned), 2)
                            return round(float(value), 2)
                        except (ValueError, TypeError):
                            return value
                    report_df_copy[col] = report_df_copy[col].apply(ensure_float)

            # Explicitly convert column types to ensure Excel recognizes them correctly
            for col in report_df_copy.columns:
                if ('search_volume' in col.lower() or 'suchvolumen' in col.lower() or
                    col.lower().endswith('_sv') or 'max_sv' in col.lower() or 'min_sv' in col.lower() or
                    col.startswith(('2023-', '2024-', '2025-'))):
                    # Force integer dtype for search volume columns
                    try:
                        # Convert to nullable integer type
                        report_df_copy[col] = report_df_copy[col].astype('Int64')
                    except (ValueError, TypeError):
                        # Fallback: keep as is if conversion fails
                        pass

        if top10serp_df_copy is not None:
            top10serp_df_copy = clean_nan_values(top10serp_df_copy)
            top10serp_df_copy = truncate_urls_in_dataframe(top10serp_df_copy)

            # Convert ranking-related columns back to numeric for Excel export
            for col in top10serp_df_copy.columns:
                if '_position_with_serp-features' in col.lower():
                    def convert_position_to_numeric(value):
                        if pd.isna(value) or value is None:
                            return value
                        try:
                            return int(float(str(value)))  # Convert to integer
                        except (ValueError, TypeError):
                            return value  # Keep original if conversion fails

                    top10serp_df_copy[col] = top10serp_df_copy[col].apply(convert_position_to_numeric)

            # Ensure search volume columns are numeric (integers)
            for col in top10serp_df_copy.columns:
                if 'search_volume' in col.lower() or 'suchvolumen' in col.lower():
                    def ensure_integer(value):
                        if pd.isna(value) or value is None:
                            return value
                        try:
                            if isinstance(value, str):
                                # Remove any formatting and convert.
                                # This logic handles German number format (e.g., "1.234,56") by removing
                                # thousand separators (.) and converting the decimal separator (,) to a dot.
                                cleaned = value.strip().replace('.', '').replace(',', '.')
                                if cleaned == '' or cleaned.lower() == 'nan':
                                    return None
                                # Convert to float, round to the nearest whole number, then to integer.
                                return int(round(float(cleaned)))
                            elif isinstance(value, float):
                                if value.is_integer():
                                    return int(value)
                                else:
                                    return int(round(value))
                            elif isinstance(value, int):
                                return value
                            else:
                                return int(float(str(value)))
                        except (ValueError, TypeError, OverflowError):
                            return value
                    top10serp_df_copy[col] = top10serp_df_copy[col].apply(ensure_integer)

            # Also convert top10serp search volume columns to Int64 dtype
            for col in top10serp_df_copy.columns:
                if 'search_volume' in col.lower() or 'suchvolumen' in col.lower():
                    try:
                        top10serp_df_copy[col] = top10serp_df_copy[col].astype('Int64')
                    except (ValueError, TypeError):
                        pass

            # Get translations
            if report_df_copy is not None:
                translations = get_column_translations(report_df_copy, export_language)
                report_df_copy.rename(columns=translations['german'], inplace=True)
                if export_language == 'English':
                    report_df_copy.rename(columns=translations['english'], inplace=True)

            if top10serp_df_copy is not None:
                translations = get_column_translations(top10serp_df_copy, export_language, is_top10serp=True)
                top10serp_df_copy.rename(columns=translations['german'], inplace=True)
                if export_language == 'English':
                    top10serp_df_copy.rename(columns=translations['english'], inplace=True)

            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                # Write the DataFrames to Excel
                if report_df_copy is not None:
                    report_df_copy.to_excel(writer, sheet_name='Report', index=False)
                if top10serp_df_copy is not None:
                    top10serp_df_copy.to_excel(writer, sheet_name='Top 10 SERP', index=False)

                # Get the workbook and worksheet objects
                workbook = writer.book

                # Define number formats - use simpler, more compatible formats
                if export_language == 'German':
                    # Use standard number format - Excel will apply German formatting based on system locale
                    german_integer_format = workbook.add_format({'num_format': '#,##0'})
                    german_decimal_format = workbook.add_format({'num_format': '#,##0.00'})
                else:
                    # English number format
                    english_integer_format = workbook.add_format({'num_format': '#,##0'})
                    english_decimal_format = workbook.add_format({'num_format': '#,##0.00'})

                if report_df_copy is not None:
                    report_worksheet = writer.sheets['Report']

                    # Apply number formatting to specific columns
                    for idx, col in enumerate(report_df_copy.columns):
                        col_lower = col.lower()

                        # Set column widths
                        max_data_length = report_df_copy[col].astype(str).apply(len).max() if len(report_df_copy) > 0 else 0
                        col_name_length = len(str(col))
                        max_length = max(max_data_length, col_name_length)
                        max_length = min(max_length + 2, 100)

                        # Apply German/English number formatting to numeric columns
                        if export_language == 'German':
                            if ('suchvolumen' in col_lower or 'search_volume' in col_lower or
                                col_lower.endswith('_sv') or 'max_sv' in col_lower or 'min_sv' in col_lower or
                                col.startswith(('2023-', '2024-', '2025-'))):
                                # Format as German integers with thousand separators: 1.234.567
                                report_worksheet.set_column(idx, idx, max_length, german_integer_format)
                            elif 'cpc' in col_lower:
                                # Format as German decimals with comma: 1,23
                                report_worksheet.set_column(idx, idx, max_length, german_decimal_format)
                            elif col_lower.endswith('_ranking') or col_lower.endswith('_ranking_url'):
                                # Ranking columns explizit als Integer formatieren
                                report_worksheet.set_column(idx, idx, max_length, german_integer_format)
                            else:
                                report_worksheet.set_column(idx, idx, max_length)
                        else:
                            if ('search_volume' in col_lower or 'suchvolumen' in col_lower or
                                col_lower.endswith('_sv') or 'max_sv' in col_lower or 'min_sv' in col_lower or
                                col.startswith(('2023-', '2024-', '2025-'))):
                                # Format as English integers: 1,234,567
                                report_worksheet.set_column(idx, idx, max_length, english_integer_format)
                            elif 'cpc' in col_lower:
                                # Format as English decimals: 1.23
                                report_worksheet.set_column(idx, idx, max_length, english_decimal_format)
                            elif col_lower.endswith('_ranking') or col_lower.endswith('_ranking_url'):
                                # Ranking columns explizit als Integer formatieren
                                report_worksheet.set_column(idx, idx, max_length, english_integer_format)
                            else:
                                report_worksheet.set_column(idx, idx, max_length)

                # If we have a Top 10 SERP sheet, set its column widths and formatting too
                if top10serp_df_copy is not None:
                    serp_worksheet = writer.sheets['Top 10 SERP']
                    for idx, col in enumerate(top10serp_df_copy.columns):
                        col_lower = col.lower()

                        # Set column widths
                        max_data_length = top10serp_df_copy[col].astype(str).apply(len).max() if len(top10serp_df_copy) > 0 else 0
                        col_name_length = len(str(col))
                        max_length = max(max_data_length, col_name_length)
                        max_length = min(max_length + 2, 100)

                        # Apply German/English number formatting
                        if export_language == 'German':
                            if 'suchvolumen' in col_lower or 'search_volume' in col_lower:
                                serp_worksheet.set_column(idx, idx, max_length, german_integer_format)
                            elif (
                                col_lower.endswith('_position_with_serp-features')
                                or col_lower.endswith('_position')
                                or col.endswith('_Position_mit_SERP_Funktionen')
                                or col.endswith('_Position')
                            ):
                                serp_worksheet.set_column(idx, idx, max_length, german_integer_format)
                            else:
                                serp_worksheet.set_column(idx, idx, max_length)
                        else:
                            if 'search_volume' in col_lower or 'suchvolumen' in col_lower:
                                serp_worksheet.set_column(idx, idx, max_length, english_integer_format)
                            elif (
                                col_lower.endswith('_position_with_serp-features')
                                or col_lower.endswith('_position')
                                or col.endswith('_Position_with_SERP_Features')
                                or col.endswith('_Position')
                            ):
                                serp_worksheet.set_column(idx, idx, max_length, english_integer_format)
                            else:
                                serp_worksheet.set_column(idx, idx, max_length)

            excel_data = excel_buffer.getvalue()
            b64_excel = base64.b64encode(excel_data).decode()
            href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="{name}.xlsx">Download {name}</a>'
            st.markdown(href, unsafe_allow_html=True)

    def show_dataframe(report, export_language='German', is_top10serp=False):
        """
        Shows a preview of the first 100 rows of the report DataFrame, with translated column names if needed.
        """
        report_copy = report.copy()

        # Clean nan values first
        report_copy = clean_nan_values(report_copy)

        # Prepare dataframe for Streamlit to avoid PyArrow serialization issues
        report_copy = prepare_dataframe_for_streamlit(report_copy)

        # Apply German number formatting for preview
        if export_language == 'German':
            for col in report_copy.columns:
                if 'search_volume' in col.lower() or 'suchvolumen' in col.lower():
                    report_copy[col] = report_copy[col].apply(format_number_german)
                elif 'cpc' in col.lower():
                    report_copy[col] = report_copy[col].apply(format_number_german)
                elif col.endswith('_sv') or 'max_sv' in col or 'min_sv' in col:
                    report_copy[col] = report_copy[col].apply(format_number_german)
                elif col.startswith(('2023-', '2024-', '2025-')):  # Monthly search volume columns
                    report_copy[col] = report_copy[col].apply(format_number_german)

        # Listen-Spalten in Strings umwandeln, damit Arrow/Streamlit keine Fehler wirft
        for col in ['SERP_features', 'SERP_features_owned']:
            if col in report_copy.columns:
                report_copy[col] = report_copy[col].apply(list_to_str)

        # Get translations
        translations = get_column_translations(report_copy, export_language, is_top10serp)
        report_copy.rename(columns=translations['german'], inplace=True)
        if export_language == 'English':
            report_copy.rename(columns=translations['english'], inplace=True)

        # Convert boolean values to Yes/No or Ja/Nein
        bool_map = {'German': {True: 'Ja', False: 'Nein'}, 'English': {True: 'Yes', False: 'No'}}
        for col in report_copy.columns:
            if report_copy[col].dtype == bool or (report_copy[col].dropna().isin([True, False]).all() and report_copy[col].notna().any()):
                report_copy[col] = report_copy[col].map(bool_map.get(export_language, bool_map['English']))

        st.write("Preview of the First 100 Rows:")
        st.dataframe(report_copy.head(100))

    def chunk_dataframe(df, chunk_size=1000):
        chunks = []
        num_chunks = len(df) // chunk_size + 1
        for i in range(num_chunks):
            start = i * chunk_size
            end = (i + 1) * chunk_size
            chunk = df[start:end]
            chunks.append(chunk)
        return chunks

    async def create_search_volume_tasks_batch_async(client, chunks, country, language, device, check_seasonality):
        """
        Create search volume tasks for multiple chunks concurrently
        """
        async with aiohttp.ClientSession() as session:
            tasks = []
            for chunk in chunks:
                task = get_search_volume_async(chunk, client, country, language, device, check_seasonality, session=session)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_task_ids = []
            all_errors = []

            for result in results:
                if isinstance(result, Exception):
                    all_errors.append(f"Exception in search volume task creation: {str(result)}")
                else:
                    task_ids, errors = result
                    if task_ids:
                        all_task_ids.extend(task_ids)
                    if errors:
                        all_errors.extend(errors)

            return all_task_ids, all_errors

    async def create_serp_tasks_batch_async(client, chunks, country, language, device, check_ai_overviews):
        """
        Create SERP tasks for multiple chunks concurrently
        """
        async with aiohttp.ClientSession() as session:
            tasks = []
            for chunk in chunks:
                task = get_ranking_positions_async(client, chunk, country, language, device, check_ai_overviews, session=session)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_task_ids = []
            all_errors = []

            for result in results:
                if isinstance(result, Exception):
                    all_errors.append(f"Exception in SERP task creation: {str(result)}")
                else:
                    task_ids, errors = result
                    if task_ids:
                        all_task_ids.extend(task_ids)
                    if errors:
                        all_errors.extend(errors)

            return all_task_ids, all_errors

    def init_session_state():
        """
        Initializes or updates the Streamlit session state variables.
        """
        if 'confirmed_preview' not in st.session_state:
            st.session_state.confirmed_preview = False

    def delete_task(task_id):
        """Delete a task from the database"""
        conn = get_db_connection()
        try:
            c = conn.cursor()



            # Delete from results tables first (only if they exist)
            c.execute('DELETE FROM search_volume_results WHERE task_id = ?', (task_id,))
            c.execute('DELETE FROM serp_results WHERE task_id = ?', (task_id,))

            # Delete from main tasks table
            c.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))

            conn.commit()

            # Don't run VACUUM here as it can cause locks - run it separately if needed
            # c.execute('VACUUM')
            # conn.commit()

            return True
        except sqlite3.Error as e:
            st.error(f"Error deleting task: {str(e)}")
            return False
        finally:

            conn.close()



    def get_search_volume_results(task_id):
        """Get search volume results from the separate table"""
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute('SELECT results FROM search_volume_results WHERE task_id = ?', (task_id,))
            result = c.fetchone()
            if result:
                return json.loads(result[0])
            return None
        except sqlite3.Error as e:
            st.error(f"Error getting search volume results: {str(e)}")
            return None
        finally:
            conn.close()



    def get_serp_results(task_id):
        """Get SERP results from the separate table"""
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute('SELECT results FROM serp_results WHERE task_id = ?', (task_id,))
            result = c.fetchone()
            if result:
                return json.loads(result[0])
            return None
        except sqlite3.Error as e:
            st.error(f"Error getting SERP results: {str(e)}")
            return None
        finally:
            conn.close()

    def update_processed_tasks(task_id, processed_sv_tasks, processed_serp_tasks):
        """Update the processed tasks in the database with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            conn = get_db_connection()
            try:
                c = conn.cursor()
                c.execute('''UPDATE tasks
                            SET processed_sv_tasks = ?,
                                processed_serp_tasks = ?
                            WHERE task_id = ?''',
                            (json.dumps(list(processed_sv_tasks)),
                             json.dumps(list(processed_serp_tasks)),
                             task_id))
                conn.commit()
                return True
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    st.error(f"Error updating processed tasks: {str(e)}")
                    return False
            except sqlite3.Error as e:
                st.error(f"Error updating processed tasks: {str(e)}")
                return False
            finally:
                conn.close()
        return False

    def check_time_elapsed(created_at_str):
        """Check if 2 minutes have elapsed since task creation"""
        try:
            # Parse the created_at string and add 2 hours to match local time
            created_at = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
            current_time = datetime.now()

            # Calculate time difference
            time_diff = current_time - created_at
            minutes_elapsed = time_diff.total_seconds() / 60
            return minutes_elapsed >= 2, minutes_elapsed
        except (ValueError, TypeError) as e:
            print(f"Error in check_time_elapsed: {str(e)}")
            return False, 0

    def calculate_unique_invalid_keywords(validation_result):
        """Calculate the number of unique invalid keywords (not error instances)"""
        unique_invalid_keywords = set()
        for error in validation_result.invalid_keywords:
            if not error.keyword.startswith('BATCH_SIZE_'):
                unique_invalid_keywords.add(error.keyword)
        return len(unique_invalid_keywords)

    def update_keyword_action(session_key, keyword, action):
        """Helper function to update keyword action in session state"""
        action_key = f"action_{keyword}"
        st.session_state[session_key]['keyword_actions'][action_key] = action

    def clean_and_validate_keywords_with_dialog(keywords_df, task_type, export_language='German'):
        """
        Comprehensive keyword cleaning and validation with user dialog for invalid keywords

        Args:
            keywords_df: DataFrame with keywords
            task_type: Type of task ('rankings_and_search_volume', 'search_volume_only', 'rankings_only')
            export_language: Language for UI ('German' or 'English')

        Returns:
            Tuple of (cleaned_keywords_df, validation_summary)
        """
        if keywords_df is None or keywords_df.empty:
            return keywords_df, {'total': 0, 'valid': 0, 'invalid': 0, 'cleaned': 0, 'removed': 0}

        # Get original keywords for comparison
        original_keywords = keywords_df['Keyword'].tolist()

        # Validate keywords first
        validation_result = validate_keywords_for_task_type(original_keywords, task_type)

        # Group invalid keywords by error type for better user experience
        invalid_keywords_by_type = {}
        for error in validation_result.invalid_keywords:
            if not error.keyword.startswith('BATCH_SIZE_'):
                if error.error_type not in invalid_keywords_by_type:
                    invalid_keywords_by_type[error.error_type] = []
                invalid_keywords_by_type[error.error_type].append({
                    'keyword': error.keyword,
                    'message': error.message,
                    'suggestion': error.suggestion
                })

        # If no invalid keywords, return cleaned DataFrame
        if not invalid_keywords_by_type:
            # Apply appropriate cleaning based on task type
            cleaned_keywords = []
            for keyword in original_keywords:
                if task_type == 'search_volume_only':
                    cleaned = clean_keyword_for_search_volume(keyword)
                elif task_type == 'rankings_only':
                    cleaned = clean_keyword_for_serp(keyword)
                else:  # rankings_and_search_volume
                    # For rankings_and_search_volume, keep the original keyword
                    # The API functions will handle the appropriate cleaning for each API
                    cleaned = keyword
                cleaned_keywords.append(cleaned)

            cleaned_df = keywords_df.copy()
            cleaned_df['Keyword'] = cleaned_keywords

            # Success message will be shown in main function

            return cleaned_df, {
                'total': len(original_keywords),
                'valid': len(original_keywords),
                'invalid': 0,
                'cleaned': len(original_keywords),
                'removed': 0
            }


        st.subheader("🔍 Invalid Keywords Found")

        # Create tabs for different error types
        if len(invalid_keywords_by_type) > 1:
            error_tabs = st.tabs(list(invalid_keywords_by_type.keys()))
            for i, (error_type, keywords) in enumerate(invalid_keywords_by_type.items()):
                with error_tabs[i]:
                    st.write(f"**{error_type.replace('_', ' ').title()}** ({len(keywords)} keywords)")
                    for item in keywords:
                        with st.expander(f"❌ {item['keyword']}"):
                            st.write(f"**Error:** {item['message']}")
                            if item['suggestion']:
                                st.write(f"**Suggestion:** {item['suggestion']}")
        else:
            # Single error type - show directly
            error_type, keywords = list(invalid_keywords_by_type.items())[0]
            st.write(f"**{error_type.replace('_', ' ').title()}** ({len(keywords)} keywords)")
            for item in keywords:
                with st.expander(f"❌ {item['keyword']}"):
                    st.write(f"**Error:** {item['message']}")
                    if item['suggestion']:
                        st.write(f"**Suggestion:** {item['suggestion']}")

        # User action selection per keyword
        st.subheader("🛠️ Choose Action for Each Invalid Keyword")

        # Create a unique key for this session
        session_key = f"keyword_action_{hash(str(original_keywords))}"

        if session_key not in st.session_state:
            st.session_state[session_key] = {
                'keyword_actions': {},
                'manual_corrections': {},
                'processed': False
            }



        # Get all unique invalid keywords
        all_invalid_keywords = set()
        for error_type, keywords in invalid_keywords_by_type.items():
            for item in keywords:
                all_invalid_keywords.add(item['keyword'])

        # Show action selection for each invalid keyword
        for i, original in enumerate(sorted(all_invalid_keywords)):
            st.write(f"**Keyword: {original}**")

            # Initialize action if not exists
            action_key = f"action_{original}"
            if action_key not in st.session_state[session_key]['keyword_actions']:
                st.session_state[session_key]['keyword_actions'][action_key] = 'Remove'

            # Action selection for this keyword
            current_action = st.session_state[session_key]['keyword_actions'].get(action_key, 'Remove')

            st.write(f"Current action: {current_action}")

            # Use buttons for action selection
            col1, col2 = st.columns(2)

            with col1:
                if st.button("Remove", key=f"remove_{original}_{session_key}_{i}", type="primary" if current_action == "Remove" else "secondary"):
                    st.session_state[session_key]['keyword_actions'][action_key] = "Remove"
                    st.rerun()

            with col2:
                if st.button("Manually correct", key=f"manual_{original}_{session_key}_{i}", type="primary" if current_action == "Manually correct" else "secondary"):
                    st.session_state[session_key]['keyword_actions'][action_key] = "Manually correct"
                    st.rerun()

            # Get the current action after potential updates
            action = st.session_state[session_key]['keyword_actions'].get(action_key, 'Remove')

            # Show manual correction field if selected - use direct action value
            if action == "Manually correct":
                corrected_key = f"correction_{original}"

                # Initialize correction if not exists
                if corrected_key not in st.session_state[session_key]['manual_corrections']:
                    st.session_state[session_key]['manual_corrections'][corrected_key] = original

                # Get all suggestions for this keyword
                suggestions = []
                for error_type, keywords in invalid_keywords_by_type.items():
                    for item in keywords:
                        if item['keyword'] == original and item['suggestion']:
                            suggestions.append(item['suggestion'])

                suggestion_text = f" (Suggestions: {', '.join(set(suggestions))})" if suggestions else ""

                corrected = st.text_input(
                    f"Correct '{original}'{suggestion_text}:",
                    value=st.session_state[session_key]['manual_corrections'][corrected_key],
                    key=f"manual_corr_{hash(original)}_{i}"
                )

                # Update the correction in session state
                st.session_state[session_key]['manual_corrections'][corrected_key] = corrected







        # Preview section
        st.subheader("📋 Preview")

        # Show before/after comparison
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Original Keywords (invalid):**")
            # Only show invalid keywords
            invalid_keywords_list = list(all_invalid_keywords)
            if invalid_keywords_list:
                st.dataframe(pd.DataFrame({'Original': invalid_keywords_list}))
            else:
                st.write("No invalid keywords found.")

        # Process keywords based on user action
        final_keywords = []
        removed_keywords = []
        cleaned_keywords = []

        for keyword in original_keywords:
            # Check if keyword is invalid
            is_invalid = any(
                error.keyword == keyword and not error.keyword.startswith('BATCH_SIZE_')
                for error in validation_result.invalid_keywords
            )

            if not is_invalid:
                # Valid keyword - apply cleaning
                if task_type == 'search_volume_only':
                    cleaned = clean_keyword_for_search_volume(keyword)
                elif task_type == 'rankings_only':
                    cleaned = clean_keyword_for_serp(keyword)
                else:  # rankings_and_search_volume
                    # For rankings_and_search_volume, keep the original keyword
                    # The API functions will handle the appropriate cleaning for each API
                    cleaned = keyword

                final_keywords.append(cleaned)
                cleaned_keywords.append(cleaned)
            else:
                # Invalid keyword - handle based on individual user action
                action_key = f"action_{keyword}"
                action = st.session_state[session_key]['keyword_actions'].get(action_key, 'remove')

                if action == 'Remove':
                    removed_keywords.append(keyword)
                elif action == 'Manually correct':
                    # Find the corrected version
                    corrected_key = f"correction_{keyword}"
                    corrected = st.session_state[session_key]['manual_corrections'].get(corrected_key, keyword)

                    if corrected and corrected.strip():
                        # Check if the correction is actually different from the original
                        if corrected != keyword:
                            # For manually corrected keywords, use the correction as-is
                            # The API functions will handle the appropriate cleaning for each API
                            cleaned = corrected



                            final_keywords.append(cleaned)
                            cleaned_keywords.append(cleaned)
                        else:
                            # No actual correction was made - keep the original keyword for now
                            # It will be caught by the final validation
                            final_keywords.append(keyword)
                            cleaned_keywords.append(keyword)
                    else:
                        # No correction provided - remove
                        removed_keywords.append(keyword)
                else:
                    # Default: remove if action is not recognized
                    removed_keywords.append(keyword)

        with col2:
            st.write("**Final Keywords (corrected):**")
            # Show only the corrected invalid keywords
            corrected_keywords = []
            for original in original_keywords:
                if original in all_invalid_keywords:
                    # Check if this keyword was manually corrected
                    action_key = f"action_{original}"
                    action = st.session_state[session_key]['keyword_actions'].get(action_key, 'Remove')

                    if action == 'Manually correct':
                        corrected_key = f"correction_{original}"
                        corrected = st.session_state[session_key]['manual_corrections'].get(corrected_key, original)
                        if corrected and corrected.strip():
                            corrected_keywords.append(corrected)
                    elif action == 'Remove':
                        # This keyword was removed, don't show it
                        pass
                    else:
                        # Keyword was cleaned automatically
                        # Find the cleaned version in final_keywords
                        for final_kw in final_keywords:
                            if final_kw != original and final_kw in cleaned_keywords:
                                corrected_keywords.append(final_kw)
                                break

            if corrected_keywords:
                st.dataframe(pd.DataFrame({'Corrected': corrected_keywords}))
            else:
                st.write("No corrected keywords.")

        # Show removed keywords if any
        if removed_keywords:
            with st.expander(f"🗑️ Removed Keywords ({len(removed_keywords)})"):
                st.write("The following keywords were removed:")
                for keyword in removed_keywords:
                    st.write(f"- {keyword}")

        # Create final DataFrame with proper length matching
        if len(final_keywords) == len(keywords_df):
            final_keywords_df = keywords_df.copy()
            final_keywords_df['Keyword'] = final_keywords
        else:
            # Create new DataFrame with only the keywords that remain
            final_keywords_df = pd.DataFrame({'Keyword': final_keywords})
            if 'search_volume' in keywords_df.columns:
                final_keywords_df['search_volume'] = None

        # Mark as processed
        st.session_state[session_key]['processed'] = True

        # Show validate button
        if st.button("✅ Validate & Continue", key=f"validate_{session_key}"):
            if len(final_keywords) == 0:
                st.error("❌ No keywords remaining! All keywords were removed or invalid. Please add valid keywords to continue.")
                return None, {
                    'cleaned': len(cleaned_keywords),
                    'removed': len(removed_keywords)
                }

            # Check if all errors are fixed by re-validating the final keywords
            final_validation_result = validate_keywords_for_task_type(final_keywords, task_type)

            # Show all remaining errors (no ignored keywords filtering)
            remaining_errors = []
            for error in final_validation_result.invalid_keywords:
                if not error.keyword.startswith('BATCH_SIZE_'):
                    remaining_errors.append(error)

            if remaining_errors:
                st.error(f"❌ {len(remaining_errors)} keywords still have validation errors! Please fix them before continuing.")
                st.write("**Remaining errors:**")
                for error in remaining_errors:
                    st.write(f"- {error.keyword}: {error.message}")

                # Also show which keywords were not actually corrected
                st.write("**Keywords that need correction:**")
                for keyword in original_keywords:
                    if keyword in all_invalid_keywords:
                        action_key = f"action_{keyword}"
                        action = st.session_state[session_key]['keyword_actions'].get(action_key, 'Remove')

                        if action == 'Manually correct':
                            corrected_key = f"correction_{keyword}"
                            corrected = st.session_state[session_key]['manual_corrections'].get(corrected_key, keyword)

                            if corrected == keyword:
                                st.write(f"- '{keyword}' was not actually corrected (still has errors)")
                            elif corrected in [error.keyword for error in remaining_errors]:
                                st.write(f"- '{keyword}' was corrected to '{corrected}' but still has errors")



                # Clear the ready flag to force re-validation
                if f"keywords_ready_{session_key}" in st.session_state:
                    del st.session_state[f"keywords_ready_{session_key}"]

                return None, {
                    'cleaned': len(cleaned_keywords),
                    'removed': len(removed_keywords)
                }
            else:
                st.session_state[f"keywords_ready_{session_key}"] = True

                # Show appropriate success message based on what was done
                if len(removed_keywords) > 0:
                    st.success(f"✅ Validation successful! {len(final_keywords)} keywords ready for task creation. {len(removed_keywords)} invalid keywords were removed.")
                else:
                    st.success(f"✅ Validation successful! {len(final_keywords)} keywords ready for task creation.")

                st.rerun()

        # Return None if not ready to continue
        if not st.session_state.get(f"keywords_ready_{session_key}", False):
            return None, {
                'cleaned': len(cleaned_keywords),
                'removed': len(removed_keywords)
            }

        return final_keywords_df, {
            'cleaned': len(cleaned_keywords),
            'removed': len(removed_keywords)
        }

    def main():
        apply_claneo_branding("Keyword Research & Analysis", "Advanced SEO Keyword Intelligence")

        # Show README in an expander before using this app
        with st.expander("Before using this app"):
            st.markdown(read_markdown_file(markdown_file_path))

        init_session_state()

        # Initialize database
        db_path = setup_database()
        if not db_path:
            st.error("Failed to setup database. Please check the error messages above.")
            return

        # Initialize both sync and async clients
        client = RestClient(str(st.secrets["dataforseo"]["user"]), str(st.secrets["dataforseo"]["pw"]))
        async_client = AsyncRestClient(str(st.secrets["dataforseo"]["user"]), str(st.secrets["dataforseo"]["pw"]))
        sorted_countries = custom_sort(COUNTRIES, preferred_countries)
        sorted_languages = custom_sort(LANGUAGES, preferred_languages)

        # Create tabs at the top
        tab1, tab2 = st.tabs(["Create Task", "View Results"])

        with tab1:
            uploaded_file = st.file_uploader("Upload Excel file with keywords", type=['xlsx', 'xls'])

            # Text area for keywords (as alternative)
            keywords_container = st.container()
            with keywords_container:
                keywords_text = st.text_area("Or enter keywords manually 🔑 (separated by commas or line breaks):", key="keywords_input")

            # Process keywords from either source
            keywords_df = None
            if uploaded_file is not None:
                try:
                    df = pd.read_excel(uploaded_file)
                    first_column = df.columns[0]
                    keywords_df = pd.DataFrame(df[first_column].values, columns=['Keyword'])
                    # Entferne leere oder nur aus Leerzeichen bestehende Zeilen
                    keywords_df = keywords_df.dropna(subset=['Keyword'])
                    keywords_df = keywords_df[keywords_df['Keyword'].astype(str).str.strip() != '']

                    # Jetzt clean_keyword anwenden
                    keywords_df['Keyword'] = keywords_df['Keyword'].apply(clean_keyword)
                    st.write(f"Anzahl Keywords: {len(keywords_df)}")
                except Exception as e:
                    st.error(f"Error reading Excel file: {str(e)}")
                    return
            elif keywords_text.strip():
                # Convert text area to DataFrame
                keywords_df = text_to_df(keywords_text, 'Keyword')

            if keywords_df is not None and not keywords_df.empty:
                # Add search_volume column for consistency
                keywords_df['search_volume'] = None

                st.write('Preview of the first 100 rows of your data, please make sure that it displays as intended.')
                st.dataframe(keywords_df.head(100))

                # Task-Auswahl VOR Validierung
                data_type = st.radio(
                    "Select Data Type",
                    ["Rankings & Search Volume", "Search Volume Only", "Rankings Only"],
                    index=0,
                    key="task_type_selection_initial",
                    help="Choose the type of data to retrieve: Rankings & Search Volume (complete analysis), Search Volume Only (keyword metrics), or Rankings Only (SERP positions without search volume)"
                )
                # Mapping für Validierungsfunktion
                task_type_map = {
                    "Rankings & Search Volume": "rankings_and_search_volume",
                    "Search Volume Only": "search_volume_only",
                    "Rankings Only": "rankings_only"
                }
                selected_task_type = task_type_map[data_type]

                if st.button("Get Keyword Insights"):
                    st.session_state.confirmed_preview = True
                    st.session_state.selected_task_type = selected_task_type
                    st.rerun()

                if st.session_state.confirmed_preview:
                    # Run validation mit gewähltem Task-Typ
                    cleaned_keywords_df, validation_summary = clean_and_validate_keywords_with_dialog(
                        keywords_df, st.session_state.get('selected_task_type', 'rankings_and_search_volume'), 'German'
                    )

                    # Store the cleaned keywords in session state for task creation
                    if cleaned_keywords_df is not None and not cleaned_keywords_df.empty:
                        st.session_state['cleaned_keywords_df'] = cleaned_keywords_df
                        st.session_state['validation_completed'] = True
                        # Show success message when validation is completed (for both Get Insights and Validate & Continue)
                        if validation_summary.get('invalid', 0) == 0:
                            st.success("✅ All keywords are valid!")

                    # Only show task parameters if validation is completed
                    if st.session_state.get('validation_completed', False):
                        log_usage(username, "Keywords")

                        country = st.selectbox("Country", sorted_countries)
                        language = st.selectbox("Language", sorted_languages)
                        device = st.selectbox("Device", DEVICES)
                        export_language = st.selectbox("Export Language for Excel", ["German", "English"])


                    else:
                        st.info("Please complete the keyword validation above before proceeding.")
                        return

                    if st.session_state.get('selected_task_type') == 'rankings_and_search_volume':
                        domain = st.text_input("Enter your domain")
                        if domain:
                            num_competitors = st.number_input("Enter the number of competitors", min_value=0, value=1, step=1)
                            competitors = []
                            for i in range(num_competitors):
                                competitor = st.text_input(f"Enter competitor {i+1}").strip()
                                if competitor:
                                    competitors.append(competitor)

                            seasonality_check = st.checkbox("Check Seasonality")

                            # Add AI Overviews checkbox
                            ai_overviews_check = st.checkbox("Include AI Overviews")



                            if st.button("Create Task"):
                                # Use already cleaned keywords from session state
                                if 'cleaned_keywords_df' in st.session_state:
                                    keywords_df = st.session_state['cleaned_keywords_df']
                                else:
                                    st.error("❌ No cleaned keywords found. Please run keyword validation first.")
                                    return

                                if keywords_df is None or keywords_df.empty:
                                    st.error("❌ No keywords available! Cannot create task.")
                                    return

                                task_id = generate_task_id(domain)
                                with st.spinner("Creating tasks..."):
                                    # Save initial task with competitor information
                                    task_data = {
                                        'domain': domain,
                                        'keywords': json.dumps(keywords_df.to_dict()),
                                        'country': country,
                                        'language': language,
                                        'device': device,
                                        'check_seasonality': seasonality_check,
                                        'check_ai_overviews': ai_overviews_check,
                                        'competitors': competitors,
                                        'export_language': export_language
                                    }

                                    if save_task(username, task_id, domain, json.dumps(keywords_df.to_dict()),
                                               country, language, device, task_type='rankings_and_search_volume',
                                               check_seasonality=seasonality_check, check_ai_overviews=ai_overviews_check,
                                               competitors=competitors, export_language=export_language):

                                        # Process keywords in chunks
                                        chunks = chunk_dataframe(keywords_df, chunk_size=1000)
                                        all_sv_task_ids = []
                                        all_serp_task_ids = []

                                        # Create search volume and SERP tasks concurrently
                                        with st.spinner("Creating tasks concurrently..."):
                                            # Create tasks for both search volume and SERP concurrently
                                            async def create_tasks_concurrently():
                                                sv_task = create_search_volume_tasks_batch_async(async_client, chunks, country, language, device, seasonality_check)
                                                serp_task = create_serp_tasks_batch_async(async_client, chunks, country, language, device, ai_overviews_check)

                                                # Execute both tasks concurrently
                                                return await asyncio.gather(sv_task, serp_task, return_exceptions=True)

                                            # Run the async function
                                            sv_result, serp_result = asyncio.run(create_tasks_concurrently())

                                            # Process search volume results
                                            if isinstance(sv_result, Exception):
                                                st.error(f"Error creating search volume tasks: {str(sv_result)}")
                                            else:
                                                sv_task_ids, sv_errors = sv_result
                                                if sv_task_ids:
                                                    all_sv_task_ids.extend(sv_task_ids)
                                                if sv_errors:
                                                    for error in sv_errors:
                                                        st.warning(f"Search volume warning: {error}")

                                            # Process SERP results
                                            if isinstance(serp_result, Exception):
                                                st.error(f"Error creating SERP tasks: {str(serp_result)}")
                                            else:
                                                serp_task_ids, serp_errors = serp_result
                                                if serp_task_ids:
                                                    all_serp_task_ids.extend(serp_task_ids)
                                                if serp_errors:
                                                    for error in serp_errors:
                                                        st.warning(f"SERP warning: {error}")

                                        if all_sv_task_ids or all_serp_task_ids:
                                            # Update the task with all task IDs and competitor information
                                            task_data = {
                                                'sv_task_ids': all_sv_task_ids,
                                                'serp_task_ids': all_serp_task_ids,
                                                'competitors': competitors,
                                                'export_language': export_language
                                            }
                                            if update_task_status(task_id, 'pending', task_data):
                                                st.success(f"""Tasks created successfully!
                                                - {len(all_sv_task_ids)} search volume tasks
                                                - {len(all_serp_task_ids)} SERP tasks""")
                                            else:
                                                st.error("Failed to update task with task IDs")
                                    else:
                                        st.error("Failed to create initial task")
                        else:
                            st.error("Please enter a domain")
                    if st.session_state.get('selected_task_type') == 'search_volume_only':
                        check_seasonality = st.checkbox("Check Seasonality")

                        if st.button("Create Task"):
                            # Use already cleaned keywords from session state
                            if 'cleaned_keywords_df' in st.session_state:
                                keywords_df = st.session_state['cleaned_keywords_df']
                            else:
                                st.error("❌ No cleaned keywords found. Please run keyword validation first.")
                                return

                            if keywords_df is None or keywords_df.empty:
                                st.error("❌ No keywords available! Cannot create task.")
                                return

                            task_id = generate_task_id("search_volume")
                            with st.spinner("Creating tasks..."):
                                # Save initial task
                                if save_task(username, task_id, "", json.dumps(keywords_df.to_dict()),
                                           country, language, device, task_type='search_volume_only',
                                           check_seasonality=check_seasonality, export_language=export_language):

                                    # Process keywords in chunks
                                    chunks = chunk_dataframe(keywords_df, chunk_size=1000)
                                    all_sv_task_ids = []

                                    # Create search volume tasks concurrently
                                    with st.spinner("Creating search volume tasks..."):
                                        async def create_sv_tasks():
                                            return await create_search_volume_tasks_batch_async(async_client, chunks, country, language, device, check_seasonality)

                                        sv_result = asyncio.run(create_sv_tasks())

                                        if isinstance(sv_result, Exception):
                                            st.error(f"Error creating search volume tasks: {str(sv_result)}")
                                        else:
                                            sv_task_ids, sv_errors = sv_result
                                            if sv_task_ids:
                                                all_sv_task_ids.extend(sv_task_ids)
                                            if sv_errors:
                                                for error in sv_errors:
                                                    st.warning(f"Search volume warning: {error}")

                                    if all_sv_task_ids:
                                        # Update the task with task IDs
                                        task_data = {
                                            'sv_task_ids': all_sv_task_ids,
                                            'serp_task_ids': [],
                                            'export_language': export_language
                                        }
                                        if update_task_status(task_id, 'pending', task_data):
                                            st.success(f"""Tasks created successfully!
                                            - {len(all_sv_task_ids)} search volume tasks""")
                                        else:
                                            st.error("Failed to update task with task IDs")
                                    else:
                                        st.error("No tasks were created")
                                else:
                                    st.error("Failed to create initial task")

                    if st.session_state.get('selected_task_type') == 'rankings_only':
                        domain = st.text_input("Enter your domain")
                        if domain:
                            num_competitors = st.number_input("Enter the number of competitors", min_value=0, value=1, step=1)
                            competitors = []
                            for i in range(num_competitors):
                                competitor = st.text_input(f"Enter competitor {i+1}").strip()
                                if competitor:
                                    competitors.append(competitor)

                            # Add AI Overviews checkbox
                            ai_overviews_check = st.checkbox("Include AI Overviews")

                            if st.button("Create Task"):
                                # Use already cleaned keywords from session state
                                if 'cleaned_keywords_df' in st.session_state:
                                    keywords_df = st.session_state['cleaned_keywords_df']
                                else:
                                    st.error("❌ No cleaned keywords found. Please run keyword validation first.")
                                    return

                                if keywords_df is None or keywords_df.empty:
                                    st.error("❌ No keywords available! Cannot create task.")
                                    return

                                task_id = generate_task_id(domain)
                                with st.spinner("Creating tasks..."):
                                    # Save initial task with competitor information
                                    if save_task(username, task_id, domain, json.dumps(keywords_df.to_dict()),
                                               country, language, device, task_type='rankings_only',
                                               check_seasonality=False, check_ai_overviews=ai_overviews_check,
                                               competitors=competitors, export_language=export_language):

                                        # Process keywords in chunks
                                        chunks = chunk_dataframe(keywords_df, chunk_size=1000)
                                        all_serp_task_ids = []

                                        # Create SERP tasks only
                                        with st.spinner("Creating SERP tasks..."):
                                            async def create_serp_tasks():
                                                return await create_serp_tasks_batch_async(async_client, chunks, country, language, device, ai_overviews_check)

                                            serp_result = asyncio.run(create_serp_tasks())

                                            if isinstance(serp_result, Exception):
                                                st.error(f"Error creating SERP tasks: {str(serp_result)}")
                                            else:
                                                serp_task_ids, serp_errors = serp_result
                                                if serp_task_ids:
                                                    all_serp_task_ids.extend(serp_task_ids)
                                                if serp_errors:
                                                    for error in serp_errors:
                                                        st.warning(f"SERP warning: {error}")

                                        if all_serp_task_ids:
                                            # Update the task with task IDs
                                            task_data = {
                                                'sv_task_ids': [],
                                                'serp_task_ids': all_serp_task_ids,
                                                'competitors': competitors,
                                                'export_language': export_language
                                            }
                                            if update_task_status(task_id, 'pending', task_data):
                                                st.success(f"""Tasks created successfully!
                                                - {len(all_serp_task_ids)} SERP tasks""")
                                            else:
                                                st.error("Failed to update task with task IDs")
                                        else:
                                            st.error("No tasks were created")
                                    else:
                                        st.error("Failed to create initial task")
                        else:
                            st.error("Please enter a domain")

        with tab2:
            tasks = get_user_tasks(username)
            if tasks:
                for task in tasks:
                    # --- Build user-friendly expander label ---
                    task_type_raw = task.get('task_type', 'Unbekannter Typ')
                    domain_display_for_label = task.get('domain', '')
                    status_display_for_label = task.get('status', 'Unbekannter Status')
                    created_at_str_for_label = task.get('created_at')

                    adjusted_date_str_for_label = "Datum N/A"
                    if created_at_str_for_label:
                        try:
                            created_at_dt_orig = datetime.strptime(created_at_str_for_label, '%Y-%m-%d %H:%M:%S')
                            created_at_adjusted_for_label = created_at_dt_orig + timedelta(hours=2)
                            adjusted_date_str_for_label = created_at_adjusted_for_label.strftime('%d %b %Y') # e.g., 15 Mai 2024
                        except (ValueError, TypeError):
                            # Fallback if parsing/adjustment fails, use the date part of the original string
                            adjusted_date_str_for_label = created_at_str_for_label.split(' ')[0]

                    user_friendly_task_type_for_label = "Unbekannter Typ"
                    if task_type_raw == 'rankings_and_search_volume':
                        user_friendly_task_type_for_label = "Rankings & Suchvolumen"
                    elif task_type_raw == 'search_volume_only':
                        user_friendly_task_type_for_label = "Nur Suchvolumen"
                    elif task_type_raw == 'rankings_only':
                        user_friendly_task_type_for_label = "Nur Rankings"

                    expander_label_parts = []
                    expander_label_parts.append(adjusted_date_str_for_label)
                    if domain_display_for_label and task_type_raw not in ['search_volume_only']:
                        expander_label_parts.append(f"'{domain_display_for_label}'")
                    expander_label_parts.append(user_friendly_task_type_for_label)

                    # Add status with emoji instead of HTML
                    status_emoji = "🔴" if status_display_for_label == "pending" else "🟢"
                    expander_label_parts.append(f"{status_emoji} {status_display_for_label}")
                    expander_label = " | ".join(expander_label_parts)


                    with st.expander(expander_label):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            if task_type_raw in ['rankings_and_search_volume', 'rankings_only']:
                              st.write(f"**Domain:** {task['domain']}")
                            created_at_str = task['created_at']
                            display_timestamp = "N/A"
                            if created_at_str:
                                try:
                                    created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                                    created_at_adjusted_dt = created_at_dt + timedelta(hours=2)
                                    display_timestamp = created_at_adjusted_dt.strftime('%Y-%m-%d %H:%M:%S')
                                except (ValueError, TypeError):
                                    display_timestamp = f"{created_at_str} (Error adjusting time)"
                            st.write(f"**Created:** {display_timestamp}")
                            st.write(f"**Status:** {task['status']}")

                            task_type_display = task.get('task_type', 'N/A')
                            if task_type_display == 'rankings_and_search_volume':
                                task_type_display = "Rankings & Search Volume"
                            elif task_type_display == 'search_volume_only':
                                task_type_display = "Search Volume Only"
                            elif task_type_display == 'rankings_only':
                                task_type_display = "Rankings Only"
                            st.write(f"**Task Type:** {task_type_display}")

                            # Only show Check Seasonality for non-rankings-only tasks
                            if task_type_raw != 'rankings_only':
                                st.write(f"**Check Seasonality:** {'Yes' if task.get('check_seasonality') else 'No'}")
                            st.write(f"**Include AI Overviews:** {'Yes' if task.get('check_ai_overviews') else 'No'}")
                            # NEW: Show Country, Language, Device
                            st.write(f"**Country:** {task.get('country', 'N/A')}")
                            st.write(f"**Language:** {task.get('language', 'N/A')}")
                            st.write(f"**Device:** {task.get('device', 'N/A')}")
                            st.write(f"**Export Language:** {task.get('export_language', 'English')}")
                        with col2:
                            if st.button("🗑️ Delete", key=f"delete_{task['task_id']}"):
                                if delete_task(task['task_id']):
                                    st.success("Task deleted successfully!")
                                    st.rerun()

                        if task['status'] == 'pending':
                            if st.button("Check Results", key=task['task_id']):
                                # Check if enough time has passed
                                time_elapsed, minutes = check_time_elapsed(task['created_at'])
                                if not time_elapsed:
                                    remaining_minutes = 2 - minutes
                                    remaining_seconds = int((remaining_minutes - int(remaining_minutes)) * 60)
                                    st.warning(f"Please wait {int(remaining_minutes)} minutes and {remaining_seconds} seconds before checking results.")

                                else:
                                    with st.spinner("Checking task results..."):
                                        sv_task_ids = json.loads(task['search_volume_task_ids']) if task['search_volume_task_ids'] else []
                                        serp_task_ids = json.loads(task['serp_task_ids']) if task['serp_task_ids'] else []

                                        if not sv_task_ids and not serp_task_ids:
                                            st.error("No task IDs found in database")
                                            return

                                        # Get previously processed tasks from database
                                        processed_sv_tasks = set(json.loads(task['processed_sv_tasks'])) if task.get('processed_sv_tasks') else set()
                                        processed_serp_tasks = set(json.loads(task['processed_serp_tasks'])) if task.get('processed_serp_tasks') else set()

                                        # Get results directly from check_tasks_ready using async version
                                        async def check_results_async():
                                            return await check_tasks_ready_async(
                                                async_client, sv_task_ids, serp_task_ids, processed_sv_tasks, processed_serp_tasks,
                                                check_ai_overviews=task.get('check_ai_overviews', False),
                                                domain=task.get('domain'),
                                                competitors=json.loads(task.get('competitors', '[]')) if task.get('competitors') else []
                                            )

                                        is_ready, errors, results, processed_sv_tasks, processed_serp_tasks = asyncio.run(check_results_async())

                                        # Update processed tasks in database
                                        update_processed_tasks(task['task_id'], processed_sv_tasks, processed_serp_tasks)

                                        # Check if ALL tasks are ready (completed)
                                        if is_ready:
                                            # All tasks are completed - update the task status to completed
                                            task_data = {
                                                'search_volume_results': results["sv_results"],
                                                'serp_results': results["serp_results"]
                                            }

                                            if update_task_status(task['task_id'], 'completed', task_data):
                                                st.success("All tasks completed! Results retrieved and saved!")
                                                time.sleep(2)  # Give user time to see the success message
                                                st.rerun()
                                        else:
                                            # Some tasks are still pending - save partial results but keep status as pending
                                            if results["sv_results"] or results["serp_results"]:
                                                # Save partial results without changing the task status
                                                task_data = {
                                                    'search_volume_results': results["sv_results"],
                                                    'serp_results': results["serp_results"]
                                                }
                                                update_task_status(task['task_id'], 'pending', task_data)
                                                st.info("Partial results available. Some tasks are still processing.")

                                            # Show appropriate message to user
                                            if errors:
                                                # Check if it's the "still in progress" message
                                                if any("still in progress" in error for error in errors):
                                                    st.info(errors[0])  # Show the informative message about pending tasks
                                                else:
                                                    st.error("Error retrieving results:")
                                                    for error in errors:
                                                        st.write(error)
                                            else:
                                                st.info("No results available yet. Please try again later.")

                        elif task['status'] == 'completed':
                            # Clear any cached data to ensure fresh processing
                            st.cache_data.clear()

                            try:
                                # Load the results from the database using new functions
                                sv_results = get_search_volume_results(task['task_id']) or []
                                serp_results = get_serp_results(task['task_id']) or []

                                # Fallback to old columns if new tables are empty (for backward compatibility)
                                if not sv_results and task.get('search_volume_results'):
                                    sv_results = json.loads(task['search_volume_results'])
                                if not serp_results and task.get('serp_results'):
                                    serp_results = json.loads(task['serp_results'])
                                keywords_dict = json.loads(task['keywords'])
                                keywords_df = pd.DataFrame.from_dict(keywords_dict)

                                # Get export language early
                                task_export_language = task.get('export_language', 'German')

                                # Create a search volume DataFrame
                                sv_df = pd.DataFrame(sv_results)

                                # Check if we have meaningful results
                                if len(sv_results) == 0 and len(serp_results) == 0:
                                    st.error("No results found. This task may have failed or the keywords may not have returned any data.")
                                    return
                                elif len(sv_results) == 0 and task.get('task_type') in ['rankings_and_search_volume']:
                                    st.warning("Search volume data is missing. Only SERP results are available.")

                                if not sv_df.empty:
                                    # Calculate seasonality if enabled
                                    if task.get('check_seasonality'):
                                        sv_df['seasonality'] = False
                                        sv_df['max_sv'] = 0
                                        sv_df['min_sv'] = 0
                                        sv_df['months_max_sv'] = ''

                                        for i in range(len(sv_df)):
                                            try:
                                                monthly_searches = sv_df['monthly_searches'][i]
                                                if monthly_searches and isinstance(monthly_searches, list):
                                                    monthly = pd.DataFrame(monthly_searches)
                                                    if len(monthly) > 0:
                                                        if (monthly['search_volume'].max() - monthly['search_volume'].min()) > sv_df['search_volume'][i]:
                                                            sv_df.loc[i, 'seasonality'] = True
                                                        sv_df.loc[i, 'max_sv'] = monthly['search_volume'].max()
                                                        sv_df.loc[i, 'min_sv'] = monthly['search_volume'].min()
                                                        # months_max_sv: Monate mit max_sv, aufsteigend sortiert
                                                        max_sv_value = monthly['search_volume'].max()
                                                        months_max_list = monthly['month'].loc[monthly['search_volume'] == max_sv_value].to_list()
                                                        months_max_list_sorted = sorted(months_max_list)
                                                        sv_df.loc[i, 'months_max_sv'] = str(months_max_list_sorted)
                                            except (KeyError, IndexError, TypeError, AttributeError) as e:
                                                st.warning(f"Could not process seasonality data for keyword {sv_df['keyword'][i] if 'keyword' in sv_df.columns else 'unknown'}: {str(e)}")
                                                continue

                                        # Monthly searches column is now preserved for process_serp_results or SV-only display

                                    if serp_results:  # If we have SERP results
                                        # Get competitors from the task data
                                        competitors = json.loads(task['competitors']) if task.get('competitors') else []

                                        # Process SERP results - pass empty DataFrame if no SV data
                                        sv_df_for_processing = sv_df if not sv_df.empty else pd.DataFrame()


                                        report_df, serp_df = process_serp_results(serp_results, sv_df_for_processing, task['domain'], competitors, check_ai_overviews=task.get('check_ai_overviews', False), export_language=task.get('export_language', 'English'), check_seasonality=task.get('check_seasonality', False), task_created_at=task.get('created_at'))

                                        # Display Report
                                        st.subheader("Report")
                                        show_dataframe(report_df, task.get('export_language', 'German'))

                                        # Create and display Top 10 SERP Data
                                        top10serp_df = transpose_serp_results(serp_df)

                                        st.subheader("Top 10 SERP Data")
                                        show_dataframe(top10serp_df, task.get('export_language', 'German'), is_top10serp=True)

                                        # Download combined Excel file
                                        download_excel_link(report_df, top10serp_df, f"results_{task['task_id']}", export_language=task_export_language)
                                    else:
                                        # Search volume only results
                                        st.subheader("Search Volume Results")

                                        # Prepare sv_df for display with expanded monthly columns
                                        sv_df_display_list = []

                                        all_monthly_headers_sv_only = set()
                                        if task.get('check_seasonality') and 'monthly_searches' in sv_df.columns:
                                            for _idx, sv_row in sv_df.iterrows():
                                                monthly_list = sv_row.get('monthly_searches')
                                                if isinstance(monthly_list, list):
                                                    for month_data in monthly_list:
                                                        if isinstance(month_data, dict) and 'year' in month_data and 'month' in month_data:
                                                            header = f"{month_data['year']}-{str(month_data['month']).zfill(2)}"
                                                            all_monthly_headers_sv_only.add(header)
                                        sorted_monthly_headers_sv_only = sorted(list(all_monthly_headers_sv_only))

                                        for _idx, row in sv_df.iterrows():
                                            new_row_data = {
                                                'keyword': row.get('keyword'),
                                                'search_volume': row.get('search_volume'),
                                                'competition': row.get('competition'),
                                                'cpc': row.get('cpc')
                                            }
                                            # Add monthly search data only if seasonality is checked
                                            if task.get('check_seasonality'):
                                                for header in sorted_monthly_headers_sv_only:
                                                    new_row_data[header] = None

                                                monthly_list_for_keyword = row.get('monthly_searches')
                                                if isinstance(monthly_list_for_keyword, list):
                                                    for month_data_item in monthly_list_for_keyword:
                                                        if isinstance(month_data_item, dict) and 'year' in month_data_item and 'month' in month_data_item:
                                                            header = f"{month_data_item['year']}-{str(month_data_item['month']).zfill(2)}"
                                                            new_row_data[header] = month_data_item.get('search_volume')

                                            # Add seasonality data if present
                                            if task.get('check_seasonality'):
                                                if 'seasonality' in row: new_row_data['seasonality'] = row.get('seasonality')
                                                if 'max_sv' in row: new_row_data['max_sv'] = row.get('max_sv')
                                                # Add min_sv
                                                if 'min_sv' in row: new_row_data['min_sv'] = row.get('min_sv')
                                                # Sort months_max_sv ascending if present and is a list
                                                months_max = row.get('months_max_sv')
                                                if isinstance(months_max, list):
                                                    new_row_data['months_max_sv'] = str(sorted(months_max))
                                                else:
                                                    new_row_data['months_max_sv'] = months_max
                                            sv_df_display_list.append(new_row_data)

                                        sv_df_final = pd.DataFrame(sv_df_display_list)

                                        # Define column order
                                        final_sv_cols = ['keyword', 'search_volume']
                                        final_sv_cols.extend(['competition', 'cpc'])
                                        if task.get('check_seasonality'):
                                            if 'seasonality' in sv_df_final.columns: final_sv_cols.append('seasonality')
                                            if 'max_sv' in sv_df_final.columns: final_sv_cols.append('max_sv')
                                            if 'min_sv' in sv_df_final.columns: final_sv_cols.append('min_sv')
                                            if 'months_max_sv' in sv_df_final.columns: final_sv_cols.append('months_max_sv')

                                        # Add monthly search columns at the end only if seasonality is checked
                                        if task.get('check_seasonality') and sorted_monthly_headers_sv_only:
                                            final_sv_cols.extend(sorted_monthly_headers_sv_only)

                                        for col in final_sv_cols: # Ensure all columns exist
                                            if col not in sv_df_final.columns:
                                                sv_df_final[col] = None
                                        sv_df_final = sv_df_final.reindex(columns=final_sv_cols)

                                        show_dataframe(sv_df_final)
                                        download_excel_link(sv_df_final, None, f"search_volume_{task['task_id']}", export_language=task_export_language)

                                elif task.get('task_type') == 'rankings_only' and serp_results:
                                    # Rankings only results
                                    st.subheader("Rankings Report")

                                    # Get competitors from the task data
                                    competitors = json.loads(task['competitors']) if task.get('competitors') else []

                                    # Process SERP results with empty search volume DataFrame
                                    empty_sv_df = pd.DataFrame()
                                    report_df, serp_df = process_serp_results(serp_results, empty_sv_df, task['domain'], competitors, check_ai_overviews=task.get('check_ai_overviews', False), export_language=task.get('export_language', 'English'), check_seasonality=False, rankings_only=True, task_created_at=task.get('created_at'))

                                    # Display Report
                                    show_dataframe(report_df, task.get('export_language', 'German'))

                                    # Create and display Top 10 SERP Data
                                    top10serp_df = transpose_serp_results(serp_df, rankings_only=True)

                                    st.subheader("Top 10 SERP Data")
                                    show_dataframe(top10serp_df, task.get('export_language', 'German'), is_top10serp=True)

                                    # Download combined Excel file
                                    download_excel_link(report_df, top10serp_df, f"rankings_{task['task_id']}", export_language=task_export_language)
                            except Exception as e:
                                st.error(f"Error processing results: {str(e)}")
                                st.write("Raw search volume results:", task['search_volume_results'])
                                st.write("Raw SERP results:", task['serp_results'])
            else:
                st.info("No tasks found. Create a new task in the 'Create Task' tab.")

def run_authenticated_main():
    """Main function for authenticated users"""
    main()

if __name__ == "__main__":
    if not authentication_status:
        st.warning("⚠️ Please log in to access the Keywords Tool.")
        st.info("Use the login button in the sidebar to authenticate with Microsoft.")
    else:
        # Logout button for authenticated users
        logout()
        run_authenticated_main()
