from typing import List, Optional
from pydantic import BaseModel, EmailStr, validator, constr
from datetime import datetime


# Схема ВХОДЯЩИХ данных при регистрации.
# Клиент должен прислать email и password — больше ничего.
class UserCreate(BaseModel):
    email: EmailStr      # EmailStr автоматически проверит, что это валидный email
    # Минимальную длину намеренно НЕ задаём через constr: ограничения типа
    # срабатывают раньше валидатора, и пользователь получал бы английское
    # «String should have at least 8 characters» вместо русского текста ниже.
    # Длину проверяет сам валидатор — сообщения остаются на русском.
    password: constr(max_length=50)        # обычный пароль (в открытом виде, придёт по сети)

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
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")

# Уровни, для которых каталог наполнен и показывается в интерфейсе. Сейчас
# совпадает с LEVELS, но остаётся отдельной константой: наполненность каталога
# и допустимый уровень профиля — разные вещи, и расходятся при добавлении
# нового уровня раньше слов для него.
CATALOG_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


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
    # min_length здесь тоже не ставим — по той же причине, что и у пароля:
    # иначе на пустую строку придёт английское сообщение Pydantic, а не наше.
    text: constr(max_length=100)
    translation: constr(max_length=100)
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
    # Картинка-сцена к фразе и состояние её генерации: none / pending / ready /
    # failed. Само описание сцены (scene_prompt) клиенту НЕ отдаём: это эталон
    # для режима «опиши картинку», и увидев его, пользователь просто спишет.
    image_url: Optional[str] = None
    image_status: str = "none"
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


# Описание картинки, которое пользователь написал своими словами.
class DescribeRequest(BaseModel):
    text: constr(max_length=1000)

    @validator('text')
    def validate_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Опишите, что происходит на картинке')
        return v.strip()


# Разбор описания: оценка, тёплый комментарий и подсказки по грамматике.
# grammar_ru показываем отдельно от оценки — по решению «оценка мягкая»
# грамматика не влияет на повторы, а служит подсказкой на будущее.
class DescribeVerdict(BaseModel):
    grade: int
    used_word: bool
    correct: bool
    feedback_ru: str
    grammar_ru: List[str] = []
    better_en: str = ""
    offline: bool = False


# Полный ответ эндпоинта: разбор + слово с обновлённым прогрессом,
# чтобы фронту не приходилось запрашивать слово отдельно.
class DescribeResponse(BaseModel):
    verdict: DescribeVerdict
    word: WordResponse
    describes_left: int  # -1 у Premium: лимита нет


# --- Каталог готовых слов ---

# Максимальный размер батча массового добавления. Ограничение защищает и от
# случайного «выбрать всё» на огромном каталоге, и от намеренной перегрузки.
MAX_BULK_ADD = 50


# Категория каталога в списке фильтров.
class CategoryResponse(BaseModel):
    id: int
    slug: str
    title: str
    words_count: int = 0   # сколько активных слов в категории на выбранном уровне

    class Config:
        from_attributes = True


# Уровень CEFR в справочнике уровней.
class LevelResponse(BaseModel):
    code: str        # A1
    title: str       # A1 · начинающий


# Каталожное слово в выдаче. in_dictionary говорит, что слово уже есть
# в личном словаре пользователя, — кнопка добавления для него неактивна.
class CatalogWordResponse(BaseModel):
    id: int
    text: str
    translation: str
    part_of_speech: Optional[str] = None
    level: str
    transcription: Optional[str] = None
    example_en: Optional[str] = None
    example_ru: Optional[str] = None
    categories: List[str] = []      # slug'и категорий
    in_dictionary: bool = False

    class Config:
        from_attributes = True


class PaginatedCatalogResponse(BaseModel):
    items: List[CatalogWordResponse]
    total: int
    page: int
    size: int
    pages: int


# Массовое добавление: список идентификаторов каталожных слов.
class CatalogAddRequest(BaseModel):
    word_ids: List[int]

    @validator('word_ids')
    def validate_ids(cls, v):
        if not v:
            raise ValueError('Выберите хотя бы одно слово')
        if len(v) > MAX_BULK_ADD:
            raise ValueError(f'За один раз можно добавить не больше {MAX_BULK_ADD} слов')
        return list(dict.fromkeys(v))   # убираем повторы, порядок сохраняем


# Результат массового добавления. Разделяем причины пропуска: дубль — это
# нормальный исход, а упёршийся лимит требует показать предложение Premium.
class CatalogAddResult(BaseModel):
    added_count: int
    skipped_count: int       # уже были в словаре
    limit_skipped_count: int  # не поместились в дневной лимит бесплатного тарифа
    failed_count: int         # не найдены в каталоге или выключены
    added_ids: List[int] = []
    skipped_ids: List[int] = []
    limit_skipped_ids: List[int] = []
    failed_ids: List[int] = []
    errors: List[str] = []
    daily_remaining: int = -1  # сколько слов ещё можно добавить сегодня (-1 — без лимита)


# Запрос предпросмотра фраз для слова (ещё не сохранённого).
class PhrasePreviewRequest(BaseModel):
    text: constr(min_length=1, max_length=100)
    translation: Optional[str] = None


# Ответ с вариантами фраз.
class PhrasePreviewResponse(BaseModel):
    text: str
    phrases: List[str]