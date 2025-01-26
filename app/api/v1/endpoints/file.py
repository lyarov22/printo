import re
import tempfile
from PyPDF2 import PdfReader
from fastapi import APIRouter, Depends, UploadFile, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.db.session import get_db
from fastapi import File, UploadFile
from app.schemas.file import FileUploadResponse, FileRead
from app.core.security import decode_access_token
import os
from pathlib import Path
from datetime import datetime
from docx2pdf import convert

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


def format_size(size_in_bytes):
    """Преобразует размер из байт в килобайты или мегабайты."""
    if size_in_bytes >= 1024 * 1024:
        return f"{round(size_in_bytes / (1024 * 1024), 2)} MB"
    else:
        return f"{round(size_in_bytes / 1024, 2)} KB"


def calculate_pages(file_path: str, ext: str) -> int:
    """Подсчёт страниц в файле."""
    if ext == ".pdf":
        reader = PdfReader(file_path)
        return len(reader.pages)
    elif ext == ".docx":
        pdf_path = file_path + ".pdf"
        convert(file_path, pdf_path)  # Конвертируем DOCX в PDF
        reader = PdfReader(pdf_path)
        pages = len(reader.pages)
        os.remove(pdf_path)  # Удаляем временный PDF
        return pages
    else:
        raise ValueError("Unsupported file format")


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    # Проверяем пользователя
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Находим user_id по email
    user_query = await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_email})
    user_id = user_query.scalar_one_or_none()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Проверяем допустимое расширение файла
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    # Создаём временный файл для обработки
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        pages_count = calculate_pages(tmp_path, ext)  # Подсчёт страниц
    except ValueError:
        os.remove(tmp_path)
        raise HTTPException(status_code=400, detail="Error processing file")

    # Проверяем хранилище пользователя
    query = text("SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = :user_id")
    user_files = await db.execute(query, {"user_id": user_id})
    total_size = user_files.scalar_one_or_none() or 0

    file_size = len(await file.read())  # Получаем размер загружаемого файла
    await file.seek(0)  # Возвращаем указатель на начало файла

    if (total_size + file_size) > MAX_USER_STORAGE_MB * 1024 * 1024:
        os.remove(tmp_path)
        raise HTTPException(status_code=400, detail="Storage limit exceeded")

    # Создаём уникальную директорию для пользователя
    user_upload_dir = UPLOAD_DIR / sanitize_filename(user_email)
    user_upload_dir.mkdir(exist_ok=True)

    # Генерируем безопасное имя файла
    timestamp = datetime.utcnow().isoformat().replace(":", "-")
    safe_filename = sanitize_filename(file.filename)
    filename = f"{timestamp}_{safe_filename}"
    filepath = user_upload_dir / filename

    # Сохраняем файл
    os.rename(tmp_path, filepath)

    # Добавляем запись в базу данных
    new_file = File(
        user_id=user_id,
        original_filename=file.filename,
        filename=safe_filename,
        filepath=str(filepath),
        size=file_size,
        uploaded_at=datetime.utcnow(),
        pages_count=pages_count  # Добавляем количество страниц
    )
    db.add(new_file)
    await db.commit()
    await db.refresh(new_file)

    return FileUploadResponse(
        id=new_file.id,
        filename=new_file.filename,
        size=file_size,
        pages=pages_count
    )

@router.get("/files", response_model=dict)
async def list_files(
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    # Проверяем пользователя
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Получаем user_id по user_email
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Получаем файлы пользователя
    query_files = text("SELECT * FROM files WHERE user_id = :user_id")
    result_files = await db.execute(query_files, {"user_id": user_id})
    files = [
        {
            **dict(row),
            "size": format_size(row["size"])  # Форматируем размер
        }
        for row in result_files.mappings()
    ]

    # Считаем оставшееся место
    query_storage = text(
        "SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = :user_id")
    result_storage = await db.execute(query_storage, {"user_id": user_id})
    used_storage = result_storage.scalar_one_or_none() or 0
    remaining_storage_mb = round(
        (MAX_USER_STORAGE_MB * 1024 * 1024 - used_storage) / (1024 * 1024), 2)

    return {
        "files": files,  # Теперь размер файлов форматирован
        "remaining_storage_mb": remaining_storage_mb
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
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    # Получаем user_id по user_email
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Проверяем существование файла
    query = text(
        "SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_id})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {
                file_id} not found or does not belong to the user"
        )

    # Удаляем файл с диска, если он существует
    filepath = Path(file.filepath)
    if filepath.exists():
        filepath.unlink()  # Удаляем файл с диска
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found on the disk"
        )

    # Удаляем запись из базы данных
    delete_query = text("DELETE FROM files WHERE id = :file_id")
    await db.execute(delete_query, {"file_id": file_id})
    await db.commit()


@router.patch("/files/{file_id}", status_code=status.HTTP_200_OK)
async def rename_file(
    file_id: int,
    new_name: str,
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    # Получаем user_id по user_email
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Проверяем существование файла
    query = text("SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_id})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found or does not belong to the user"
        )

    # Обновляем имя файла
    new_filename = f"{new_name}{Path(file.filename).suffix}"
    update_query = text("UPDATE files SET filename = :new_filename WHERE id = :file_id")
    await db.execute(update_query, {"new_filename": new_filename, "file_id": file_id})
    await db.commit()

    return {"message": f"File renamed to {new_filename}"}

@router.get("/files/download/{file_id}")
async def download_file(
    file_id: int,
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    # Получаем user_id по user_email
    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Проверяем существование файла
    query = text("SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_id})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found or does not belong to the user"
        )

    filepath = Path(file.filepath)
    if not filepath.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on the server"
        )

    return FileResponse(
        path=str(filepath),
        filename=file.filename,
        media_type="application/octet-stream"
    )