import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, verify_password
from app.database import Base, get_db
from app.main import app
from app.models import Business, User


class EmployeeTests(unittest.TestCase):
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
            db.commit()

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self, email, password, role, business):
        return self.client.post("/auth/login", json={"email": email, "password": password,
                                                   "role": role, "business_name": business})

    def test_owner_creates_employee_and_salesperson_can_log_in(self):
        self.assertEqual(self.login("a@example.com", "owner-password", "owner", "Shop A").status_code, 200)
        payload = {"name": "Employee", "email": "staff@example.com", "password": "staff-password"}
        result = self.client.post("/employees", json=payload)
        self.assertEqual(result.status_code, 201)
        self.assertNotIn("password", result.json())
        self.assertEqual(result.json()["role"], "salesperson")
        with self.sessions() as db:
            employee = db.get(User, result.json()["user_id"])
            self.assertEqual(employee.business_id, 1)
            self.assertTrue(verify_password(payload["password"], employee.password_hash))
        self.assertEqual(self.client.post("/employees", json=payload).status_code, 409)
        self.assertEqual(self.login("staff@example.com", "staff-password", "salesperson", "Shop A").status_code, 200)
        self.assertEqual(self.client.get("/employees").status_code, 403)
        self.assertEqual(self.client.post("/employees", json=payload).status_code, 403)

    def test_tenant_isolation_and_deactivation(self):
        self.login("a@example.com", "owner-password", "owner", "Shop A")
        result = self.client.post("/employees", json={"name": "Staff", "email": "s@example.com", "password": "staff-password"})
        employee_id = result.json()["user_id"]
        self.login("b@example.com", "owner-password", "owner", "Shop B")
        self.assertEqual(self.client.get("/employees").json(), [])
        self.assertEqual(self.client.patch(f"/employees/{employee_id}/deactivate").status_code, 404)
        self.login("s@example.com", "staff-password", "salesperson", "Shop A")
        staff_token = self.client.cookies.get("oleyn_session")
        self.client.cookies.clear()
        self.login("a@example.com", "owner-password", "owner", "Shop A")
        self.assertEqual(self.client.patch(f"/employees/{employee_id}/deactivate").status_code, 200)
        self.client.cookies.clear()
        self.client.cookies.set("oleyn_session", staff_token)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.login("s@example.com", "staff-password", "salesperson", "Shop A").status_code, 401)


if __name__ == "__main__":
    unittest.main()
