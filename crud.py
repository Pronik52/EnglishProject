from sqlalchemy.orm import Session
from passlib.context import CryptContext
from auth import verify_password

import models
import schemas

# Настраиваем "контекст" хеширования: используем алгоритм bcrypt.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Превращает обычный пароль в хеш (для сохранения в базу).
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# Ищет пользователя в базе по email. Вернёт объект User или None.
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


# Создаёт нового пользователя в базе.
def create_user(db: Session, user: schemas.UserCreate):
    # 1. Хешируем пароль из входящих данных.
    hashed = hash_password(user.password)

    # 2. Создаём объект модели User (это ещё НЕ запись в базе, просто объект в памяти).
    db_user = models.User(
        email=user.email,
        hashed_password=hashed
    )

    # 3. Добавляем объект в сессию (готовим к записи).
    db.add(db_user)

    # 4. Фиксируем изменения в базе (вот теперь реально пишется INSERT).
    db.commit()

    # 5. Обновляем объект из базы — чтобы получить сгенерированные id и created_at.
    db.refresh(db_user)

    return db_user

# Проверяет логин: находит юзера по email и сверяет пароль.
# Возвращает объект User если всё ок, иначе None.
def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return None  # нет такого пользователя
    if not verify_password(password, user.hashed_password):
        return None  # пароль неверный
    return user