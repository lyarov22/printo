import random
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.storage.memory import MemoryStorage
from app.core.config import settings

# TODO: Поменять на ваш адрес FastAPI
api_url = "http://127.0.0.1:8000" + settings.API_V1_STR

# Инициализация бота и диспетчера с использованием MemoryStorage
bot = Bot(token=settings.TELEGRAM_API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хэндлер для команды /start
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Привет! Нажми кнопку ниже, чтобы поделиться номером телефона.", reply_markup=keyboard)

# Хэндлер для получения контакта пользователя
@dp.message(F.contact)
async def get_contact(message: types.Message):
    phone_number = message.contact.phone_number

    # Генерация 4-значного кода
    code = str(random.randint(1000, 9999))

    # Отправка кода в ваше FastAPI приложение для сохранения
    async with aiohttp.ClientSession() as session:
        url = f"{api_url}/codes/generate"
        payload = {"phone": phone_number, "code": code}
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                await message.answer(f"Ваш код: {code}\nВведите его в приложении для входа.")
            else:
                await message.answer("Не удалось сгенерировать код, попробуйте позже.")

async def main():
    # Запуск поллинга
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
