from html import escape
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models import SalesInvoice, User
from app.schemas.sale import PaymentCreate, PaymentResponse, SaleCreate, SaleResponse
from app.services.sales import (IdempotencyConflict, InsufficientStock, InvalidAmount, NotFound,
                                create_sale, get_invoice, invoice_response, record_payment)

router = APIRouter(prefix="/sales", tags=["Sales and invoices"])


@router.post("", response_model=SaleResponse, status_code=201)
def add_sale(data: SaleCreate, response: Response, idempotency_key: UUID = Header(...),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        invoice, created = create_sale(db, user, data, str(idempotency_key))
    except NotFound:
        raise HTTPException(status_code=404, detail="Customer or product not found") from None
    except InsufficientStock:
        raise HTTPException(status_code=409, detail="Insufficient stock") from None
    except InvalidAmount:
        raise HTTPException(status_code=422, detail="Invalid total or initial payment") from None
    except IdempotencyConflict:
        raise HTTPException(status_code=409, detail="Idempotency key used for a different sale") from None
    if not created:
        response.status_code = 200
    return invoice


@router.get("", response_model=list[SaleResponse])
def list_sales(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoices = db.scalars(select(SalesInvoice).where(SalesInvoice.business_id == user.business_id)
                          .order_by(SalesInvoice.invoice_id.desc())).all()
    return [invoice_response(db, invoice) for invoice in invoices]


@router.get("/{invoice_id}", response_model=SaleResponse)
def read_sale(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return invoice_response(db, get_invoice(db, user.business_id, invoice_id))
    except NotFound:
        raise HTTPException(status_code=404, detail="Invoice not found") from None


@router.post("/{invoice_id}/payments", response_model=PaymentResponse, status_code=201)
def add_payment(invoice_id: int, data: PaymentCreate, response: Response, idempotency_key: UUID = Header(...),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        payment, created = record_payment(db, user, invoice_id, data.amount, str(idempotency_key))
    except NotFound:
        raise HTTPException(status_code=404, detail="Invoice not found") from None
    except InvalidAmount:
        raise HTTPException(status_code=409, detail="Payment exceeds invoice due") from None
    except IdempotencyConflict:
        raise HTTPException(status_code=409, detail="Idempotency key used for a different payment") from None
    if not created:
        response.status_code = 200
    return payment


@router.get("/{invoice_id}/print", response_class=HTMLResponse)
def print_invoice(invoice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        invoice = invoice_response(db, get_invoice(db, user.business_id, invoice_id))
    except NotFound:
        raise HTTPException(status_code=404, detail="Invoice not found") from None
    rows = "".join(f"<tr><td>{escape(item.product_name)}</td><td>{item.quantity}</td>"
                   f"<td>{item.unit_price:.2f}</td><td>{item.quantity * item.unit_price:.2f}</td></tr>"
                   for item in invoice.items)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Invoice {invoice.invoice_id}</title>
<style>body{{font:16px Arial,sans-serif;max-width:750px;margin:2rem auto;padding:0 1rem;color:#222}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.6rem;border-bottom:1px solid #ddd;text-align:left}}
.totals{{text-align:right}}@media print{{button{{display:none}}}}</style></head><body>
<h1>{escape(invoice.business_name)}</h1><h2>Invoice #{invoice.invoice_id}</h2>
<p>Customer: {escape(invoice.customer_name)}<br>Salesperson: {escape(invoice.salesperson_name)}<br>
Created (UTC): {invoice.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
<table><thead><tr><th>Product</th><th>Quantity</th><th>Unit price (BDT)</th><th>Total (BDT)</th></tr></thead>
<tbody>{rows}</tbody></table><div class="totals"><p>Total: BDT {invoice.total:.2f}</p>
<p>Paid: BDT {invoice.paid:.2f}</p><p>Due: BDT {invoice.due:.2f}</p></div>
<button onclick="window.print()">Print invoice</button></body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})
