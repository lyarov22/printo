import re
import subprocess
import tempfile
from PyPDF2 import PdfReader
from fastapi import APIRouter, Depends, UploadFile, HTTPException, status, File as FastAPIFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.db.models.file import File
from app.db.session import get_db
from app.schemas.file import FileUploadResponse
from app.core.security import decode_access_token
import os
from pathlib import Path
from datetime import datetime

router = APIRouter()
UPLOAD_DIR = Path("./uploads")  # Директория для хранения файлов
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_USER_STORAGE_MB = 100
ALLOWED_EXTENSIONS = {".docx", ".doc", ".pdf"}
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

def convert_to_pdf_and_count_pages(input_file: str, output_dir: str) -> tuple[str, int | None]:
    """Конвертирует файл в PDF с помощью LibreOffice и подсчитывает количество страниц."""
    try:
        input_path = Path(input_file)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Если файл уже PDF, возвращаем его путь и подсчитываем страницы
        if input_path.suffix.lower() == ".pdf":
            pdf_file = input_file
        else:
            subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    input_file,
                    "--outdir",
                    str(output_path)
                ],
                check=True
            )
            pdf_file = str(output_path / f"{input_path.stem}.pdf")

        # Подсчёт страниц с помощью pdfinfo
        page_info = subprocess.check_output(["pdfinfo", pdf_file]).decode()
        pages = int([line.split(":")[1].strip() for line in page_info.splitlines() if "Pages" in line][0])

        return pdf_file if input_path.suffix.lower() != ".pdf" else None, pages
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to convert {input_file} to PDF: {e}")
    except Exception as e:
        raise RuntimeError(f"Error counting pages: {e}")

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    token: str = Depends(decode_access_token),
    db: AsyncSession = Depends(get_db)
):
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_query = await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_email})
    user_id = user_query.scalar_one_or_none()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    query = text("SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = :user_id")
    user_files = await db.execute(query, {"user_id": user_id})
    total_size = user_files.scalar_one_or_none() or 0

    file_size = os.path.getsize(tmp_path)

    if (total_size + file_size) > MAX_USER_STORAGE_MB * 1024 * 1024:
        os.remove(tmp_path)
        raise HTTPException(status_code=400, detail="Storage limit exceeded")

    user_upload_dir = UPLOAD_DIR / sanitize_filename(user_email)
    user_upload_dir.mkdir(exist_ok=True)

    timestamp = datetime.utcnow().isoformat().replace(":", "-")
    safe_filename = sanitize_filename(file.filename)
    filename = f"{timestamp}_{safe_filename}"
    filepath = user_upload_dir / filename

    os.rename(tmp_path, filepath)

    # Конвертируем в PDF и подсчитываем страницы
    try:
        temp_pdf_path, pages_count = convert_to_pdf_and_count_pages(str(filepath), str(user_upload_dir))
    except Exception as e:
        os.remove(filepath)
        raise HTTPException(status_code=500, detail=str(e))

    new_file = File(
        user_id=user_id,
        original_filename=file.filename,
        filename=safe_filename,
        filepath=str(filepath),
        temp_pdf_path=temp_pdf_path,
        size=file_size,
        uploaded_at=datetime.utcnow(),
        pages_count=pages_count
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
    user_email = token.get("sub")
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query_files = text("SELECT * FROM files WHERE user_id = :user_id")
    result_files = await db.execute(query_files, {"user_id": user_id})
    files = [
        {
            **dict(row),
            "size": format_size(row["size"])
        }
        for row in result_files.mappings()
    ]

    query_storage = text(
        "SELECT COALESCE(SUM(size), 0) FROM files WHERE user_id = :user_id")
    result_storage = await db.execute(query_storage, {"user_id": user_id})
    used_storage = result_storage.scalar_one_or_none() or 0
    remaining_storage_mb = round(
        (MAX_USER_STORAGE_MB * 1024 * 1024 - used_storage) / (1024 * 1024), 2)

    return {
        "files": files,
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

    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    query = text(
        "SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_id})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found or does not belong to the user"
        )

    filepath = Path(file.filepath)
    if filepath.exists():
        filepath.unlink()
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found on the disk"
        )

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

    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    query = text("SELECT * FROM files WHERE id = :file_id AND user_id = :user_id")
    result = await db.execute(query, {"file_id": file_id, "user_id": user_id})
    file = result.fetchone()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} not found or does not belong to the user"
        )

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

    query_user_id = text("SELECT id FROM users WHERE email = :email")
    result_user_id = await db.execute(query_user_id, {"email": user_email})
    user_id = result_user_id.scalar_one_or_none()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

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
