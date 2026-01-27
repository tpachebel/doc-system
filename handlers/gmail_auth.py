from google_auth_oauthlib.flow import InstalledAppFlow
from handlers.gmail_config import SCOPES, CLIENT_SECRET, TOKEN_PATH

def main():
	if not CLIENT_SECRET.exists():
		raise SystemExit(f"Missing: {CLIENT_SECRET}")

	flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
	creds = flow.run_local_server(port=0, prompt="consent", authorization_prompt_message="")

	TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
	TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
	print(f"Wrote: {TOKEN_PATH}")

if __name__ == "__main__":
	main()