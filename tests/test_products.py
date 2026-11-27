import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import Business, Product, StockMovement, User


class ProductTests(unittest.TestCase):
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
                            password_hash=hash_password("owner-password"), role="owner"))
                if name == "Shop A":
                    db.add(User(business_id=business.business_id, name="Staff", email="staff@example.com",
                                password_hash=hash_password("staff-password"), role="salesperson"))
            db.commit()

        def override_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.product = {"name": "Rice 5kg", "sku": "RICE-5", "selling_price": "500.00",
                        "purchase_cost": "400.00", "opening_stock": 10}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self, email="a@example.com", role="owner", business="Shop A", password="owner-password"):
        response = self.client.post("/auth/login", json={"email": email, "password": password,
                                                        "role": role, "business_name": business})
        self.assertEqual(response.status_code, 200)

    def test_creation_sku_uniqueness_and_business_isolation(self):
        self.assertEqual(self.client.get("/products").status_code, 401)
        self.login()
        result = self.client.post("/products", json=self.product)
        self.assertEqual(result.status_code, 201)
        product_id = result.json()["product_id"]
        self.assertEqual(result.json()["stock_quantity"], 10)
        self.assertEqual(self.client.post("/products", json=self.product).status_code, 409)
        auto = self.client.post("/products", json={"name": "Oil", "selling_price": "50"})
        self.assertEqual(auto.status_code, 201)
        self.assertTrue(auto.json()["sku"].startswith("PRD-"))
        self.login("b@example.com", business="Shop B")
        self.assertEqual(self.client.get(f"/products/{product_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/products/{product_id}/history").status_code, 404)
        self.assertEqual(self.client.patch(f"/products/{product_id}", json={"name": "Changed"}).status_code, 404)
        self.assertEqual(self.client.post("/products", json=self.product).status_code, 201)

    def test_adjustment_history_and_nonnegative_stock(self):
        self.login()
        product_id = self.client.post("/products", json=self.product).json()["product_id"]
        result = self.client.post(f"/products/{product_id}/adjustments", json={"quantity_change": -3, "reason": "Damaged"})
        self.assertEqual(result.json()["stock_quantity"], 7)
        self.assertEqual(self.client.post(f"/products/{product_id}/adjustments", json={"quantity_change": -8, "reason": "Count"}).status_code, 409)
        self.assertEqual(self.client.post(f"/products/{product_id}/adjustments", json={"quantity_change": 0, "reason": "Count"}).status_code, 422)
        history = self.client.get(f"/products/{product_id}/history").json()
        self.assertEqual([row["quantity_change"] for row in history], [10, -3])
        self.assertEqual(history[1]["reason"], "Damaged")
        self.assertTrue(history[1]["user_id"])
        with self.sessions() as db:
            self.assertEqual(db.get(Product, product_id).stock_quantity,
                             db.scalar(select(func.sum(StockMovement.quantity_change)).where(StockMovement.product_id == product_id)))

    def test_salesperson_access_does_not_expose_cost(self):
        self.login()
        product_id = self.client.post("/products", json=self.product).json()["product_id"]
        self.login("staff@example.com", role="salesperson", password="staff-password")
        for path in ("/products", f"/products/{product_id}", f"/products/{product_id}/stock", f"/products/{product_id}/history"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("purchase_cost", response.text)
        self.assertNotIn("reason", self.client.get(f"/products/{product_id}/history").text)
        self.assertEqual(self.client.post("/products", json=self.product).status_code, 403)
        self.assertEqual(self.client.patch(f"/products/{product_id}", json={"selling_price": "1"}).status_code, 403)
        self.assertEqual(self.client.post(f"/products/{product_id}/adjustments", json={"quantity_change": 1, "reason": "Test"}).status_code, 403)

    def test_invalid_product_and_duplicate_update(self):
        self.login()
        first = self.client.post("/products", json=self.product).json()
        second = self.client.post("/products", json={"name": "Oil", "sku": "OIL", "selling_price": "12.50"}).json()
        self.assertEqual(self.client.patch(f"/products/{second['product_id']}", json={"sku": first["sku"]}).status_code, 409)
        for invalid in ({"selling_price": "-1"}, {"opening_stock": -1}, {"name": "  "}, {"selling_price": "1.001"}):
            self.assertEqual(self.client.post("/products", json={**self.product, **invalid}).status_code, 422)
        self.assertEqual(self.client.patch(f"/products/{first['product_id']}", json={"stock_quantity": 99}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
