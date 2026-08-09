# Campaign Link Hub

A Flask-based dashboard for browsing campaign links from a Google Sheet, organized by sheet tab/category.

## Features
- Reads live data from Google Sheets using a read-only service account
- Shows each sheet tab as a category in the UI
- Search and filter campaigns
- Open in Brave tabs/windows or copy link
- Ready for deployment on a Python host

## Setup
1. Create a Python virtual environment and install dependencies:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Create a service account in Google Cloud and share the spreadsheet with it as Viewer.
3. Copy `.env.example` to `.env` and fill in your values.
4. Start the app:
   ```bash
   flask run
   ```

## Environment variables
- `GOOGLE_SHEET_ID`
- `GOOGLE_SHEET_RANGE` (optional; leave blank to read all tabs)
- `GOOGLE_SERVICE_ACCOUNT_PATH`
- `PORT` (optional)

## GitHub safety
- Do not commit the real `service_account.json` file.
- Do not commit `.env` files.
- Keep secrets in your deployment platform environment variables instead.
