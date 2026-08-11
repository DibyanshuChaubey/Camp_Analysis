import base64
import datetime as dt
import json
import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
import time

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
import logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

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


class CredentialError(Exception):
    pass


class GoogleSheetsError(Exception):
    pass


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


def validate_service_account_info(info: dict):
    if not isinstance(info, dict):
        raise CredentialError("Service account info is not a JSON object")
    required_keys = {"type", "client_email", "private_key"}
    if not required_keys.issubset(set(info.keys())):
        raise CredentialError("Service account JSON is missing required fields")
    if info.get("type") != "service_account":
        raise CredentialError("Service account JSON 'type' is not 'service_account'")
    private_key = str(info.get("private_key", "")).strip()
    if not private_key.startswith("-----BEGIN") or "PRIVATE KEY" not in private_key:
        raise CredentialError("Service account private key is malformed")
    return True


def build_google_api_error_message(exc):
    text = str(exc).lower()
    response = getattr(exc, "resp", None)
    status = getattr(response, "status", None)

    if status == 403:
        return "The Google service account does not have access to this spreadsheet. Share the sheet with the service account email as Viewer or Editor."
    if status == 404:
        return "The Google spreadsheet could not be found. Verify GOOGLE_SHEET_ID and the spreadsheet permissions."
    if isinstance(exc, PermissionError) or any(token in text for token in ["permission", "forbidden", "access denied", "not authorized"]):
        return "The Google service account does not have permission to access the spreadsheet. Share the sheet with the service account email as Viewer or Editor."
    if any(token in text for token in ["timed out", "timeout", "connection attempt failed", "name or service not known", "network is unreachable", "connection reset", "temporary failure", "certificate verify failed"]):
        return "Google Sheets could not be reached. Check your internet connection, VPN/proxy/firewall settings, and DNS resolution."
    if any(token in text for token in ["invalid_grant", "invalid_client", "private key", "client_email", "not authorized"]):
        return "The Google service account credentials are invalid or incomplete. Verify the JSON contents and that the service account is active."
    return f"Google Sheets request failed: {exc}"


def build_google_credentials():
    if service_account is None or build is None:
        raise ImportError("Google client dependencies are not installed.")

    if SERVICE_ACCOUNT_JSON:
        candidate_info = parse_service_account_json(SERVICE_ACCOUNT_JSON)
        if candidate_info is None:
            raise CredentialError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON or base64-encoded JSON")
        try:
            validate_service_account_info(candidate_info)
        except CredentialError:
            raise
        return service_account.Credentials.from_service_account_info(
            candidate_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )

    if SERVICE_ACCOUNT_JSON_BASE64:
        try:
            decoded = base64.b64decode(SERVICE_ACCOUNT_JSON_BASE64, validate=True)
            info = json.loads(decoded.decode("utf-8"))
            validate_service_account_info(info)
            return service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
            )
        except Exception as exc:
            raise CredentialError("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 is invalid or does not contain a valid service account JSON") from exc

    if SERVICE_ACCOUNT_PATH and SERVICE_ACCOUNT_PATH.exists():
        try:
            # don't log file contents; just validate structure
            with open(SERVICE_ACCOUNT_PATH, "r", encoding="utf-8") as fh:
                info = json.load(fh)
            validate_service_account_info(info)
        except Exception as exc:
            raise CredentialError("Service account file is invalid or missing required fields") from exc
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

    # Determine tab names with optional retries for transient errors
    MAX_ATTEMPTS = 3
    backoff = 0.5
    if SHEET_RANGE:
        raw_name = SHEET_RANGE.split("!")[0].strip("'")
        tab_names = [raw_name]
    else:
        attempt = 0
        while attempt < MAX_ATTEMPTS:
            try:
                metadata = service.spreadsheets().get(
                    spreadsheetId=SHEET_ID,
                    fields="sheets/properties/title",
                ).execute()
                tab_names = [sheet["properties"]["title"] for sheet in metadata.get("sheets", [])]
                break
            except Exception as exc:
                attempt += 1
                if attempt >= MAX_ATTEMPTS:
                    logger.exception("Failed to fetch spreadsheet metadata after retries")
                    raise GoogleSheetsError(build_google_api_error_message(exc)) from exc
                time.sleep(backoff * attempt)

    categories = []
    for tab_name in tab_names:
        attempt = 0
        while attempt < MAX_ATTEMPTS:
            try:
                campaigns = fetch_google_sheet_rows_for_tab(service, tab_name)
                break
            except Exception as exc:
                attempt += 1
                if attempt >= MAX_ATTEMPTS:
                    logger.exception("Failed to fetch values for tab %s", tab_name)
                    raise GoogleSheetsError(f"Failed to fetch values for tab {tab_name}: {build_google_api_error_message(exc)}") from exc
                time.sleep(backoff * attempt)

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
        logger.error("GOOGLE_SHEET_ID is not configured")
        return (
            jsonify({
                "categories": [],
                "campaigns": [],
                "source": "missing_credentials",
                "error": "GOOGLE_SHEET_ID is not configured.",
                "error_code": "missing_sheet_id",
                "updated_at": now,
            }),
            503,
        )

    credentials_missing = not SERVICE_ACCOUNT_JSON and not SERVICE_ACCOUNT_JSON_BASE64 and (not SERVICE_ACCOUNT_PATH or not SERVICE_ACCOUNT_PATH.exists())
    if credentials_missing:
        return (
            jsonify({
                "categories": [],
                "campaigns": [],
                "source": "missing_credentials",
                "error": "No valid Google service account credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 or GOOGLE_SERVICE_ACCOUNT_PATH.",
                "error_code": "missing_credentials",
                "updated_at": now,
            }),
            503,
        )

    try:
        payload = fetch_google_sheet_rows()
    except GoogleSheetsError as exc:
        logger.exception("GoogleSheetsError while fetching rows")
        return (
            jsonify({
                "categories": [],
                "campaigns": [],
                "source": "google_sheets_error",
                "error": "Failed to fetch Google Sheets data.",
                "error_code": "google_sheets_error",
                "details": str(exc),
                "updated_at": now,
            }),
            500,
        )
    except CredentialError as exc:
        logger.exception("Credential error while building Google credentials")
        return (
            jsonify({
                "categories": [],
                "campaigns": [],
                "source": "missing_credentials",
                "error": "Google service account credentials are invalid.",
                "error_code": "invalid_credentials",
                "details": str(exc),
                "updated_at": now,
            }),
            503,
        )
    except Exception as exc:
        logger.exception("Unexpected error while fetching campaigns")
        return (
            jsonify({
                "categories": [],
                "campaigns": [],
                "source": "unknown_error",
                "error": "Unexpected server error.",
                "error_code": "server_error",
                "details": str(exc),
                "updated_at": now,
            }),
            500,
        )

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
        logger.warning("/open called without url")
        return jsonify({"status": "error", "message": "No valid URL provided.", "error_code": "missing_url"}), 400

    host = request.host.lower()
    is_local = "localhost" in host or "127.0.0.1" in host or "0.0.0.0" in host or host.startswith("127.") or host.startswith("192.168.") or host.startswith("10.") or host.startswith("172.")

    if not is_local:
        return jsonify({
            "status": "browser_only",
            "url": url,
            "mode": mode,
            "browser": "browser_only",
        })

    brave_path = detect_brave_browser()
    if brave_path:
        success = open_url_in_browser(url, mode)
        if not success:
            logger.exception("Failed to open Brave for url: %s", url)
            return jsonify({"status": "error", "message": "Failed to open Brave.", "error_code": "browser_launch_failed"}), 500
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
    logger.warning("No supported browser found to open url: %s", url)
    return jsonify({"status": "error", "message": "Brave and Chrome were not found on this machine.", "error_code": "no_browser_found"}), 404


if __name__ == "__main__":
    # Respect environment variables for host/port/debug
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug_env = os.getenv("FLASK_DEBUG") or os.getenv("DEBUG") or os.getenv("FLASK_ENV") == "development"
    debug = str(debug_env).lower() in {"1", "true", "yes", "on"}
    logger.info("Starting app on %s:%s debug=%s", host, port, debug)
    app.run(host=host, port=port, debug=debug)
