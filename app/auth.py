import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import SessionLocal, get_db
from . import models

load_dotenv()

# Читаем настройки токена из .env
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

# Имена cookie живут рядом с проверкой токена, чтобы роутер, middleware и
# dependency использовали один и тот же источник истины.
ACCESS_COOKIE_NAME = "access_token"
CSRF_COOKIE_NAME = "csrf_token"

# Тот же контекст хеширования, что и в crud.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Проверяет: совпадает ли введённый пароль с хешем из базы.
# bcrypt сам умеет сравнивать пароль с хешем (НЕ "расхешировать", а проверить).
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# Создаёт JWT-токен.
# data — что положить внутрь (мы положим email).
def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    # Считаем момент, когда токен "протухнет".
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # "exp" — стандартное поле JWT для срока годности.
    to_encode.update({"exp": expire})

    # Кодируем и подписываем токен секретным ключом.
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Проверяет токен и достаёт из него email. Если токен битый/просрочен — вернёт None.
def decode_access_token_payload(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def decode_access_token(token: str) -> Optional[str]:
    payload = decode_access_token_payload(token)
    if payload is None:
        return None
    return payload.get("sub")  # "sub" (subject) — кого касается токен


# Swagger и внешние API-клиенты получают Bearer JWT через /token. Для браузерной
# SPA основной транспорт — HttpOnly cookie; auto_error=False позволяет проверить
# cookie, если заголовка Authorization нет.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,
)


def credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_access_token(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
) -> str:
    """Берёт JWT из Bearer header (API) или HttpOnly cookie (браузер)."""
    token = bearer_token or request.cookies.get(ACCESS_COOKIE_NAME)
    if token is None:
        raise credentials_exception()
    return token

# ГЛАВНАЯ функция этапа.
# JWT уже извлечён get_access_token из Bearer header или cookie.
def get_current_user(token: str = Depends(get_access_token), db: Session = Depends(get_db)):
    # Заготовка ошибки 401 — будем её бросать при любой проблеме с токеном.
    invalid_credentials = credentials_exception()

    # 1. Проверяем токен и достаём email (функция из этапа 4).
    email = decode_access_token(token)
    if email is None:
        raise invalid_credentials  # токен битый или просрочен

    # 2. Ищем пользователя в базе по email из токена.
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise invalid_credentials  # юзера удалили, а токен ещё на руках

    # 3. Всё ок — возвращаем объект пользователя.
    return user
