# app/db/repositories/login_code.py

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.login_code import LoginCode

async def create_login_code(db: AsyncSession, phone: str, code: str, ttl_minutes: int = 5) -> LoginCode:
    """
    Создаёт запись в БД с одноразовым кодом.
    ttl_minutes - время жизни кода (по умолчанию 5 минут).
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=ttl_minutes)

    # Можно добавить логику "если пользователь уже просил код, то не создавать чаще, чем раз в N секунд"
    # Но это тема для отдельного rate-limit.

    login_code = LoginCode(
        phone=phone,
        code=code,
        created_at=now,
        expires_at=expires_at,
        is_used=False
    )
    db.add(login_code)
    await db.commit()
    await db.refresh(login_code)
    return login_code

async def get_valid_login_code(db: AsyncSession, phone: str, code: str) -> LoginCode | None:
    """
    Ищет неиспользованный код, ещё не истёкший и соответствующий телефону.
    """
    now = datetime.utcnow()
    query = (
        select(LoginCode)
        .where(LoginCode.phone == phone)
        .where(LoginCode.code == code)
        .where(LoginCode.is_used == False)
        .where(LoginCode.expires_at > now)
    )
    result = await db.execute(query)
    return result.scalars().first()

async def mark_code_as_used(db: AsyncSession, code_instance: LoginCode) -> None:
    """Помечаем код как использованный (чтобы нельзя было использовать повторно)."""
    code_instance.is_used = True
    await db.commit()
    await db.refresh(code_instance)
