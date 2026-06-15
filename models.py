from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base


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