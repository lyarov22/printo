from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, verify_password, get_password_hash
from app.db.repositories.login_code import get_valid_login_code, mark_code_as_used
from app.db.repositories.user import get_user_by_email, create_user, get_user_by_phone
from app.schemas.user import TelegramLoginSchema, UserAuth, UserCreate, UserRead, Token
from app.db.session import get_db

router = APIRouter()

@router.post("/register", response_model=UserRead)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    existing_user = await get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = await create_user(db, {
        "email": user.email,
        "hashed_password": hashed_password,
        "name": user.name,
        "surname": user.surname,
        "phone": user.phone
    })
    return new_user

@router.post("/login", response_model=Token)
async def login(user: UserAuth, db: AsyncSession = Depends(get_db)):
    """
    Аутентификация пользователя по email и паролю.
    - **email**: Электронная почта
    - **password**: Пароль
    - **Возвращает**: JWT-токен, если учетные данные верны
    """
    existing_user = await get_user_by_email(db, user.email)

    if not existing_user or not verify_password(user.password, existing_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token({"sub": existing_user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login/telegram")
async def telegram_login(data: TelegramLoginSchema, db: AsyncSession = Depends(get_db)):
    """
    Пользователь вводит телефон и код, полученный в Telegram.
    Эндпоинт проверяет код, создаёт/возвращает пользователя, выдаёт JWT.
    """
    # Проверяем, что код есть в БД, не истёк и не использован
    login_code = await get_valid_login_code(db, data.phone, data.code)
    if not login_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или просроченный код"
        )

    # Отмечаем код как использованный, чтобы нельзя было юзать повторно
    await mark_code_as_used(db, login_code)

    # Проверяем, есть ли пользователь в БД
    # (лучше в репозитории user завести отдельную функцию get_user_by_phone)
    user = await get_user_by_phone(db, data.phone)

    if not user:
        # Если такого телефона нет, создаём нового пользователя.
        # Но перед этим хорошо бы проверить, нет ли конфликтующих полей.
        # Например, если phone уникальный, то всё ок.
        user = await create_user(db, {
            "email": f"{data.phone}@example.com",  # если e-mail не обязателен
            "hashed_password": "",                 # раз логинимся по телефону
            "name": "",
            "surname": "",
            "phone": data.phone
        })

    # Генерируем токен
    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}