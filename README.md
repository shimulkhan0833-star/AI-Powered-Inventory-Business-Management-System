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

## Database identifiers

Each table uses a descriptive primary key: `business_id`, `user_id`,
`session_id`, `customer_id`, `product_id`, `purchase_id`, `purchase_item_id`,
`invoice_id`, `invoice_item_id`, `payment_id`, or `movement_id`. Foreign keys
use the same name as the identifier they refer to. For example,
`products.business_id` references `businesses.business_id`.

API responses now use these names instead of a generic `id` (for example,
`product_id` and `invoice_id`). Existing API clients using `id` must be updated.
The identifier migration preserves existing values and relationships.

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
business, and `PATCH /employees/{employee_id}/deactivate` to disable access. Salespeople
cannot use these endpoints. The owner must share credentials privately; there
is currently no password-change or password-reset feature.

## Products and stock

The owner can use `POST /products` to add a product. Supply a name, selling
price, optional purchase cost and SKU, and optional whole-number opening stock.
When no SKU is provided, the server generates one. SKUs are unique per business.

Both roles can list products with `GET /products`, view one with
`GET /products/{product_id}`, read its current stock at `GET /products/{product_id}/stock`, and
view stock history at `GET /products/{product_id}/history`. Salesperson responses do
not include purchase costs or free-text adjustment reasons.

Only owners can update product details with `PATCH /products/{product_id}` or adjust
stock with `POST /products/{product_id}/adjustments`, providing a signed
`quantity_change` and a `reason`. Stock may not go below zero. The product's
balance and the corresponding movement are saved together. Every future
stock-changing flow must lock the product and update both records in the same
transaction. Quantities currently support whole units only.

These endpoints require a login session. They do not yet include a visual
interface or duplicate-request protection for
stock adjustments. Avoid retrying an adjustment until its result is known.

## Purchases and memo drafts

Owners can create a manual purchase with `POST /purchases`. Include an
`Idempotency-Key` header containing a UUID, and a body such as:

```json
{
  "supplier_name": "Example supplier",
  "items": [{"product_id": 1, "quantity": 5, "unit_price": "100.00"}]
}
```

Reuse the same key and identical purchase details when retrying. The first
successful request returns 201; a retry returns the same purchase with 200.
Reusing the key with different details returns 409. Stock, purchase items,
and stock movements are committed together. `GET /purchases` and
`GET /purchases/{purchase_id}` are owner-only because they expose purchase prices.

`POST /purchases/memo-draft` accepts a JPEG or PNG up to 5 MB as a multipart
`file`. It sends the image to Google's Gemini API using `GOOGLE_API_KEY` and
the optional `GEMINI_MODEL` setting. It returns an untrusted draft only: the
owner must review all fields, match items to product IDs, and submit the
normal purchase request to save. If the service is unavailable, the endpoint
returns 503 and the manual purchase endpoint remains available. Uploaded
images are sent to Google; do not upload confidential documents without the
business's permission. Gemini usage may incur charges.

The default model is configurable because availability and pricing can vary.
AI output is not validated for accuracy, and no visual review screen exists
yet. See [Google's structured-output documentation](https://ai.google.dev/gemini-api/docs/structured-output)
for the API format.

## Customers, sales, and invoices

Both owners and salespeople can create customers with `POST /customers` and
view their running dues at `GET /customers` or `GET /customers/{customer_id}`.
Create a sale with `POST /sales`, a UUID `Idempotency-Key` header, and a body:

```json
{
  "customer_id": 1,
  "items": [{"product_id": 1, "quantity": 2}],
  "initial_payment": "400.00"
}
```

The server uses the product's current selling price; clients cannot submit a
price. Each invoice stores the names, SKU, and price at the time of sale.
Stock is locked and checked before the invoice, initial payment, and movements
are committed together. A retry with the same key and body returns the existing
invoice; a different body with that key returns 409.

Record subsequent payments with `POST /sales/{invoice_id}/payments` using a
new UUID `Idempotency-Key` and a body such as `{"amount":"200.00"}`. Reuse
that key on a retry. Payments greater than the remaining invoice due are
rejected. `GET /sales/{invoice_id}` returns the invoice and current paid/due amounts;
`GET /sales/{invoice_id}/print` shows a printable invoice in the browser. Both roles
can access their business's invoices; purchase costs are never included.

Invoice and payment timestamps are stored as UTC and returned with a `Z`
suffix. Older product and purchase timestamps use the database's local clock
and have not yet been migrated to UTC. Returns, discounts, payment reversals,
and the visual sales and customer forms are not implemented yet.

To run the tests against an isolated in-memory database:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```
