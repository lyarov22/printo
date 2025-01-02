from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.db.session import get_db
from app.db.models.order import Order, OrderFile
from app.db.models.file import File
from app.core.security import decode_access_token
from datetime import datetime

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

    # Проверяем, что файлы принадлежат пользователю
    query = text("SELECT * FROM files WHERE id IN :file_ids AND user_id = :user_id")
    result = await db.execute(query, {"file_ids": tuple(file_ids), "user_id": user_email})
    user_files = result.fetchall()

    if len(user_files) != len(file_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Some files do not belong to the user")

    # Рассчитываем цену (пример: 10 единиц за страницу, учитываем копии)
    total_price = sum(
        len(file.size) * copies[idx] * (2 if duplex else 1)
        for idx, file in enumerate(user_files)
    )

    # Создаем заказ
    new_order = Order(
        user_id=user_email,
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
