from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from datetime import datetime
from app.db.session import get_db
from app.core.security import decode_access_token  # Импорт функции для проверки токена

router = APIRouter()

@router.post("/pay/{order_id}")
async def process_payment(
    order_id: int,
    token: dict = Depends(decode_access_token),  # Проверка токена
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")  # Получаем email пользователя из токена
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получение ID пользователя
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Проверяем существование заказа
    query_order = text("SELECT * FROM orders WHERE id = :order_id AND user_id = :user_id")
    result_order = await db.execute(query_order, {"order_id": order_id, "user_id": user_id})
    order = result_order.fetchone()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.status != "created":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is not in 'created' status")

    # Обновляем статус на 'paid'
    query_update = text("UPDATE orders SET status = :status, updated_at = :updated_at WHERE id = :order_id")
    await db.execute(query_update, {
        "status": "paid",
        "updated_at": datetime.utcnow(),
        "order_id": order_id
    })
    await db.commit()

    return {"order_id": order_id, "status": "paid"}
