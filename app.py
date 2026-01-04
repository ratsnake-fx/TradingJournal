import streamlit as st
import pandas as pd
import json
import uuid
from datetime import datetime, time
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# --- PAGE CONFIG ---
st.set_page_config(page_title="Pro Trading Journal", layout="wide", page_icon="📈")

# --- PASSWORTSCHUTZ ---
def check_password():
    """Prüft ob das Passwort korrekt ist"""
    
    def password_entered():
        """Callback wenn Passwort eingegeben wurde"""
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Passwort nicht im State behalten
        else:
            st.session_state["password_correct"] = False

    # Erstes Mal oder Passwort falsch
    if "password_correct" not in st.session_state:
        st.markdown("""
        <div style="display: flex; justify-content: center; align-items: center; height: 60vh;">
            <div style="text-align: center;">
                <h1>🦅 Trading Journal</h1>
                <p style="color: #888;">Bitte Passwort eingeben</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input(
                "Passwort", 
                type="password", 
                on_change=password_entered, 
                key="password",
                placeholder="Passwort eingeben..."
            )
        return False
    
    elif not st.session_state["password_correct"]:
        st.markdown("""
        <div style="display: flex; justify-content: center; align-items: center; height: 60vh;">
            <div style="text-align: center;">
                <h1>🦅 Trading Journal</h1>
                <p style="color: #888;">Bitte Passwort eingeben</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input(
                "Passwort", 
                type="password", 
                on_change=password_entered, 
                key="password",
                placeholder="Passwort eingeben..."
            )
            st.error("❌ Falsches Passwort")
        return False
    
    return True

# Passwort prüfen - wenn falsch, stoppe hier
if not check_password():
    st.stop()

# --- GOOGLE SHEETS SETUP ---
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Google Drive Images Folder ID
IMAGES_FOLDER_ID = "1NeI3YSdPMxyjIEywNonPfifJSUwhWGQI"

@st.cache_resource
def get_google_client():
    """Erstellt Google Sheets Client aus Streamlit Secrets oder lokaler Datei"""
    try:
        # Versuche zuerst Streamlit Secrets (für Cloud Deployment)
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except:
        # Fallback: Lokale JSON Datei
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    
    return gspread.authorize(creds)

def get_drive_service():
    """Erstellt Google Drive Service für Datei-Uploads"""
    from googleapiclient.discovery import build
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    
    return build('drive', 'v3', credentials=creds)

def upload_image_to_drive(uploaded_file, trade_id, image_number):
    """Lädt ein Bild zu Google Drive hoch und gibt die File-ID zurück"""
    from googleapiclient.http import MediaIoBaseUpload
    import io
    
    drive_service = get_drive_service()
    
    # Dateiname: TradeID_Bildnummer.extension (z.B. 00001NQ04012026_01.png)
    file_extension = uploaded_file.name.split('.')[-1].lower()
    filename = f"{trade_id}_{image_number:02d}.{file_extension}"
    
    # Metadata für die Datei
    file_metadata = {
        'name': filename,
        'parents': [IMAGES_FOLDER_ID]
    }
    
    # Datei hochladen
    media = MediaIoBaseUpload(
        io.BytesIO(uploaded_file.getvalue()),
        mimetype=uploaded_file.type,
        resumable=True
    )
    
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink, webContentLink'
    ).execute()
    
    # Datei öffentlich lesbar machen für Anzeige
    drive_service.permissions().create(
        fileId=file['id'],
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return {
        'id': file['id'],
        'name': filename,
        'link': f"https://drive.google.com/uc?id={file['id']}"
    }

def get_images_for_trade(trade_id):
    """Holt alle Bilder für einen Trade aus Google Drive"""
    try:
        drive_service = get_drive_service()
        
        # Suche nach Dateien die mit der Trade-ID beginnen
        query = f"'{IMAGES_FOLDER_ID}' in parents and name contains '{trade_id}' and trashed=false"
        results = drive_service.files().list(
            q=query,
            fields="files(id, name, webViewLink, webContentLink)"
        ).execute()
        
        files = results.get('files', [])
        
        # Erstelle URLs für die Bilder
        images = []
        for f in files:
            images.append({
                'id': f['id'],
                'name': f['name'],
                'url': f"https://drive.google.com/uc?id={f['id']}"
            })
        
        return images
    except Exception as e:
        st.warning(f"Fehler beim Laden der Bilder: {e}")
        return []

def delete_image_from_drive(file_id):
    """Löscht ein Bild aus Google Drive"""
    try:
        drive_service = get_drive_service()
        drive_service.files().delete(fileId=file_id).execute()
        return True
    except:
        return False

@st.cache_resource
def get_or_create_spreadsheet():
    """Holt oder erstellt das Trading Journal Spreadsheet"""
    client = get_google_client()
    
    try:
        # Versuche existierendes Spreadsheet zu öffnen
        spreadsheet = client.open("TradingJournal_Data")
    except gspread.SpreadsheetNotFound:
        # Erstelle neues Spreadsheet im geteilten Ordner
        spreadsheet = client.create("TradingJournal_Data")
        
        # Erstelle Worksheets
        # Trades Sheet
        trades_ws = spreadsheet.sheet1
        trades_ws.update_title("Trades")
        trades_ws.update('A1:M1', [["id", "trade_id", "date", "time", "account", "asset", "direction", "pnl", "notes", "tags", "checklist", "reviewed", "created_at"]])
        
        # Settings Sheet
        settings_ws = spreadsheet.add_worksheet(title="Settings", rows=100, cols=10)
        settings_ws.update('A1:B1', [["key", "value"]])
        default_settings = {
            "accounts": json.dumps(["-- Kein Konto --", "Privat", "FTMO 12.2025 100K"]),
            "assets": json.dumps(["-- Kein Asset --", "NQ", "ES", "DAX", "EURUSD", "GOLD", "GBPJPY", "USDCAD", "CADCHF", "YEN BASKET"])
        }
        settings_ws.update('A2:B3', [["accounts", default_settings["accounts"]], ["assets", default_settings["assets"]]])
        
        # Checklist Schema Sheet
        checklist_ws = spreadsheet.add_worksheet(title="ChecklistSchema", rows=100, cols=10)
        checklist_ws.update('A1:B1', [["schema_json", ""]])
        default_checklist = get_default_checklist()
        checklist_ws.update('A2', [[json.dumps(default_checklist, ensure_ascii=False)]])
    
    return spreadsheet

def get_default_checklist():
    return {
        "Markt-Status": {
            "m_range": {"label": "Range Markt", "description": "Der Markt bewegt sich seitwärts.", "image": None, "order": 0},
            "m_long": {"label": "Long Trend", "description": "Klarer Aufwärtstrend.", "image": None, "order": 1},
            "m_short": {"label": "Short Trend", "description": "Klarer Abwärtstrend.", "image": None, "order": 2}
        },
        "Setup & Play": {
            "p_vwap": {"label": "VWAP Play", "description": "Trade basiert auf VWAP.", "image": None, "order": 0},
            "p_manip": {"label": "Manipulation", "description": "Manipulation Zone erkannt.", "image": None, "order": 1},
            "p_wol": {"label": "WOL", "description": "Week Open Level.", "image": None, "order": 2},
            "p_mm": {"label": "Market Maker", "description": "Market Maker Setup.", "image": None, "order": 3}
        },
        "Einstieg & Risk": {
            "e_liq": {"label": "Liquidität", "description": "Einstieg nach Liquiditäts-Sweep.", "image": None, "order": 0},
            "e_val": {"label": "Value Area", "description": "Einstieg in Value Area.", "image": None, "order": 1},
            "r_ok": {"label": "Risk Mgmt (1-2%)", "description": "Risikomanagement eingehalten.", "image": None, "order": 2}
        },
        "Ergebnis": {
            "winner": {"label": "Winner", "description": "", "image": None, "order": 0},
            "looser": {"label": "Looser", "description": "", "image": None, "order": 1},
            "n_plan": {"label": "Nach Plan", "description": "", "image": None, "order": 2}
        }
    }

# --- STYLE CSS ---
st.markdown("""
<style>
    .stMetric { background-color: #1E1E1E; border: 1px solid #333; border-radius: 5px; padding: 10px; }
    .kw-header { color: #4CAF50; font-size: 1.5em; margin-top: 20px; margin-bottom: 10px; border-bottom: 1px solid #444; }
    .stCheckbox { margin-bottom: -10px; }
    .trade-id-box { 
        background-color: #2d2d2d; 
        border: 1px solid #4CAF50; 
        border-radius: 5px; 
        padding: 8px 12px; 
        font-family: monospace; 
        font-size: 1.1em;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# --- DATA FUNCTIONS ---

def load_settings():
    """Lädt Settings aus Google Sheets"""
    spreadsheet = get_or_create_spreadsheet()
    settings_ws = spreadsheet.worksheet("Settings")
    data = settings_ws.get_all_records()
    
    settings = {}
    for row in data:
        try:
            settings[row["key"]] = json.loads(row["value"])
        except:
            settings[row["key"]] = row["value"]
    
    # Defaults falls nicht vorhanden
    if "accounts" not in settings:
        settings["accounts"] = ["-- Kein Konto --", "Privat"]
    if "assets" not in settings:
        settings["assets"] = ["-- Kein Asset --", "NQ", "ES"]
    
    return settings

def save_settings(settings):
    """Speichert Settings in Google Sheets"""
    spreadsheet = get_or_create_spreadsheet()
    settings_ws = spreadsheet.worksheet("Settings")
    
    # Clear and rewrite
    settings_ws.clear()
    settings_ws.update('A1:B1', [["key", "value"]])
    
    rows = []
    for key, value in settings.items():
        rows.append([key, json.dumps(value) if isinstance(value, list) else value])
    
    if rows:
        settings_ws.update(f'A2:B{len(rows)+1}', rows)

def load_checklist_schema():
    """Lädt Checklist Schema aus Google Sheets"""
    spreadsheet = get_or_create_spreadsheet()
    try:
        checklist_ws = spreadsheet.worksheet("ChecklistSchema")
        schema_json = checklist_ws.acell('A2').value
        if schema_json:
            return json.loads(schema_json)
    except:
        pass
    return get_default_checklist()

def save_checklist_schema(schema):
    """Speichert Checklist Schema in Google Sheets"""
    spreadsheet = get_or_create_spreadsheet()
    checklist_ws = spreadsheet.worksheet("ChecklistSchema")
    checklist_ws.update('A2', [[json.dumps(schema, ensure_ascii=False)]])

def load_data():
    """Lädt Trades aus Google Sheets"""
    spreadsheet = get_or_create_spreadsheet()
    trades_ws = spreadsheet.worksheet("Trades")
    
    data = trades_ws.get_all_records()
    if not data:
        return pd.DataFrame(columns=["id", "trade_id", "date", "time", "account", "asset", "direction", "pnl", "notes", "tags", "checklist", "reviewed", "created_at"])
    
    df = pd.DataFrame(data)
    
    # Konvertierungen
    if "date" in df.columns and len(df) > 0:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    if "reviewed" in df.columns:
        df["reviewed"] = df["reviewed"].apply(lambda x: x == "True" or x == True)
    if "pnl" in df.columns:
        df["pnl"] = pd.to_numeric(df["pnl"], errors='coerce').fillna(0)
    
    return df

@st.cache_data(ttl=60)  # Cache für 60 Sekunden
def load_data_cached():
    """Gecachte Version von load_data - reduziert API Anfragen"""
    return load_data()

def get_next_trade_number():
    """Ermittelt die nächste fortlaufende Trade-Nummer"""
    df = load_data_cached()
    if df.empty:
        return 1
    
    if "trade_id" not in df.columns:
        return 1
    
    max_num = 0
    for tid in df["trade_id"]:
        try:
            tid_str = str(tid)
            if len(tid_str) >= 5 and tid_str[:5].isdigit():
                num = int(tid_str[:5])
                max_num = max(max_num, num)
        except:
            pass
    
    return max_num + 1 if max_num > 0 else 1

def generate_trade_id(asset, date):
    """Generiert Trade-ID im Format: 00001XAUUSD03012026"""
    num = get_next_trade_number()
    asset_clean = asset.replace(" ", "").replace("-", "").replace("--", "").upper()
    if asset_clean == "KEINASSET":
        asset_clean = "NONE"
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d")
    date_str = date.strftime("%d%m%Y")
    return f"{num:05d}{asset_clean}{date_str}"

def save_entry(entry_data, mode="new"):
    """Speichert einen Trade in Google Sheets"""
    spreadsheet = get_or_create_spreadsheet()
    trades_ws = spreadsheet.worksheet("Trades")
    
    # Checklist zu JSON konvertieren
    if isinstance(entry_data.get("checklist"), dict):
        entry_data["checklist"] = json.dumps(entry_data["checklist"])
    
    # Time zu String
    if isinstance(entry_data.get("time"), time):
        entry_data["time"] = entry_data["time"].strftime("%H:%M")
    
    # Date zu String
    if hasattr(entry_data.get("date"), 'strftime'):
        entry_data["date"] = entry_data["date"].strftime("%Y-%m-%d")
    
    # Reviewed zu String
    entry_data["reviewed"] = str(entry_data.get("reviewed", False))
    
    # Created timestamp
    if "created_at" not in entry_data:
        entry_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if mode == "edit":
        # Finde und update existierende Zeile
        all_data = trades_ws.get_all_values()
        headers = all_data[0]
        
        for i, row in enumerate(all_data[1:], start=2):
            if row[0] == entry_data["id"]:
                # Update diese Zeile
                new_row = [entry_data.get(h, "") for h in headers]
                trades_ws.update(f'A{i}:M{i}', [new_row])
                return
    
    # Neue Zeile hinzufügen
    headers = ["id", "trade_id", "date", "time", "account", "asset", "direction", "pnl", "notes", "tags", "checklist", "reviewed", "created_at"]
    new_row = [str(entry_data.get(h, "")) for h in headers]
    trades_ws.append_row(new_row)

def delete_entry(entry_id):
    """Löscht einen Trade aus Google Sheets"""
    spreadsheet = get_or_create_spreadsheet()
    trades_ws = spreadsheet.worksheet("Trades")
    
    all_data = trades_ws.get_all_values()
    for i, row in enumerate(all_data[1:], start=2):
        if row[0] == entry_id:
            trades_ws.delete_rows(i)
            return

def update_review_status(trade_id, status):
    """Aktualisiert den Review-Status eines Trades"""
    spreadsheet = get_or_create_spreadsheet()
    trades_ws = spreadsheet.worksheet("Trades")
    
    all_data = trades_ws.get_all_values()
    headers = all_data[0]
    reviewed_col = headers.index("reviewed") + 1
    
    for i, row in enumerate(all_data[1:], start=2):
        if row[0] == trade_id:
            trades_ws.update_cell(i, reviewed_col, str(status))
            return

# --- PLOTLY HELPERS ---
def plot_gauge(value, title, min_val=0, max_val=100):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number", value = value, title = {'text': title},
        gauge = {'axis': {'range': [min_val, max_val]}, 'bar': {'color': "#00cc96" if value > 50 else "#EF553B"}}
    ))
    fig.update_layout(height=150, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)")
    return fig

# --- APP START ---
try:
    settings = load_settings()
    df = load_data()
    checklist_schema = load_checklist_schema()
    connection_ok = True
except Exception as e:
    st.error(f"⚠️ Verbindung zu Google Sheets fehlgeschlagen: {e}")
    st.info("Bitte prüfe deine Credentials und Internetverbindung.")
    connection_ok = False
    settings = {"accounts": ["-- Kein Konto --"], "assets": ["-- Kein Asset --"]}
    df = pd.DataFrame()
    checklist_schema = get_default_checklist()

if "success_msg" in st.session_state:
    st.toast(st.session_state["success_msg"], icon="✅")
    del st.session_state["success_msg"]

st.title("🦅 Trading Journal Command Center")

if connection_ok:
    st.caption("☁️ Verbunden mit Google Sheets")

# --- TABS ---
tab_input, tab_journal, tab_dash, tab_checklist, tab_settings = st.tabs([
    "➕ Neuer Trade", 
    "🗂️ Tagebuch", 
    "📊 Dashboard", 
    "✅ Checkliste",
    "⚙️ Einstellungen"
])

# =========================================================
# TAB 1: NEUER TRADE (INPUT)
# =========================================================
with tab_input:
    st.header("Neuen Trade erfassen")
    
    # Zeige letzte Trade-ID zum Kopieren
    if "last_trade_id" in st.session_state:
        trade_id_value = st.session_state["last_trade_id"]
        
        st.success(f"✅ Trade erfolgreich gespeichert!")
        st.markdown("### 🆔 Deine Trade-ID:")
        
        st.markdown(f"""
        <div style="
            background-color: #1a1a2e; 
            border: 2px solid #4CAF50; 
            border-radius: 10px; 
            padding: 15px 20px; 
            margin: 10px 0;
        ">
            <code style="
                font-size: 1.4em; 
                font-weight: bold; 
                color: #4CAF50;
                letter-spacing: 1px;
            ">{trade_id_value}</code>
        </div>
        """, unsafe_allow_html=True)
        
        st.text_input(
            "Trade-ID (markieren & kopieren):", 
            value=trade_id_value, 
            key="copy_field",
            disabled=False,
            label_visibility="collapsed"
        )
        
        if st.button("✖️ Schliessen & Neuen Trade erfassen", key="close_trade_id"):
            del st.session_state["last_trade_id"]
            st.rerun()
        
        st.markdown("---")
    
    # Trade Eingabe
    c1, c2, c3, c4 = st.columns(4)
    i_date = c1.date_input("Datum", datetime.now(), key="input_date")
    i_time = c1.time_input("Uhrzeit", datetime.now().time(), key="input_time")
    i_acc = c2.selectbox("Konto", settings["accounts"], key="input_account")
    i_ass = c3.selectbox("Asset", settings["assets"], key="input_asset")
    i_dir = c4.selectbox("Richtung", ["Long", "Short"], key="input_direction")
    
    # Live Trade-ID Vorschau
    preview_trade_id = generate_trade_id(i_ass, i_date)
    st.markdown(f"""
    <div style="
        background-color: #2d2d2d; 
        border: 1px solid #666; 
        border-radius: 8px; 
        padding: 10px 15px; 
        margin: 10px 0;
        display: flex;
        align-items: center;
        gap: 15px;
    ">
        <span style="color: #888;">🆔 Trade-ID:</span>
        <code style="
            font-size: 1.2em; 
            font-weight: bold; 
            color: #4CAF50;
            letter-spacing: 1px;
        ">{preview_trade_id}</code>
        <span style="color: #666; font-size: 0.85em;">(wird beim Speichern vergeben)</span>
    </div>
    """, unsafe_allow_html=True)
    
    c5, c6 = st.columns(2)
    i_pnl = c5.number_input("PnL ($)", step=10.0, value=0.0, key="input_pnl")
    i_tags = c6.text_input("Tags", placeholder="Setup A, Fehler B...", key="input_tags")
    
    st.markdown("---")
    st.subheader("Checkliste")
    
    cl_data = {}
    cols = st.columns(3)
    idx = 0
    for cat, items in checklist_schema.items():
        with cols[idx % 3]:
            st.markdown(f"**{cat}**")
            sorted_items = sorted(items.items(), key=lambda x: x[1].get("order", 0))
            for k, item_info in sorted_items:
                help_text = item_info.get("description", "")
                cl_data[k] = st.checkbox(
                    item_info["label"], 
                    key=f"new_{k}",
                    help=help_text if help_text else None
                )
        idx += 1
        
    st.markdown("---")
    i_notes = st.text_area("Notizen", key="input_notes")
    
    # Screenshot Upload
    st.markdown("---")
    st.subheader("📷 Screenshots")
    i_files = st.file_uploader(
        "Bilder hochladen", 
        accept_multiple_files=True, 
        type=['png', 'jpg', 'jpeg', 'gif'],
        key="input_files"
    )
    if i_files:
        st.info(f"{len(i_files)} Bild(er) ausgewählt - werden beim Speichern hochgeladen")
    
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("💾 Trade Speichern", type="primary", use_container_width=True):
            trade_id = generate_trade_id(i_ass, i_date)
            entry = {
                "id": str(uuid.uuid4()),
                "trade_id": trade_id,
                "date": i_date, "time": i_time, "account": i_acc, "asset": i_ass,
                "direction": i_dir, "pnl": i_pnl, "notes": i_notes, "tags": i_tags,
                "checklist": cl_data, "reviewed": False
            }
            save_entry(entry)
            
            # Bilder hochladen
            if i_files:
                with st.spinner("Bilder werden hochgeladen..."):
                    for img_num, uploaded_file in enumerate(i_files, start=1):
                        try:
                            upload_image_to_drive(uploaded_file, trade_id, img_num)
                        except Exception as e:
                            st.warning(f"Fehler beim Upload von {uploaded_file.name}: {e}")
            
            st.session_state["success_msg"] = f"Trade {trade_id} gespeichert!"
            st.session_state["last_trade_id"] = trade_id
            # Cache leeren damit neue Daten geladen werden
            st.cache_data.clear()
            st.rerun()

# =========================================================
# TAB 2: TAGEBUCH LISTE
# =========================================================
with tab_journal:
    st.header("📖 Mein Trading Tagebuch")
    
    # Refresh Button
    if st.button("🔄 Aktualisieren"):
        st.cache_data.clear()
        st.rerun()
    
    # Suchfunktion
    search_col1, search_col2, search_col3 = st.columns([3, 2, 1])
    with search_col1:
        search_query = st.text_input(
            "🔍 Suche", 
            placeholder="Trade-ID, Tags, Asset, Notizen...",
            key="search_query",
            label_visibility="collapsed"
        )
    with search_col2:
        search_field = st.selectbox(
            "Suchen in",
            ["Alles", "Trade-ID", "Tags", "Asset", "Notizen", "Konto"],
            key="search_field",
            label_visibility="collapsed"
        )
    with search_col3:
        if st.button("✖️ Reset", key="clear_search"):
            st.session_state["search_query"] = ""
            st.rerun()
    
    st.markdown("---")
    
    # Daten neu laden für aktuelle Ansicht
    df = load_data()
    
    if df.empty:
        st.info("Noch keine Einträge.")
    else:
        df["datetime_sort"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
        df_sorted = df.sort_values(by="datetime_sort", ascending=False)
        
        # Filter anwenden
        if search_query:
            search_lower = search_query.lower()
            
            if search_field == "Trade-ID":
                mask = df_sorted["trade_id"].astype(str).str.lower().str.contains(search_lower, na=False)
            elif search_field == "Tags":
                mask = df_sorted["tags"].astype(str).str.lower().str.contains(search_lower, na=False)
            elif search_field == "Asset":
                mask = df_sorted["asset"].astype(str).str.lower().str.contains(search_lower, na=False)
            elif search_field == "Notizen":
                mask = df_sorted["notes"].astype(str).str.lower().str.contains(search_lower, na=False)
            elif search_field == "Konto":
                mask = df_sorted["account"].astype(str).str.lower().str.contains(search_lower, na=False)
            else:
                mask = (
                    df_sorted["trade_id"].astype(str).str.lower().str.contains(search_lower, na=False) |
                    df_sorted["tags"].astype(str).str.lower().str.contains(search_lower, na=False) |
                    df_sorted["asset"].astype(str).str.lower().str.contains(search_lower, na=False) |
                    df_sorted["notes"].astype(str).str.lower().str.contains(search_lower, na=False) |
                    df_sorted["account"].astype(str).str.lower().str.contains(search_lower, na=False)
                )
            
            df_filtered = df_sorted[mask]
            st.info(f"🔍 {len(df_filtered)} Treffer für '{search_query}'")
        else:
            df_filtered = df_sorted
        
        if df_filtered.empty:
            st.warning("Keine Trades gefunden.")
        else:
            current_kw = None
            
            for index, row in df_filtered.iterrows():
                date_obj = row["date"]
                isocal = date_obj.isocalendar()
                kw_label = f"KW {isocal[1]} / {isocal[0]}"
                if kw_label != current_kw:
                    st.markdown(f"<div class='kw-header'>{kw_label}</div>", unsafe_allow_html=True)
                    current_kw = kw_label
                
                status = "✅" if row["reviewed"] else "⭕"
                pnl_color = "🟢" if row["pnl"] >= 0 else "🔴"
                trade_id_display = str(row.get("trade_id", ""))[:15] + "..." if len(str(row.get("trade_id", ""))) > 15 else str(row.get("trade_id", "N/A"))
                expander_title = f"{status} [{trade_id_display}] {row['asset']} {row['direction']} | {row['account']} | {row['date']} {row['time']} | {pnl_color} {row['pnl']} $"
                
                with st.expander(expander_title, expanded=False):
                    st.markdown("**Trade-ID:**")
                    st.code(row.get("trade_id", "N/A"), language=None)
                    
                    edit_key = f"edit_{row['id']}"
                    if edit_key not in st.session_state: 
                        st.session_state[edit_key] = False
                    
                    if st.session_state[edit_key]:
                        # Edit Mode
                        with st.form(f"form_{row['id']}"):
                            c1, c2, c3 = st.columns(3)
                            e_date = c1.date_input("Datum", row["date"])
                            try: 
                                val_time = datetime.strptime(str(row["time"]), "%H:%M").time()
                            except: 
                                val_time = time(0,0)
                            e_time = c1.time_input("Uhrzeit", val_time)
                            e_acc = c2.selectbox("Konto", settings["accounts"], index=settings["accounts"].index(row["account"]) if row["account"] in settings["accounts"] else 0)
                            e_ass = c3.selectbox("Asset", settings["assets"], index=settings["assets"].index(row["asset"]) if row["asset"] in settings["assets"] else 0)
                            e_dir = c3.selectbox("Richtung", ["Long", "Short"], index=0 if row["direction"] == "Long" else 1)
                            e_pnl = st.number_input("PnL", value=float(row["pnl"]))
                            e_tags = st.text_input("Tags", value=str(row.get("tags", "")))
                            e_notes = st.text_area("Notizen", str(row.get("notes", "")))
                            
                            st.subheader("Checkliste anpassen")
                            try: 
                                saved_cl = json.loads(row["checklist"]) if isinstance(row["checklist"], str) else row["checklist"]
                            except: 
                                saved_cl = {}
                            new_cl_data = {}
                            cc_cols = st.columns(3)
                            cc_idx = 0
                            for cat, items in checklist_schema.items():
                                with cc_cols[cc_idx % 3]:
                                    st.markdown(f"**{cat}**")
                                    sorted_items = sorted(items.items(), key=lambda x: x[1].get("order", 0))
                                    for k, item_info in sorted_items:
                                        help_text = item_info.get("description", "")
                                        val = st.checkbox(
                                            item_info["label"], 
                                            value=saved_cl.get(k, False), 
                                            key=f"edit_{row['id']}_{k}",
                                            help=help_text if help_text else None
                                        )
                                        new_cl_data[k] = val
                                cc_idx += 1
                            
                            if st.form_submit_button("Änderungen speichern"):
                                updated_entry = {
                                    "id": row["id"],
                                    "trade_id": row.get("trade_id", ""),
                                    "date": e_date,
                                    "time": e_time,
                                    "account": e_acc,
                                    "asset": e_ass,
                                    "direction": e_dir,
                                    "pnl": e_pnl,
                                    "tags": e_tags,
                                    "notes": e_notes,
                                    "checklist": new_cl_data,
                                    "reviewed": row.get("reviewed", False),
                                    "created_at": row.get("created_at", "")
                                }
                                save_entry(updated_entry, mode="edit")
                                st.session_state[edit_key] = False
                                st.session_state["success_msg"] = "Trade aktualisiert!"
                                st.cache_data.clear()
                                st.rerun()
                        
                        if st.button("Abbrechen", key=f"cncl_{row['id']}"):
                            st.session_state[edit_key] = False
                            st.rerun()
                    else:
                        # View Mode
                        st.subheader("Details & Checkliste")
                        vc1, vc2 = st.columns([1, 2])
                        
                        with vc1:
                            st.markdown(f"**Notizen:**")
                            st.info(row['notes'] if row['notes'] else "- keine -")
                            st.markdown(f"**Tags:** {row.get('tags', '-')}")
                            
                            # Bilder aus Google Drive laden
                            trade_id_for_images = str(row.get("trade_id", ""))
                            if trade_id_for_images:
                                images = get_images_for_trade(trade_id_for_images)
                                if images:
                                    st.markdown("**📷 Screenshots:**")
                                    for img in images:
                                        st.image(img['url'], caption=img['name'], use_container_width=True)
                        
                        with vc2:
                            try: 
                                saved_cl = json.loads(row["checklist"]) if isinstance(row["checklist"], str) else row["checklist"]
                            except: 
                                saved_cl = {}
                            
                            v_cols = st.columns(3)
                            v_idx = 0
                            for cat, items in checklist_schema.items():
                                with v_cols[v_idx % 3]:
                                    st.caption(f"**{cat}**")
                                    sorted_items = sorted(items.items(), key=lambda x: x[1].get("order", 0))
                                    for k, item_info in sorted_items:
                                        is_checked = saved_cl.get(k, False)
                                        help_text = item_info.get("description", "")
                                        st.checkbox(
                                            item_info["label"], 
                                            value=is_checked, 
                                            disabled=True, 
                                            key=f"view_{row['id']}_{k}",
                                            help=help_text if help_text else None
                                        )
                                v_idx += 1
                        
                        st.divider()
                        b1, b2, b3 = st.columns([1, 1, 4])
                        if b1.button("✏️ Editieren", key=f"be_{row['id']}"):
                            st.session_state[edit_key] = True
                            st.rerun()
                        
                        btn_txt = "Als offen markieren" if row["reviewed"] else "✅ Als Reviewed markieren"
                        if b2.button(btn_txt, key=f"br_{row['id']}"):
                            update_review_status(row["id"], not row["reviewed"])
                            st.cache_data.clear()
                            st.rerun()
                        
                        if b3.button("🗑️ Löschen", key=f"del_{row['id']}"):
                            delete_entry(row["id"])
                            st.cache_data.clear()
                            st.warning("Gelöscht!")
                            st.rerun()

# =========================================================
# TAB 3: DASHBOARD
# =========================================================
with tab_dash:
    df = load_data()
    if df.empty:
        st.info("Keine Daten.")
    else:
        total_pnl = df["pnl"].sum()
        win_rate = (len(df[df["pnl"] > 0]) / len(df) * 100) if len(df) > 0 else 0
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Net P&L", f"{total_pnl:.2f} $")
        k2.plotly_chart(plot_gauge(win_rate, "Win Rate"), use_container_width=True)
        k3.metric("Trades", len(df))
        
        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            daily = df.groupby("date")["pnl"].sum().reset_index()
            fig = px.bar(daily, x="date", y="pnl", color="pnl", color_continuous_scale=["red", "green"], title="Daily PnL")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Letzte Aktivitäten")
            st.dataframe(df[["date", "asset", "pnl"]].sort_values("date", ascending=False).head(5), hide_index=True)

# =========================================================
# TAB 4: CHECKLISTE VERWALTEN
# =========================================================
with tab_checklist:
    st.header("✅ Checkliste verwalten")
    st.markdown("Kategorien und Checklisten-Punkte verwalten.")
    
    categories = list(checklist_schema.keys())
    
    col_cat1, col_cat2 = st.columns([2, 1])
    with col_cat1:
        selected_cat = st.selectbox("Kategorie auswählen", categories)
    with col_cat2:
        st.markdown("")
        st.markdown("")
        if st.button("➕ Neue Kategorie"):
            st.session_state["show_new_cat"] = True
    
    if st.session_state.get("show_new_cat", False):
        with st.form("new_category_form"):
            new_cat_name = st.text_input("Name der neuen Kategorie")
            col1, col2 = st.columns(2)
            if col1.form_submit_button("Erstellen"):
                if new_cat_name and new_cat_name not in checklist_schema:
                    checklist_schema[new_cat_name] = {}
                    save_checklist_schema(checklist_schema)
                    st.session_state["show_new_cat"] = False
                    st.session_state["success_msg"] = f"Kategorie '{new_cat_name}' erstellt!"
                    st.cache_data.clear()
                    st.rerun()
            if col2.form_submit_button("Abbrechen"):
                st.session_state["show_new_cat"] = False
                st.rerun()
    
    st.divider()
    
    if selected_cat:
        st.subheader(f"Punkte in '{selected_cat}'")
        
        items = checklist_schema.get(selected_cat, {})
        sorted_items = sorted(items.items(), key=lambda x: x[1].get("order", 0))
        
        for i, (key, item_data) in enumerate(sorted_items):
            with st.expander(f"{item_data['label']}", expanded=False):
                st.markdown(f"**Beschreibung:** {item_data.get('description', 'Keine Beschreibung')}")
                
                col1, col2, col3, col4 = st.columns(4)
                
                if col1.button("⬆️", key=f"up_{key}") and i > 0:
                    prev_key = sorted_items[i-1][0]
                    checklist_schema[selected_cat][key]["order"], checklist_schema[selected_cat][prev_key]["order"] = \
                        checklist_schema[selected_cat][prev_key]["order"], checklist_schema[selected_cat][key]["order"]
                    save_checklist_schema(checklist_schema)
                    st.cache_data.clear()
                    st.rerun()
                
                if col2.button("⬇️", key=f"down_{key}") and i < len(sorted_items) - 1:
                    next_key = sorted_items[i+1][0]
                    checklist_schema[selected_cat][key]["order"], checklist_schema[selected_cat][next_key]["order"] = \
                        checklist_schema[selected_cat][next_key]["order"], checklist_schema[selected_cat][key]["order"]
                    save_checklist_schema(checklist_schema)
                    st.cache_data.clear()
                    st.rerun()
                
                if col3.button("🗑️ Löschen", key=f"del_item_{key}"):
                    del checklist_schema[selected_cat][key]
                    save_checklist_schema(checklist_schema)
                    st.session_state["success_msg"] = "Punkt gelöscht!"
                    st.cache_data.clear()
                    st.rerun()
        
        st.divider()
        st.subheader("Neuen Punkt hinzufügen")
        with st.form("new_item_form"):
            ni_key = st.text_input("Interner Schlüssel (z.B. p_vpoc)", placeholder="p_vpoc")
            ni_label = st.text_input("Anzeigename", placeholder="VPoc")
            ni_desc = st.text_area("Beschreibung", placeholder="Volume Point of Control...")
            
            if st.form_submit_button("➕ Punkt hinzufügen"):
                if ni_key and ni_label:
                    max_order = max([v.get("order", 0) for v in items.values()], default=-1) + 1
                    checklist_schema[selected_cat][ni_key] = {
                        "label": ni_label,
                        "description": ni_desc,
                        "image": None,
                        "order": max_order
                    }
                    save_checklist_schema(checklist_schema)
                    st.session_state["success_msg"] = f"'{ni_label}' hinzugefügt!"
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Bitte Schlüssel und Label ausfüllen.")
        
        st.divider()
        if st.button(f"🗑️ Kategorie '{selected_cat}' löschen", type="secondary"):
            if len(checklist_schema) > 1:
                del checklist_schema[selected_cat]
                save_checklist_schema(checklist_schema)
                st.session_state["success_msg"] = f"Kategorie '{selected_cat}' gelöscht!"
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Mindestens eine Kategorie muss existieren.")

# =========================================================
# TAB 5: EINSTELLUNGEN
# =========================================================
with tab_settings:
    st.header("⚙️ Einstellungen")
    
    col_acc, col_ass = st.columns(2)
    
    with col_acc:
        st.subheader("🏦 Konten verwalten")
        
        accounts = [a for a in settings["accounts"] if a != "-- Kein Konto --"]
        
        for i, acc in enumerate(accounts):
            with st.expander(acc, expanded=False):
                c1, c2, c3, c4 = st.columns(4)
                
                if c1.button("⬆️", key=f"up_acc_{i}") and i > 0:
                    real_idx = settings["accounts"].index(acc)
                    settings["accounts"][real_idx], settings["accounts"][real_idx-1] = \
                        settings["accounts"][real_idx-1], settings["accounts"][real_idx]
                    save_settings(settings)
                    st.cache_data.clear()
                    st.rerun()
                
                if c2.button("⬇️", key=f"dn_acc_{i}") and i < len(accounts) - 1:
                    real_idx = settings["accounts"].index(acc)
                    settings["accounts"][real_idx], settings["accounts"][real_idx+1] = \
                        settings["accounts"][real_idx+1], settings["accounts"][real_idx]
                    save_settings(settings)
                    st.cache_data.clear()
                    st.rerun()
                
                if c3.button("🗑️", key=f"del_acc_{i}"):
                    settings["accounts"].remove(acc)
                    save_settings(settings)
                    st.session_state["success_msg"] = f"'{acc}' gelöscht!"
                    st.cache_data.clear()
                    st.rerun()
        
        st.divider()
        with st.form("new_acc_form"):
            new_acc = st.text_input("Neues Konto", placeholder="z.B. Apex 2")
            if st.form_submit_button("➕ Konto hinzufügen"):
                if new_acc and new_acc not in settings["accounts"]:
                    settings["accounts"].append(new_acc)
                    save_settings(settings)
                    st.session_state["success_msg"] = f"'{new_acc}' hinzugefügt!"
                    st.cache_data.clear()
                    st.rerun()
    
    with col_ass:
        st.subheader("📊 Assets verwalten")
        
        assets = [a for a in settings["assets"] if a != "-- Kein Asset --"]
        
        for i, ass in enumerate(assets):
            with st.expander(ass, expanded=False):
                c1, c2, c3, c4 = st.columns(4)
                
                if c1.button("⬆️", key=f"up_ass_{i}") and i > 0:
                    real_idx = settings["assets"].index(ass)
                    settings["assets"][real_idx], settings["assets"][real_idx-1] = \
                        settings["assets"][real_idx-1], settings["assets"][real_idx]
                    save_settings(settings)
                    st.cache_data.clear()
                    st.rerun()
                
                if c2.button("⬇️", key=f"dn_ass_{i}") and i < len(assets) - 1:
                    real_idx = settings["assets"].index(ass)
                    settings["assets"][real_idx], settings["assets"][real_idx+1] = \
                        settings["assets"][real_idx+1], settings["assets"][real_idx]
                    save_settings(settings)
                    st.cache_data.clear()
                    st.rerun()
                
                if c3.button("🗑️", key=f"del_ass_{i}"):
                    settings["assets"].remove(ass)
                    save_settings(settings)
                    st.session_state["success_msg"] = f"'{ass}' gelöscht!"
                    st.cache_data.clear()
                    st.rerun()
        
        st.divider()
        with st.form("new_ass_form"):
            new_ass = st.text_input("Neues Asset", placeholder="z.B. BTC")
            if st.form_submit_button("➕ Asset hinzufügen"):
                if new_ass and new_ass not in settings["assets"]:
                    settings["assets"].append(new_ass)
                    save_settings(settings)
                    st.session_state["success_msg"] = f"'{new_ass}' hinzugefügt!"
                    st.cache_data.clear()
                    st.rerun()
    
    st.divider()
    st.info(f"📊 Trades Gesamt: {len(df)}")
    st.caption("☁️ Daten werden in Google Sheets gespeichert")
