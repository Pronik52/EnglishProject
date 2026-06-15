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