import os
import json
import datetime
from datetime import timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDENTIALS_PATH = "credentials.json"
TOKEN_PATH = "token.json"


def _write_credentials_from_env() -> None:
    # Render (and most hosts) can't receive .gitignore'd files directly, so
    # their contents are stored as environment variables instead and written
    # out to real files on container startup, which is what the Google
    # client library actually expects to read from disk.
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if credentials_json and not os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH, "w") as credentials_file:
            credentials_file.write(credentials_json)

    token_json = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_json and not os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(token_json)


def get_calendar_service():
    _write_credentials_from_env()

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_upcoming_events(hours_ahead: int = 1) -> list:
    service = get_calendar_service()
    now = datetime.datetime.now(timezone.utc).isoformat()
    later = (datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=hours_ahead)).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=now,
        timeMax=later,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


if __name__ == "__main__":
    events = get_upcoming_events(hours_ahead=1)
    for event in events:
        print(event.get("summary"), "-", event.get("start"))