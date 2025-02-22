# app/api/endpoints/codes.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.repositories.login_code import create_login_code

import re

router = APIRouter()

class CodeGenerateSchema(BaseModel):
    phone: str
    code: str

def validate_phone(phone: str) -> bool:
    # Простейшая проверка на цифры + возможный плюс
    pattern = r"^\+?\d{7,15}$"
    return bool(re.match(pattern, phone))

@router.post("/generate")
async def generate_code(data: CodeGenerateSchema, db: AsyncSession = Depends(get_db)):
    """
    Генерация (сохранение) кода в БД.
    Используется ботом, когда пользователь делится номером.
    """
    if not validate_phone(data.phone):
        raise HTTPException(status_code=400, detail="Неверный формат телефона")

    # Создаём код с TTL 5 минут (по умолчанию)
    await create_login_code(db, data.phone, data.code)
    return {"status": "ok"}
