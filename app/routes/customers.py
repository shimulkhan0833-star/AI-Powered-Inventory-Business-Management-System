from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models import Customer, User
from app.schemas.sale import CustomerCreate, CustomerPaymentResponse, CustomerResponse, PaymentCreate
from app.services.sales import IdempotencyConflict, InvalidAmount, NotFound, customer_response, record_customer_payment

router = APIRouter(prefix="/customers", tags=["Customers and dues"])


@router.post("", response_model=CustomerResponse, status_code=201)
def add_customer(data: CustomerCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = Customer(business_id=user.business_id, name=data.name, phone=data.phone)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer_response(db, customer)


@router.get("", response_model=list[CustomerResponse])
def list_customers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customers = db.scalars(select(Customer).where(Customer.business_id == user.business_id).order_by(Customer.customer_id)).all()
    return [customer_response(db, customer) for customer in customers]


@router.get("/{customer_id}", response_model=CustomerResponse)
def read_customer(customer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.scalar(select(Customer).where(Customer.customer_id == customer_id, Customer.business_id == user.business_id))
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer_response(db, customer)


@router.post("/{customer_id}/payments", response_model=CustomerPaymentResponse, status_code=201)
def add_customer_payment(customer_id: int, data: PaymentCreate, response: Response,
                         idempotency_key: UUID = Header(...), user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    try:
        payment, created = record_customer_payment(db, user, customer_id, data.amount, str(idempotency_key))
    except NotFound:
        raise HTTPException(status_code=404, detail="Customer not found") from None
    except InvalidAmount:
        raise HTTPException(status_code=409, detail="Payment exceeds customer due") from None
    except IdempotencyConflict:
        raise HTTPException(status_code=409, detail="Idempotency key used for a different payment") from None
    if not created:
        response.status_code = 200
    return payment
