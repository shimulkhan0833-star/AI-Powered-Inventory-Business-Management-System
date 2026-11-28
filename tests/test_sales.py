import unittest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import Business, Customer, CustomerPayment, Payment, Product, SalesInvoice, StockMovement, User


class SalesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            for name, email in (("Shop A", "a@example.com"), ("Shop B", "b@example.com")):
                business = Business(name=name)
                db.add(business)
                db.flush()
                db.add(User(business_id=business.business_id, name="Owner", email=email,
                            password_hash=hash_password("password123"), role="owner"))
                db.add(Customer(business_id=business.business_id, name="Customer", phone=None))
                db.add(Product(business_id=business.business_id, name="Rice", sku="RICE", selling_price=Decimal("500"),
                               purchase_cost=Decimal("400"), stock_quantity=5))
                if name == "Shop A":
                    db.add(User(business_id=business.business_id, name="Staff", email="staff@example.com",
                                password_hash=hash_password("password123"), role="salesperson"))
            db.commit()

        def override_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.payload = {"customer_id": 1, "items": [{"product_id": 1, "quantity": 2}], "initial_payment": "400.00"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self, email="staff@example.com", role="salesperson", business="Shop A"):
        response = self.client.post("/auth/login", json={"email": email, "password": "password123",
                                                        "role": role, "business_name": business})
        self.assertEqual(response.status_code, 200)

    def test_sale_retry_snapshot_stock_and_print_invoice(self):
        self.login()
        key = str(uuid4())
        response = self.client.post("/sales", json=self.payload, headers={"Idempotency-Key": key})
        self.assertEqual(response.status_code, 201, response.text)
        invoice = response.json()
        self.assertEqual((invoice["total"], invoice["paid"], invoice["due"]), ("1000.00", "400.00", "600.00"))
        self.assertTrue(invoice["created_at"].endswith("Z"))
        self.assertNotIn("purchase_cost", response.text)
        self.assertEqual(self.client.post("/sales", json=self.payload, headers={"Idempotency-Key": key}).status_code, 200)
        changed = {**self.payload, "initial_payment": "0"}
        self.assertEqual(self.client.post("/sales", json=changed, headers={"Idempotency-Key": key}).status_code, 409)
        with self.sessions() as db:
            product = db.get(Product, 1)
            self.assertEqual(product.stock_quantity, 3)
            movement = db.scalar(select(StockMovement))
            self.assertEqual((movement.quantity_change, movement.invoice_id), (-2, invoice["invoice_id"]))
            product.name = "New name"
            product.selling_price = Decimal("900")
            db.commit()
        original = self.client.get(f"/sales/{invoice['invoice_id']}").json()
        self.assertEqual(original["items"][0]["product_name"], "Rice")
        self.assertEqual(original["items"][0]["unit_price"], "500.00")
        printed = self.client.get(f"/sales/{invoice['invoice_id']}/print")
        self.assertEqual(printed.status_code, 200)
        self.assertIn(f"INV-{invoice['invoice_id']:05d}", printed.text)
        self.assertIn("Rice", printed.text)
        self.assertNotIn("purchase_cost", printed.text)

    def test_partial_payments_retry_overpayment_and_customer_due(self):
        self.login()
        invoice = self.client.post("/sales", json=self.payload, headers={"Idempotency-Key": str(uuid4())}).json()
        self.assertEqual(self.client.get("/customers/1").json()["due"], "600.00")
        key = str(uuid4())
        path = f"/sales/{invoice['invoice_id']}/payments"
        self.assertEqual(self.client.post(path, json={"amount": "200"}, headers={"Idempotency-Key": key}).status_code, 201)
        self.assertEqual(self.client.post(path, json={"amount": "200"}, headers={"Idempotency-Key": key}).status_code, 200)
        self.assertEqual(self.client.post(path, json={"amount": "201"}, headers={"Idempotency-Key": key}).status_code, 409)
        self.assertEqual(self.client.post(path, json={"amount": "401"}, headers={"Idempotency-Key": str(uuid4())}).status_code, 409)
        self.assertEqual(self.client.post(path, json={"amount": "0"}, headers={"Idempotency-Key": str(uuid4())}).status_code, 422)
        self.assertEqual(self.client.get("/customers/1").json()["due"], "400.00")
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.sum(Payment.amount)).where(Payment.invoice_id == invoice["invoice_id"])), Decimal("600"))

    def test_invalid_sale_rolls_back_and_rejects_overpayment(self):
        self.login()
        headers = {"Idempotency-Key": str(uuid4())}
        self.assertEqual(self.client.post("/sales", json={**self.payload, "items": [{"product_id": 1, "quantity": 6}]}, headers=headers).status_code, 409)
        self.assertEqual(self.client.post("/sales", json={**self.payload, "initial_payment": "1001"}, headers=headers).status_code, 422)
        with self.sessions() as db:
            self.assertEqual(db.get(Product, 1).stock_quantity, 5)
            self.assertEqual(db.scalar(select(func.count()).select_from(SalesInvoice)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(StockMovement)), 0)

    def test_business_isolation_and_server_side_prices(self):
        self.login()
        bad = {**self.payload, "items": [{"product_id": 2, "quantity": 1}]}
        self.assertEqual(self.client.post("/sales", json=bad, headers={"Idempotency-Key": str(uuid4())}).status_code, 404)
        bad_customer = {**self.payload, "customer_id": 2}
        self.assertEqual(self.client.post("/sales", json=bad_customer, headers={"Idempotency-Key": str(uuid4())}).status_code, 404)
        supplied_price = {**self.payload, "items": [{"product_id": 1, "quantity": 1, "unit_price": "1"}]}
        self.assertEqual(self.client.post("/sales", json=supplied_price, headers={"Idempotency-Key": str(uuid4())}).status_code, 422)
        invoice = self.client.post("/sales", json=self.payload, headers={"Idempotency-Key": str(uuid4())}).json()
        self.login("b@example.com", role="owner", business="Shop B")
        self.assertEqual(self.client.get(f"/sales/{invoice['invoice_id']}").status_code, 404)
        self.assertEqual(self.client.post(f"/sales/{invoice['invoice_id']}/payments", json={"amount": "1"}, headers={"Idempotency-Key": str(uuid4())}).status_code, 404)
        self.assertEqual(self.client.get("/customers/1").status_code, 404)

    def test_customer_payment_allocates_oldest_invoices_and_retries(self):
        self.login()
        first = self.client.post("/sales", json={**self.payload, "items": [{"product_id": 1, "quantity": 1}], "initial_payment": "100"}, headers={"Idempotency-Key": str(uuid4())}).json()
        second = self.client.post("/sales", json={**self.payload, "items": [{"product_id": 1, "quantity": 1}], "initial_payment": "0"}, headers={"Idempotency-Key": str(uuid4())}).json()
        path = "/customers/1/payments"
        key = str(uuid4())
        response = self.client.post(path, json={"amount": "600"}, headers={"Idempotency-Key": key})
        self.assertEqual(response.status_code, 201, response.text)
        allocations = response.json()["allocations"]
        self.assertEqual([(p["invoice_id"], p["amount"]) for p in allocations], [(first["invoice_id"], "400.00"), (second["invoice_id"], "200.00")])
        self.assertEqual(self.client.get("/customers/1").json()["due"], "300.00")
        self.assertEqual(self.client.get(f"/sales/{first['invoice_id']}").json()["due"], "0.00")
        self.assertEqual(self.client.get(f"/sales/{second['invoice_id']}").json()["due"], "300.00")
        retry = self.client.post(path, json={"amount": "600"}, headers={"Idempotency-Key": key})
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), response.json())
        self.assertEqual(self.client.post(path, json={"amount": "601"}, headers={"Idempotency-Key": key}).status_code, 409)
        self.assertEqual(self.client.post(path, json={"amount": "301"}, headers={"Idempotency-Key": str(uuid4())}).status_code, 409)
        self.assertEqual(self.client.post(path, json={"amount": "0"}, headers={"Idempotency-Key": str(uuid4())}).status_code, 422)
        self.assertEqual(self.client.get("/customers/1").json()["due"], "300.00")
        self.login("b@example.com", role="owner", business="Shop B")
        self.assertEqual(self.client.post(path, json={"amount": "1"}, headers={"Idempotency-Key": str(uuid4())}).status_code, 404)

    def test_customer_payment_rolls_back_all_allocations_on_failure(self):
        self.login()
        self.client.post("/sales", json=self.payload, headers={"Idempotency-Key": str(uuid4())})
        with patch("app.services.sales.utc_now", side_effect=[datetime.now(), RuntimeError("test failure")]):
            with self.assertRaises(RuntimeError):
                self.client.post("/customers/1/payments", json={"amount": "200"}, headers={"Idempotency-Key": str(uuid4())})
        self.assertEqual(self.client.get("/customers/1").json()["due"], "600.00")
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CustomerPayment)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(Payment)), 1)

    def test_customer_history_includes_sales_and_grouped_payment_references(self):
        self.login()
        empty = self.client.get("/customers/1/history")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["sales"], [])
        first = self.client.post("/sales", json={**self.payload, "items": [{"product_id": 1, "quantity": 1}], "initial_payment": "100"}, headers={"Idempotency-Key": str(uuid4())}).json()
        second = self.client.post("/sales", json={**self.payload, "items": [{"product_id": 1, "quantity": 1}], "initial_payment": "0"}, headers={"Idempotency-Key": str(uuid4())}).json()
        batch = self.client.post("/customers/1/payments", json={"amount": "600"}, headers={"Idempotency-Key": str(uuid4())}).json()
        history = self.client.get("/customers/1/history").json()
        self.assertEqual(history["customer"]["due"], "300.00")
        sales = {sale["invoice_id"]: sale for sale in history["sales"]}
        self.assertEqual(set(sales), {first["invoice_id"], second["invoice_id"]})
        self.assertEqual(sales[first["invoice_id"]]["due"], "0.00")
        self.assertEqual(sales[second["invoice_id"]]["due"], "300.00")
        payments = [payment for sale in sales.values() for payment in sale["payments"]]
        self.assertEqual(len(payments), 3)
        grouped = [payment for payment in payments if payment["customer_payment_id"] == batch["customer_payment_id"]]
        self.assertEqual({payment["invoice_id"] for payment in grouped}, set(sales))
        self.assertEqual(sum(Decimal(payment["amount"]) for payment in grouped), Decimal("600.00"))
        self.assertTrue(all(payment["created_at"].endswith("Z") for payment in payments))
        self.login("b@example.com", role="owner", business="Shop B")
        self.assertEqual(self.client.get("/customers/1/history").status_code, 404)
        self.assertEqual(self.client.get("/customers/2/history").json()["sales"], [])


if __name__ == "__main__":
    unittest.main()
