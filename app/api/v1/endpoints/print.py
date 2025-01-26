from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from datetime import datetime
from app.db.session import get_db
from app.core.security import decode_access_token
import subprocess
from pathlib import Path
import os

router = APIRouter()

PDF_PRINTER_NAME = "PDF"  # Имя виртуального принтера PDF

@router.post("/print/{order_id}")
async def send_to_virtual_printer(
    order_id: int,
    token: dict = Depends(decode_access_token),  # Авторизация через токен
    db: AsyncSession = Depends(get_db)
):
    # Проверка авторизации
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получаем ID пользователя
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Проверяем заказ
    query_order = text("SELECT * FROM orders WHERE id = :order_id AND user_id = :user_id")
    result_order = await db.execute(query_order, {"order_id": order_id, "user_id": user_id})
    order = result_order.fetchone()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.status != "paid":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is not in 'paid' status")

    # Получаем временные PDF-файлы заказа
    query_files = text("SELECT f.temp_pdf_path FROM order_files of JOIN files f ON of.file_id = f.id WHERE of.order_id = :order_id")
    result_files = await db.execute(query_files, {"order_id": order_id})
    files = result_files.fetchall()

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files associated with this order")

    # Печать файлов на виртуальный принтер
    for file in files:
        temp_pdf_path = file.temp_pdf_path
        if not temp_pdf_path or not Path(temp_pdf_path).exists():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Temporary PDF file {temp_pdf_path} does not exist")

        try:
            # Отправляем PDF-файл на принтер
            subprocess.run(["lp", "-d", PDF_PRINTER_NAME, temp_pdf_path], check=True)
            print(f"Файл {temp_pdf_path} отправлен на принтер {PDF_PRINTER_NAME}")
            
            # Удаляем временный файл после успешной печати
            os.remove(temp_pdf_path)
            print(f"Временный файл {temp_pdf_path} удалён")
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка печати файла {temp_pdf_path}: {e}")

    # Обновляем статус заказа
    query_update = text("UPDATE orders SET status = :status, updated_at = :updated_at WHERE id = :order_id")
    await db.execute(query_update, {
        "status": "closed",
        "updated_at": datetime.utcnow(),
        "order_id": order_id
    })
    await db.commit()

    return {"order_id": order_id, "status": "closed", "message": "Files sent to virtual printer and temporary files deleted"}
