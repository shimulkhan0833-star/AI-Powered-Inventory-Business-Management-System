from fastapi import FastAPI

from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.employees import router as employees_router
from app.routes.products import router as products_router
from app.routes.purchases import router as purchases_router
from app.routes.customers import router as customers_router
from app.routes.sales import router as sales_router

app = FastAPI(title="Oleyn Stock")
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(employees_router)
app.include_router(products_router)
app.include_router(purchases_router)
app.include_router(customers_router)
app.include_router(sales_router)
