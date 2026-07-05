from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import verify_password, pwd_context

# Ищет пользователя в базе по email. Вернёт объект User или None.
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


# Создаёт нового пользователя в базе.
def create_user(db: Session, user: schemas.UserCreate):
    # 1. Хешируем пароль из входящих данных.
    hashed = pwd_context.hash(user.password)

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

# Меняет уровень пользователя (A1..C1) и сохраняет в базу.
def update_level(db: Session, user: models.User, level: str):
    user.level = level
    db.commit()
    db.refresh(user)
    return user


# Переключает тариф пользователя (Premium вкл/выкл) и сохраняет в базу.
def set_premium(db: Session, user: models.User, is_premium: bool):
    user.is_premium = is_premium
    db.commit()
    db.refresh(user)
    return user


# Проверяет логин: находит юзера по email и сверяет пароль.
# Возвращает объект User если всё ок, иначе None.
def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return None  # нет такого пользователя
    if not verify_password(password, user.hashed_password):
        return None  # пароль неверный
    return user