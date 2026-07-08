from sqlalchemy.sql import func
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


# Класс User описывает таблицу "users".
# Наследуемся от Base — так SQLAlchemy узнаёт, что это таблица.
class User(Base):
    __tablename__ = "users"  # имя таблицы в базе

    # id — первичный ключ, автоинкремент (1, 2, 3...).
    id = Column(Integer, primary_key=True, index=True)

    # email — строка, уникальная (двух одинаковых быть не может),
    # обязательная (nullable=False = не может быть пустой).
    email = Column(String, unique=True, nullable=False, index=True)

    # hashed_password — пароль храним НЕ в открытом виде, а как хеш.
    # (хеширование настроим на следующем этапе, пока просто поле)
    hashed_password = Column(String, nullable=False)

    # Уровень владения языком (CEFR): A1, A2, B1, B2, C1.
    # По нему генератор подбирает фразы нужной сложности.
    level = Column(String, nullable=False, default="A1", server_default="A1")

    # Тариф: False — бесплатный (лимит слов в день), True — Premium (безлимит).
    is_premium = Column(Boolean, nullable=False, default=False, server_default="false")

    # До какого момента действует Premium. Заложено под будущее авто-отключение
    # по таймеру (сейчас тариф снимается вручную). NULL — Premium не куплен.
    premium_until = Column(DateTime(timezone=True), nullable=True)

    # created_at — дата регистрации. server_default=func.now() значит:
    # при создании записи база сама подставит текущее время.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Обратная связь: позволяет писать user.words и получить список его слов.
    # back_populates связывает обе стороны: User.words <-> Word.owner.
    words = relationship("Word", back_populates="owner")

class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, index=True)

    # Само слово на английском и его перевод.
    text = Column(String, nullable=False)
    translation = Column(String, nullable=False)

    # Короткая фраза с этим словом — её генерирует бэкенд, чтобы слово
    # запоминалось в контексте, а не изолированно.
    phrase = Column(String, nullable=True)

    # Русский перевод фразы целиком (для показа в тренировке после ответа).
    # Заполняется при генерации фразы; для старых слов дозаполняется лениво.
    phrase_ru = Column(String, nullable=True)

    is_learned = Column(Boolean, default=False, nullable=False, server_default="false")

    # Сколько раз пользователь повторил слово (общий счётчик, для статистики).
    review_count = Column(Integer, default=0)

    # SRS (интервальные повторы, система Лейтнера):
    # srs_level — «коробка» 0..5, due_at — когда слово снова пора повторить.
    srs_level = Column(Integer, nullable=False, default=0, server_default="0")
    due_at = Column(DateTime, nullable=True)

    # Сколько раз для слова уже перегенерировали фразу («другая фраза»).
    # На бесплатном тарифе доступно FREE_REGEN_LIMIT генераций на слово,
    # дальше — только Premium. Счётчик не сбрасывается.
    regen_count = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ВНЕШНИЙ КЛЮЧ: ссылка на id пользователя из таблицы users.
    # Это поле "Владелец" в терминах 1С.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # СВЯЗЬ на уровне ORM: позволяет писать word.owner и получать объект User.
    # Это НЕ колонка в базе — это удобство Python-кода.
    owner = relationship("User", back_populates="words")