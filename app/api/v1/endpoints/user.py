# File: app/api/v1/endpoints/user.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.user import UserCreate, UserRead
from app.db.repositories.user import create_user, get_user_by_email
from app.db.session import get_db

router = APIRouter()

@router.post("/register", response_model=UserRead)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    existing_user = await get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return await create_user(db, user)