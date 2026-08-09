import datetime as dt
import json
import os
import subprocess
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except Exception:
    service_account = None
    build = None


BASE_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_PATH_VALUE = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "").strip()
SERVICE_ACCOUNT_PATH = Path(SERVICE_ACCOUNT_PATH_VALUE).expanduser() if SERVICE_ACCOUNT_PATH_VALUE else None
if SERVICE_ACCOUNT_PATH and not SERVICE_ACCOUNT_PATH.is_absolute():
    SERVICE_ACCOUNT_PATH = (BASE_DIR / SERVICE_ACCOUNT_PATH).resolve()

SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_RANGE = os.getenv("GOOGLE_SHEET_RANGE", "").strip()

app = Flask(__name__)


def normalize_rows(rows):
    normalized = []
    if not rows:
        return normalized

    first_row = rows[0]
    if isinstance(first_row, list):
        cleaned = [str(cell).strip().lower().replace(" ", "") for cell in first_row]
        if any(field in cleaned for field in ["campaignname", "campaign", "link", "supportlink", "supp.link", "url"]):
            rows = rows[1:]

    for row in rows:
        if not row:
            continue
        if isinstance(row, dict):
            name = (row.get("CAMPAIGN NAME") or row.get("Campaign Name") or "").strip()
            link = (row.get("SUPP. LINK") or row.get("Link") or row.get("URL") or "").strip()
        else:
            if len(row) < 2:
                continue
            name = str(row[0]).strip()
            link = str(row[1]).strip()

        if name and link:
            normalized.append({"name": name, "link": link})

    return normalized


def fetch_google_sheet_rows_for_tab(service, tab_name):
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{tab_name}!A1:Z1000",
    ).execute()
    values = result.get("values", [])
    return normalize_rows(values)


def build_google_credentials():
    if service_account is None or build is None:
        raise ImportError("Google client dependencies are not installed.")

    if SERVICE_ACCOUNT_JSON:
        try:
            info = json.loads(SERVICE_ACCOUNT_JSON)
            return service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
        except Exception as exc:
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_JSON is invalid: {exc}") from exc

    if SERVICE_ACCOUNT_PATH and SERVICE_ACCOUNT_PATH.exists():
        return service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_PATH),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )

    raise FileNotFoundError("No valid Google service account credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_PATH.")


def fetch_google_sheet_rows():
    if not SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID is not set. Add it to your environment variables.")

    creds = build_google_credentials()

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    if SHEET_RANGE:
        raw_name = SHEET_RANGE.split("!")[0].strip("'")
        tab_names = [raw_name]
    else:
        metadata = service.spreadsheets().get(
            spreadsheetId=SHEET_ID,
            fields="sheets/properties/title",
        ).execute()
        tab_names = [sheet["properties"]["title"] for sheet in metadata.get("sheets", [])]

    categories = []
    for tab_name in tab_names:
        campaigns = fetch_google_sheet_rows_for_tab(service, tab_name)
        if campaigns:
            categories.append({"name": tab_name, "campaigns": campaigns})

    if not categories:
        raise ValueError("No valid campaign tabs found in the spreadsheet. Check the tab names or the sheet range.")

    flat = []
    for category in categories:
        flat.extend(category["campaigns"])

    return {"categories": categories, "flat": flat}


def detect_brave_browser():
    candidates = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expanduser(r"~\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def open_url_in_browser(url: str, mode: str = "new_tab"):
    if not url:
        return False

    brave_path = detect_brave_browser()
    if brave_path:
        if mode == "new_tab":
            subprocess.Popen([brave_path, "--new-tab", url])
        elif mode == "new_window":
            subprocess.Popen([brave_path, "--new-window", url])
        else:
            subprocess.Popen([brave_path, url])
        return True

    if mode == "new_tab":
        webbrowser.open_new_tab(url)
    elif mode == "new_window":
        webbrowser.open_new(url)
    else:
        webbrowser.open(url)
    return True


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/campaigns")
def api_campaigns():
    if not SHEET_ID or (not SERVICE_ACCOUNT_JSON and (not SERVICE_ACCOUNT_PATH or not SERVICE_ACCOUNT_PATH.exists())):
        return jsonify({"categories": [], "campaigns": [], "source": "missing_credentials", "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}), 503

    try:
        payload = fetch_google_sheet_rows()
    except Exception as exc:
        return jsonify({"categories": [], "campaigns": [], "source": "google_sheets_error", "error": str(exc), "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}), 500

    return jsonify(
        {
            "categories": payload.get("categories", []),
            "campaigns": payload.get("flat", []),
            "source": "google_sheets",
            "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@app.route("/open")
def open_link():
    url = request.args.get("url", "")
    mode = request.args.get("mode", "new_tab")
    success = open_url_in_browser(url, mode)
    if not success:
        return jsonify({"status": "error", "message": "No valid URL provided."}), 400
    return jsonify({"status": "ok", "url": url, "mode": mode})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
