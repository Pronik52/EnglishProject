from typing import List
from pydantic import BaseModel, EmailStr, validator, constr
from datetime import datetime


# Схема ВХОДЯЩИХ данных при регистрации.
# Клиент должен прислать email и password — больше ничего.
class UserCreate(BaseModel):
    email: EmailStr      # EmailStr автоматически проверит, что это валидный email
    password: constr(min_length=8, max_length=50)        # обычный пароль (в открытом виде, придёт по сети)

    @validator('password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Пароль должен содержать минимум 8 символов')
        if not any(c.isupper() for c in v):
            raise ValueError('Пароль должен содержать хотя бы одну заглавную букву')
        if not any(c.isdigit() for c in v):
            raise ValueError('Пароль должен содержать хотя бы одну цифру')
        return v


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
    text: constr(min_length=1, max_length=100)
    translation: constr(min_length=1, max_length=100)
    is_learned: bool = False

    @validator('text', 'translation')
    def validate_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Поле не может быть пустым')
        return v.strip()

# Исходящие данные: что вернём клиенту.
class PaginatedWordResponse(BaseModel):
    items: List[WordResponse]
    total: int
    page: int
    size: int
    pages: int

class WordResponse(BaseModel):
    id: int
    text: str
    translation: str
    review_count: int
    is_learned: bool
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Тело запроса для ручной установки is_learned.
# Только одно поле — больше ничего менять не разрешаем.
class WordLearnedUpdate(BaseModel):
    is_learned: bool