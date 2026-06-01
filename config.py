import os
CLIENT_ID = os.environ.get("ML_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("ML_REDIRECT_URI", "https://tscshop.com.br")
TOKEN_FILE = "tokens.json"

# Configurações de e-mail
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")
