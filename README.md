# Oleyn Stock

A multi-tenant inventory and business management application for small businesses.
The MVP is being developed in small, testable steps.

## Requirements

- Python 3.10 or later

## Run locally

From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API documentation or
`http://127.0.0.1:8000/health` to check that the application is running.
The health endpoint checks the application process only; it does not check a database.

## Project layout

```text
app/
  main.py             # FastAPI app and router registration
  routes/health.py    # Application health endpoint
```

Database models, authentication, and business features will be added in later steps.
