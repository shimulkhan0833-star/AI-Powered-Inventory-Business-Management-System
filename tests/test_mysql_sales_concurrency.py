"""Opt-in MySQL integration test; creates and removes only its own fixture rows."""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Business, Customer, Payment, Product, SalesInvoice, SalesInvoiceItem, StockMovement, User
from app.schemas.sale import SaleCreate
from app.services.sales import InsufficientStock, InvalidAmount, create_sale, record_payment


@unittest.skipUnless(os.getenv("RUN_MYSQL_CONCURRENCY") == "1", "Requires explicit MySQL integration opt-in")
class MySQLSalesConcurrencyTests(unittest.TestCase):
    def test_last_unit_can_only_be_sold_once(self):
        engine = get_engine()
        marker = uuid4().hex
        business_id = None
        try:
            with Session(engine) as db:
                business = Business(name=f"Concurrency test {marker}")
                db.add(business)
                db.flush()
                business_id = business.business_id
                owner = User(business_id=business_id, name="Test", email=f"{marker}@example.invalid",
                             password_hash="test-only", role="owner")
                customer = Customer(business_id=business_id, name="Test customer")
                product = Product(business_id=business_id, name="Test product", sku="TEST",
                                  selling_price=Decimal("10"), stock_quantity=1)
                db.add_all([owner, customer, product])
                db.flush()
                user_id, customer_id, product_id = owner.user_id, customer.customer_id, product.product_id
                db.commit()

            barrier = threading.Barrier(2)

            def sell_one():
                with Session(engine) as db:
                    user = db.get(User, user_id)
                    body = SaleCreate(customer_id=customer_id, items=[{"product_id": product_id, "quantity": 1}])
                    barrier.wait(timeout=10)
                    try:
                        create_sale(db, user, body, str(uuid4()))
                        return "saved"
                    except InsufficientStock:
                        return "insufficient"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: sell_one(), range(2)))
            self.assertCountEqual(outcomes, ["saved", "insufficient"])
            with Session(engine) as db:
                self.assertEqual(db.get(Product, product_id).stock_quantity, 0)
                invoices = db.scalars(select(SalesInvoice).where(SalesInvoice.business_id == business_id)).all()
                self.assertEqual(len(invoices), 1)
                invoice_id = invoices[0].invoice_id

            barrier = threading.Barrier(2)

            def pay_seven():
                with Session(engine) as db:
                    user = db.get(User, user_id)
                    barrier.wait(timeout=10)
                    try:
                        record_payment(db, user, invoice_id, Decimal("7.00"), str(uuid4()))
                        return "saved"
                    except InvalidAmount:
                        return "exceeds due"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: pay_seven(), range(2)))
            self.assertCountEqual(outcomes, ["saved", "exceeds due"])
            with Session(engine) as db:
                self.assertEqual(db.get(SalesInvoice, invoice_id).paid_amount, Decimal("7.00"))
        finally:
            if business_id is not None:
                with Session(engine) as db:
                    # Restrict cleanup to the business created by this test.
                    fixture = db.scalar(select(Business.business_id).where(
                        Business.business_id == business_id, Business.name == f"Concurrency test {marker}"
                    ))
                    if fixture is not None:
                        for model in (StockMovement, Payment, SalesInvoiceItem, SalesInvoice, Product, Customer, User):
                            db.execute(delete(model).where(model.business_id == business_id))
                        db.execute(delete(Business).where(Business.business_id == business_id, Business.name == f"Concurrency test {marker}"))
                        db.commit()
