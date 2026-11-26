import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import verify_password
from app.database import Base, get_db
from app.main import app
from app.models import Business, User
from app.schemas.auth import BusinessRegistration
from app.services.registration import register_business


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        def override_db():
            with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.payload = {
            "business_name": "Rahim Traders",
            "owner_name": "Rahim",
            "email": "Rahim@example.com",
            "password": "a-strong-password",
        }

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_registration_creates_linked_owner_with_hashed_password(self):
        response = self.client.post("/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertNotIn("password", body)
        self.assertEqual(body["role"], "owner")
        self.assertEqual(body["email"], "rahim@example.com")
        with self.session_factory() as db:
            owner = db.get(User, body["user_id"])
            self.assertEqual(owner.business_id, body["business_id"])
            self.assertEqual(db.get(Business, owner.business_id).name, "Rahim Traders")
            self.assertNotEqual(owner.password_hash, self.payload["password"])
            self.assertTrue(verify_password(self.payload["password"], owner.password_hash))

    def test_duplicate_email_does_not_create_another_business(self):
        self.assertEqual(self.client.post("/auth/register", json=self.payload).status_code, 201)
        response = self.client.post("/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 409)
        with self.session_factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Business)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 1)

    def test_invalid_input_is_rejected_without_creating_records(self):
        for invalid in (
            {"email": "not-an-email"},
            {"password": "short"},
            {"business_name": "   "},
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(
                    self.client.post("/auth/register", json={**self.payload, **invalid}).status_code,
                    422,
                )
        with self.session_factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Business)), 0)

    def test_failure_after_business_insert_rolls_back_both_records(self):
        with self.session_factory() as db:
            original_flush = db.flush
            calls = 0

            def fail_on_owner_flush():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("Simulated failure while saving owner")
                original_flush()

            with patch.object(db, "flush", side_effect=fail_on_owner_flush):
                with self.assertRaises(RuntimeError):
                    register_business(db, BusinessRegistration(**self.payload))
            self.assertEqual(db.scalar(select(func.count()).select_from(Business)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 0)


if __name__ == "__main__":
    unittest.main()
