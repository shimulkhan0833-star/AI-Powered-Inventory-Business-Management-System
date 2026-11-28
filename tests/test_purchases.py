import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import Business, Product, Purchase, StockMovement, User
from app.services.memo import ExtractedItem, ExtractedMemo


class PurchaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            for business_name, email in (("Shop A", "a@example.com"), ("Shop B", "b@example.com")):
                business = Business(name=business_name)
                db.add(business)
                db.flush()
                db.add(User(business_id=business.business_id, name="Owner", email=email,
                            password_hash=hash_password("owner-password"), role="owner"))
                db.add(Product(business_id=business.business_id, name="Rice", sku="RICE", selling_price=50, stock_quantity=0))
                if business_name == "Shop A":
                    db.add(User(business_id=business.business_id, name="Staff", email="staff@example.com",
                                password_hash=hash_password("staff-password"), role="salesperson"))
            db.commit()

        def override_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.payload = {"supplier_name": "Supplier", "items": [{"product_id": 1, "quantity": 3, "unit_price": "12.50"}]}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self, email="a@example.com", role="owner", business="Shop A", password="owner-password"):
        self.assertEqual(self.client.post("/auth/login", json={"email": email, "password": password,
                                  "role": role, "business_name": business}).status_code, 200)

    def test_purchase_is_atomic_and_retry_is_idempotent(self):
        self.login()
        key = str(uuid4())
        result = self.client.post("/purchases", json=self.payload, headers={"Idempotency-Key": key})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()["total"], "37.50")
        retry = self.client.post("/purchases", json=self.payload, headers={"Idempotency-Key": key})
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["purchase_id"], result.json()["purchase_id"])
        changed = {**self.payload, "items": [{"product_id": 1, "quantity": 4, "unit_price": "12.50"}]}
        self.assertEqual(self.client.post("/purchases", json=changed, headers={"Idempotency-Key": key}).status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 1).stock_quantity, 3)
            self.assertEqual(db.scalar(select(func.count()).select_from(Purchase)), 1)
            movement = db.scalar(select(StockMovement))
            self.assertEqual(movement.quantity_change, 3)
            self.assertEqual(movement.purchase_id, result.json()["purchase_id"])

    def test_invalid_product_rolls_back_and_tenants_are_isolated(self):
        self.login()
        bad = {"items": [{"product_id": 1, "quantity": 2, "unit_price": "1"},
                         {"product_id": 2, "quantity": 1, "unit_price": "1"}]}
        self.assertEqual(self.client.post("/purchases", json=bad, headers={"Idempotency-Key": str(uuid4())}).status_code, 404)
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 1).stock_quantity, 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(Purchase)), 0)
        saved = self.client.post("/purchases", json=self.payload, headers={"Idempotency-Key": str(uuid4())}).json()
        self.login("b@example.com", business="Shop B")
        self.assertEqual(self.client.get("/purchases").json(), [])
        self.assertEqual(self.client.get(f"/purchases/{saved['purchase_id']}").status_code, 404)

    def test_salesperson_cannot_access_purchase_or_ai(self):
        self.login("staff@example.com", role="salesperson", password="staff-password")
        self.assertEqual(self.client.get("/purchases").status_code, 403)
        self.assertEqual(self.client.post("/purchases", json=self.payload, headers={"Idempotency-Key": str(uuid4())}).status_code, 403)
        self.assertEqual(self.client.post("/purchases/memo-draft", files={"file": ("memo.png", b"\x89PNG\r\n\x1a\nimage", "image/png")}).status_code, 403)

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"})
    @patch("app.services.memo.time.sleep")
    @patch("app.services.memo.ChatGoogleGenerativeAI")
    def test_memo_draft_does_not_save_and_ai_failure_has_manual_fallback(self, model, sleep):
        self.login()
        invoke = model.return_value.with_structured_output.return_value.invoke
        invoke.return_value = ExtractedMemo(supplier_name="Shop", items=[ExtractedItem(product_name="Rice", quantity="2", unit_price="10")])
        image = {"file": ("memo.png", b"\x89PNG\r\n\x1a\nimage", "image/png")}
        result = self.client.post("/purchases/memo-draft", files=image)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["items"][0]["quantity"], "2")
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Purchase)), 0)
            self.assertEqual(db.get(Product, 1).stock_quantity, 0)
        invoke.side_effect = httpx.TimeoutException("timeout")
        result = self.client.post("/purchases/memo-draft", files=image)
        self.assertEqual(result.status_code, 503)
        self.assertIn("manually", result.json()["detail"])
        self.assertEqual(self.client.post("/purchases", json=self.payload, headers={"Idempotency-Key": str(uuid4())}).status_code, 201)

    def test_bad_input(self):
        self.login()
        self.assertEqual(self.client.post("/purchases", json=self.payload).status_code, 422)
        self.assertEqual(self.client.post("/purchases", json={"items": []}, headers={"Idempotency-Key": str(uuid4())}).status_code, 422)
        self.assertEqual(self.client.post("/purchases/memo-draft", files={"file": ("x.txt", b"hello", "text/plain")}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
