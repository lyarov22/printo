from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.db.models.order import Order, OrderFile
from app.db.session import get_db
from app.core.security import decode_access_token
from app.core.config import settings  # Предположим, что конфиг загружается из settings
from typing import List

router = APIRouter()

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
    query_files = text("SELECT * FROM files WHERE id = ANY(:file_ids) AND user_id = :user_id")
    result_files = await db.execute(query_files, {"file_ids": file_ids, "user_id": user_id})
    user_files = result_files.fetchall()

    if len(user_files) != len(file_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Some files do not belong to the user"
        )

    # Рассчитываем общую стоимость заказа
    total_price = sum(
        copies[idx] * settings.PRICE_PER_PAGE * (2 if duplex else 1)
        for idx in range(len(file_ids))
    )

    # Создаем новый заказ
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

@router.get("/orders", response_model=list[dict])
async def list_user_orders(
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

    # Получение списка заказов
    query_orders = text("""
        SELECT 
            o.id AS order_id,
            o.created_at,
            o.status,
            o.total_price,
            o.duplex,
            json_agg(json_build_object(
                'file_id', f.id,
                'filename', f.original_filename,
                'copies', of.copies
            )) AS files
        FROM orders o
        JOIN order_files of ON o.id = of.order_id
        JOIN files f ON of.file_id = f.id
        WHERE o.user_id = :user_id
        GROUP BY o.id
        ORDER BY o.created_at DESC
    """)
    result_orders = await db.execute(query_orders, {"user_id": user_id})
    orders = result_orders.fetchall()

    if not orders:
        return []

    # Преобразуем результат в удобный формат
    return [
        {
            "order_id": order.order_id,
            "created_at": order.created_at,
            "status": order.status,
            "total_price": order.total_price,
            "duplex": order.duplex,
            "files": order.files,
        }
        for order in orders
    ]