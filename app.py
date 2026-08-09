import base64
import datetime as dt
import json
import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

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
SERVICE_ACCOUNT_JSON_BASE64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "").strip()
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
SHEET_RANGE = os.getenv("GOOGLE_SHEET_RANGE", "").strip()

app = Flask(__name__)


def iso_now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def parse_service_account_json(raw_value: str):
    if not raw_value:
        return None

    candidate = raw_value.strip()
    if candidate.startswith("{"):
        return json.loads(candidate)

    try:
        decoded = base64.b64decode(candidate, validate=True)
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        try:
            return json.loads(candidate)
        except Exception:
            return None


def build_google_credentials():
    if service_account is None or build is None:
        raise ImportError("Google client dependencies are not installed.")

    candidate_info = parse_service_account_json(SERVICE_ACCOUNT_JSON)
    if candidate_info:
        return service_account.Credentials.from_service_account_info(
            candidate_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )

    if SERVICE_ACCOUNT_JSON_BASE64:
        try:
            decoded = base64.b64decode(SERVICE_ACCOUNT_JSON_BASE64, validate=True)
            info = json.loads(decoded.decode("utf-8"))
            return service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
        except Exception as exc:
            raise ValueError(f"GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 is invalid: {exc}") from exc

    if SERVICE_ACCOUNT_PATH and SERVICE_ACCOUNT_PATH.exists():
        return service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_PATH),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )

    raise FileNotFoundError("No valid Google service account credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 or GOOGLE_SERVICE_ACCOUNT_PATH.")


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
    env_path = os.getenv("BRAVE_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        env_path,
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expanduser(r"~\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def detect_chrome_browser():
    env_path = os.getenv("CHROME_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def open_url_in_browser(url: str, mode: str = "new_tab"):
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    brave_path = detect_brave_browser()
    if brave_path:
        try:
            if mode == "new_tab":
                subprocess.Popen([brave_path, "--new-tab", url])
            elif mode == "new_window":
                subprocess.Popen([brave_path, "--new-window", url])
            else:
                subprocess.Popen([brave_path, url])
            return True
        except Exception:
            return False

    chrome_path = detect_chrome_browser()
    if chrome_path:
        try:
            if mode == "new_tab":
                subprocess.Popen([chrome_path, "--new-tab", url])
            elif mode == "new_window":
                subprocess.Popen([chrome_path, "--new-window", url])
            else:
                subprocess.Popen([chrome_path, url])
            return True
        except Exception:
            return False

    return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/campaigns")
def api_campaigns():
    now = iso_now()
    if not SHEET_ID:
        return jsonify({"categories": [], "campaigns": [], "source": "missing_credentials", "error": "GOOGLE_SHEET_ID is not configured.", "updated_at": now}), 503

    credentials_missing = not SERVICE_ACCOUNT_JSON and not SERVICE_ACCOUNT_JSON_BASE64 and (not SERVICE_ACCOUNT_PATH or not SERVICE_ACCOUNT_PATH.exists())
    if credentials_missing:
        return jsonify({"categories": [], "campaigns": [], "source": "missing_credentials", "error": "No valid Google service account credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 or GOOGLE_SERVICE_ACCOUNT_PATH.", "updated_at": now}), 503

    try:
        payload = fetch_google_sheet_rows()
    except Exception as exc:
        return jsonify({"categories": [], "campaigns": [], "source": "google_sheets_error", "error": str(exc), "updated_at": now}), 500

    return jsonify(
        {
            "categories": payload.get("categories", []),
            "campaigns": payload.get("flat", []),
            "source": "google_sheets",
            "updated_at": iso_now(),
        }
    )


@app.route("/open")
def open_link():
    url = request.args.get("url", "")
    mode = request.args.get("mode", "new_tab")
    if not url:
        return jsonify({"status": "error", "message": "No valid URL provided."}), 400

    host = request.host.lower()
    is_local = "localhost" in host or "127.0.0.1" in host or "0.0.0.0" in host or host.startswith("127.")

    if not is_local:
        return jsonify({
            "status": "error",
            "message": "This feature only works on the local machine where Brave is installed. Vercel cannot launch your desktop browser.",
            "url": url,
            "mode": mode,
            "browser": "blocked_for_deployed_app",
        }), 403

    brave_path = detect_brave_browser()
    if brave_path:
        success = open_url_in_browser(url, mode)
        if not success:
            return jsonify({"status": "error", "message": "Failed to open Brave."}), 500
        return jsonify({"status": "ok", "url": url, "mode": mode, "browser": "brave"})

    chrome_path = detect_chrome_browser()
    if chrome_path:
        return jsonify({
            "status": "needs_browser_choice",
            "message": "Brave was not found. Open this link in Chrome instead?",
            "url": url,
            "mode": mode,
            "browser": "chrome",
        })

    return jsonify({"status": "error", "message": "Brave and Chrome were not found on this machine."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
