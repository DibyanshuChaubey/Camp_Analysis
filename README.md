# Campaign Link Hub

A Flask-based dashboard for browsing campaign links from a Google Sheet, organized by sheet tab/category.
A small Flask app that reads campaign links from a Google Sheet, presents them in a searchable UI, and provides convenient ways to open or copy links locally or when deployed.

# Campaign Link Hub

A concise Flask application that reads campaign links from Google Sheets and provides a searchable UI to copy or open links.

Key features
- Live Google Sheets integration (service account via file, JSON, or base64)
- Categorized view by spreadsheet tab, search/filter, and preserved selection order
- Open selected links: server-side native launch when local; client-side tab/window opens when deployed

Quick start
1. Create and activate a virtual environment, then install dependencies:
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```
2. Provide Google credentials and sheet info in environment variables (see below).
3. Start the app for local testing:
```powershell
$env:FLASK_APP = 'app.py'
flask run
```

Environment variables
- `GOOGLE_SHEET_ID` (required)
- `GOOGLE_SHEET_RANGE` (optional)
- `GOOGLE_SERVICE_ACCOUNT_PATH` or `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`
- `BRAVE_PATH` / `CHROME_PATH` (optional, local browser paths)
- `PORT` (optional)

API
- `GET /api/campaigns` — returns `{ categories, campaigns, source, updated_at }`
- `GET /open?url=...&mode=...` — when running locally the server attempts to open the URL natively; otherwise the response indicates how the client should open the link

Files of interest
- `app.py` — server, Sheets integration, `/api/campaigns` and `/open` endpoints
- `static/app.js` — client behavior, selection and open logic
- `templates/index.html` — UI

Security and deployment notes
- Do not commit real service account files or `.env` to source control.
- In serverless deployments (Vercel/Netlify) native server-side browser launches are unavailable; the client will open links in the user's browser.
- Run the app with `debug=False` in production and add structured logging for observability.

Recommended next steps
- Add a `.env.example` documenting variables
- Add unit tests for `normalize_rows()` and credential parsing
- Add basic logging and a CI check (lint + tests)

For other changes or to add CI/tests, tell me which task you want next.
   - Fetch spreadsheet metadata and values using the Google Sheets API and normalize rows into `{name, link}` objects (`fetch_google_sheet_rows()` and `normalize_rows()`).
