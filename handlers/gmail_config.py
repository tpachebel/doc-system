from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

BASE = Path(r"C:\Users\tragh\Nextcloud\DocSystem\state\secrets\gmail")
CLIENT_SECRET = BASE / "client_secret.json"
TOKEN_PATH = BASE / "token.json"
LABEL_NAME = "DocSystem/Ingest"
MAX_MESSAGES_PER_RUN = 10