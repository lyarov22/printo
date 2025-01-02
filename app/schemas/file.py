from pydantic import BaseModel

class FileUploadResponse(BaseModel):
    id: int
    filename: str
    size: int

class FileRead(BaseModel):
    id: int
    original_filename: str
    filename: str
    filepath: str
    size: int
    uploaded_at: str

    class Config:
        orm_mode = True
