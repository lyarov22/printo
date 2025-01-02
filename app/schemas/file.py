from pydantic import BaseModel
from datetime import datetime

class FileRead(BaseModel):
    id: int
    filename: str
    size: int
    uploaded_at: datetime

    class Config:
        from_attributes = True

class FileUploadResponse(BaseModel):
    id: int
    filename: str
    size: int
