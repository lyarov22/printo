from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

Base = declarative_base()

# Создаем движок для PostgreSQL
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,  # Лог SQL-запросов, можно отключить в продакшене
)

async_session = sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Генератор для получения сессий
async def get_db():
    async with async_session() as session:
        yield session
