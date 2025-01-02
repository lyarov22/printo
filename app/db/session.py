from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Базовый класс моделей
Base = declarative_base()

# Подключение к SQLite
if "sqlite" in settings.DATABASE_URL:
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

engine = create_async_engine(
    settings.DATABASE_URL, 
    connect_args=connect_args, 
    echo=True
)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db():
    async with async_session() as session:
        yield session
