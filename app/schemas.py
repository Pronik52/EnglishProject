from typing import List, Optional
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
# Допустимые уровни CEFR.
LEVELS = ("A1", "A2", "B1", "B2", "C1")


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    level: str
    is_premium: bool
    created_at: datetime

    # Этот блок разрешает Pydantic читать данные напрямую из объекта SQLAlchemy
    # (из модели User), а не только из словаря.
    class Config:
        from_attributes = True


# Статус тарифа и дневного лимита.
class BillingStatus(BaseModel):
    is_premium: bool
    premium_until: Optional[datetime] = None  # до какого момента действует Premium
    daily_limit: int      # лимит слов в день на бесплатном тарифе
    used_today: int       # сколько слов добавлено сегодня
    remaining: int        # сколько ещё можно сегодня (для Premium — не ограничено)
    regen_limit: int      # бесплатных генераций фразы на слово


# Покупка Premium. Платёжные данные фиктивные — оплату не проводим,
# карту не валидируем и НЕ храним, поле нужно только чтобы имитировать форму.
class PurchaseRequest(BaseModel):
    plan: int  # срок в месяцах: 1, 3 или 12
    card_number: Optional[str] = None
    card_exp: Optional[str] = None
    card_cvc: Optional[str] = None
    card_holder: Optional[str] = None

    @validator('plan')
    def plan_must_be_valid(cls, v):
        if v not in (1, 3, 12):
            raise ValueError('Допустимые планы: 1, 3 или 12 месяцев')
        return v


# Смена уровня пользователя.
class LevelUpdate(BaseModel):
    level: str

    @validator('level')
    def validate_level(cls, v):
        v = v.strip().upper()
        if v not in LEVELS:
            raise ValueError(f"Уровень должен быть одним из: {', '.join(LEVELS)}")
        return v

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
class WordResponse(BaseModel):
    id: int
    text: str
    translation: str
    phrase: Optional[str] = None
    phrase_ru: Optional[str] = None
    review_count: int
    regen_count: int = 0
    srs_level: int = 0
    due_at: Optional[datetime] = None
    is_learned: bool
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class PaginatedWordResponse(BaseModel):
    items: List[WordResponse]
    total: int
    page: int
    size: int
    pages: int

# Тело запроса для ручной установки is_learned.
# Только одно поле — больше ничего менять не разрешаем.
class WordLearnedUpdate(BaseModel):
    is_learned: bool


# Ответ в викторине: правильно ли пользователь выбрал слово.
class AnswerRequest(BaseModel):
    correct: bool


# Запрос предпросмотра фраз для слова (ещё не сохранённого).
class PhrasePreviewRequest(BaseModel):
    text: constr(min_length=1, max_length=100)
    translation: Optional[str] = None


# Ответ с вариантами фраз.
class PhrasePreviewResponse(BaseModel):
    text: str
    phrases: List[str]