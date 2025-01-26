from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str
    API_V1_STR: str
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    PRICE_PER_PAGE: int
    PRINTER_NAME: str

    class Config:
        from_attributes = True
        env_file = ".env"

settings = Settings()
