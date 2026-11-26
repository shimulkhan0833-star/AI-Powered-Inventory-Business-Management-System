# Oleyn Stock

A multi-tenant inventory and business management application for small businesses.
The MVP is being developed in small, testable steps.

## Requirements

- Python 3.10 or later
- MySQL with an existing `oleyn_stock` database

## Run locally

From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Before starting the app, edit `.env` and enter your local MySQL credentials.
The file is ignored by Git and must not be shared. Then apply the database
migrations and start the app:

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

Alembic tracks schema changes in the database. Review generated migration files
before applying them; migrations can alter existing data and tables.

Open `http://127.0.0.1:8000/docs` for the API documentation or
`http://127.0.0.1:8000/health` to check that the application is running.
The health endpoint checks the application process only; it does not check a database.

## Project layout

```text
app/
  main.py             # FastAPI app and router registration
  database.py         # SQLAlchemy engine and request sessions
  models/             # SQLAlchemy table definitions
  routes/health.py    # Application health endpoint
migrations/           # Alembic schema migrations
```

Authentication and business features will be added in later steps.
