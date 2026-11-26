import unittest
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import Business, LoginSession, User
from app.services.sessions import utc_now


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            business = Business(name="Test shop")
            db.add(business)
            db.flush()
            for role in ("owner", "salesperson"):
                db.add(User(business_id=business.id, name=role, email=f"{role}@example.com",
                            password_hash=hash_password("password123"), role=role))
            db.commit()

        def override_db():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def login(self, role="owner", password="password123", email=None, business_name="Test shop"):
        return self.client.post("/auth/login", json={"email": email or f"{role}@example.com", "password": password, "role": role, "business_name": business_name})

    def test_both_roles_can_login_and_access_their_identity(self):
        for role in ("owner", "salesperson"):
            with self.subTest(role=role):
                response = self.login(role)
                self.assertEqual(response.status_code, 200)
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertIn("SameSite=strict", response.headers["set-cookie"])
                self.assertEqual(response.json()["role"], role)
                self.assertEqual(self.client.get("/auth/me").json()["business_id"], 1)
                self.assertNotIn("password_hash", response.json())

    def test_missing_and_bad_credentials_are_rejected(self):
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.login(password="wrong").status_code, 401)
        self.assertEqual(self.login(email="unknown@example.com").status_code, 401)
        self.assertEqual(self.login(role="salesperson", email="owner@example.com").status_code, 401)
        self.assertEqual(self.login(business_name="Another shop").status_code, 401)
        self.assertEqual(self.login(business_name="  TEST SHOP  ").status_code, 200)

    def test_logout_revokes_session_even_if_token_is_reused(self):
        self.login()
        token = self.client.cookies.get("oleyn_session")
        self.assertEqual(self.client.post("/auth/logout").status_code, 204)
        self.client.cookies.set("oleyn_session", token)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

    def test_expired_or_deactivated_session_is_rejected(self):
        self.login()
        with self.sessions() as db:
            session = db.scalar(select(LoginSession))
            session.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.login()
        with self.sessions() as db:
            owner = db.scalar(select(User).where(User.role == "owner"))
            owner.is_active = False
            db.commit()
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.login().status_code, 401)

    def test_login_rotates_previous_session(self):
        self.login()
        old_token = self.client.cookies.get("oleyn_session")
        self.login("salesperson")
        self.client.cookies.set("oleyn_session", old_token)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()
