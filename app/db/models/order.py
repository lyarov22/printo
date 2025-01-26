from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.db.session import Base
from datetime import datetime

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)  # Время создания
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Время обновления
    status = Column(String, default="pending")  # Статусы: pending, completed, failed
    total_price = Column(Integer, nullable=False)
    duplex = Column(Boolean, default=False)  # Двухсторонняя печать

    # Связь с файлами
    order_files = relationship("OrderFile", back_populates="order")


class OrderFile(Base):
    __tablename__ = "order_files"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    copies = Column(Integer, default=1)  # Количество копий

    # Связь с заказами
    order = relationship("Order", back_populates="order_files")
