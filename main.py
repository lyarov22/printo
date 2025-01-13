from fastapi import FastAPI, File, UploadFile
import os
import tempfile
from PyPDF2 import PdfReader
from docx2pdf import convert

app = FastAPI()

@app.post("/print")
async def print_file(file: UploadFile = File(...)):
    # Сохраняем загружаемый файл во временной папке
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    pages_count = 0

    if ext == ".pdf":
        # Определяем кол-во страниц в PDF
        reader = PdfReader(tmp_path)
        pages_count = len(reader.pages)

    elif ext == ".docx":
        # Сначала конвертируем DOCX -> PDF
        pdf_path = tmp_path + ".pdf"
        convert(tmp_path, pdf_path)
        reader = PdfReader(pdf_path)
        pages_count = len(reader.pages)
        os.remove(pdf_path)  # Удаляем временный PDF

    else:
        os.remove(tmp_path)
        return {"error": "Неподдерживаемый формат файла"}

    # Эмулируем отправку на печать
    # Здесь можно добавить логику отправки реальному принтеру,
    # но пока просто выводим информацию:
    print(f"Файл: {file.filename}. Количество страниц: {pages_count}")
    print("Эмулируем печать...")

    # Удаляем временный файл
    os.remove(tmp_path)

    return {"file": file.filename, "pages": pages_count, "status": "Файл отправлен на печать (эмуляция)"}
