import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models as _models  # Register all tables.


class BusinessJourneyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        sessions = sessionmaker(bind=self.engine)
        def override():
            with sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def post(self, url, body, **kwargs):
        response = self.client.post(url, json=body, **kwargs)
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def test_owner_to_salesperson_flow_and_business_isolation(self):
        self.assertIn("Sign in to your shop", self.client.get("/").text)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.post("/auth/register", {"business_name": "Journey Shop", "owner_name": "Owner", "email": "journey@example.com", "password": "password123"})
        self.post("/auth/login", {"business_name": "Journey Shop", "email": "journey@example.com", "password": "password123", "role": "owner"})
        self.assertEqual(self.client.get("/auth/me").json()["business_name"], "Journey Shop")
        self.post("/employees", {"name": "Seller", "email": "seller@example.com", "password": "password123"})
        product = self.post("/products", {"name": "Rice", "selling_price": "500", "purchase_cost": "400", "opening_stock": 10})
        pid = product["product_id"]
        self.post("/purchases", {"items": [{"product_id": pid, "quantity": 5, "unit_price": "400"}]}, headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(self.client.get(f"/products/{pid}/stock").json()["stock_quantity"], 15)
        self.post("/auth/login", {"business_name": "Journey Shop", "email": "seller@example.com", "password": "password123", "role": "salesperson"})
        self.assertNotIn("purchase_cost", self.client.get(f"/products/{pid}").json())
        self.assertEqual(self.client.get("/purchases").status_code, 403)
        customer = self.post("/customers", {"name": "Buyer"})
        invoice = self.post("/sales", {"customer_id": customer["customer_id"], "items": [{"product_id": pid, "quantity": 2}], "initial_payment": "400"}, headers={"Idempotency-Key": str(uuid4())})
        self.post(f"/sales/{invoice['invoice_id']}/payments", {"amount": "200"}, headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(self.client.get(f"/customers/{customer['customer_id']}").json()["due"], "400.00")
        self.assertEqual(self.client.get(f"/products/{pid}/stock").json()["stock_quantity"], 13)
        self.assertEqual([m["quantity_change"] for m in self.client.get(f"/products/{pid}/history").json()], [10, 5, -2])
        self.assertEqual(self.client.get(f"/sales/{invoice['invoice_id']}/print").status_code, 200)
        self.post("/auth/register", {"business_name": "Other Shop", "owner_name": "Other", "email": "other@example.com", "password": "password123"})
        self.post("/auth/login", {"business_name": "Other Shop", "email": "other@example.com", "password": "password123", "role": "owner"})
        self.assertEqual(self.client.get(f"/products/{pid}").status_code, 404)
        self.assertEqual(self.client.get(f"/sales/{invoice['invoice_id']}").status_code, 404)
