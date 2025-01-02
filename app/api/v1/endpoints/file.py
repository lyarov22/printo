import re
from fastapi import APIRouter, Depends, UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.db.session import get_db
from app.db.models.file import File
from app.schemas.file import FileUploadResponse, FileRead
from app.core.security import decode_access_token
import os
from pathlib import Path
from datetime import datetime

router = APIRouter()
UPLOAD_DIR = Path("./uploads")  # Директория для хранения файлов
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_USER_STORAGE_MB = 100

def sanitize_filename(filename: str) -> str:
    """
    Убираем недопустимые символы из имени файла.
    """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile,
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    # Проверяем пользователя
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Создаем уникальную директорию для пользователя
    user_upload_dir = UPLOAD_DIR / sanitize_filename(user_email)
    user_upload_dir.mkdir(exist_ok=True)

    # Проверяем объем данных, хранящихся пользователем
    query = text("SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = :user_id")
    user_files = await db.execute(query, {"user_id": user_email})
    total_size = user_files.scalar_one_or_none() or 0

    file_size = len(await file.read())  # Получаем размер загружаемого файла
    await file.seek(0)  # Возвращаем указатель на начало файла

    if (total_size + file_size) > MAX_USER_STORAGE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Storage limit exceeded")

    # Генерируем безопасное имя файла
    timestamp = datetime.utcnow().isoformat().replace(":", "-")  # Заменяем `:` на `-`
    safe_filename = sanitize_filename(file.filename)
    filename = f"{timestamp}_{safe_filename}"
    filepath = user_upload_dir / filename

    # Сохраняем файл
    with open(filepath, "wb") as f:
        f.write(await file.read())

    # Добавляем запись в БД
    new_file = File(
        user_id=user_email,
        filename=file.filename,
        filepath=str(filepath),
        size=file_size,
    )
    db.add(new_file)
    await db.commit()
    await db.refresh(new_file)

    return FileUploadResponse(id=new_file.id, filename=new_file.filename, size=new_file.size)