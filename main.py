from fastapi import FastAPI
from fastapi_utils.tasks import repeat_every
from app.core.config import settings
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.codes import router as codes_router
from app.api.v1.endpoints.file import router as file_router
from app.api.v1.endpoints.order import router as order_router
from app.api.v1.endpoints.payment import router as payment_router
from app.api.v1.endpoints.print import router as print_router
from app.db.session import engine, Base, get_db
from app.tasks.cleanup import cleanup_old_files
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME)
api_version = settings.API_V1_STR

# Register routers
app.include_router(auth_router, prefix=f"{api_version}/auth", tags=["auth"])
app.include_router(codes_router, prefix=f"{api_version}/codes", tags=["codes"])
app.include_router(file_router, prefix=f"{api_version}/files", tags=["files"])
app.include_router(order_router, prefix=f"{api_version}/orders", tags=["orders"])
app.include_router(payment_router, prefix=f"{api_version}", tags=["payments"])
app.include_router(print_router, prefix=f"{api_version}", tags=["print"])

@app.on_event("startup")
async def startup():
    # Создаем таблицы в базе данных
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Startup event completed. Database tables created.")

# Отдельная регистрация повторяющейся задачи
@app.on_event("startup")
@repeat_every(seconds=3600)  # Выполняем раз в час
async def schedule_cleanup():
    async for db in get_db():  # Используем get_db как генератор
        await cleanup_old_files(db)
