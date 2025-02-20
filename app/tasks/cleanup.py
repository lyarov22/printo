from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from sqlalchemy.future import select
from app.db.models.file import File
from app.db.session import get_db
import logging

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("cleanup.log", encoding="utf-8"),
        # logging.StreamHandler(),            # Лог в консоль
    ],
)
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("./uploads")

async def cleanup_old_files(db: AsyncSession):
    one_month_ago = datetime.utcnow() - timedelta(days=30)
    logger.info("Начало очистки старых файлов. Проверяем файлы старше %s", one_month_ago)

    result = await db.execute(
        select(File).where(File.uploaded_at < one_month_ago)
    )
    old_files = result.scalars().all()

    if not old_files:
        logger.info("Нет файлов для удаления.")
        return

    for file in old_files:
        file_path = Path(file.filepath)
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info("Файл %s успешно удален.", file_path)
            else:
                logger.warning("Файл %s не найден.", file_path)

            await db.delete(file)
            logger.info("Запись о файле %s удалена из базы данных.", file.filename)

        except Exception as e:
            logger.error("Ошибка при удалении файла %s: %s", file_path, str(e))

    await db.commit()
    logger.info("Очистка завершена. Удалено файлов: %d", len(old_files))