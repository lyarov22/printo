from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    surname: str
    phone: str

class UserRead(BaseModel):
    id: int
    email: EmailStr
    name: str
    surname: str

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str
