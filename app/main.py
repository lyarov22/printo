from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.endpoints.auth import router as auth_router
from app.db.session import engine, Base
from app.db.models.user import User  # Убедитесь, что модели импортированы

app = FastAPI(title=settings.PROJECT_NAME)

# Register routers
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])

@app.on_event("startup")
async def startup():
    # Создаем таблицы в базе данных
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
