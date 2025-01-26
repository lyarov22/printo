from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.db.models.order import Order, OrderFile
from app.db.session import get_db
from app.core.security import decode_access_token
from app.core.config import settings  # Предположим, что конфиг загружается из settings
from typing import List
from PyPDF2 import PdfReader
from docx import Document
from pathlib import Path

router = APIRouter()

price_per_page = settings.PRICE_PER_PAGE

@router.post("/orders")
async def create_order(
    file_ids: list[int],
    copies: list[int],
    duplex: bool = False,
    token: dict = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получение ID пользователя
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Проверяем, что файлы принадлежат пользователю
    query = text("SELECT id, pages FROM files WHERE id = ANY(:file_ids) AND user_id = :user_id")
    result = await db.execute(query, {"file_ids": file_ids, "user_id": user_id})
    user_files = result.fetchall()

    if len(user_files) != len(file_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Some files do not belong to the user")

    # Рассчитываем цену на основе количества страниц из базы данных
    total_price = 0
    for idx, file in enumerate(user_files):
        total_price += file.pages * copies[idx] * price_per_page

    if duplex:
        total_price = int(total_price * 0.8)  # Скидка 20% за двустороннюю печать

    # Создаём заказ
    new_order = Order(
        user_id=user_id,
        created_at=datetime.utcnow(),
        status="pending",
        total_price=total_price,
        duplex=duplex
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)

    # Связываем файлы с заказом
    for idx, file in enumerate(user_files):
        order_file = OrderFile(
            order_id=new_order.id,
            file_id=file.id,
            copies=copies[idx]
        )
        db.add(order_file)
    await db.commit()

    return {"order_id": new_order.id, "status": new_order.status, "total_price": total_price}
