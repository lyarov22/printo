from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base

class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_filename = Column(String, nullable=False)  # Оригинальное имя файла
    filename = Column(String, nullable=False)  # Уникальное имя файла на диске
    pages_count = Column(Integer, default=0)  # Количество страниц
    filepath = Column(String, nullable=False)
    temp_pdf_path = Column(String, nullable=True)
    size = Column(Integer, nullable=False)
    uploaded_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="files")
