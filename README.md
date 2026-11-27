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

## Register a business

Use `POST /auth/register` in `/docs` with `business_name`, `owner_name`,
`email`, and `password` (8–128 characters). This creates the business and
its Owner in one transaction. The response does not contain the password.
Email addresses are unique across the system. Registration does not
automatically sign the owner in yet.

## Log in and out

Use `POST /auth/login` with email, password, role (`owner` or `salesperson`),
and business name. Owners and salespeople use the
same endpoint. It sets an HTTP-only session cookie; `GET /auth/me` returns the
current user and business, and `POST /auth/logout` revokes the session.
Sessions expire after eight hours and inactive users cannot use them.

For local HTTP development `SESSION_COOKIE_SECURE=false` is the default. Set
`SESSION_COOKIE_SECURE=true` in production and serve the app over HTTPS.
Login rate limiting, password changes, and full role authorization are still
to be implemented before production use.

## Employees

An authenticated owner can use `POST /employees` to create a salesperson using
their name, email, and password, `GET /employees` to list salespeople in their
business, and `PATCH /employees/{id}/deactivate` to disable access. Salespeople
cannot use these endpoints. The owner must share credentials privately; there
is currently no password-change or password-reset feature.

## Products and stock

The owner can use `POST /products` to add a product. Supply a name, selling
price, optional purchase cost and SKU, and optional whole-number opening stock.
When no SKU is provided, the server generates one. SKUs are unique per business.

Both roles can list products with `GET /products`, view one with
`GET /products/{id}`, read its current stock at `GET /products/{id}/stock`, and
view stock history at `GET /products/{id}/history`. Salesperson responses do
not include purchase costs or free-text adjustment reasons.

Only owners can update product details with `PATCH /products/{id}` or adjust
stock with `POST /products/{id}/adjustments`, providing a signed
`quantity_change` and a `reason`. Stock may not go below zero. The product's
balance and the corresponding movement are saved together. Every future
stock-changing flow must lock the product and update both records in the same
transaction. Quantities currently support whole units only.

These endpoints require a login session. They do not yet include a visual
interface, purchase and sales flows, or duplicate-request protection for
stock adjustments. Avoid retrying an adjustment until its result is known.

To run the tests against an isolated in-memory database:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```
