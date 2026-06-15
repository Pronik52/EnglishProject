from pydantic import BaseModel, EmailStr
from datetime import datetime


# Схема ВХОДЯЩИХ данных при регистрации.
# Клиент должен прислать email и password — больше ничего.
class UserCreate(BaseModel):
    email: EmailStr      # EmailStr автоматически проверит, что это валидный email
    password: str        # обычный пароль (в открытом виде, придёт по сети)


# Схема ИСХОДЯЩИХ данных — что мы вернём клиенту после регистрации.
# ВАЖНО: пароль/хеш сюда НЕ включаем — клиенту его знать не нужно.
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    # Этот блок разрешает Pydantic читать данные напрямую из объекта SQLAlchemy
    # (из модели User), а не только из словаря.
    class Config:
        from_attributes = True

# Входящие данные при создании слова: текст и перевод.
# owner_id СЮДА НЕ кладём — владельца определим из токена, а не из тела запроса!
class WordCreate(BaseModel):
    text: str
    translation: str


# Исходящие данные: что вернём клиенту.
class WordResponse(BaseModel):
    id: int
    text: str
    translation: str
    review_count: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True