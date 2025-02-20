from sqlalchemy import Column, String, Boolean
from app.db.session import Base

class Device(Base):
    __tablename__ = "devices"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False, unique=True)
    secret_key = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
