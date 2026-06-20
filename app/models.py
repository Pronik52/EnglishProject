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
    is_learned = Column(Boolean, default=False, nullable=False, server_default="false")

    # Сколько раз пользователь повторил слово (для будущей логики обучения).
    review_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ВНЕШНИЙ КЛЮЧ: ссылка на id пользователя из таблицы users.
    # Это поле "Владелец" в терминах 1С.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # СВЯЗЬ на уровне ORM: позволяет писать word.owner и получать объект User.
    # Это НЕ колонка в базе — это удобство Python-кода.
    owner = relationship("User", back_populates="words")