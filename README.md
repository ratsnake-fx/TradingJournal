# Trading Journal Cloud ☁️

Trading Journal mit Google Sheets Backend für Zugriff von überall.

## Setup für Streamlit Cloud

### 1. GitHub Repository erstellen
1. Gehe zu github.com und erstelle ein neues Repository
2. Lade diese Dateien hoch:
   - `app.py`
   - `requirements.txt`

### 2. Streamlit Cloud verbinden
1. Gehe zu [share.streamlit.io](https://share.streamlit.io)
2. "New app" klicken
3. Dein GitHub Repository auswählen
4. Main file: `app.py`

### 3. Secrets konfigurieren
1. In Streamlit Cloud: App Settings → Secrets
2. Füge folgendes ein (mit deinen echten Werten):

```toml
[gcp_service_account]
type = "service_account"
project_id = "tradingjournal-483302"
private_key_id = "DEIN_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "trading-journal-bot@tradingjournal-483302.iam.gserviceaccount.com"
client_id = "114012475267836265468"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/trading-journal-bot%40tradingjournal-483302.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
```

### 4. Fertig! 🎉
Deine App ist jetzt online unter `https://deinname-tradingjournal.streamlit.app`

## Lokales Testen

1. `pip install -r requirements.txt`
2. Erstelle `.streamlit/secrets.toml` mit deinen Credentials
3. `streamlit run app.py`
