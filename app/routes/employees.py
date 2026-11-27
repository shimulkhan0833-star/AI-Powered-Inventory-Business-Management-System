from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import require_owner
from app.core.security import hash_password
from app.database import get_db
from app.models import User
from app.schemas.employee import EmployeeCreate, EmployeeResponse

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.post("", response_model=EmployeeResponse, status_code=201)
def create_employee(data: EmployeeCreate, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    email = str(data.email)
    if db.scalar(select(User.user_id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    employee = User(business_id=owner.business_id, name=data.name, email=email,
                    password_hash=hash_password(data.password), role="salesperson")
    db.add(employee)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(User.user_id).where(User.email == email)) is not None:
            raise HTTPException(status_code=409, detail="An account with this email already exists") from None
        raise
    db.refresh(employee)
    return employee


@router.get("", response_model=list[EmployeeResponse])
def list_employees(owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    return db.scalars(select(User).where(User.business_id == owner.business_id, User.role == "salesperson")).all()


@router.patch("/{employee_id}/deactivate", response_model=EmployeeResponse)
def deactivate_employee(employee_id: int, owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    employee = db.scalar(select(User).where(
        User.user_id == employee_id, User.business_id == owner.business_id, User.role == "salesperson"
    ))
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    employee.is_active = False
    db.commit()
    db.refresh(employee)
    return employee
