import re
from fastapi import APIRouter, Depends, UploadFile, HTTPException, status
from fastapi.responses import FileResponse
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
ALLOWED_EXTENSIONS = {".docx", ".doc", ".pdf", ".png", ".jpg"}
MAX_FILE_SIZE_MB = 10  # Максимальный размер файла в мегабайтах


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Проверяем расширение файла
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File format not allowed. Allowed formats: {
                ', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Проверяем размер файла
    # Получаем размер загружаемого файла в байтах
    file_size = len(await file.read())
    await file.seek(0)  # Возвращаем указатель на начало файла
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds {MAX_FILE_SIZE_MB} MB limit"
        )

    # Создаем уникальную директорию для пользователя
    user_upload_dir = UPLOAD_DIR / sanitize_filename(user_email)
    user_upload_dir.mkdir(exist_ok=True)

    # Проверяем объем данных, хранящихся пользователем
    query = text(
        "SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = :user_id")
    user_files = await db.execute(query, {"user_id": user_email})
    total_size = user_files.scalar_one_or_none() or 0

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
        original_filename=file.filename,  # Сохраняем оригинальное имя
        filename=filename,
        filepath=str(filepath),
        size=file_size,
        uploaded_at=datetime.utcnow()
    )
    db.add(new_file)
    await db.commit()
    await db.refresh(new_file)

    return FileUploadResponse(id=new_file.id, filename=new_file.filename, size=new_file.size)


@router.get("/files", response_model=dict)
async def list_files(
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получаем список файлов пользователя
    query = text("SELECT * FROM files WHERE user_id = :user_id")
    result = await db.execute(query, {"user_id": user_email})
    files = result.fetchall()

    # Подсчитываем общий размер загруженных файлов
    query_size = text("SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = :user_id")
    result_size = await db.execute(query_size, {"user_id": user_email})
    total_size = result_size.scalar_one_or_none() or 0

    # Вычисляем оставшееся место
    max_storage = MAX_USER_STORAGE_MB * 1024 * 1024  # Преобразуем МБ в байты
    remaining_storage = max_storage - total_size
    remaining_storage_mb = round(remaining_storage / (1024 * 1024), 2)

    # Конвертируем размер файла в удобочитаемый формат
    def format_size(size):
        if size >= 1024 * 1024:
            return f"{round(size / (1024 * 1024), 2)} MB"
        elif size >= 1024:
            return f"{round(size / 1024, 2)} KB"
        else:
            return f"{size} B"

    return {
        "files": [
            {
                "id": file.id,
                "original_filename": file.original_filename,
                "filename": file.filename,
                "filepath": file.filepath,
                "size": format_size(file.size),
                "uploaded_at": file.uploaded_at
            } for file in files
        ],
        "remaining_storage_mb": remaining_storage_mb,
    }

@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: int,
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    query = text(
        "SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_email})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    filepath = Path(file.filepath)
    if filepath.exists():
        filepath.unlink()  # Удаляем файл с диска

    delete_query = text("DELETE FROM files WHERE id = :file_id")
    await db.execute(delete_query, {"file_id": file_id})
    await db.commit()


@router.patch("/files/{file_id}", response_model=FileRead)
async def rename_file(
    file_id: int,
    new_name: str,
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Проверяем, что файл принадлежит пользователю
    query = text(
        "SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_email})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Извлекаем расширение исходного файла
    original_extension = Path(file.original_filename).suffix
    if not original_extension:
        # Если нет в оригинальном имени, берём из реального
        original_extension = Path(file.filename).suffix

    # Генерируем новое имя с расширением
    sanitized_name = sanitize_filename(new_name) + original_extension

    # Обновляем оригинальное имя файла в базе данных
    update_query = text(
        "UPDATE files SET original_filename = :original_filename WHERE id = :file_id"
    )
    await db.execute(update_query, {"original_filename": sanitized_name, "file_id": file_id})
    await db.commit()

    return FileRead(
        id=file.id,
        original_filename=sanitized_name,
        filename=file.filename,
        filepath=file.filepath,
        size=file.size,
        uploaded_at=file.uploaded_at
    )


@router.get("/files/download/{file_id}", response_class=FileResponse)
async def download_file(
    file_id: int,
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    # Проверяем пользователя
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Ищем файл в базе данных
    query = text(
        "SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_email})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Проверяем, существует ли файл на диске
    filepath = Path(file.filepath)
    if not filepath.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="File not found on disk")

    # Возвращаем файл в ответе
    return FileResponse(
        path=filepath,
        media_type="application/octet-stream",
        filename=file.original_filename  # Имя файла, которое увидит пользователь
    )
