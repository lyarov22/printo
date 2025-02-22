from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models.user import User

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalars().first()

async def get_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    result = await db.execute(select(User).filter(User.phone == phone))
    return result.scalars().first()

async def create_user(db: AsyncSession, user_data: dict) -> User:
    # Перед созданием нужно убедиться, что email или phone не заняты
    phone = user_data.get("phone")
    email = user_data.get("email")

    # Проверка на дубликаты по телефону:
    if phone:
        existing_by_phone = await get_user_by_phone(db, phone)
        if existing_by_phone:
            raise ValueError("Пользователь с таким телефоном уже существует")

    # Проверка на дубликаты по email (если требуется):
    # existing_by_email = await get_user_by_email(db, email)
    # if existing_by_email:
    #    raise ValueError("Пользователь с таким email уже существует")

    user = User(**user_data)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user