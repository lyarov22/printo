from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.db.models.order import Order, OrderFile
from app.db.session import get_db
from app.core.config import settings
from app.core.security import decode_access_token
from typing import List

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
    query = text("SELECT id, pages_count FROM files WHERE id = ANY(:file_ids) AND user_id = :user_id")
    result = await db.execute(query, {"file_ids": file_ids, "user_id": user_id})
    user_files = result.fetchall()

    if len(user_files) != len(file_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Some files do not belong to the user")

    # Рассчитываем цену на основе количества страниц из базы данных
    total_price = 0
    files_with_pages = []
    for idx, file in enumerate(user_files):
        file_data = {"file_id": file.id, "pages_count": file.pages_count, "copies": copies[idx]}
        files_with_pages.append(file_data)
        total_price += file.pages_count * copies[idx] * price_per_page

    if duplex:
        total_price = int(total_price * 0.8)  # Скидка 20% за двустороннюю печать

    # Создаём заказ
    new_order = Order(
        user_id=user_id,
        created_at=datetime.utcnow(),
        status="created",
        total_price=total_price,
        duplex=duplex
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)

    # Связываем файлы с заказом
    for file_data in files_with_pages:
        order_file = OrderFile(
            order_id=new_order.id,
            file_id=file_data["file_id"],
            copies=file_data["copies"]
        )
        db.add(order_file)
    await db.commit()

    return {
        "order_id": new_order.id,
        "status": new_order.status,
        "total_price": total_price,
        "files": files_with_pages
    }


@router.get("/orders")
async def list_orders(
    token: dict = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получаем ID пользователя
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Получаем список заказов
    query_orders = text("SELECT * FROM orders WHERE user_id = :user_id ORDER BY created_at DESC")
    result_orders = await db.execute(query_orders, {"user_id": user_id})
    orders = result_orders.mappings().all()  # Преобразуем в список словарей

    return {"orders": orders}



@router.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    token: dict = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получаем ID пользователя
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Получаем информацию о заказе
    query_order = text("SELECT * FROM orders WHERE id = :order_id AND user_id = :user_id")
    result_order = await db.execute(query_order, {"order_id": order_id, "user_id": user_id})
    order = result_order.mappings().first()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # Преобразуем RowMapping в словарь
    order = dict(order)

    # Получаем информацию о файлах, связанных с заказом
    query_files = text("""
        SELECT 
            f.id AS file_id,
            f.original_filename,
            f.pages_count,
            of.copies
        FROM order_files of
        JOIN files f ON of.file_id = f.id
        WHERE of.order_id = :order_id
    """)
    result_files = await db.execute(query_files, {"order_id": order_id})
    files = result_files.mappings().all()

    # Добавляем информацию о файлах к заказу
    order["files"] = files

    return order


@router.delete("/orders/{order_id}")
async def delete_order(
    order_id: int,
    token: dict = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получаем ID пользователя
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Удаляем связанные записи из order_files
    query_delete_files = text("DELETE FROM order_files WHERE order_id = :order_id")
    await db.execute(query_delete_files, {"order_id": order_id})

    # Удаляем заказ
    query_delete_order = text("DELETE FROM orders WHERE id = :order_id AND user_id = :user_id RETURNING id")
    result_delete_order = await db.execute(query_delete_order, {"order_id": order_id, "user_id": user_id})
    deleted_order = result_delete_order.fetchone()

    if not deleted_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found or already deleted")

    await db.commit()
    return {"message": f"Order {order_id} deleted successfully"}
