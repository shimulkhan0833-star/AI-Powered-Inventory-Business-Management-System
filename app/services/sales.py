"""Atomic invoices, stock-outs, and invoice payments."""

import hashlib
import json
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Business, Customer, CustomerPayment, Payment, Product, SalesInvoice, SalesInvoiceItem, StockMovement, User
from app.schemas.sale import CustomerPaymentResponse, CustomerResponse, PaymentResponse, SaleCreate, SaleItemResponse, SaleResponse
from app.services.sessions import utc_now


class NotFound(Exception):
    pass


class InsufficientStock(Exception):
    pass


class InvalidAmount(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


def customer_response(db: Session, customer: Customer) -> CustomerResponse:
    due = db.scalar(select(func.coalesce(func.sum(SalesInvoice.total - SalesInvoice.paid_amount), 0)).where(
        SalesInvoice.business_id == customer.business_id, SalesInvoice.customer_id == customer.customer_id
    ))
    return CustomerResponse(customer_id=customer.customer_id, name=customer.name, phone=customer.phone, due=due)


def invoice_response(db: Session, invoice: SalesInvoice) -> SaleResponse:
    items = db.scalars(select(SalesInvoiceItem).where(
        SalesInvoiceItem.business_id == invoice.business_id, SalesInvoiceItem.invoice_id == invoice.invoice_id
    ).order_by(SalesInvoiceItem.invoice_item_id)).all()
    payments = db.scalars(select(Payment).where(
        Payment.business_id == invoice.business_id, Payment.invoice_id == invoice.invoice_id
    ).order_by(Payment.payment_id)).all()
    return SaleResponse(invoice_id=invoice.invoice_id, business_id=invoice.business_id, business_name=invoice.business_name,
                        customer_id=invoice.customer_id, customer_name=invoice.customer_name,
                        user_id=invoice.user_id, salesperson_name=invoice.salesperson_name,
                        created_at=invoice.created_at, total=invoice.total, paid=invoice.paid_amount,
                        due=invoice.total - invoice.paid_amount,
                        items=[SaleItemResponse.model_validate(item) for item in items],
                        payments=[PaymentResponse.model_validate(payment) for payment in payments])


def invoice_digest(data: SaleCreate) -> str:
    payload = {"customer_id": data.customer_id,
               "initial_payment": str(data.initial_payment.quantize(Decimal("0.01"))),
               "items": [{"product_id": item.product_id, "quantity": item.quantity}
                         for item in sorted(data.items, key=lambda item: item.product_id)]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def get_invoice(db: Session, business_id: int, invoice_id: int, *, lock: bool = False) -> SalesInvoice:
    query = select(SalesInvoice).where(SalesInvoice.business_id == business_id, SalesInvoice.invoice_id == invoice_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    invoice = db.scalar(query)
    if invoice is None:
        raise NotFound
    return invoice


def create_sale(db: Session, user: User, data: SaleCreate, key: str) -> tuple[SaleResponse, bool]:
    business_id, user_id, user_name = user.business_id, user.user_id, user.name
    digest = invoice_digest(data)
    customer = db.scalar(select(Customer).where(Customer.customer_id == data.customer_id, Customer.business_id == business_id))
    business = db.get(Business, business_id)
    if customer is None or business is None:
        raise NotFound
    invoice = SalesInvoice(business_id=business_id, customer_id=customer.customer_id, user_id=user_id,
                           business_name=business.name, customer_name=customer.name, salesperson_name=user_name,
                           total=Decimal("0"), paid_amount=Decimal("0"), idempotency_key=key,
                           request_hash=digest, created_at=utc_now())
    try:
        db.add(invoice)
        db.flush()
        total = Decimal("0")
        for line in sorted(data.items, key=lambda item: item.product_id):
            product = db.scalar(select(Product).where(Product.product_id == line.product_id,
                Product.business_id == business_id).with_for_update().execution_options(populate_existing=True))
            if product is None:
                raise NotFound
            if product.stock_quantity < line.quantity:
                raise InsufficientStock
            total += product.selling_price * line.quantity
            if total > Decimal("9999999999999999.99"):
                raise InvalidAmount
            product.stock_quantity -= line.quantity
            db.add(SalesInvoiceItem(business_id=business_id, invoice_id=invoice.invoice_id, product_id=product.product_id,
                                    product_name=product.name, sku=product.sku, quantity=line.quantity,
                                    unit_price=product.selling_price))
            db.add(StockMovement(business_id=business_id, product_id=product.product_id, user_id=user_id,
                                 invoice_id=invoice.invoice_id, quantity_change=-line.quantity,
                                 movement_type="sale", reason=f"Sale #{invoice.invoice_id}", created_at=utc_now()))
        if data.initial_payment > total:
            raise InvalidAmount
        invoice.total, invoice.paid_amount = total, data.initial_payment
        if data.initial_payment > 0:
            db.add(Payment(business_id=business_id, invoice_id=invoice.invoice_id, user_id=user_id,
                           amount=data.initial_payment, created_at=utc_now()))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(SalesInvoice).where(SalesInvoice.business_id == business_id,
                                                        SalesInvoice.idempotency_key == key))
        if existing is None:
            raise
        if existing.request_hash != digest:
            raise IdempotencyConflict from None
        return invoice_response(db, existing), False
    except Exception:
        db.rollback()
        raise
    db.refresh(invoice)
    return invoice_response(db, invoice), True


def record_payment(db: Session, user: User, invoice_id: int, amount: Decimal, key: str) -> tuple[PaymentResponse, bool]:
    business_id, user_id = user.business_id, user.user_id
    try:
        invoice = get_invoice(db, business_id, invoice_id, lock=True)
        existing = db.scalar(select(Payment).where(Payment.business_id == business_id,
            Payment.idempotency_key == key).with_for_update())
        if existing is not None:
            if existing.invoice_id != invoice_id or existing.amount != amount:
                raise IdempotencyConflict
            return PaymentResponse.model_validate(existing), False
        if amount > invoice.total - invoice.paid_amount:
            raise InvalidAmount
        payment = Payment(business_id=business_id, invoice_id=invoice.invoice_id, user_id=user_id,
                          amount=amount, idempotency_key=key, created_at=utc_now())
        db.add(payment)
        invoice.paid_amount += amount
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Payment).where(Payment.business_id == business_id, Payment.idempotency_key == key))
        if existing is None:
            raise
        if existing.invoice_id != invoice_id or existing.amount != amount:
            raise IdempotencyConflict from None
        return PaymentResponse.model_validate(existing), False
    except Exception:
        db.rollback()
        raise
    db.refresh(payment)
    return PaymentResponse.model_validate(payment), True


def customer_payment_response(db: Session, batch: CustomerPayment) -> CustomerPaymentResponse:
    allocations = db.scalars(select(Payment).where(Payment.business_id == batch.business_id,
        Payment.customer_payment_id == batch.customer_payment_id).order_by(Payment.payment_id)).all()
    return CustomerPaymentResponse(customer_payment_id=batch.customer_payment_id, customer_id=batch.customer_id,
        amount=batch.amount, created_at=batch.created_at,
        allocations=[PaymentResponse.model_validate(payment) for payment in allocations])


def record_customer_payment(db: Session, user: User, customer_id: int, amount: Decimal, key: str) -> tuple[CustomerPaymentResponse, bool]:
    business_id, user_id = user.business_id, user.user_id

    def previous():
        return db.scalar(select(CustomerPayment).where(CustomerPayment.business_id == business_id,
            CustomerPayment.idempotency_key == key))

    def replay(batch):
        if batch.customer_id != customer_id or batch.amount != amount:
            raise IdempotencyConflict
        return customer_payment_response(db, batch), False

    try:
        customer = db.scalar(select(Customer).where(Customer.business_id == business_id, Customer.customer_id == customer_id))
        if customer is None:
            raise NotFound
        existing = previous()
        if existing is not None:
            return replay(existing)
        batch = CustomerPayment(business_id=business_id, customer_id=customer_id, user_id=user_id,
                                amount=amount, idempotency_key=key, created_at=utc_now())
        db.add(batch)
        db.flush()
        invoices = db.scalars(select(SalesInvoice).where(
            SalesInvoice.business_id == business_id, SalesInvoice.customer_id == customer_id,
            SalesInvoice.paid_amount < SalesInvoice.total,
        ).order_by(SalesInvoice.created_at, SalesInvoice.invoice_id).with_for_update().execution_options(populate_existing=True)).all()
        if amount > sum((invoice.total - invoice.paid_amount for invoice in invoices), Decimal("0")):
            raise InvalidAmount
        remaining = amount
        for invoice in invoices:
            if remaining <= 0:
                break
            allocated = min(remaining, invoice.total - invoice.paid_amount)
            invoice.paid_amount += allocated
            db.add(Payment(business_id=business_id, invoice_id=invoice.invoice_id, user_id=user_id,
                           customer_payment_id=batch.customer_payment_id, amount=allocated, created_at=utc_now()))
            remaining -= allocated
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = previous()
        if existing is None:
            raise
        return replay(existing)
    except Exception:
        db.rollback()
        raise
    db.refresh(batch)
    return customer_payment_response(db, batch), True
